"""
Source interface definitions for the Situation Monitor.

This module defines the abstract base classes that all content sources
must implement. These interfaces are used by Agent 4 (Collector).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any, AsyncIterator
from enum import Enum


class SourcePriority(Enum):
    """Priority levels for source scheduling."""
    CRITICAL = 1    # Breaking news - check every 1-5 minutes
    HIGH = 2        # Important updates - check every 15-30 minutes
    MEDIUM = 3      # Regular monitoring - check every 1-2 hours
    LOW = 4         # Background monitoring - check daily


@dataclass
class RateLimit:
    """Rate limiting configuration for a source."""
    requests_per_minute: int = 10
    requests_per_hour: int = 100
    requests_per_day: int = 1000
    min_interval_seconds: float = 6.0  # Minimum time between requests
    
    def __post_init__(self):
        # Ensure min_interval respects requests_per_minute
        calculated_interval = 60.0 / self.requests_per_minute
        self.min_interval_seconds = max(self.min_interval_seconds, calculated_interval)


@dataclass
class SourceConfig:
    """Configuration for a content source."""
    source_id: str
    name: str
    base_url: str
    source_type: str = "news"
    priority: SourcePriority = SourcePriority.MEDIUM
    rate_limit: RateLimit = None
    enabled: bool = True
    
    # Scheduling
    check_interval_minutes: int = 60
    
    # Retry configuration
    max_retries: int = 3
    retry_backoff_base: float = 2.0
    
    # Source-specific settings
    custom_headers: Dict[str, str] = None
    selectors: Dict[str, str] = None
    
    def __post_init__(self):
        if self.rate_limit is None:
            self.rate_limit = RateLimit()
        if self.custom_headers is None:
            self.custom_headers = {}
        if self.selectors is None:
            self.selectors = {}


class Source(ABC):
    """
    Abstract base class for all content sources.
    
    All sources (RSS feeds, news sites, APIs, etc.) must implement this interface.
    """
    
    def __init__(self, config: SourceConfig):
        self.config = config
        self._last_fetch: Optional[datetime] = None
        self._consecutive_failures: int = 0
    
    @property
    def source_id(self) -> str:
        return self.config.source_id
    
    @property
    def name(self) -> str:
        return self.config.name
    
    @property
    def priority(self) -> SourcePriority:
        return self.config.priority
    
    @abstractmethod
    async def fetch(self, query: Optional[str] = None) -> List["RawDocument"]:
        """
        Fetch content from this source.
        
        Args:
            query: Optional search query or filter
            
        Returns:
            List of RawDocument objects
        """
        pass
    
    @abstractmethod
    async def check_updates(self) -> List["RawDocument"]:
        """
        Check for new/updated content since last fetch.
        
        Returns:
            List of new or updated RawDocument objects
        """
        pass
    
    def rate_limit(self) -> RateLimit:
        """Get rate limiting configuration for this source."""
        return self.config.rate_limit
    
    def should_fetch(self) -> bool:
        """Check if enough time has passed since last fetch."""
        if self._last_fetch is None:
            return True
        
        elapsed = (datetime.utcnow() - self._last_fetch).total_seconds()
        return elapsed >= self.config.rate_limit.min_interval_seconds
    
    def record_success(self):
        """Record a successful fetch."""
        self._last_fetch = datetime.utcnow()
        self._consecutive_failures = 0
    
    def record_failure(self):
        """Record a failed fetch."""
        self._consecutive_failures += 1
    
    def get_backoff_seconds(self) -> float:
        """Get current backoff time based on consecutive failures."""
        if self._consecutive_failures == 0:
            return 0
        import math
        return self.config.retry_backoff_base ** min(self._consecutive_failures, 6)
    
    @abstractmethod
    def get_check_interval(self) -> int:
        """Get the recommended check interval in minutes."""
        pass


class RSSSource(Source):
    """Base class for RSS feed sources."""
    
    def __init__(self, config: SourceConfig, feed_url: Optional[str] = None):
        super().__init__(config)
        self.feed_url = feed_url or config.base_url
    
    def get_check_interval(self) -> int:
        # RSS feeds typically update every 15-60 minutes
        priority_intervals = {
            SourcePriority.CRITICAL: 5,
            SourcePriority.HIGH: 15,
            SourcePriority.MEDIUM: 30,
            SourcePriority.LOW: 60,
        }
        return priority_intervals.get(self.config.priority, 30)


class WebSource(Source):
    """Base class for web scraping sources."""
    
    def __init__(self, config: SourceConfig):
        super().__init__(config)
        self._seen_urls: set = set()
    
    def get_check_interval(self) -> int:
        # Web sources vary by priority
        priority_intervals = {
            SourcePriority.CRITICAL: 5,
            SourcePriority.HIGH: 15,
            SourcePriority.MEDIUM: 60,
            SourcePriority.LOW: 1440,  # Daily
        }
        return priority_intervals.get(self.config.priority, 60)
    
    def is_new_url(self, url: str) -> bool:
        """Check if URL hasn't been seen before."""
        return url not in self._seen_urls
    
    def mark_url_seen(self, url: str):
        """Mark URL as seen."""
        self._seen_urls.add(url)


class APISource(Source):
    """Base class for API-based sources."""
    
    def __init__(self, config: SourceConfig, api_key: Optional[str] = None):
        super().__init__(config)
        self.api_key = api_key
    
    def get_check_interval(self) -> int:
        # API sources often have stricter limits
        priority_intervals = {
            SourcePriority.CRITICAL: 10,
            SourcePriority.HIGH: 30,
            SourcePriority.MEDIUM: 120,
            SourcePriority.LOW: 360,
        }
        return priority_intervals.get(self.config.priority, 120)


# Import at bottom to avoid circular imports
from models import RawDocument
