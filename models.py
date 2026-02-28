"""
Data models for the Situation Monitor content pipeline.

Defines RawDocument and ProcessedDocument models for storing
content at different stages of the pipeline.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List, Any
from enum import Enum
import hashlib
import json


class DocumentStatus(Enum):
    """Status of a document in the processing pipeline."""
    PENDING = "pending"
    FETCHING = "fetching"
    EXTRACTED = "extracted"
    PROCESSED = "processed"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    DEAD_LETTER = "dead_letter"


class SourceType(Enum):
    """Types of content sources."""
    NEWS = "news"
    ACADEMIC = "academic"
    GOVERNMENT = "government"
    SOCIAL = "social"
    BLOG = "blog"
    RSS = "rss"
    API = "api"


@dataclass
class RawDocument:
    """
    Raw document as fetched from source.
    
    Contains the original HTML/metadata before any processing.
    """
    # Core identifiers
    id: str = field(default_factory=lambda: "")
    source_id: str = ""
    source_type: SourceType = SourceType.NEWS
    url: str = ""
    
    # Raw content
    raw_html: str = ""
    raw_text: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    status_code: int = 200
    
    # Metadata
    fetched_at: datetime = field(default_factory=datetime.utcnow)
    content_hash: str = ""
    
    # Processing state
    status: DocumentStatus = DocumentStatus.PENDING
    retry_count: int = 0
    error_message: Optional[str] = None
    
    def __post_init__(self):
        """Generate ID and content hash if not provided."""
        if not self.id:
            self.id = self._generate_id()
        if not self.content_hash and self.raw_html:
            self.content_hash = self._compute_hash()
    
    def _generate_id(self) -> str:
        """Generate unique document ID."""
        timestamp = datetime.utcnow().isoformat()
        base = f"{self.source_id}:{self.url}:{timestamp}"
        return hashlib.sha256(base.encode()).hexdigest()[:16]
    
    def _compute_hash(self) -> str:
        """Compute hash of raw content for deduplication."""
        normalized = self.raw_html.lower().strip()
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "url": self.url,
            "raw_html": self.raw_html,
            "raw_text": self.raw_text,
            "headers": self.headers,
            "status_code": self.status_code,
            "fetched_at": self.fetched_at.isoformat(),
            "content_hash": self.content_hash,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RawDocument":
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            source_id=data.get("source_id", ""),
            source_type=SourceType(data.get("source_type", "news")),
            url=data.get("url", ""),
            raw_html=data.get("raw_html", ""),
            raw_text=data.get("raw_text", ""),
            headers=data.get("headers", {}),
            status_code=data.get("status_code", 200),
            fetched_at=datetime.fromisoformat(data["fetched_at"]) if data.get("fetched_at") else datetime.utcnow(),
            content_hash=data.get("content_hash", ""),
            status=DocumentStatus(data.get("status", "pending")),
            retry_count=data.get("retry_count", 0),
            error_message=data.get("error_message"),
        )


@dataclass  
class ExtractedContent:
    """Content extracted from a raw document."""
    title: str = ""
    author: Optional[str] = None
    publish_date: Optional[datetime] = None
    article_text: str = ""
    summary: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    language: str = "en"
    
    # Link extraction
    links: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "author": self.author,
            "publish_date": self.publish_date.isoformat() if self.publish_date else None,
            "article_text": self.article_text,
            "summary": self.summary,
            "keywords": self.keywords,
            "language": self.language,
            "links": self.links,
            "images": self.images,
        }


@dataclass
class ProcessedDocument:
    """
    Processed document ready for analysis.
    
    Contains cleaned text and extracted entities from downstream analyzers.
    """
    # Reference to raw document
    raw_document_id: str = ""
    
    # Extracted content
    extracted: ExtractedContent = field(default_factory=ExtractedContent)
    
    # Processing metadata
    processed_at: datetime = field(default_factory=datetime.utcnow)
    processor_version: str = "1.0.0"
    
    # Entities (populated by Agent 2 / NLP pipeline)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    
    # Analysis results (populated by Agent 5)
    sentiment_score: Optional[float] = None
    relevance_score: Optional[float] = None
    category: Optional[str] = None
    
    # Queue management
    queued_for_analysis: bool = False
    analysis_completed: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_document_id": self.raw_document_id,
            "extracted": self.extracted.to_dict(),
            "processed_at": self.processed_at.isoformat(),
            "processor_version": self.processor_version,
            "entities": self.entities,
            "sentiment_score": self.sentiment_score,
            "relevance_score": self.relevance_score,
            "category": self.category,
            "queued_for_analysis": self.queued_for_analysis,
            "analysis_completed": self.analysis_completed,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProcessedDocument":
        extracted_data = data.get("extracted", {})
        extracted = ExtractedContent(
            title=extracted_data.get("title", ""),
            author=extracted_data.get("author"),
            publish_date=datetime.fromisoformat(extracted_data["publish_date"]) if extracted_data.get("publish_date") else None,
            article_text=extracted_data.get("article_text", ""),
            summary=extracted_data.get("summary"),
            keywords=extracted_data.get("keywords", []),
            language=extracted_data.get("language", "en"),
            links=extracted_data.get("links", []),
            images=extracted_data.get("images", []),
        )
        
        return cls(
            raw_document_id=data.get("raw_document_id", ""),
            extracted=extracted,
            processed_at=datetime.fromisoformat(data["processed_at"]) if data.get("processed_at") else datetime.utcnow(),
            processor_version=data.get("processor_version", "1.0.0"),
            entities=data.get("entities", []),
            sentiment_score=data.get("sentiment_score"),
            relevance_score=data.get("relevance_score"),
            category=data.get("category"),
            queued_for_analysis=data.get("queued_for_analysis", False),
            analysis_completed=data.get("analysis_completed", False),
        )


@dataclass
class DeadLetterItem:
    """
    Item that failed processing and was moved to dead letter queue.
    """
    document_id: str = ""
    source_id: str = ""
    url: str = ""
    error_message: str = ""
    error_type: str = ""
    failed_at: datetime = field(default_factory=datetime.utcnow)
    raw_data: Optional[str] = None
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "source_id": self.source_id,
            "url": self.url,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "failed_at": self.failed_at.isoformat(),
            "raw_data": self.raw_data,
            "retry_count": self.retry_count,
        }


@dataclass
class HealthStatus:
    """Health check status for the collection system."""
    status: str = "healthy"  # healthy, degraded, unhealthy
    last_check: datetime = field(default_factory=datetime.utcnow)
    active_jobs: int = 0
    queue_size: int = 0
    dead_letter_size: int = 0
    circuit_breakers: Dict[str, str] = field(default_factory=dict)
    recent_errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "last_check": self.last_check.isoformat(),
            "active_jobs": self.active_jobs,
            "queue_size": self.queue_size,
            "dead_letter_size": self.dead_letter_size,
            "circuit_breakers": self.circuit_breakers,
            "recent_errors": self.recent_errors,
        }
