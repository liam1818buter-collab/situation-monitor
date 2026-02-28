"""
Tests for the NLP Analysis Pipeline.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import List

from situation_monitor.core.models import MonitoringResult, AlertRule, AlertSeverity
from situation_monitor.analysis.models import (
    SentimentScore,
    SentimentLabel,
    Summary,
    EntityMention,
    Keyword,
    Topic,
    Trend,
    TrendDirection,
    AlertCandidate,
    ChangeDetectionResult,
    AnalysisResult,
    BatchAnalysisResult,
    DocumentAnalysis,
)
from situation_monitor.analysis.modules import (
    SentimentAnalyzer,
    SentimentConfig,
    Summarizer,
    SummarizerConfig,
    EntityExtractor,
    EntityConfig,
    KeywordExtractor,
    KeywordConfig,
    TrendDetector,
    TrendConfig,
    ChangeDetector,
    ChangeDetectionConfig,
)
from situation_monitor.analysis.pipeline import AnalysisPipeline, PipelineConfig


# =============================================================================
# Sentiment Tests
# =============================================================================

class TestSentimentAnalyzer:
    """Tests for sentiment analysis module."""
    
    @pytest.fixture
    async def analyzer(self):
        config = SentimentConfig(use_transformers=False)  # Use VADER only for speed
        analyzer = SentimentAnalyzer(config)
        await analyzer.initialize()
        return analyzer
    
    @pytest.mark.asyncio
    async def test_analyze_positive(self):
        """Test positive sentiment detection."""
        config = SentimentConfig(use_transformers=False)
        analyzer = SentimentAnalyzer(config)
        await analyzer.initialize()
        
        text = "This is absolutely wonderful! I love it so much."
        result = analyzer.analyze(text)
        
        assert result is not None
        assert result.label == SentimentLabel.POSITIVE
        assert result.compound_score > 0
        assert result.positive_score > result.negative_score
    
    @pytest.mark.asyncio
    async def test_analyze_negative(self):
        """Test negative sentiment detection."""
        config = SentimentConfig(use_transformers=False)
        analyzer = SentimentAnalyzer(config)
        await analyzer.initialize()
        
        text = "This is terrible and awful. I hate it."
        result = analyzer.analyze(text)
        
        assert result is not None
        assert result.label == SentimentLabel.NEGATIVE
        assert result.compound_score < 0
        assert result.negative_score > result.positive_score
    
    @pytest.mark.asyncio
    async def test_analyze_neutral(self):
        """Test neutral sentiment detection."""
        config = SentimentConfig(use_transformers=False)
        analyzer = SentimentAnalyzer(config)
        await analyzer.initialize()
        
        text = "The meeting is scheduled for tomorrow at 3 PM."
        result = analyzer.analyze(text)
        
        assert result is not None
        # Should be neutral or near-neutral
        assert abs(result.compound_score) < 0.5
    
    @pytest.mark.asyncio
    async def test_analyze_empty(self):
        """Test empty text handling."""
        config = SentimentConfig(use_transformers=False)
        analyzer = SentimentAnalyzer(config)
        await analyzer.initialize()
        
        result = analyzer.analyze("")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_analyze_batch(self):
        """Test batch sentiment analysis."""
        config = SentimentConfig(use_transformers=False)
        analyzer = SentimentAnalyzer(config)
        await analyzer.initialize()
        
        texts = [
            "I love this product!",
            "This is terrible.",
            "It's okay I guess."
        ]
        results = analyzer.analyze_batch(texts)
        
        assert len(results) == 3
        assert results[0].label == SentimentLabel.POSITIVE
        assert results[1].label == SentimentLabel.NEGATIVE


# =============================================================================
# Summarization Tests
# =============================================================================

class TestSummarizer:
    """Tests for summarization module."""
    
    @pytest.mark.asyncio
    async def test_summarize_fallback(self):
        """Test extractive summarization fallback."""
        config = SummarizerConfig(fallback_to_extractive=True)
        summarizer = Summarizer(config)
        await summarizer.initialize()
        
        text = """
        Artificial intelligence is transforming the way we work and live. 
        Machine learning algorithms can now process vast amounts of data 
        to identify patterns and make predictions. Deep learning, a subset 
        of machine learning, uses neural networks with many layers to model 
        complex patterns. These technologies are being applied in healthcare, 
        finance, transportation, and many other fields. The impact of AI 
        on society is profound and continues to grow.
        """
        
        result = summarizer.summarize(text)
        
        assert result is not None
        assert len(result.text) > 0
        assert result.summary_length < result.original_length
        assert result.compression_ratio < 1.0
    
    @pytest.mark.asyncio
    async def test_summarize_short_text(self):
        """Test handling of short text."""
        config = SummarizerConfig()
        summarizer = Summarizer(config)
        await summarizer.initialize()
        
        result = summarizer.summarize("Short text.")
        assert result is None  # Too short to summarize


# =============================================================================
# Entity Extraction Tests
# =============================================================================

class TestEntityExtractor:
    """Tests for entity extraction module."""
    
    @pytest.mark.asyncio
    async def test_extract_entities(self):
        """Test basic entity extraction."""
        config = EntityConfig()
        extractor = EntityExtractor(config)
        
        # May fail if spaCy model not installed
        initialized = await extractor.initialize()
        if not initialized:
            pytest.skip("spaCy model not available")
        
        text = "Apple Inc. is planning to open a new store in Paris, France. Tim Cook announced the expansion."
        entities = extractor.extract_entities(text, "doc1")
        
        assert len(entities) > 0
        
        # Check for expected entities
        entity_texts = [e.entity for e in entities]
        assert "Apple" in entity_texts or "Apple Inc." in entity_texts
        assert "Paris" in entity_texts or "France" in entity_texts
    
    @pytest.mark.asyncio
    async def test_entity_tracking(self):
        """Test entity tracking across documents."""
        config = EntityConfig()
        extractor = EntityExtractor(config)
        
        initialized = await extractor.initialize()
        if not initialized:
            pytest.skip("spaCy model not available")
        
        # Extract from multiple documents
        extractor.extract_entities("Microsoft announced new products.", "doc1")
        extractor.extract_entities("Microsoft continues to grow.", "doc2")
        
        history = extractor.get_entity_history()
        assert len(history) > 0
        
        # Find Microsoft entity
        microsoft = [e for e in history if "Microsoft" in e.entity]
        if microsoft:
            assert microsoft[0].mention_count >= 2


# =============================================================================
# Keyword Extraction Tests
# =============================================================================

class TestKeywordExtractor:
    """Tests for keyword extraction module."""
    
    @pytest.mark.asyncio
    async def test_extract_keywords(self):
        """Test keyword extraction."""
        config = KeywordConfig(method="tfidf")
        extractor = KeywordExtractor(config)
        await extractor.initialize()
        
        text = """
        Python is a high-level programming language known for its readability 
        and versatility. Python is widely used in data science, machine learning, 
        web development, and automation. The Python community is very active 
        and contributes many useful libraries and frameworks.
        """
        
        keywords = extractor.extract_keywords(text, top_n=5)
        
        assert len(keywords) > 0
        assert all(kw.score > 0 for kw in keywords)
        
        # Python should be a top keyword
        keyword_texts = [kw.text.lower() for kw in keywords]
        assert "python" in keyword_texts


# =============================================================================
# Trend Detection Tests
# =============================================================================

class TestTrendDetector:
    """Tests for trend detection module."""
    
    def test_detect_trend_increasing(self):
        """Test detection of increasing trend."""
        config = TrendConfig(min_percent_change=10.0)
        detector = TrendDetector(config)
        
        base_time = datetime.utcnow()
        
        # Add previous period data (low frequency)
        for i in range(5):
            detector.add_data_point("ai", base_time - timedelta(hours=48-i), 2)
        
        # Add current period data (high frequency)
        for i in range(5):
            detector.add_data_point("ai", base_time - timedelta(hours=12-i), 10)
        
        trends = detector.detect_trends(keywords=["ai"], hours=24)
        
        assert len(trends) > 0
        assert trends[0].keyword == "ai"
        assert trends[0].direction == TrendDirection.INCREASING
        assert trends[0].percent_change > 0
    
    def test_no_trend_stable(self):
        """Test detection of stable (no trend) data."""
        config = TrendConfig(min_percent_change=50.0)
        detector = TrendDetector(config)
        
        base_time = datetime.utcnow()
        
        # Add consistent data
        for i in range(10):
            detector.add_data_point("stable", base_time - timedelta(hours=i), 5)
        
        trends = detector.detect_trends(keywords=["stable"], hours=24)
        
        # Should not detect significant trend
        assert len(trends) == 0


# =============================================================================
# Change Detection Tests
# =============================================================================

class TestChangeDetector:
    """Tests for change detection module."""
    
    def test_detect_changes(self):
        """Test basic change detection."""
        config = ChangeDetectionConfig(min_percent_change=20.0)
        detector = ChangeDetector(config)
        
        current = {"metric1": 100, "metric2": 50}
        previous = {"metric1": 80, "metric2": 50}
        
        changes = detector.detect_changes(current, previous)
        
        assert len(changes) == 1
        assert changes[0].metric_name == "metric1"
        assert changes[0].percent_change == 25.0
    
    def test_sentiment_shift_detection(self):
        """Test sentiment shift alert generation."""
        config = ChangeDetectionConfig(
            enable_sentiment_alerts=True,
            sentiment_shift_threshold=0.3
        )
        detector = ChangeDetector(config)
        
        current = SentimentScore(
            label=SentimentLabel.POSITIVE,
            confidence=0.8,
            positive_score=0.7,
            negative_score=0.1,
            neutral_score=0.2,
            compound_score=0.6
        )
        
        previous = SentimentScore(
            label=SentimentLabel.NEGATIVE,
            confidence=0.7,
            positive_score=0.1,
            negative_score=0.7,
            neutral_score=0.2,
            compound_score=-0.6
        )
        
        alert = detector.detect_sentiment_shift(current, previous, ["doc1"])
        
        assert alert is not None
        assert alert.alert_type == "sentiment_shift"
        assert alert.severity in ["medium", "high"]


# =============================================================================
# Pipeline Tests
# =============================================================================

class TestAnalysisPipeline:
    """Tests for the main analysis pipeline."""
    
    @pytest.fixture
    def sample_monitoring_result(self):
        """Create a sample monitoring result."""
        return MonitoringResult(
            source_id="test_source",
            timestamp=datetime.utcnow(),
            raw_data={
                "title": "AI Breakthrough",
                "content": "Scientists have made a major breakthrough in artificial intelligence research. The new system demonstrates remarkable capabilities in understanding natural language and solving complex problems."
            },
            processed_data={
                "text": "Scientists have made a major breakthrough in artificial intelligence research. The new system demonstrates remarkable capabilities in understanding natural language and solving complex problems."
            },
            title="AI Breakthrough",
            content="Scientists have made a major breakthrough in artificial intelligence research. The new system demonstrates remarkable capabilities in understanding natural language and solving complex problems."
        )
    
    @pytest.mark.asyncio
    async def test_pipeline_initialization(self):
        """Test pipeline initialization."""
        config = PipelineConfig(
            enable_sentiment=True,
            enable_keywords=True,
            enable_entities=False,  # Skip spaCy for speed
            enable_topics=False,
            enable_trends=True,
            enable_alerts=True
        )
        
        pipeline = AnalysisPipeline(config={"enable_sentiment": True})
        success = await pipeline.initialize()
        
        assert success is True
        assert pipeline._initialized is True
    
    @pytest.mark.asyncio
    async def test_analyze_document(self, sample_monitoring_result):
        """Test single document analysis."""
        pipeline = AnalysisPipeline(config={
            "enable_sentiment": True,
            "enable_keywords": True,
            "enable_entities": False,
            "enable_summarization": False,
            "enable_topics": False,
            "enable_trends": False,
            "enable_alerts": False
        })
        
        await pipeline.initialize()
        
        result = await pipeline.analyze(sample_monitoring_result)
        
        assert result is not None
        assert result.success is True
        assert result.source_id == "test_source"
        
        # Check sentiment
        if result.sentiment:
            assert result.sentiment.compound_score is not None
        
        # Check keywords
        assert len(result.keywords) > 0
    
    @pytest.mark.asyncio
    async def test_analyze_batch(self):
        """Test batch document analysis."""
        pipeline = AnalysisPipeline(config={
            "enable_sentiment": True,
            "enable_keywords": True,
            "enable_entities": False,
            "enable_topics": False
        })
        
        await pipeline.initialize()
        
        documents = [
            MonitoringResult(
                source_id="source1",
                timestamp=datetime.utcnow(),
                raw_data={"text": "Great product, love it!"},
                processed_data={"text": "Great product, love it!"}
            ),
            MonitoringResult(
                source_id="source2",
                timestamp=datetime.utcnow(),
                raw_data={"text": "Terrible experience, very disappointed."},
                processed_data={"text": "Terrible experience, very disappointed."}
            )
        ]
        
        result = await pipeline.analyze_batch(documents)
        
        assert result is not None
        assert result.document_count == 2
        assert len(result.document_analyses) == 2
    
    @pytest.mark.asyncio
    async def test_check_rules(self, sample_monitoring_result):
        """Test alert rule checking."""
        pipeline = AnalysisPipeline()
        await pipeline.initialize()
        
        rules = [
            AlertRule(
                id="rule1",
                name="AI mentions",
                keywords=["AI", "artificial intelligence"],
                severity=AlertSeverity.INFO,
                enabled=True
            ),
            AlertRule(
                id="rule2",
                name="Security alerts",
                keywords=["security", "breach"],
                severity=AlertSeverity.WARNING,
                enabled=True
            )
        ]
        
        alerts = await pipeline.check_rules(sample_monitoring_result, rules)
        
        assert len(alerts) == 1
        assert alerts[0].rule_id == "rule1"
    
    @pytest.mark.asyncio
    async def test_empty_content_handling(self):
        """Test handling of empty content."""
        pipeline = AnalysisPipeline()
        await pipeline.initialize()
        
        empty_result = MonitoringResult(
            source_id="empty_source",
            timestamp=datetime.utcnow(),
            raw_data={},
            content=""
        )
        
        result = await pipeline.analyze(empty_result)
        
        assert result is not None
        assert result.success is False
        assert "No content" in result.error
    
    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test pipeline statistics."""
        pipeline = AnalysisPipeline(config={
            "enable_sentiment": True,
            "enable_keywords": True
        })
        
        await pipeline.initialize()
        
        stats = pipeline.get_stats()
        
        assert stats["initialized"] is True
        assert "modules" in stats
        assert stats["modules"]["sentiment"] is True


