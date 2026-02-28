"""
Tests for the alert notification system with analysis integration.

Tests the AlertManager's process_analysis and should_alert methods,
as well as all notification channels.
"""

import asyncio
import json
import os
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock

from situation_monitor.alerts.manager import AlertManager
from situation_monitor.alerts.models import (
    Alert,
    AlertRule,
    Severity,
    AlertCondition,
    AnalysisResult,
    AlertState
)
from situation_monitor.alerts.channels.base import Channel, ChannelConfig, DeliveryResult, ChannelStatus
from situation_monitor.alerts.channels.console import ConsoleChannel
from situation_monitor.alerts.channels.discord import DiscordChannel
from situation_monitor.alerts.channels.email import EmailChannel
from situation_monitor.alerts.channels.webhook import WebhookChannel
from situation_monitor.alerts.channels.local import LocalChannel
from situation_monitor.core.models import Alert as CoreAlert, AlertSeverity


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def alert_manager():
    """Create a fresh alert manager for testing."""
    return AlertManager(
        default_rate_limit_seconds=0,  # Disable for tests
        enable_deduplication=False
    )


@pytest.fixture
def sample_analysis():
    """Create a sample analysis result."""
    return AnalysisResult(
        situation_id="sit-123",
        timestamp=datetime.utcnow(),
        sentiment_score=-0.5,
        sentiment_change=-0.4,
        entities=[{"name": "TestCorp", "type": "ORG"}],
        new_entities=["NewEntity"],
        keywords=[{"text": "crisis", "score": 0.9}],
        keyword_spikes=["crisis", "urgent"],
        document_count=10,
        sources=["source1", "source2"],
        raw_analysis={"test": "data"}
    )


@pytest.fixture
def minimal_analysis():
    """Create a minimal analysis with no significant changes."""
    return AnalysisResult(
        situation_id="sit-456",
        timestamp=datetime.utcnow(),
        sentiment_score=0.1,
        sentiment_change=0.05,
        entities=[],
        new_entities=[],
        keywords=[],
        keyword_spikes=[],
        document_count=5,
        sources=["source1"],
        raw_analysis={}
    )


@pytest.fixture
def channel_config():
    """Create a basic channel config."""
    return ChannelConfig(
        enabled=True,
        min_severity="info",
        rate_limit_seconds=0
    )


class MockChannel(Channel):
    """Mock channel for testing."""
    
    def __init__(self, name: str, config: ChannelConfig, should_succeed: bool = True):
        super().__init__(name, config)
        self.should_succeed = should_succeed
        self.sent_alerts = []
    
    async def send(self, alert) -> DeliveryResult:
        self.sent_alerts.append(alert)
        
        if self.should_succeed:
            self._record_success()
            return DeliveryResult(
                success=True,
                channel=self.name,
                alert_id=alert.id
            )
        else:
            self._record_error()
            return DeliveryResult(
                success=False,
                channel=self.name,
                alert_id=alert.id,
                error_message="Mock failure"
            )


# ============================================================================
# AlertManager should_alert Tests
# ============================================================================

class TestShouldAlert:
    """Tests for the should_alert method."""
    
    def test_sentiment_shift_triggers_alert(self, alert_manager, sample_analysis):
        """Test that significant sentiment shift triggers alert."""
        sample_analysis.sentiment_change = -0.4
        assert alert_manager.should_alert(sample_analysis) is True
    
    def test_small_sentiment_change_no_alert(self, alert_manager, minimal_analysis):
        """Test that small sentiment change doesn't trigger alert."""
        minimal_analysis.sentiment_change = 0.1
        assert alert_manager.should_alert(minimal_analysis) is False
    
    def test_new_entities_trigger_alert(self, alert_manager, sample_analysis):
        """Test that new entities trigger alert."""
        sample_analysis.new_entities = ["NewCorp", "NewPerson"]
        sample_analysis.sentiment_change = 0.0  # Reset sentiment
        assert alert_manager.should_alert(sample_analysis) is True
    
    def test_keyword_spikes_trigger_alert(self, alert_manager, sample_analysis):
        """Test that keyword spikes trigger alert."""
        sample_analysis.keyword_spikes = ["urgent", "breaking"]
        sample_analysis.sentiment_change = 0.0
        sample_analysis.new_entities = []
        assert alert_manager.should_alert(sample_analysis) is True
    
    def test_critical_negative_sentiment_triggers_alert(self, alert_manager, sample_analysis):
        """Test that very negative sentiment triggers alert."""
        sample_analysis.sentiment_score = -0.8
        sample_analysis.sentiment_change = 0.0
        sample_analysis.new_entities = []
        sample_analysis.keyword_spikes = []
        assert alert_manager.should_alert(sample_analysis) is True
    
    def test_no_alert_when_nothing_significant(self, alert_manager, minimal_analysis):
        """Test that no alert when nothing significant found."""
        assert alert_manager.should_alert(minimal_analysis) is False


