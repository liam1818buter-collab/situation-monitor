"""
Tests for Situation Monitor core functionality.
"""

import asyncio
import pytest
from datetime import datetime
from typing import Any, Dict, List

from situation_monitor.core.base import Source, Analyzer, Storage, Notifier
from situation_monitor.core.models import (
    MonitoringResult, 
    Alert, 
    SourceConfig,
    AlertRule,
    AlertSeverity
)
from situation_monitor.core.rate_limiter import TokenBucket, RateLimiter
from situation_monitor.core.retry import retry, RetryError
from situation_monitor.core.utils import generate_id, hash_content, CircularBuffer
from situation_monitor.config.settings import Settings, get_settings


# ============================================================================
# Source Tests
# ============================================================================

class MockSource(Source):
    """Mock implementation of Source for testing."""
    
    def __init__(self, config: SourceConfig, fail_connect: bool = False):
        super().__init__(config)
        self.fetch_count = 0
        self.fail_connect = fail_connect
        self._test_data = [
            {"id": "1", "content": "Test content 1"},
            {"id": "2", "content": "Test content 2"},
        ]
    
    async def fetch(self) -> List[MonitoringResult]:
        self.fetch_count += 1
        return [
            MonitoringResult(
                source_id=self.config.id,
                raw_data=item,
                content=item["content"],
                hash=hash_content(item["content"])
            )
            for item in self._test_data
        ]
    
    async def test_connection(self) -> bool:
        return not self.fail_connect


@pytest.fixture
def mock_source_config():
    return SourceConfig(
        id="test-source",
        name="Test Source",
        type="mock",
        interval_seconds=60
    )


@pytest.mark.asyncio
async def test_source_initialization(mock_source_config):
    """Test source initialization."""
    source = MockSource(mock_source_config)
    assert source.source_id == "test-source"
    assert source.status == "initialized"
    
    initialized = await source.initialize()
    assert initialized is True
    assert source.status == "active"


@pytest.mark.asyncio
async def test_source_fetch(mock_source_config):
    """Test source fetch returns monitoring results."""
    source = MockSource(mock_source_config)
    await source.initialize()
    
    results = await source.fetch()
    assert len(results) == 2
    assert all(isinstance(r, MonitoringResult) for r in results)
    assert results[0].source_id == "test-source"


@pytest.mark.asyncio
async def test_source_connection_test(mock_source_config):
    """Test source connection testing."""
    source_ok = MockSource(mock_source_config, fail_connect=False)
    assert await source_ok.test_connection() is True
    
    source_fail = MockSource(mock_source_config, fail_connect=True)
    assert await source_fail.test_connection() is False


@pytest.mark.asyncio
async def test_source_shutdown(mock_source_config):
    """Test source cleanup."""
    source = MockSource(mock_source_config)
    await source.initialize()
    await source.shutdown()
    assert source.status == "disabled"


# ============================================================================
# Analyzer Tests
# ============================================================================

class MockAnalyzer(Analyzer):
    """Mock implementation of Analyzer for testing."""
    
    async def analyze(self, data: MonitoringResult) -> Dict[str, Any]:
        return {
            "sentiment": "neutral",
            "keywords_found": [],
            "word_count": len(str(data.content).split()) if data.content else 0
        }
    
    async def check_rules(
        self, 
        data: MonitoringResult, 
        rules: List[AlertRule]
    ) -> List[Alert]:
        alerts = []
        for rule in rules:
            if not rule.enabled:
                continue
            
            # Simple keyword matching
            content = str(data.content or "").lower()
            matched = any(kw.lower() in content for kw in rule.keywords)
            
            if matched:
                alerts.append(Alert(
                    id=generate_id("alert", data.source_id, rule.id),
                    rule_id=rule.id,
                    source_id=data.source_id,
                    severity=rule.severity,
                    title=f"Alert: {rule.name}",
                    message=f"Keywords matched in {data.source_id}",
                    data=data
                ))
        return alerts


@pytest.fixture
def sample_result():
    return MonitoringResult(
        source_id="test-source",
        raw_data={"content": "Security alert: vulnerability found"},
        content="Security alert: vulnerability found"
    )