# =============================================================================
# Model Validation Tests
# =============================================================================

def test_sentiment_score_validation():
    """Test SentimentScore model validation."""
    score = SentimentScore(
        label=SentimentLabel.POSITIVE,
        confidence=0.9,
        positive_score=0.8,
        negative_score=0.05,
        neutral_score=0.15,
        compound_score=0.75
    )
    
    assert score.label == SentimentLabel.POSITIVE
    assert 0 <= score.confidence <= 1


def test_summary_validation():
    """Test Summary model validation."""
    summary = Summary(
        text="Short summary.",
        original_length=1000,
        summary_length=100,
        compression_ratio=0.1,
        method="extractive"
    )
    
    assert summary.compression_ratio == 0.1
    assert summary.compression_ratio <= 1.0


def test_alert_candidate_validation():
    """Test AlertCandidate model validation."""
    alert = AlertCandidate(
        alert_type="trend_spike",
        severity="high",
        title="Test Alert",
        description="This is a test alert",
        confidence=0.85,
        source_document_ids=["doc1", "doc2"],
        affected_keywords=["keyword1"]
    )
    
    assert alert.alert_type == "trend_spike"
    assert alert.confidence == 0.85


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.asyncio
async def test_full_pipeline_integration():
    """Test full pipeline integration."""
    # Create pipeline with minimal config for speed
    pipeline = AnalysisPipeline(config={
        "enable_sentiment": True,
        "enable_keywords": True,
        "enable_summarization": False,  # Skip for speed
        "enable_entities": False,  # Skip spaCy
        "enable_topics": False,
        "enable_trends": True,
        "enable_alerts": True
    })
    
    success = await pipeline.initialize()
    assert success is True
    
    # Create test documents
    documents = [
        MonitoringResult(
            source_id="news",
            timestamp=datetime.utcnow(),
            raw_data={"text": f"Document {i} about technology and innovation."},
            processed_data={"text": f"Document {i} about technology and innovation."}
        )
        for i in range(5)
    ]
    
    # Analyze batch
    result = await pipeline.analyze_batch(documents)
    
    assert result.document_count == 5
    assert len(result.document_analyses) == 5
    
    # Check that analyses have expected fields
    for analysis in result.document_analyses:
        assert analysis.sentiment is not None
        assert len(analysis.keywords) > 0
        assert analysis.processing_time_ms > 0
    
    await pipeline.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
