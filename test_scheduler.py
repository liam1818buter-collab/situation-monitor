"""
Tests for the CollectionScheduler and CollectorEngine.

Run with: pytest test_scheduler.py -v
"""

import asyncio
import pytest
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import RawDocument, ProcessedDocument, DocumentStatus, SourceType, SourcePriority
from interfaces import Source, SourceConfig, WebSource, RSSSource, APISource, RateLimit
from collector import (
    CollectorEngine, ContentExtractor, DeduplicationStore,
    CircuitBreaker
)
from scheduler import CollectionScheduler, PrioritizedSource


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_db():
    """Create temporary database file."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    yield f"sqlite:///{db_path}"
    os.unlink(db_path)


@pytest.fixture
def sample_source_config():
    """Create sample source config."""
    return SourceConfig(
        source_id="test_source",
        name="Test Source",
        base_url="https://example.com",
        priority=SourcePriority.MEDIUM,
        rate_limit=RateLimit(requests_per_minute=10),
    )


@pytest.fixture
def mock_source(sample_source_config):
    """Create mock source for testing."""
    source = Mock(spec=WebSource)
    source.source_id = "test_source"
    source.name = "Test Source"
    source.priority = SourcePriority.MEDIUM
    source.config = sample_source_config
    source.fetch = AsyncMock(return_value=[])
    source.check_updates = AsyncMock(return_value=[])
    return source


@pytest.fixture
def sample_raw_document():
    """Create sample raw document."""
    return RawDocument(
        source_id="test_source",
        url="https://example.com/article1",
        raw_html="<html><body><h1>Test Article</h1><p>Content here</p></body></html>",
        status_code=200,
    )


# =============================================================================
# Model Tests
# =============================================================================

class TestModels:
    """Test data models."""
    
    def test_raw_document_creation(self):
        """Test RawDocument creation."""
        doc = RawDocument(
            source_id="test",
            url="https://example.com",
            raw_html="<html>test</html>",
        )
        
        assert doc.source_id == "test"
        assert doc.url == "https://example.com"
        assert doc.status == DocumentStatus.PENDING
        assert doc.content_hash is not None
        assert doc.id is not None
    
    def test_raw_document_serialization(self):
        """Test RawDocument serialization."""
        doc = RawDocument(
            source_id="test",
            url="https://example.com",
            raw_html="<html>test</html>",
        )
        
        data = doc.to_dict()
        restored = RawDocument.from_dict(data)
        
        assert restored.source_id == doc.source_id
        assert restored.url == doc.url
        assert restored.content_hash == doc.content_hash
    
    def test_raw_document_deduplication_hash(self):
        """Test that identical content produces same hash."""
        doc1 = RawDocument(raw_html="<html>Same Content</html>")
        doc2 = RawDocument(raw_html="<html>Same Content</html>")
        
        assert doc1.content_hash == doc2.content_hash
    
    def test_document_status_enum(self):
        """Test DocumentStatus enum."""
        assert DocumentStatus.PENDING.value == "pending"
        assert DocumentStatus.FAILED.value == "failed"


# =============================================================================
# Interface Tests
# =============================================================================

class TestInterfaces:
    """Test source interfaces."""
    
    def test_rate_limit_defaults(self):
        """Test RateLimit default values."""
        rl = RateLimit()
        assert rl.requests_per_minute == 10
        assert rl.min_interval_seconds >= 6.0
    
    def test_rate_limit_custom(self):
        """Test RateLimit with custom values."""
        rl = RateLimit(requests_per_minute=30)
        assert rl.requests_per_minute == 30
        assert rl.min_interval_seconds >= 2.0
    
    def test_source_config_defaults(self):
        """Test SourceConfig defaults."""
        config = SourceConfig(
            source_id="test",
            name="Test",
            base_url="https://test.com",
        )
        
        assert config.rate_limit is not None
        assert config.custom_headers == {}
        assert config.selectors == {}
        assert config.enabled is True
    
    def test_source_priority_ordering(self):
        """Test SourcePriority ordering."""
        assert SourcePriority.CRITICAL.value < SourcePriority.HIGH.value
        assert SourcePriority.HIGH.value < SourcePriority.MEDIUM.value
        assert SourcePriority.MEDIUM.value < SourcePriority.LOW.value


# =============================================================================
# Collector Tests
# =============================================================================

class TestContentExtractor:
    """Test ContentExtractor."""
    
    def test_extract_title_from_html(self):
        """Test title extraction."""
        html = """
        <html>
            <head><title>Page Title</title></head>
            <body><h1>Article Title</h1></body>
        </html>
        """
        
        extractor = ContentExtractor()
        result = extractor.extract(html, "https://example.com")
        
        assert "Page Title" in result.title or "Article Title" in result.title
    
    def test_extract_article_text(self):
        """Test article text extraction."""
        html = """
        <html>
            <body>
                <article>
                    <p>This is the first paragraph of the article.</p>
                    <p>This is the second paragraph.</p>
                </article>
            </body>
        </html>
        """
        
        extractor = ContentExtractor()
        result = extractor.extract(html, "https://example.com")
        
        assert "first paragraph" in result.article_text
        assert "second paragraph" in result.article_text
    
    def test_extract_links(self):
        """Test link extraction."""
        html = """
        <html>
            <body>
                <a href="/page1">Link 1</a>
                <a href="https://other.com/page">Link 2</a>
            </body>
        </html>
        """
        
        extractor = ContentExtractor()
        result = extractor.extract(html, "https://example.com")
        
        assert any("/page1" in link for link in result.links)


class TestDeduplicationStore:
    """Test DeduplicationStore."""
    
    def test_is_duplicate(self):
        """Test duplicate detection."""
        store = DeduplicationStore()
        
        hash1 = "abc123"
        hash2 = "def456"
        
        assert not store.is_duplicate(hash1)
        store.add(hash1)
        assert store.is_duplicate(hash1)
        assert not store.is_duplicate(hash2)
    
    def test_is_url_changed(self):
        """Test URL change detection."""
        store = DeduplicationStore()
        
        url = "https://example.com/page"
        hash1 = "content_v1"
        hash2 = "content_v2"
        
        assert store.is_url_changed(url, hash1)
        store.add(hash1, url)
        
        assert store.is_url_changed(url, hash2)
        assert not store.is_url_changed(url, hash1)
    
    def test_max_size_limit(self):
        """Test store size limiting."""
        store = DeduplicationStore(max_size=5)
        
        for i in range(10):
            store.add(f"hash{i}")
        
        assert len(store._hashes) <= 5


class TestCircuitBreaker:
    """Test CircuitBreaker."""
    
    def test_initial_state(self):
        """Test initial state is closed."""
        cb = CircuitBreaker()
        assert cb.state == CircuitBreaker.STATE_CLOSED
        assert cb.can_execute() is True
    
    def test_opens_after_failures(self):
        """Test circuit opens after threshold failures."""
        cb = CircuitBreaker(failure_threshold=3)
        
        for _ in range(3):
            cb.record_failure()
        
        assert cb.state == CircuitBreaker.STATE_OPEN
        assert cb.can_execute() is False
    
    def test_half_open_after_timeout(self):
        """Test circuit goes half-open after timeout."""
        cb = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0  # Immediate recovery for testing
        )
        
        cb.record_failure()
        assert cb.state == CircuitBreaker.STATE_HALF_OPEN
    
    def test_closes_after_successes(self):
        """Test circuit closes after successful half-open calls."""
        cb = CircuitBreaker(
            failure_threshold=1,
            recovery_timeout=0,
            half_open_max_calls=2
        )
        
        cb.record_failure()
        assert cb.state == CircuitBreaker.STATE_HALF_OPEN
        
        cb.record_success()
        assert cb.state == CircuitBreaker.STATE_HALF_OPEN  # Need more successes
        
        cb.record_success()
        assert cb.state == CircuitBreaker.STATE_CLOSED


class TestCollectorEngine:
    """Test CollectorEngine."""
    
    @pytest.fixture
    def engine(self):
        """Create test engine."""
        return CollectorEngine(use_stealth=False)
    
    def test_initialization(self, engine):
        """Test engine initialization."""
        assert engine.use_stealth is False
        assert engine.max_concurrent == 5
        assert engine.stats['fetched'] == 0
    
    def test_deduplication(self, engine, sample_raw_document):
        """Test document deduplication."""
        doc1 = sample_raw_document
        doc2 = RawDocument(
            source_id="test_source",
            url="https://example.com/article2",
            raw_html=sample_raw_document.raw_html,  # Same content
        )
        
        # Process first document
        result1 = asyncio.run(engine.process_document(doc1))
        assert result1 is not None
        
        # Second should be duplicate
        result2 = asyncio.run(engine.process_document(doc2))
        assert result2 is None
        
        assert engine.stats['deduplicated'] == 1
    
    def test_change_detection(self, engine):
        """Test change detection for same URL."""
        url = "https://example.com/page"
        
        doc1 = RawDocument(source_id="test", url=url, raw_html="Version 1")
        doc2 = RawDocument(source_id="test", url=url, raw_html="Version 2")
        doc3 = RawDocument(source_id="test", url=url, raw_html="Version 1")
        
        # First fetch
        result1 = asyncio.run(engine.process_document(doc1))
        assert result1 is not None
        
        # Changed content
        result2 = asyncio.run(engine.process_document(doc2))
        assert result2 is not None
        
        # Back to original (should be detected as seen)
        result3 = asyncio.run(engine.process_document(doc3))
        assert result3 is None  # Already seen this hash
    
    def test_extract_content(self, engine, sample_raw_document):
        """Test content extraction."""
        processed = engine.extract_content(sample_raw_document)
        
        assert processed.raw_document_id == sample_raw_document.id
        assert processed.extracted.title is not None
    
    def test_circuit_breaker_per_source(self, engine):
        """Test circuit breaker isolation per source."""
        cb1 = engine._get_circuit_breaker("source1")
        cb2 = engine._get_circuit_breaker("source2")
        
        assert cb1 is not cb2
        
        cb1.record_failure()
        assert cb1.can_execute() is True  # Below threshold
        assert cb2.can_execute() is True
    
    def test_dead_letter_queue(self, engine):
        """Test dead letter queue."""
        engine._add_to_dead_letter("source1", "https://example.com", "Error", "Exception")
        
        dlq = engine.get_dead_letter_queue()
        assert len(dlq) == 1
        assert dlq[0].source_id == "source1"
        assert dlq[0].error_type == "Exception"


# =============================================================================
# Scheduler Tests
# =============================================================================

class TestPrioritizedSource:
    """Test PrioritizedSource."""
    
    def test_priority_comparison(self):
        """Test priority-based ordering."""
        now = datetime.utcnow()
        
        ps1 = PrioritizedSource(
            priority=1,
            next_check=now,
            source=Mock(source_id="high")
        )
        
        ps2 = PrioritizedSource(
            priority=2,
            next_check=now,
            source=Mock(source_id="low")
        )
        
        # Lower priority value = higher priority
        assert ps1 < ps2


class TestCollectionScheduler:
    """Test CollectionScheduler."""
    
    @pytest.fixture
    async def scheduler(self, temp_db):
        """Create test scheduler."""
        sched = CollectionScheduler(db_path=temp_db)
        yield sched
        await sched.stop()
    
    @pytest.mark.asyncio
    async def test_add_source(self, temp_db, mock_source):
        """Test adding source to scheduler."""
        scheduler = CollectionScheduler(db_path=temp_db)
        
        result = scheduler.add_source(mock_source)
        assert result is True
        assert mock_source.source_id in scheduler._sources
        
        await scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_remove_source(self, temp_db, mock_source):
        """Test removing source."""
        scheduler = CollectionScheduler(db_path=temp_db)
        
        scheduler.add_source(mock_source)
        result = scheduler.remove_source(mock_source.source_id)
        
        assert result is True
        assert mock_source.source_id not in scheduler._sources
        
        await scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_get_check_interval(self, temp_db):
        """Test check interval calculation."""
        scheduler = CollectionScheduler(db_path=temp_db)
        
        # Create mock sources with different priorities
        critical_source = Mock(spec=Source)
        critical_source.priority = SourcePriority.CRITICAL
        critical_source.config = Mock(check_interval_minutes=None)
        
        low_source = Mock(spec=Source)
        low_source.priority = SourcePriority.LOW
        low_source.config = Mock(check_interval_minutes=None)
        
        critical_interval = scheduler._get_check_interval(critical_source)
        low_interval = scheduler._get_check_interval(low_source)
        
        assert critical_interval < low_interval
        
        await scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_get_health_status(self, temp_db):
        """Test health status reporting."""
        scheduler = CollectionScheduler(db_path=temp_db)
        
        health = scheduler.get_health_status()
        
        assert health.status in ["healthy", "degraded", "unhealthy"]
        assert health.active_jobs == 0
        assert health.queue_size == 0
        
        await scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_stats_tracking(self, temp_db):
        """Test statistics tracking."""
        scheduler = CollectionScheduler(db_path=temp_db)
        
        stats = scheduler.get_stats()
        
        assert 'jobs_scheduled' in stats
        assert 'sources' in stats
        assert stats['sources'] == 0
        
        await scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_trigger_immediate_check(self, temp_db, mock_source):
        """Test triggering immediate check."""
        scheduler = CollectionScheduler(db_path=temp_db)
        
        scheduler.add_source(mock_source)
        
        # Should return True for existing source
        result = scheduler.trigger_immediate_check(mock_source.source_id)
        assert result is True
        
        # Should return False for non-existent source
        result = scheduler.trigger_immediate_check("nonexistent")
        assert result is False
        
        await scheduler.stop()


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests."""
    
    @pytest.mark.asyncio
    async def test_full_collection_flow(self, temp_db):
        """Test full collection flow from source to queue."""
        # Create components
        scheduler = CollectionScheduler(db_path=temp_db)
        
        # Create mock source that returns documents
        mock_doc = RawDocument(
            source_id="test",
            url="https://example.com/article",
            raw_html="<html><h1>Title</h1><p>Content</p></html>",
        )
        
        mock_source = Mock(spec=WebSource)
        mock_source.source_id = "test_source"
        mock_source.name = "Test"
        mock_source.priority = SourcePriority.MEDIUM
        mock_source.config = SourceConfig(
            source_id="test_source",
            name="Test",
            base_url="https://example.com",
        )
        mock_source.fetch = AsyncMock(return_value=[mock_doc])
        
        # Track documents
        documents_received = []
        def on_document(doc):
            documents_received.append(doc)
        
        scheduler.add_document_callback(on_document)
        scheduler.add_source(mock_source)
        
        # Manually trigger check
        await scheduler._execute_source_check("test_source")
        
        # Verify document was processed
        assert len(documents_received) == 1
        assert documents_received[0].extracted.title is not None
        
        await scheduler.stop()
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self, temp_db):
        """Test circuit breaker with failing source."""
        scheduler = CollectionScheduler(db_path=temp_db)
        
        # Create failing source
        mock_source = Mock(spec=WebSource)
        mock_source.source_id = "failing_source"
        mock_source.name = "Failing"
        mock_source.priority = SourcePriority.MEDIUM
        mock_source.config = SourceConfig(
            source_id="failing_source",
            name="Failing",
            base_url="https://example.com",
        )
        mock_source.fetch = AsyncMock(side_effect=Exception("Network error"))
        
        scheduler.add_source(mock_source)
        
        # Execute check multiple times to trigger circuit breaker
        for _ in range(6):
            try:
                await scheduler._execute_source_check("failing_source")
            except:
                pass
        
        # Circuit should be open
        circuit_state = scheduler.collector.get_circuit_breaker_states().get("failing_source")
        assert circuit_state in ["open", "half_open"]
        
        await scheduler.stop()


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