# ============================================================================
# AlertManager process_analysis Tests
# ============================================================================

class TestProcessAnalysis:
    """Tests for the process_analysis method."""
    
    @pytest.mark.asyncio
    async def test_process_analysis_sends_alert(self, alert_manager, sample_analysis):
        """Test that process_analysis sends alerts when warranted."""
        mock_channel = MockChannel("mock", ChannelConfig(enabled=True))
        alert_manager.add_channel(mock_channel)
        
        results = await alert_manager.process_analysis("sit-123", sample_analysis)
        
        assert len(results) == 1
        assert results[0].success is True
        assert len(mock_channel.sent_alerts) == 1
    
    @pytest.mark.asyncio
    async def test_process_analysis_no_alert_when_not_warranted(self, alert_manager, minimal_analysis):
        """Test that no alert sent when analysis doesn't warrant it."""
        mock_channel = MockChannel("mock", ChannelConfig(enabled=True))
        alert_manager.add_channel(mock_channel)
        
        results = await alert_manager.process_analysis("sit-456", minimal_analysis)
        
        assert len(results) == 0
        assert len(mock_channel.sent_alerts) == 0
    
    @pytest.mark.asyncio
    async def test_process_analysis_specific_channels(self, alert_manager, sample_analysis):
        """Test sending to specific channels only."""
        mock1 = MockChannel("mock1", ChannelConfig(enabled=True))
        mock2 = MockChannel("mock2", ChannelConfig(enabled=True))
        alert_manager.add_channel(mock1)
        alert_manager.add_channel(mock2)
        
        results = await alert_manager.process_analysis(
            "sit-123",
            sample_analysis,
            channels=["mock1"]
        )
        
        assert len(mock1.sent_alerts) == 1
        assert len(mock2.sent_alerts) == 0
    
    @pytest.mark.asyncio
    async def test_process_analysis_disabled_channel_skipped(self, alert_manager, sample_analysis):
        """Test that disabled channels are skipped."""
        mock = MockChannel("mock", ChannelConfig(enabled=False))
        alert_manager.add_channel(mock)
        
        results = await alert_manager.process_analysis("sit-123", sample_analysis)
        
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_process_analysis_no_channels_configured(self, alert_manager, sample_analysis):
        """Test behavior when no channels configured."""
        results = await alert_manager.process_analysis("sit-123", sample_analysis)
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_process_analysis_channel_failure(self, alert_manager, sample_analysis):
        """Test handling of channel failure."""
        mock = MockChannel("mock", ChannelConfig(enabled=True), should_succeed=False)
        alert_manager.add_channel(mock)
        
        results = await alert_manager.process_analysis("sit-123", sample_analysis)
        
        assert len(results) == 1
        assert results[0].success is False


# ============================================================================
# Severity Determination Tests
# ============================================================================

class TestDetermineSeverity:
    """Tests for the _determine_severity method."""
    
    def test_critical_severity_for_extreme_negative_sentiment(self, alert_manager):
        """Test critical severity for very negative sentiment."""
        analysis = AnalysisResult(
            situation_id="test",
            sentiment_score=-0.9,
            sentiment_change=0.0
        )
        severity = alert_manager._determine_severity(analysis)
        assert severity == Severity.CRITICAL
    
    def test_critical_severity_for_major_sentiment_shift(self, alert_manager):
        """Test critical severity for major sentiment shift."""
        analysis = AnalysisResult(
            situation_id="test",
            sentiment_score=0.0,
            sentiment_change=0.6
        )
        severity = alert_manager._determine_severity(analysis)
        assert severity == Severity.CRITICAL
    
    def test_warning_severity_for_moderate_negative_sentiment(self, alert_manager):
        """Test warning severity for moderately negative sentiment."""
        analysis = AnalysisResult(
            situation_id="test",
            sentiment_score=-0.6,
            sentiment_change=0.0
        )
        severity = alert_manager._determine_severity(analysis)
        assert severity == Severity.WARNING
    
    def test_warning_severity_for_multiple_new_entities(self, alert_manager):
        """Test warning severity for multiple new entities."""
        analysis = AnalysisResult(
            situation_id="test",
            sentiment_score=0.0,
            new_entities=["A", "B", "C", "D"]
        )
        severity = alert_manager._determine_severity(analysis)
        assert severity == Severity.WARNING
    
    def test_info_severity_for_minor_changes(self, alert_manager):
        """Test info severity for minor changes."""
        analysis = AnalysisResult(
            situation_id="test",
            sentiment_score=-0.2,
            new_entities=["One"]
        )
        severity = alert_manager._determine_severity(analysis)
        assert severity == Severity.INFO


