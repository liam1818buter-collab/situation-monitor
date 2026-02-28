"""
Tests for the alert and notification system.
"""

import asyncio
import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import pytest

from situation_monitor.core.models import Alert, AlertSeverity, MonitoringResult
from situation_monitor.alerts.channels.base import Channel, ChannelConfig, DeliveryResult, ChannelStatus
from situation_monitor.alerts.channels.email import EmailChannel
from situation_monitor.alerts.channels.discord import DiscordChannel
from situation_monitor.alerts.channels.slack import SlackChannel
from situation_monitor.alerts.channels.local import LocalChannel
from situation_monitor.alerts.channels.webhook import WebhookChannel
from situation_monitor.alerts.manager import AlertManager
from situation_monitor.alerts.rules import AlertRulesEngine, RuleConfig, AggregationMode


class MockChannel(Channel):
    """Mock channel for testing."""
    
    def __init__(self, name: str, config: ChannelConfig, should_succeed: bool = True):
        super().__init__(name, config)
        self.should_succeed = should_succeed
        self.sent_alerts = []
    
    async def send(self, alert: Alert) -> DeliveryResult:
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


# Fixtures
@pytest.fixture
def sample_alert():
    """Create a sample alert for testing."""
    return Alert(
        id="test-alert-001",
        rule_id="test-rule",
        source_id="test-source",
        severity=AlertSeverity.WARNING,
        title="Test Alert",
        message="This is a test alert message",
        timestamp=datetime.utcnow()
    )


@pytest.fixture
def sample_monitoring_result():
    """Create a sample monitoring result."""
    return MonitoringResult(
        source_id="test-source",
        timestamp=datetime.utcnow(),
        raw_data={"test": "data"},
        title="Test Content",
        content="Test content body",
        url="https://example.com/test"
    )


@pytest.fixture
def channel_config():
    """Create a basic channel config."""
    return ChannelConfig(
        enabled=True,
        min_severity="info",
        rate_limit_seconds=0  # No rate limiting for tests
    )


# Channel Tests
class TestChannelBase:
    """Tests for the base Channel class."""
    
    def test_channel_initialization(self, channel_config):
        """Test channel initialization."""
        channel = MockChannel("test", channel_config)
        
        assert channel.name == "test"
        assert channel.enabled is True
        assert channel.status == ChannelStatus.ACTIVE
    
    def test_channel_disable_enable(self, channel_config):
        """Test disabling and enabling channels."""
        channel = MockChannel("test", channel_config)
        
        channel.disable()
        assert channel.enabled is False
        assert channel.status == ChannelStatus.DISABLED
        
        channel.enable()
        assert channel.enabled is True
        assert channel.status == ChannelStatus.ACTIVE
    
    @pytest.mark.asyncio
    async def test_channel_severity_filter(self, sample_alert):
        """Test severity filtering."""
        config = ChannelConfig(enabled=True, min_severity="error")
        channel = MockChannel("test", config)
        
        # Info alert should be filtered
        sample_alert.severity = AlertSeverity.INFO
        result = await channel.send(sample_alert)
        assert result.success is False
        assert "filtered" in result.error_message.lower()
        
        # Critical alert should pass
        sample_alert.severity = AlertSeverity.CRITICAL
        result = await channel.send(sample_alert)
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_channel_quiet_hours(self, sample_alert):
        """Test quiet hours functionality."""
        config = ChannelConfig(
            enabled=True,
            min_severity="info",
            quiet_hours_start=0,
            quiet_hours_end=23  # Whole day
        )
        channel = MockChannel("test", config)
        
        result = await channel.send(sample_alert)
        assert result.success is False
        assert "quiet hours" in result.error_message.lower()
    
    @pytest.mark.asyncio
    async def test_channel_rate_limit(self, sample_alert):
        """Test rate limiting."""
        config = ChannelConfig(enabled=True, rate_limit_seconds=3600)
        channel = MockChannel("test", config)
        
        # First send should work
        result = await channel.send(sample_alert)
        assert result.success is True
        
        # Second send should be rate limited
        result = await channel.send(sample_alert)
        assert result.success is False
        assert "rate limited" in result.error_message.lower()


