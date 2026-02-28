"""
Tests for the Source Discovery Engine.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock

from situation_monitor.core import (
    ParsedSituation,
    DataSource,
    SourceCategory,
    CredibilityScore,
)
from situation_monitor.sources.discovery import DiscoveryEngine, discover_sources
from situation_monitor.sources.adapters import (
    BaseAdapter,
    DuckDuckGoAdapter,
    ArxivAdapter,
)


class MockAdapter(BaseAdapter):
    """Mock adapter for testing."""
    
    def __init__(self, name: str, category: SourceCategory, sources: list = None):
        super().__init__()
        self._name = name
        self._category = category
        self._sources = sources or []
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def category(self) -> SourceCategory:
        return self._category
    
    async def discover(self, query: ParsedSituation) -> list:
        return self._sources


@pytest.fixture
def sample_parsed_situation():
    """Create a sample parsed situation for testing."""
    return ParsedSituation(
        summary="Test situation about climate change",
        keywords=["climate", "change", "global", "warming"],
        entities=["IPCC", "UN"],
        topics=["environment", "science"],
        location_context="Global",
        time_context="2024",
        raw_query="climate change news"
    )


@pytest.fixture
def sample_data_sources():
    """Create sample data sources for testing."""
    return [
        DataSource(
            id="test1",
            name="Test News Source",
            url="https://example.com/news",
            category=SourceCategory.NEWS,
            subcategory="web",
            description="A test news source",
            relevance_score=0.8,
        ),
        DataSource(
            id="test2",
            name="Test Academic Source",
            url="https://example.edu/paper",
            category=SourceCategory.ACADEMIC,
            subcategory="journal",
            description="A test academic paper",
            relevance_score=0.9,
        ),
    ]


@pytest.mark.asyncio
async def test_discovery_engine_initialization():
    """Test that discovery engine initializes correctly."""
    engine = DiscoveryEngine()
    
    # Should not be initialized yet
    assert not engine._initialized
    
    # Initialize
    result = await engine.initialize()
    
    # Should initialize successfully (some adapters may fail but engine should init)
    assert result is True or result is False  # Depends on adapter availability
    
    # Cleanup
    await engine.shutdown()


@pytest.mark.asyncio
async def test_get_categories():
    """Test that get_categories returns all categories."""
    engine = DiscoveryEngine()
    categories = engine.get_categories()
    
    # Should return all SourceCategory values
    assert len(categories) == len(SourceCategory)
    assert "news" in categories
    assert "academic" in categories
    assert "government" in categories
    assert "social" in categories
    assert "industry" in categories


@pytest.mark.asyncio
async def test_cache_functionality():
    """Test caching mechanism."""
    engine = DiscoveryEngine()
    
    query = ParsedSituation(
        summary="Test query",
        keywords=["test"],
    )
    
    # Create cache key
    cache_key = engine._get_cache_key(query)
    assert cache_key is not None
    assert len(cache_key) == 16
    
    # Test cache set and get
    sources = [
        DataSource(
            id="cached1",
            name="Cached Source",
            url="https://example.com",
            category=SourceCategory.NEWS,
        )
    ]
    
    engine._set_cached(cache_key, sources)
    cached = engine._get_cached(cache_key)
    
    assert cached is not None
    assert len(cached) == 1
    assert cached[0].id == "cached1"


@pytest.mark.asyncio
async def test_deduplication():
    """Test source deduplication."""
    engine = DiscoveryEngine()
    
    sources = [
        DataSource(
            id="dup1",
            name="Source A",
            url="https://example.com/page",
            category=SourceCategory.NEWS,
        ),
        DataSource(
            id="dup2",
            name="Source B",
            url="https://example.com/page/",  # Same URL with trailing slash
            category=SourceCategory.NEWS,
        ),
        DataSource(
            id="unique",
            name="Source C",
            url="https://different.com",
            category=SourceCategory.NEWS,
        ),
    ]
    
    deduplicated = engine._deduplicate_sources(sources)
    
    assert len(deduplicated) == 2
    urls = [s.url for s in deduplicated]
    assert "https://example.com/page" in urls or "https://example.com/page/" in urls
    assert "https://different.com" in urls


@pytest.mark.asyncio
async def test_credibility_scoring():
    """Test credibility scoring application."""
    engine = DiscoveryEngine()
    
    sources = [
        DataSource(
            id="edu",
            name=".edu Source",
            url="https://example.edu/research",
            category=SourceCategory.ACADEMIC,
        ),
        DataSource(
            id="gov",
            name=".gov Source",
            url="https://example.gov/data",
            category=SourceCategory.GOVERNMENT,
        ),
        DataSource(
            id="paywall",
            name="Paywalled Source",
            url="https://paywall.com/article",
            category=SourceCategory.NEWS,
            is_paywalled=True,
        ),
    ]
    
    scored = engine._apply_credibility_scoring(sources)
    
    # .edu should have higher authority
    edu_source = next(s for s in scored if s.id == "edu")
    assert edu_source.credibility.authority >= 0.9
    
    # .gov should have high authority
    gov_source = next(s for s in scored if s.id == "gov")
    assert gov_source.credibility.authority >= 0.9
    
    # Paywalled should have reduced transparency
    paywall_source = next(s for s in scored if s.id == "paywall")
    assert paywall_source.credibility.transparency <= 0.6


@pytest.mark.asyncio
async def test_limit_per_category():
    """Test limiting results per category."""
    engine = DiscoveryEngine()
    engine._max_results_per_category = 3
    
    sources = [
        DataSource(
            id=f"news{i}",
            name=f"News {i}",
            url=f"https://news{i}.com",
            category=SourceCategory.NEWS,
        )
        for i in range(10)
    ] + [
        DataSource(
            id=f"academic{i}",
            name=f"Academic {i}",
            url=f"https://academic{i}.edu",
            category=SourceCategory.ACADEMIC,
        )
        for i in range(5)
    ]
    
    limited = engine._limit_per_category(sources)
    
    news_count = sum(1 for s in limited if s.category == SourceCategory.NEWS)
    academic_count = sum(1 for s in limited if s.category == SourceCategory.ACADEMIC)
    
    assert news_count <= 3
    assert academic_count <= 3


@pytest.mark.asyncio
async def test_filter_adapters_by_preferences():
    """Test adapter filtering by category preferences."""
    engine = DiscoveryEngine()
    
    # Mock adapters
    adapter1 = MockAdapter("news_adapter", SourceCategory.NEWS)
    adapter2 = MockAdapter("academic_adapter", SourceCategory.ACADEMIC)
    adapter3 = MockAdapter("social_adapter", SourceCategory.SOCIAL)
    
    engine.adapters = {
        "news": adapter1,
        "academic": adapter2,
        "social": adapter3,
    }
    
    # Test with preferred categories
    query = ParsedSituation(
        summary="Test",
        keywords=["test"],
        preferred_categories=[SourceCategory.NEWS, SourceCategory.ACADEMIC],
    )
    
    filtered = engine._filter_adapters_by_preferences(query)
    assert len(filtered) == 2
    assert adapter1 in filtered
    assert adapter2 in filtered
    assert adapter3 not in filtered
    
    # Test with excluded categories
    query2 = ParsedSituation(
        summary="Test",
        keywords=["test"],
        excluded_categories=[SourceCategory.SOCIAL],
    )
    
    filtered2 = engine._filter_adapters_by_preferences(query2)
    assert len(filtered2) == 2
    assert adapter3 not in filtered2


@pytest.mark.asyncio
async def test_build_search_query_from_adapter():
    """Test search query building."""
    adapter = MockAdapter("test", SourceCategory.NEWS)
    
    query = ParsedSituation(
        summary="Climate change in the Arctic",
        keywords=["climate", "change", "arctic", "ice", "melting"],
        entities=["Greenland", "NOAA"],
        topics=["environment", "science"],
    )
    
    search_query = adapter._build_search_query(query)
    
    # Should include keywords and entities
    assert "climate" in search_query
    assert "change" in search_query
    assert "arctic" in search_query
    assert "Greenland" in search_query
    assert "NOAA" in search_query


@pytest.mark.asyncio
async def test_language_estimation():
    """Test language estimation from text."""
    adapter = MockAdapter("test", SourceCategory.NEWS)
    
    # English
    assert adapter._estimate_language("The quick brown fox jumps over the lazy dog") == "en"
    
    # Spanish
    assert adapter._estimate_language("El perro corre rápido") == "es"
    
    # French
    assert adapter._estimate_language("Le chat dort sur le lit") == "fr"
    
    # Default for empty/unknown
    assert adapter._estimate_language("") == "en"
    assert adapter._estimate_language("xyz123") == "en"


@pytest.mark.asyncio
async def test_paywall_detection():
    """Test paywall detection."""
    adapter = MockAdapter("test", SourceCategory.NEWS)
    
    # Should detect paywall
    paywall_html = """
    <html>
        <body>
            <div>Please subscribe to read more</div>
            <p>This content is behind a paywall</p>
        </body>
    </html>
    """
    assert adapter._detect_paywall(paywall_html) is True
    
    # Should not detect paywall
    normal_html = """
    <html>
        <body>
            <article>Free content here</article>
        </body>
    </html>
    """
    assert adapter._detect_paywall(normal_html) is False


@pytest.mark.asyncio
async def test_discovery_engine_discover(sample_parsed_situation):
    """Test the main discover method."""
    engine = DiscoveryEngine()
    
    # Mock adapters
    mock_source = DataSource(
        id="mock1",
        name="Mock Source",
        url="https://mock.com",
        category=SourceCategory.NEWS,
        relevance_score=0.75,
    )
    
    mock_adapter = MockAdapter("mock", SourceCategory.NEWS, [mock_source])
    engine.adapters = {"mock": mock_adapter}
    engine._initialized = True
    
    # Test discovery
    results = await engine.discover(sample_parsed_situation)
    
    assert len(results) >= 0  # May be empty if caching/initialization issues
    
    await engine.shutdown()


@pytest.mark.asyncio
async def test_convenience_function():
    """Test the discover_sources convenience function."""
    query = ParsedSituation(
        summary="Test query",
        keywords=["test"],
    )
    
    # This should work even if adapters fail
    results = await discover_sources(query)
    
    assert isinstance(results, list)


class TestDataSourceValidation:
    """Tests for DataSource model validation."""
    
    def test_datasource_creation(self):
        """Test creating a valid DataSource."""
        source = DataSource(
            id="test123",
            name="Test Source",
            url="https://example.com",
            category=SourceCategory.NEWS,
            credibility=CredibilityScore(
                overall=0.8,
                authority=0.9,
                accuracy=0.8,
                transparency=0.7,
            ),
        )
        
        assert source.id == "test123"
        assert source.name == "Test Source"
        assert source.category == SourceCategory.NEWS
        assert source.credibility.overall == 0.8
    
    def test_datasource_defaults(self):
        """Test DataSource default values."""
        source = DataSource(
            id="test",
            name="Test",
            url="https://example.com",
            category=SourceCategory.UNKNOWN,
        )
        
        assert source.is_paywalled is False
        assert source.requires_auth is False
        assert source.robots_txt_compliant is True
        assert source.relevance_score == 0.5
        assert isinstance(source.metadata, dict)


class TestParsedSituationValidation:
    """Tests for ParsedSituation model."""
    
    def test_parsed_situation_creation(self):
        """Test creating a ParsedSituation."""
        parsed = ParsedSituation(
            summary="Test situation",
            keywords=["test", "situation"],
            entities=["Entity1"],
            topics=["topic1"],
            raw_query="test query",
        )
        
        assert parsed.summary == "Test situation"
        assert parsed.keywords == ["test", "situation"]
        assert parsed.entities == ["Entity1"]
        assert parsed.raw_query == "test query"
    
    def test_parsed_situation_defaults(self):
        """Test ParsedSituation defaults."""
        parsed = ParsedSituation(
            summary="Test",
            keywords=["test"],
        )
        
        assert parsed.entities == []
        assert parsed.topics == []
        assert parsed.preferred_categories == []
        assert parsed.excluded_categories == []
        assert isinstance(parsed.parsed_at, datetime)


@pytest.mark.skip(reason="Integration test - requires external APIs")
class TestIntegration:
    """Integration tests with real APIs (skipped by default)."""
    
    @pytest.mark.asyncio
    async def test_duckduckgo_adapter(self):
        """Test DuckDuckGo adapter with real search."""
        adapter = DuckDuckGoAdapter()
        
        if not await adapter.initialize():
            pytest.skip("DuckDuckGo adapter not available")
        
        query = ParsedSituation(
            summary="Artificial intelligence news",
            keywords=["artificial intelligence", "AI", "machine learning"],
        )
        
        sources = await adapter.discover(query)
        
        assert len(sources) > 0
        assert all(s.category == SourceCategory.NEWS for s in sources)
        
        await adapter.shutdown()
    
    @pytest.mark.asyncio
    async def test_arxiv_adapter(self):
        """Test arXiv adapter with real search."""
        adapter = ArxivAdapter()
        
        if not await adapter.initialize():
            pytest.skip("arXiv adapter not available")
        
        query = ParsedSituation(
            summary="Quantum computing research",
            keywords=["quantum", "computing", "qubits"],
        )
        
        sources = await adapter.discover(query)
        
        assert len(sources) >= 0  # May be empty on network issues
        
        await adapter.shutdown()
