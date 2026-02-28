"""
Situation Monitor - Data Collection Scheduler

Agent 4: Continuous data collection system that monitors sources
and ingests new content.

Modules:
    models: Data models for RawDocument and ProcessedDocument
    interfaces: Source interface definitions (from Agent 1)
    collector: CollectorEngine with scrapling integration
    scheduler: CollectionScheduler with APScheduler

Usage:
    from situation_monitor.scheduler import CollectionScheduler
    from situation_monitor.interfaces import SourceConfig, SourcePriority
    
    scheduler = CollectionScheduler()
    scheduler.add_source(my_source)
    await scheduler.start()
"""

__version__ = "0.1.0"

# Re-export main classes for convenience
from models import (
    RawDocument,
    ProcessedDocument,
    ExtractedContent,
    DocumentStatus,
    SourceType,
    DeadLetterItem,
    HealthStatus,
)

from interfaces import (
    Source,
    SourceConfig,
    RateLimit,
    SourcePriority,
    WebSource,
    RSSSource,
    APISource,
)

from collector import CollectorEngine, CircuitBreaker
from scheduler import CollectionScheduler

__all__ = [
    # Models
    "RawDocument",
    "ProcessedDocument",
    "ExtractedContent",
    "DocumentStatus",
    "SourceType",
    "SourcePriority",
    "DeadLetterItem",
    "HealthStatus",
    # Interfaces
    "Source",
    "SourceConfig",
    "RateLimit",
    "WebSource",
    "RSSSource",
    "APISource",
    # Engine & Scheduler
    "CollectorEngine",
    "CircuitBreaker",
    "CollectionScheduler",
]