class TestAlertManager:
    """Tests for the AlertManager."""
    
    @pytest.fixture
    def manager(self):
        """Create a fresh alert manager."""
        return AlertManager(
            default_rate_limit_seconds=0,  # Disable for tests
            enable_deduplication=False
        )
    
    @pytest.mark.asyncio
    async def test_manager_initialization(self, manager):
        """Test manager initialization."""
        assert len(manager.channel_names) == 0
        assert len(manager.enabled_channels) == 0
    
    @pytest.mark.asyncio
    async def test_add_remove_channel(self, manager, channel_config):
        """Test adding and removing channels."""
        channel = MockChannel("test", channel_config)
        
        manager.add_channel(channel)
        assert "test" in manager.channel_names
        
        removed = manager.remove_channel("test")
        assert removed is True
        assert "test" not in manager.channel_names
        
        # Removing non-existent should return False
        removed = manager.remove_channel("nonexistent")
        assert removed is False
    
    @pytest.mark.asyncio
    async def test_send_alert_single_channel(self, manager, channel_config, sample_alert):
        """Test sending alert through single channel."""
        channel = MockChannel("test", channel_config, should_succeed=True)
        manager.add_channel(channel)
        
        result = await manager.send_alert(sample_alert)
        
        assert result.success is True
        assert result.alert_id == sample_alert.id
        assert result.metadata['channels_succeeded'] == 1
    
    @pytest.mark.asyncio
    async def test_send_alert_multiple_channels(self, manager, channel_config, sample_alert):
        """Test sending alert through multiple channels."""
        channel1 = MockChannel("channel1", channel_config, should_succeed=True)
        channel2 = MockChannel("channel2", channel_config, should_succeed=True)
        
        manager.add_channel(channel1)
        manager.add_channel(channel2)
        
        result = await manager.send_alert(sample_alert)
        
        assert result.success is True
        assert result.metadata['channels_succeeded'] == 2
        assert len(channel1.sent_alerts) == 1
        assert len(channel2.sent_alerts) == 1
    
    @pytest.mark.asyncio
    async def test_send_alert_partial_failure(self, manager, channel_config, sample_alert):
        """Test handling partial channel failures."""
        channel1 = MockChannel("channel1", channel_config, should_succeed=True)
        channel2 = MockChannel("channel2", channel_config, should_succeed=False)
        
        manager.add_channel(channel1)
        manager.add_channel(channel2)
        
        result = await manager.send_alert(sample_alert)
        
        # Should succeed if at least one channel succeeds
        assert result.success is True
        assert result.metadata['channels_succeeded'] == 1
        assert result.metadata['channels_attempted'] == 2
    
    @pytest.mark.asyncio
    async def test_send_alert_all_fail(self, manager, channel_config, sample_alert):
        """Test when all channels fail."""
        channel = MockChannel("test", channel_config, should_succeed=False)
        manager.add_channel(channel)
        
        result = await manager.send_alert(sample_alert)
        
        # Should still succeed due to local fallback
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_send_batch(self, manager, channel_config):
        """Test batch sending."""
        channel = MockChannel("test", channel_config)
        manager.add_channel(channel)
        
        alerts = [
            Alert(
                id=f"alert-{i}",
                rule_id="test-rule",
                source_id="test-source",
                severity=AlertSeverity.INFO,
                title=f"Alert {i}",
                message=f"Message {i}"
            )
            for i in range(5)
        ]
        
        results = await manager.send_batch(alerts)
        
        assert len(results) == 5
        assert all(results.values())
        assert len(channel.sent_alerts) == 5
    
    @pytest.mark.asyncio
    async def test_deduplication(self, sample_alert):
        """Test alert deduplication."""
        manager = AlertManager(
            default_rate_limit_seconds=3600,
            enable_deduplication=True
        )
        channel = MockChannel("test", ChannelConfig(enabled=True))
        manager.add_channel(channel)
        
        # First send should succeed
        result1 = await manager.send_alert(sample_alert)
        assert result1.success is True
        
        # Duplicate send should be rate limited
        result2 = await manager.send_alert(sample_alert)
        assert result2.success is False
        assert "rate limited" in result2.error_message.lower()
    
    def test_get_stats(self, manager, channel_config):
        """Test getting manager statistics."""
        channel = MockChannel("test", channel_config)
        manager.add_channel(channel)
        
        stats = manager.get_stats()
        
        assert stats['channels_configured'] == 1
        assert stats['channels_enabled'] == 1
        assert 'channel_stats' in stats
        assert 'rules_stats' in stats