# ============================================================================
# Alert Content Building Tests
# ============================================================================

class TestBuildAlertContent:
    """Tests for the _build_alert_content method."""
    
    def test_builds_title_with_sentiment_shift(self, alert_manager):
        """Test title includes sentiment shift info."""
        analysis = AnalysisResult(
            situation_id="test",
            sentiment_change=-0.4
        )
        title, message = alert_manager._build_alert_content(analysis, "sit-123")
        assert "Sentiment" in title
        assert "drop" in title.lower()
    
    def test_builds_title_with_new_entities(self, alert_manager):
        """Test title includes new entities info."""
        analysis = AnalysisResult(
            situation_id="test",
            new_entities=["Entity1", "Entity2"]
        )
        title, message = alert_manager._build_alert_content(analysis, "sit-123")
        assert "New entities" in message
        assert "Entity1" in message
    
    def test_builds_title_with_keyword_spikes(self, alert_manager):
        """Test title includes keyword spikes info."""
        analysis = AnalysisResult(
            situation_id="test",
            keyword_spikes=["urgent", "breaking", "news"]
        )
        title, message = alert_manager._build_alert_content(analysis, "sit-123")
        assert "Keyword spikes" in message
    
    def test_includes_document_count(self, alert_manager):
        """Test message includes document count."""
        analysis = AnalysisResult(
            situation_id="test",
            document_count=42,
            sources=["s1", "s2", "s3"]
        )
        title, message = alert_manager._build_alert_content(analysis, "sit-123")
        assert "42 documents" in message
        assert "3 sources" in message


# ============================================================================
# Console Channel Tests
# ============================================================================

class TestConsoleChannel:
    """Tests for the Console notification channel."""
    
    @pytest.mark.asyncio
    async def test_console_channel_sends(self, channel_config):
        """Test console channel outputs alert."""
        channel = ConsoleChannel(
            name="console",
            config=channel_config,
            use_colors=False,
            json_output=False
        )
        
        alert = CoreAlert(
            id="test-123",
            rule_id="rule-1",
            source_id="sit-123",
            severity=AlertSeverity.WARNING,
            title="Test Alert",
            message="This is a test message"
        )
        
        result = await channel.send(alert)
        
        assert result.success is True
        assert result.channel == "console"
    
    @pytest.mark.asyncio
    async def test_console_channel_json_output(self, channel_config):
        """Test console channel JSON output format."""
        channel = ConsoleChannel(
            name="console",
            config=channel_config,
            json_output=True
        )
        
        alert = CoreAlert(
            id="test-123",
            rule_id="rule-1",
            source_id="sit-123",
            severity=AlertSeverity.INFO,
            title="Test",
            message="Test message"
        )
        
        result = await channel.send(alert)
        
        assert result.success is True
        assert result.metadata['json_output'] is True
    
    @pytest.mark.asyncio
    async def test_console_channel_with_colors(self, channel_config):
        """Test console channel with color output."""
        channel = ConsoleChannel(
            name="console",
            config=channel_config,
            use_colors=True,
            json_output=False
        )
        
        alert = CoreAlert(
            id="test-123",
            rule_id="rule-1",
            source_id="sit-123",
            severity=AlertSeverity.CRITICAL,
            title="Critical Alert",
            message="Critical message"
        )
        
        result = await channel.send(alert)
        
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_console_channel_respects_severity_filter(self, channel_config):
        """Test that console channel respects severity filtering."""
        config = ChannelConfig(enabled=True, min_severity="error")
        channel = ConsoleChannel(
            name="console",
            config=config
        )
        
        alert = CoreAlert(
            id="test-123",
            rule_id="rule-1",
            source_id="sit-123",
            severity=AlertSeverity.INFO,
            title="Test",
            message="Test message"
        )
        
        result = await channel.send(alert)
        
        assert result.success is False
        assert "filtered" in result.error_message.lower()


# ============================================================================
# Alert Models Tests
# ============================================================================