@pytest.fixture
def sample_rules():
    return [
        AlertRule(
            id="security-rule",
            name="Security Alert",
            keywords=["security", "vulnerability"],
            severity=AlertSeverity.WARNING,
            enabled=True
        ),
        AlertRule(
            id="disabled-rule",
            name="Disabled Rule",
            keywords=["test"],
            enabled=False
        )
    ]


@pytest.mark.asyncio
async def test_analyzer_initialization():
    """Test analyzer initialization."""
    analyzer = MockAnalyzer("test-analyzer")
    assert analyzer.name == "test-analyzer"
    
    initialized = await analyzer.initialize()
    assert initialized is True
    assert analyzer._initialized is True


@pytest.mark.asyncio
async def test_analyzer_analyze(sample_result):
    """Test analyzer processing."""
    analyzer = MockAnalyzer("test-analyzer")
    await analyzer.initialize()
    
    result = await analyzer.analyze(sample_result)
    assert "sentiment" in result
    assert "word_count" in result
    assert result["word_count"] > 0


@pytest.mark.asyncio
async def test_analyzer_check_rules(sample_result, sample_rules):
    """Test rule checking."""
    analyzer = MockAnalyzer("test-analyzer")
    
    alerts = await analyzer.check_rules(sample_result, sample_rules)
    
    # Should trigger security-rule (matches "security" and "vulnerability")
    assert len(alerts) == 1
    assert alerts[0].rule_id == "security-rule"
    assert alerts[0].severity == AlertSeverity.WARNING


# ============================================================================
# Storage Tests
# ============================================================================

class MockStorage(Storage):
    """Mock implementation of Storage for testing."""
    
    def __init__(self):
        super().__init__()
        self._results: Dict[str, MonitoringResult] = {}
        self._alerts: Dict[str, Alert] = {}
        self._counter = 0
    
    async def connect(self) -> bool:
        self._connected = True
        return True
    
    async def disconnect(self) -> None:
        self._connected = False
    
    async def save_result(self, result: MonitoringResult) -> str:
        self._counter += 1
        result_id = f"result_{self._counter}"
        self._results[result_id] = result
        return result_id
    
    async def save_alert(self, alert: Alert) -> str:
        self._counter += 1
        alert_id = f"alert_{self._counter}"
        self._alerts[alert_id] = alert
        return alert_id
    
    async def get_results(
        self, 
        source_id=None, 
        since=None, 
        limit=100
    ) -> List[MonitoringResult]:
        results = list(self._results.values())
        if source_id:
            results = [r for r in results if r.source_id == source_id]
        return results[:limit]
    
    async def get_alerts(
        self, 
        acknowledged=None, 
        severity=None, 
        limit=100
    ) -> List[Alert]:
        alerts = list(self._alerts.values())
        if acknowledged is not None:
            alerts = [a for a in alerts if a.acknowledged == acknowledged]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts[:limit]
    
    async def acknowledge_alert(self, alert_id: str) -> bool:
        if alert_id in self._alerts:
            self._alerts[alert_id].acknowledged = True
            return True
        return False


@pytest.mark.asyncio
async def test_storage_connection():
    """Test storage connection."""
    storage = MockStorage()
    assert storage.is_connected is False
    
    connected = await storage.connect()
    assert connected is True
    assert storage.is_connected is True
    
    await storage.disconnect()
    assert storage.is_connected is False


@pytest.mark.asyncio
async def test_storage_save_and_retrieve(sample_result):
    """Test saving and retrieving results."""
    storage = MockStorage()
    await storage.connect()
    
    result_id = await storage.save_result(sample_result)
    assert result_id is not None
    
    results = await storage.get_results()
    assert len(results) == 1
    assert results[0].source_id == "test-source"


@pytest.mark.asyncio
async def test_storage_alert_management(sample_result):
    """Test alert storage and acknowledgment."""
    storage = MockStorage()
    await storage.connect()
    
    alert = Alert(
        id="test-alert",
        rule_id="rule-1",
        source_id="test-source",
        severity=AlertSeverity.ERROR,
        title="Test Alert",
        message="Test message",
        data=sample_result
    )
    
    alert_id = await storage.save_alert(alert)
    assert alert_id is not None
    
    # Check unacknowledged alerts
    unack = await storage.get_alerts(acknowledged=False)
    assert len(unack) == 1
    
    # Acknowledge
    success = await storage.acknowledge_alert(alert_id)
    assert success is True
    
    # Should be no more unacknowledged
    unack = await storage.get_alerts(acknowledged=False)
    assert len(unack) == 0