class TestAlertRulesEngine:
    """Tests for the AlertRulesEngine."""
    
    @pytest.fixture
    def engine(self):
        """Create a fresh rules engine."""
        return AlertRulesEngine()
    
    def test_add_remove_rule(self, engine):
        """Test adding and removing rules."""
        rule = RuleConfig(
            rule_id="test-rule",
            name="Test Rule",
            enabled=True
        )
        
        engine.add_rule(rule)
        assert engine.get_rule("test-rule") is not None
        
        removed = engine.remove_rule("test-rule")
        assert removed is True
        assert engine.get_rule("test-rule") is None
    
    def test_severity_filter(self, engine):
        """Test severity-based filtering."""
        rule = RuleConfig(
            rule_id="severity-rule",
            name="Severity Rule",
            min_severity=AlertSeverity.WARNING,
            enabled=True
        )
        engine.add_rule(rule)
        
        # Info alert should be filtered
        info_alert = Alert(
            id="info-1",
            rule_id="severity-rule",
            source_id="test",
            severity=AlertSeverity.INFO,
            title="Info Alert",
            message="Test"
        )
        assert engine.process_alert(info_alert) is None
        
        # Warning alert should pass
        warning_alert = Alert(
            id="warning-1",
            rule_id="severity-rule",
            source_id="test",
            severity=AlertSeverity.WARNING,
            title="Warning Alert",
            message="Test"
        )
        assert engine.process_alert(warning_alert) is not None
    
    def test_source_filter(self, engine):
        """Test source-based filtering."""
        rule = RuleConfig(
            rule_id="source-rule",
            name="Source Rule",
            include_sources=["allowed-source"],
            enabled=True
        )
        engine.add_rule(rule)
        
        # Disallowed source should be filtered
        bad_alert = Alert(
            id="bad-1",
            rule_id="source-rule",
            source_id="bad-source",
            severity=AlertSeverity.WARNING,
            title="Bad Alert",
            message="Test"
        )
        assert engine.process_alert(bad_alert) is None
        
        # Allowed source should pass
        good_alert = Alert(
            id="good-1",
            rule_id="source-rule",
            source_id="allowed-source",
            severity=AlertSeverity.WARNING,
            title="Good Alert",
            message="Test"
        )
        assert engine.process_alert(good_alert) is not None
    
    def test_keyword_filter(self, engine):
        """Test keyword-based filtering."""
        rule = RuleConfig(
            rule_id="keyword-rule",
            name="Keyword Rule",
            keywords=["important", "urgent"],
            enabled=True
        )
        engine.add_rule(rule)
        
        # Alert without keywords should be filtered
        no_match = Alert(
            id="no-match",
            rule_id="keyword-rule",
            source_id="test",
            severity=AlertSeverity.WARNING,
            title="Regular Alert",
            message="Nothing special here"
        )
        assert engine.process_alert(no_match) is None
        
        # Alert with keyword should pass
        match = Alert(
            id="match",
            rule_id="keyword-rule",
            source_id="test",
            severity=AlertSeverity.WARNING,
            title="Important Alert",
            message="This is urgent!"
        )
        assert engine.process_alert(match) is not None
    
    def test_rate_limiting(self, engine):
        """Test rate limiting per rule."""
        rule = RuleConfig(
            rule_id="rate-rule",
            name="Rate Rule",
            max_alerts_per_hour=2,
            enabled=True
        )
        engine.add_rule(rule)
        
        # First two alerts should pass
        for i in range(2):
            alert = Alert(
                id=f"alert-{i}",
                rule_id="rate-rule",
                source_id="test",
                severity=AlertSeverity.WARNING,
                title=f"Alert {i}",
                message="Test"
            )
            assert engine.process_alert(alert) is not None
        
        # Third alert should be rate limited (no matching rule)
        alert3 = Alert(
            id="alert-3",
            rule_id="rate-rule",
            source_id="test",
            severity=AlertSeverity.WARNING,
            title="Alert 3",
            message="Test"
        )
        assert engine.process_alert(alert3) is None
    
    def test_quiet_hours(self, engine):
        """Test quiet hours with exemption."""
        rule = RuleConfig(
            rule_id="quiet-rule",
            name="Quiet Rule",
            quiet_hours_start=0,
            quiet_hours_end=23,  # All day quiet
            quiet_hours_severity_exemption=AlertSeverity.CRITICAL,
            enabled=True
        )
        engine.add_rule(rule)
        
        # Regular alert should be filtered during quiet hours
        regular = Alert(
            id="regular",
            rule_id="quiet-rule",
            source_id="test",
            severity=AlertSeverity.WARNING,
            title="Regular Alert",
            message="Test"
        )
        assert engine.process_alert(regular) is None
        
        # Critical alert should pass (exempt)
        critical = Alert(
            id="critical",
            rule_id="quiet-rule",
            source_id="test",
            severity=AlertSeverity.CRITICAL,
            title="Critical Alert",
            message="Test"
        )
        assert engine.process_alert(critical) is not None
    
    def test_deduplication(self, engine):
        """Test alert deduplication."""
        rule = RuleConfig(
            rule_id="dedup-rule",
            name="Dedup Rule",
            enabled=True
        )
        engine.add_rule(rule)
        
        alert = Alert(
            id="alert-1",
            rule_id="dedup-rule",
            source_id="test",
            severity=AlertSeverity.WARNING,
            title="Duplicate Alert",
            message="Same content"
        )
        
        # First occurrence should pass
        assert engine.process_alert(alert) is not None
        
        # Duplicate should be filtered
        alert2 = Alert(
            id="alert-2",
            rule_id="dedup-rule",
            source_id="test",
            severity=AlertSeverity.WARNING,
            title="Duplicate Alert",
            message="Same content"
        )
        assert engine.process_alert(alert2) is None
    
    def test_digest_aggregation(self, engine):
        """Test digest aggregation mode."""
        rule = RuleConfig(
            rule_id="digest-rule",
            name="Digest Rule",
            aggregation_mode=AggregationMode.DIGEST,
            digest_interval_minutes=0,  # Immediate for testing
            enabled=True
        )
        engine.add_rule(rule)
        
        # Add alerts
        for i in range(3):
            alert = Alert(
                id=f"digest-alert-{i}",
                rule_id="digest-rule",
                source_id="test",
                severity=AlertSeverity.INFO,
                title=f"Alert {i}",
                message="Test"
            )
            result = engine.process_alert(alert)
            # Individual alerts are suppressed in digest mode
            assert result is None
        
        # Get pending digests (immediate due to 0 interval)
        digests = engine.get_pending_digests()
        assert len(digests) == 1
        assert "3 alerts" in digests[0].title