class TestAlertModels:
    """Tests for alert-specific models."""
    
    def test_alert_creation(self):
        """Test creating an alert model."""
        alert = Alert(
            id="alert-123",
            situation_id="sit-123",
            severity=Severity.WARNING,
            message="Test message",
            title="Test Alert"
        )
        
        assert alert.id == "alert-123"
        assert alert.situation_id == "sit-123"
        assert alert.severity == Severity.WARNING
        assert alert.created_at is not None
    
    def test_alert_rule_creation(self):
        """Test creating an alert rule."""
        rule = AlertRule(
            id="rule-123",
            name="Test Rule",
            situation_id="sit-123",
            condition="sentiment_shift",
            threshold=0.3,
            channels=["discord", "email"]
        )
        
        assert rule.id == "rule-123"
        assert rule.condition == "sentiment_shift"
        assert rule.threshold == 0.3
        assert rule.channels == ["discord", "email"]
        assert rule.enabled is True
    
    def test_analysis_result_creation(self):
        """Test creating an analysis result."""
        analysis = AnalysisResult(
            situation_id="sit-123",
            sentiment_score=-0.5,
            sentiment_change=-0.3,
            document_count=10
        )
        
        assert analysis.situation_id == "sit-123"
        assert analysis.sentiment_score == -0.5
        assert analysis.document_count == 10
    
    def test_severity_enum_values(self):
        """Test severity enum has correct values."""
        assert Severity.INFO.value == "info"
        assert Severity.WARNING.value == "warning"
        assert Severity.CRITICAL.value == "critical"
    
    def test_alert_condition_enum_values(self):
        """Test alert condition enum has correct values."""
        assert AlertCondition.SENTIMENT_SHIFT.value == "sentiment_shift"
        assert AlertCondition.NEW_ENTITY.value == "new_entity"
        assert AlertCondition.KEYWORD_SPIKE.value == "keyword_spike"


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_full_alert_flow():
    """Test complete alert flow from analysis to delivery."""
    # Setup
    manager = AlertManager()
    console_channel = ConsoleChannel(
        name="console",
        config=ChannelConfig(enabled=True, min_severity="info"),
        use_colors=False
    )
    manager.add_channel(console_channel)
    
    # Create analysis that should trigger alert
    analysis = AnalysisResult(
        situation_id="integration-test",
        sentiment_score=-0.6,
        sentiment_change=-0.4,
        new_entities=["CrisisCorp"],
        keyword_spikes=["urgent"],
        document_count=15,
        sources=["news", "social"]
    )
    
    # Process analysis
    results = await manager.process_analysis("integration-test", analysis)
    
    # Verify
    assert len(results) == 1
    assert results[0].success is True


@pytest.mark.asyncio
async def test_rate_limiting_between_alerts():
    """Test rate limiting prevents duplicate alerts."""
    manager = AlertManager(
        default_rate_limit_seconds=3600,  # 1 hour
        enable_deduplication=True
    )
    mock = MockChannel("mock", ChannelConfig(enabled=True))
    manager.add_channel(mock)
    
    analysis = AnalysisResult(
        situation_id="rate-test",
        sentiment_change=-0.5
    )
    
    # First alert should go through
    results1 = await manager.process_analysis("rate-test", analysis)
    assert len(results1) == 1
    assert results1[0].success is True
    
    # Second identical alert should be rate limited
    results2 = await manager.process_analysis("rate-test", analysis)
    assert len(results2) == 0  # Should not send due to rate limiting


# ============================================================================
# Configuration Tests
# ============================================================================

class TestAlertConfiguration:
    """Tests for alert configuration from environment."""
    
    def test_alert_rule_default_cooldown(self):
        """Test default cooldown is 15 minutes."""
        rule = AlertRule(
            id="test",
            name="Test Rule",
            condition="sentiment_shift",
            threshold=0.3
        )
        assert rule.cooldown_minutes == 15
    
    def test_alert_rule_custom_cooldown(self):
        """Test custom cooldown configuration."""
        rule = AlertRule(
            id="test",
            name="Test Rule",
            condition="sentiment_shift",
            threshold=0.3,
            cooldown_minutes=30
        )
        assert rule.cooldown_minutes == 30
    
    def test_severity_from_environment_config(self):
        """Test severity can be configured."""
        rule = AlertRule(
            id="test",
            name="Test Rule",
            condition="keyword_spike",
            threshold=2.0,
            min_severity=Severity.WARNING
        )
        assert rule.min_severity == Severity.WARNING


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
