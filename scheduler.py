"""
CollectionScheduler for managing periodic content collection jobs.

Uses APScheduler with asyncio support for distributed job scheduling.
Features priority-based scheduling, health checks, and SQLite persistence.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Callable, Set
from dataclasses import dataclass, field
import heapq

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, JobExecutionEvent
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from models import (
    RawDocument, ProcessedDocument, DocumentStatus,
    HealthStatus, SourceType, DeadLetterItem
)
from interfaces import Source, SourcePriority, SourceConfig
from collector import CollectorEngine, CircuitBreaker

logger = logging.getLogger(__name__)


@dataclass(order=True)
class PrioritizedSource:
    """Source wrapper for priority queue."""
    priority: int
    next_check: datetime = field(compare=True)
    source: Source = field(compare=False)
    fail_count: int = 0
    
    def __post_init__(self):
        # Ensure priority is int for comparison
        if isinstance(self.priority, SourcePriority):
            self.priority = self.priority.value


class CollectionScheduler:
    """
    Scheduler for managing content collection jobs.
    
    Features:
    - Priority-based scheduling (critical sources checked more frequently)
    - APScheduler with SQLite job persistence
    - Asyncio-based job execution
    - Health monitoring and circuit breakers
    - Rate limiting per domain
    """
    
    DEFAULT_CHECK_INTERVALS = {
        SourcePriority.CRITICAL: 5,    # 5 minutes
        SourcePriority.HIGH: 15,       # 15 minutes
        SourcePriority.MEDIUM: 60,     # 1 hour
        SourcePriority.LOW: 360,       # 6 hours
    }
    
    def __init__(
        self,
        db_path: str = "sqlite:///situation_monitor.db",
        max_concurrent_jobs: int = 10,
        max_queue_size: int = 1000,
    ):
        self.db_path = db_path
        self.max_concurrent_jobs = max_concurrent_jobs
        self.max_queue_size = max_queue_size
        
        # APScheduler setup
        jobstores = {
            'default': SQLAlchemyJobStore(url=db_path)
        }
        
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone='UTC',
        )
        
        # Collector engine
        self.collector = CollectorEngine()
        
        # Source management
        self._sources: Dict[str, Source] = {}
        self._source_configs: Dict[str, SourceConfig] = {}
        self._source_locks: Dict[str, asyncio.Lock] = {}
        
        # Priority queue for dynamic scheduling
        self._priority_queue: List[PrioritizedSource] = []
        
        # Processing queue for downstream analyzers
        self._document_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        
        # Callbacks
        self._document_callbacks: List[Callable[[ProcessedDocument], None]] = []
        self._error_callbacks: List[Callable[[str, Exception], None]] = []
        
        # Health tracking
        self._job_execution_times: Dict[str, List[datetime]] = {}
        self._recent_errors: List[str] = []
        self._max_recent_errors = 100
        
        # Running state
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.stats = {
            'jobs_scheduled': 0,
            'jobs_executed': 0,
            'jobs_failed': 0,
            'documents_collected': 0,
            'documents_queued': 0,
        }
        
        # Add event listeners
        self.scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )
    
    def add_source(self, source: Source) -> bool:
        """
        Add a source to the scheduler.
        
        Args:
            source: Source instance to add
            
        Returns:
            True if added successfully
        """
        source_id = source.source_id
        
        if source_id in self._sources:
            logger.warning(f"Source {source_id} already exists, updating")
        
        self._sources[source_id] = source
        self._source_configs[source_id] = source.config
        self._source_locks[source_id] = asyncio.Lock()
        
        # Add to priority queue
        check_interval = self._get_check_interval(source)
        next_check = datetime.utcnow() + timedelta(minutes=check_interval)
        
        prioritized = PrioritizedSource(
            priority=source.priority.value,
            next_check=next_check,
            source=source,
        )
        heapq.heappush(self._priority_queue, prioritized)
        
        # Schedule immediate first check
        self._schedule_source_check(source)
        
        logger.info(f"Added source {source_id} with priority {source.priority.name}")
        return True
    
    def remove_source(self, source_id: str) -> bool:
        """Remove a source from the scheduler."""
        if source_id not in self._sources:
            return False
        
        # Remove scheduled job
        job_id = f"check_{source_id}"
        try:
            self.scheduler.remove_job(job_id)
        except:
            pass
        
        # Remove from sources
        del self._sources[source_id]
        del self._source_configs[source_id]
        del self._source_locks[source_id]
        
        # Remove from priority queue
        self._priority_queue = [
            ps for ps in self._priority_queue
            if ps.source.source_id != source_id
        ]
        heapq.heapify(self._priority_queue)
        
        logger.info(f"Removed source {source_id}")
        return True
    
    def _get_check_interval(self, source: Source) -> int:
        """Get check interval for a source based on priority."""
        # Use source's custom interval if specified
        if hasattr(source.config, 'check_interval_minutes') and source.config.check_interval_minutes:
            return source.config.check_interval_minutes
        
        # Use priority-based default
        return self.DEFAULT_CHECK_INTERVALS.get(
            source.priority,
            self.DEFAULT_CHECK_INTERVALS[SourcePriority.MEDIUM]
        )
    
    def _schedule_source_check(self, source: Source):
        """Schedule a check job for a source."""
        source_id = source.source_id
        job_id = f"check_{source_id}"
        
        # Remove existing job if present
        try:
            self.scheduler.remove_job(job_id)
        except:
            pass
        
        # Calculate interval
        interval_minutes = self._get_check_interval(source)
        
        # Add job
        self.scheduler.add_job(
            func=self._execute_source_check,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            args=[source_id],
            replace_existing=True,
            max_instances=1,
            misfire_grace_time=300,  # 5 minutes grace
        )
        
        self.stats['jobs_scheduled'] += 1
        logger.debug(f"Scheduled {job_id} every {interval_minutes} minutes")
    
    async def _execute_source_check(self, source_id: str):
        """Execute a check for a source."""
        if source_id not in self._sources:
            logger.warning(f"Source {source_id} not found")
            return
        
        source = self._sources[source_id]
        
        # Use lock to prevent concurrent checks
        async with self._source_locks[source_id]:
            try:
                logger.debug(f"Checking source: {source_id}")
                
                # Check circuit breaker
                circuit_breaker = self.collector._get_circuit_breaker(source_id)
                if not circuit_breaker.can_execute():
                    logger.warning(f"Circuit breaker open for {source_id}, skipping")
                    return
                
                # Fetch from source
                documents = await self.collector.fetch_from_source(source)
                
                if documents:
                    logger.info(f"Collected {len(documents)} documents from {source_id}")
                    
                    # Process and queue documents
                    for raw_doc in documents:
                        await self._process_and_queue(raw_doc, source)
                    
                    self.stats['documents_collected'] += len(documents)
                
                # Record execution time for health tracking
                self._record_execution(source_id)
                
            except Exception as e:
                logger.error(f"Error checking source {source_id}: {e}")
                self._record_error(f"Source {source_id}: {str(e)}")
                
                # Trigger error callbacks
                for callback in self._error_callbacks:
                    try:
                        callback(source_id, e)
                    except:
                        pass
                
                raise
    
    async def _process_and_queue(self, raw_doc: RawDocument, source: Source):
        """Process raw document and add to queue."""
        try:
            # Extract content
            processed = self.collector.extract_content(
                raw_doc,
                custom_selectors=getattr(source.config, 'selectors', None)
            )
            
            # Add to processing queue
            if not self._document_queue.full():
                await self._document_queue.put(processed)
                self.stats['documents_queued'] += 1
                
                # Trigger callbacks
                for callback in self._document_callbacks:
                    try:
                        callback(processed)
                    except:
                        pass
            else:
                logger.warning("Document queue full, dropping document")
                
        except Exception as e:
            logger.error(f"Error processing document {raw_doc.id}: {e}")
    
    def _record_execution(self, source_id: str):
        """Record successful job execution."""
        now = datetime.utcnow()
        if source_id not in self._job_execution_times:
            self._job_execution_times[source_id] = []
        self._job_execution_times[source_id].append(now)
        
        # Keep only last 100 executions
        self._job_execution_times[source_id] = self._job_execution_times[source_id][-100:]
    
    def _record_error(self, error_msg: str):
        """Record error for health tracking."""
        timestamp = datetime.utcnow().isoformat()
        self._recent_errors.append(f"[{timestamp}] {error_msg}")
        
        # Keep only recent errors
        if len(self._recent_errors) > self._max_recent_errors:
            self._recent_errors = self._recent_errors[-self._max_recent_errors:]
    
    def _on_job_executed(self, event: JobExecutionEvent):
        """Handle job execution events."""
        if event.exception:
            self.stats['jobs_failed'] += 1
            self._record_error(f"Job {event.job_id}: {event.exception}")
        else:
            self.stats['jobs_executed'] += 1
    
    async def _dynamic_scheduler_loop(self):
        """Dynamic scheduler for priority-based checking."""
        while self._running:
            try:
                if not self._priority_queue:
                    await asyncio.sleep(1)
                    continue
                
                # Get next source to check
                now = datetime.utcnow()
                next_source = self._priority_queue[0]
                
                if next_source.next_check <= now:
                    # Pop and process
                    heapq.heappop(self._priority_queue)
                    
                    source = next_source.source
                    source_id = source.source_id
                    
                    # Execute check
                    try:
                        await self._execute_source_check(source_id)
                    except Exception as e:
                        next_source.fail_count += 1
                    
                    # Reschedule
                    check_interval = self._get_check_interval(source)
                    
                    # Exponential backoff on failures
                    if next_source.fail_count > 0:
                        backoff = min(2 ** next_source.fail_count, 360)  # Max 6 hours
                        check_interval += backoff
                    
                    next_source.next_check = now + timedelta(minutes=check_interval)
                    heapq.heappush(self._priority_queue, next_source)
                    
                    # Small delay between checks
                    await asyncio.sleep(0.1)
                else:
                    # Wait until next check
                    wait_seconds = (next_source.next_check - now).total_seconds()
                    wait_seconds = min(wait_seconds, 1.0)  # Check at least every second
                    await asyncio.sleep(wait_seconds)
                    
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(5)
    
    async def start(self):
        """Start the scheduler."""
        if self._running:
            return
        
        self._running = True
        
        # Start APScheduler
        self.scheduler.start()
        
        # Start dynamic scheduler
        self._scheduler_task = asyncio.create_task(self._dynamic_scheduler_loop())
        
        logger.info("Collection scheduler started")
    
    async def stop(self):
        """Stop the scheduler."""
        if not self._running:
            return
        
        self._running = False
        
        # Stop scheduler
        self.scheduler.shutdown(wait=False)
        
        # Cancel dynamic scheduler task
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Collection scheduler stopped")
    
    def trigger_immediate_check(self, source_id: str) -> bool:
        """
        Trigger an immediate check for a source.
        
        Args:
            source_id: Source to check
            
        Returns:
            True if triggered
        """
        if source_id not in self._sources:
            return False
        
        # Modify the source's next check time
        for ps in self._priority_queue:
            if ps.source.source_id == source_id:
                ps.next_check = datetime.utcnow()
                heapq.heapify(self._priority_queue)
                return True
        
        return False
    
    def add_document_callback(self, callback: Callable[[ProcessedDocument], None]):
        """Add callback for new documents."""
        self._document_callbacks.append(callback)
    
    def remove_document_callback(self, callback: Callable[[ProcessedDocument], None]):
        """Remove document callback."""
        if callback in self._document_callbacks:
            self._document_callbacks.remove(callback)
    
    def add_error_callback(self, callback: Callable[[str, Exception], None]):
        """Add callback for errors."""
        self._error_callbacks.append(callback)
    
    async def get_next_document(self, timeout: Optional[float] = None) -> Optional[ProcessedDocument]:
        """
        Get next document from processing queue.
        
        Args:
            timeout: Optional timeout in seconds
            
        Returns:
            ProcessedDocument or None if timeout
        """
        try:
            return await asyncio.wait_for(
                self._document_queue.get(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return None
    
    def get_health_status(self) -> HealthStatus:
        """Get current health status."""
        # Determine overall status
        recent_errors = len([e for e in self._recent_errors[-10:]])
        failed_jobs_ratio = 0
        
        total_jobs = self.stats['jobs_executed'] + self.stats['jobs_failed']
        if total_jobs > 0:
            failed_jobs_ratio = self.stats['jobs_failed'] / total_jobs
        
        if failed_jobs_ratio > 0.5 or recent_errors > 5:
            status = "unhealthy"
        elif failed_jobs_ratio > 0.2 or recent_errors > 2:
            status = "degraded"
        else:
            status = "healthy"
        
        return HealthStatus(
            status=status,
            last_check=datetime.utcnow(),
            active_jobs=len(self._sources),
            queue_size=self._document_queue.qsize(),
            dead_letter_size=len(self.collector.dead_letter_queue),
            circuit_breakers=self.collector.get_circuit_breaker_states(),
            recent_errors=self._recent_errors[-10:],
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        return {
            **self.stats,
            'sources': len(self._sources),
            'queue_size': self._document_queue.qsize(),
            'circuit_breakers': self.collector.get_circuit_breaker_states(),
        }
    
    def get_source_status(self, source_id: Optional[str] = None) -> Dict[str, Any]:
        """Get status of sources."""
        if source_id:
            if source_id not in self._sources:
                return {}
            source = self._sources[source_id]
            return {
                'source_id': source_id,
                'name': source.name,
                'priority': source.priority.name,
                'enabled': getattr(source.config, 'enabled', True),
                'circuit_breaker': self.collector.get_circuit_breaker_states().get(source_id, 'closed'),
                'last_execution_times': len(self._job_execution_times.get(source_id, [])),
            }
        
        return {
            sid: self.get_source_status(sid)
            for sid in self._sources
        }