class TestLocalChannel:
    """Tests for the Local channel."""
    
    @pytest.mark.asyncio
    async def test_local_log_file(self, sample_alert):
        """Test logging to file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as f:
            log_path = Path(f.name)
        
        try:
            config = ChannelConfig(enabled=True, rate_limit_seconds=0)
            channel = LocalChannel(
                name="local",
                config=config,
                log_file=log_path,
                enable_desktop_notifications=False
            )
            
            result = await channel.send(sample_alert)
            
            assert result.success is True
            assert result.metadata['logged_to_file'] is True
            
            # Verify log file contents
            alerts = channel.get_recent_alerts()
            assert len(alerts) == 1
            assert alerts[0]['alert_id'] == sample_alert.id
            
        finally:
            log_path.unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_local_recent_alerts(self, sample_alert):
        """Test retrieving recent alerts."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jsonl') as f:
            log_path = Path(f.name)
        
        try:
            config = ChannelConfig(enabled=True, rate_limit_seconds=0)
            channel = LocalChannel(
                name="local",
                config=config,
                log_file=log_path
            )
            
            # Send multiple alerts
            for i in range(5):
                alert = Alert(
                    id=f"alert-{i}",
                    rule_id="test",
                    source_id="test",
                    severity=AlertSeverity.INFO,
                    title=f"Alert {i}",
                    message="Test"
                )
                await channel.send(alert)
            
            # Get recent alerts with limit
            recent = channel.get_recent_alerts(limit=3)
            assert len(recent) == 3
            
            # Get all
            all_alerts = channel.get_recent_alerts(limit=100)
            assert len(all_alerts) == 5
            
        finally:
            log_path.unlink(missing_ok=True)


class TestDiscordChannel:
    """Tests for Discord channel."""
    
    def test_discord_embed_building(self, sample_alert):
        """Test Discord embed construction."""
        config = ChannelConfig(enabled=True)
        channel = DiscordChannel(
            name="discord",
            config=config,
            webhook_url="https://discord.com/api/webhooks/test"
        )
        
        embed = channel._build_embed(sample_alert)
        
        assert "title" in embed
        assert "description" in embed
        assert "color" in embed
        assert "fields" in embed
        assert embed["color"] == channel.SEVERITY_COLORS[AlertSeverity.WARNING]
    
    def test_discord_severity_emoji(self):
        """Test severity emoji mapping."""
        config = ChannelConfig(enabled=True)
        channel = DiscordChannel(
            name="discord",
            config=config,
            webhook_url="https://test.com"
        )
        
        assert "ℹ️" in channel._build_payload(Alert(
            id="t", rule_id="r", source_id="s",
            severity=AlertSeverity.INFO, title="T", message="M"
        ))['embeds'][0]['title']


