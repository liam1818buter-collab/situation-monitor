from abc import ABC, abstractmethod
from typing import List, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum
import uuid


class RateLimit(BaseModel):
    requests_per_minute: int = 10
    burst: int = 5


class Document(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    title: str
    content: str
    source_type: str
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    content_hash: Optional[str] = None


class AnalysisResult(BaseModel):
    document_id: str
    sentiment: float = 0.0  # -1 to 1
    summary: str = ""
    entities: List[str] = []
    keywords: List[str] = []
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


class Alert(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    situation_id: str
    severity: str  # INFO, WARNING, CRITICAL
    message: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Source(ABC):
    @abstractmethod
    async def fetch(self, query: str) -> List[Document]: ...
    
    @property
    @abstractmethod
    def rate_limit(self) -> RateLimit: ...


class Analyzer(ABC):
    @abstractmethod
    async def analyze(self, documents: List[Document]) -> List[AnalysisResult]: ...


class Storage(ABC):
    @abstractmethod
    async def save_document(self, doc: Document) -> str: ...
    @abstractmethod
    async def get_documents(self, situation_id: str) -> List[Document]: ...


class Notifier(ABC):
    @abstractmethod
    async def send(self, alert: Alert) -> bool: ...