# ============================================================================
# Notifier Tests
# ============================================================================

class MockNotifier(Notifier):
    """Mock implementation of Notifier for testing."""
    
    def __init__(self, name: str, fail_send: bool = False):
        super().__init__(name)
        self.sent_alerts: List[Alert] = []
        self.fail_send = fail_send
    
    async def send(self, alert: Alert) -> bool:
        if self.fail_send:
            return False
        self.sent_alerts.append(alert)
        return True
    
    async def send_batch(self, alerts: List[Alert]) -> Dict[str, bool]:
        results = {}
        for alert in alerts:
            results[alert.id] = await self.send(alert)
        return results


@pytest.mark.asyncio
async def test_notifier_send(sample_result):
    """Test sending notifications."""
    notifier = MockNotifier("test-notifier")
    
    alert = Alert(
        id="alert-1",
        rule_id="rule-1",
        source_id="test-source",
        severity=AlertSeverity.INFO,
        title="Test",
        message="Test message",
        data=sample_result
    )
    
    success = await notifier.send(alert)
    assert success is True
    assert len(notifier.sent_alerts) == 1


@pytest.mark.asyncio
async def test_notifier_batch_send(sample_result):
    """Test batch sending."""
    notifier = MockNotifier("test-notifier")
    
    alerts = [
        Alert(
            id=f"alert-{i}",
            rule_id="rule-1",
            source_id="test-source",
            severity=AlertSeverity.INFO,
            title=f"Alert {i}",
            message="Test"
        )
        for i in range(3)
    ]
    
    results = await notifier.send_batch(alerts)
    assert len(results) == 3
    assert all(results.values())
    assert len(notifier.sent_alerts) == 3


@pytest.mark.asyncio
async def test_notifier_enable_disable():
    """Test notifier enable/disable."""
    notifier = MockNotifier("test-notifier")
    assert notifier.enabled is True
    
    notifier.disable()
    assert notifier.enabled is False
    
    notifier.enable()
    assert notifier.enabled is True


# ============================================================================
# Rate Limiter Tests
# ============================================================================

@pytest.mark.asyncio
async def test_token_bucket():
    """Test token bucket rate limiting."""
    bucket = TokenBucket(rate=10, capacity=5)  # 10 tokens/sec, max 5 burst
    
    # Should be able to acquire burst immediately
    for _ in range(5):
        assert await bucket.acquire() is True
    
    # Bucket should be empty now
    assert await bucket.acquire() is False
    
    # Wait and try again
    await asyncio.sleep(0.2)
    assert await bucket.acquire() is True


@pytest.mark.asyncio
async def test_rate_limiter():
    """Test multi-bucket rate limiter."""
    limiter = RateLimiter()
    limiter.create_bucket("api", requests_per_minute=60, burst=5)
    
    # Use burst allowance
    for _ in range(5):
        assert await limiter.acquire("api") is True
    
    # Should be rate limited now
    assert await limiter.acquire("api") is False


@pytest.mark.asyncio
async def test_rate_limiter_wait():
    """Test rate limiter wait functionality."""
    limiter = RateLimiter()
    limiter.create_bucket("slow", requests_per_minute=60, burst=1)
    
    # Use the one token
    await limiter.acquire("slow")
    
    # This should wait and eventually succeed
    start = asyncio.get_event_loop().time()
    await limiter.wait("slow")
    elapsed = asyncio.get_event_loop().time() - start
    
    assert elapsed > 0.5  # Should have waited at least 0.5 seconds


# ============================================================================
# Retry Tests
# ============================================================================

@pytest.mark.asyncio
async def test_retry_success():
    """Test retry with eventual success."""
    call_count = 0
    
    @retry(max_attempts=3, base_delay=0.1)
    async def flaky_function():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("Temporary failure")
        return "success"
    
    result = await flaky_function()
    assert result == "success"
    assert call_count == 2