class TestSlackChannel:
    """Tests for Slack channel."""
    
    def test_slack_blocks_building(self, sample_alert):
        """Test Slack block construction."""
        config = ChannelConfig(enabled=True)
        channel = SlackChannel(
            name="slack",
            config=config,
            webhook_url="https://hooks.slack.com/test"
        )
        
        blocks = channel._build_blocks(sample_alert)
        
        assert len(blocks) > 0
        assert blocks[0]["type"] == "header"
        
        # Check severity field
        field_block = next((b for b in blocks if b.get("type") == "section" and "fields" in b), None)
        assert field_block is not None


class TestWebhookChannel:
    """Tests for generic webhook channel."""
    
    def test_webhook_payload_building(self, sample_alert):
        """Test webhook payload construction."""
        config = ChannelConfig(enabled=True)
        channel = WebhookChannel(
            name="webhook",
            config=config,
            url="https://example.com/webhook"
        )
        
        payload = channel._build_payload(sample_alert)
        
        assert "alert_id" in payload
        assert "severity" in payload
        assert "title" in payload
        assert payload["alert_id"] == sample_alert.id
    
    def test_webhook_payload_template(self, sample_alert):
        """Test webhook payload with template."""
        config = ChannelConfig(enabled=True)
        template = {
            "event": "alert",
            "data": {
                "id": "{{alert_id}}",
                "level": "{{severity}}"
            }
        }
        channel = WebhookChannel(
            name="webhook",
            config=config,
            url="https://example.com/webhook",
            payload_template=template
        )
        
        payload = channel._build_payload(sample_alert)
        
        assert payload["event"] == "alert"
        assert payload["data"]["id"] == sample_alert.id
        assert payload["data"]["level"] == sample_alert.severity.value
    
    def test_webhook_auth_header(self):
        """Test authentication header."""
        config = ChannelConfig(enabled=True)
        channel = WebhookChannel(
            name="webhook",
            config=config,
            url="https://example.com/webhook",
            auth_token="secret-token",
            auth_header="X-API-Key"
        )
        
        headers = channel._get_headers()
        
        assert "X-API-Key" in headers
        assert headers["X-API-Key"] == "Bearer secret-token"


class TestAlertManagerFromConfig:
    """Tests for creating AlertManager from config."""
    
    def test_from_config_basic(self):
        """Test basic config loading."""
        config = {
            "rate_limit_seconds": 600,
            "enable_deduplication": True,
            "channels": {},
            "rules": []
        }
        
        manager = AlertManager.from_config(config)
        
        assert manager is not None
        assert len(manager.channel_names) == 0
    
    def test_from_config_with_channels(self):
        """Test config with channels."""
        config = {
            "channels": {
                "discord": {
                    "enabled": True,
                    "webhook_url": "https://discord.com/api/webhooks/test",
                    "min_severity": "warning"
                },
                "local": {
                    "enabled": True,
                    "log_file": "/tmp/alerts.log"
                }
            },
            "rules": []
        }
        
        manager = AlertManager.from_config(config)
        
        assert "discord" in manager.channel_names
        assert "local" in manager.channel_names
        
        discord = manager.get_channel("discord")
        assert discord.config.min_severity == "warning"
    
    def test_from_config_with_rules(self):
        """Test config with rules."""
        config = {
            "channels": {},
            "rules": [
                {
                    "rule_id": "test-rule",
                    "name": "Test Rule",
                    "min_severity": "warning",
                    "keywords": ["error", "fail"]
                }
            ]
        }
        
        manager = AlertManager.from_config(config)
        
        stats = manager.get_stats()
        assert stats['rules_stats']['rules_configured'] == 1


# Integration Tests
@pytest.mark.asyncio
async def test_end_to_end_alert_flow():
    """Test complete alert flow from manager to channels."""
    # Setup
    manager = AlertManager()
    
    # Add mock channels
    channel1 = MockChannel("channel1", ChannelConfig(enabled=True), should_succeed=True)
    channel2 = MockChannel("channel2", ChannelConfig(enabled=True), should_succeed=True)
    manager.add_channel(channel1)
    manager.add_channel(channel2)
    
    # Add rule
    rule = RuleConfig(
        rule_id="integration-rule",
        name="Integration Rule",
        min_severity=AlertSeverity.WARNING,
        enabled=True
    )
    manager.add_rule(rule)
    
    # Create and send alert
    alert = Alert(
        id="integration-test",
        rule_id="integration-rule",
        source_id="test-source",
        severity=AlertSeverity.ERROR,
        title="Integration Test Alert",
        message="Testing full flow"
    )
    
    result = await manager.send_alert(alert)
    
    # Verify
    assert result.success is True
    assert len(channel1.sent_alerts) == 1
    assert len(channel2.sent_alerts) == 1
    
    # Check stats
    stats = manager.get_stats()
    assert stats['channels_configured'] == 2
    assert stats['total_delivered'] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