@pytest.mark.asyncio
async def test_retry_exhausted():
    """Test retry with all attempts exhausted."""
    @retry(max_attempts=2, base_delay=0.1)
    async def always_fails():
        raise ConnectionError("Always fails")
    
    with pytest.raises(RetryError):
        await always_fails()


@pytest.mark.asyncio
async def test_retry_with_should_retry():
    """Test retry with custom should_retry function."""
    call_count = 0
    
    def should_retry(exc):
        return isinstance(exc, ValueError)
    
    @retry(max_attempts=3, base_delay=0.1, should_retry=should_retry)
    async def selective_retry():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("Should retry")
        return "success"
    
    result = await selective_retry()
    assert result == "success"
    assert call_count == 2


# ============================================================================
# Utility Tests
# ============================================================================

def test_generate_id():
    """Test ID generation."""
    id1 = generate_id("part1", "part2", "part3")
    id2 = generate_id("part1", "part2", "part3")
    id3 = generate_id("different", "parts")
    
    assert len(id1) == 16
    assert id1 == id2  # Deterministic
    assert id1 != id3  # Different input = different output


def test_hash_content():
    """Test content hashing."""
    hash1 = hash_content("test content")
    hash2 = hash_content("test content")
    hash3 = hash_content("different content")
    
    assert len(hash1) == 64  # SHA256 hex
    assert hash1 == hash2  # Deterministic
    assert hash1 != hash3  # Different content = different hash


def test_circular_buffer():
    """Test circular buffer."""
    buffer = CircularBuffer(size=3)
    
    buffer.add("a")
    buffer.add("b")
    buffer.add("c")
    
    assert len(buffer) == 3
    assert list(buffer.get_all()) == ["a", "b", "c"]
    
    buffer.add("d")  # Should overwrite "a"
    assert list(buffer.get_all()) == ["b", "c", "d"]
    assert "a" not in buffer
    assert "d" in buffer


# ============================================================================
# Settings Tests
# ============================================================================

def test_settings_defaults():
    """Test default settings values."""
    settings = Settings()
    
    assert settings.app_name == "Situation Monitor"
    assert settings.debug is False
    assert settings.environment == "development"
    assert settings.log_level == "INFO"


def test_settings_validation():
    """Test settings validation."""
    # Valid log level
    settings = Settings(log_level="debug")
    assert settings.log_level == "DEBUG"
    
    # Invalid log level should raise
    with pytest.raises(ValueError):
        Settings(log_level="invalid")
    
    # Invalid environment should raise
    with pytest.raises(ValueError):
        Settings(environment="invalid")


def test_settings_paths():
    """Test path configuration."""
    settings = Settings(data_dir="./test_data")
    
    # Paths should be resolved
    assert settings.data_dir.is_absolute()


def test_is_production_development():
    """Test environment checks."""
    dev_settings = Settings(environment="development")
    prod_settings = Settings(environment="production")
    
    assert dev_settings.is_development() is True
    assert dev_settings.is_production() is False
    
    assert prod_settings.is_development() is False
    assert prod_settings.is_production() is True


# ============================================================================
# Model Tests
# ============================================================================

def test_source_config_validation():
    """Test source config validation."""
    # Valid config
    config = SourceConfig(
        id="valid-source-id",
        name="Valid Source",
        type="rss"
    )
    assert config.id == "valid-source-id"
    
    # Invalid ID
    with pytest.raises(ValueError):
        SourceConfig(
            id="invalid id with spaces!",
            name="Invalid",
            type="rss"
        )


def test_alert_creation():
    """Test alert model."""
    alert = Alert(
        id="alert-1",
        rule_id="rule-1",
        source_id="source-1",
        severity=AlertSeverity.CRITICAL,
        title="Critical Alert",
        message="Something is wrong"
    )
    
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.acknowledged is False
    
    # Test serialization
    alert_dict = alert.model_dump()
    assert alert_dict["severity"] == "critical"


def test_monitoring_result():
    """Test monitoring result model."""
    result = MonitoringResult(
        source_id="test-source",
        raw_data={"key": "value"},
        content="Test content",
        title="Test Title",
        hash="abc123"
    )
    
    assert result.source_id == "test-source"
    assert result.content == "Test content"
    assert result.timestamp is not None
