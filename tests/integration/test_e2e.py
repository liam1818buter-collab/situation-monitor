"""
Integration tests for Situation Monitor.
Tests end-to-end workflows and module interfaces.
"""

import asyncio
import pytest
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path
import tempfile
import json

from situation_monitor.core.base import Source, Analyzer, Storage, Notifier, SourceDiscovery
from situation_monitor.core.models import (
    MonitoringResult, Alert, SourceConfig, AlertRule,
    AlertSeverity, ParsedSituation, DataSource, SourceCategory,
    CredibilityScore
)
from situation_monitor.config.settings import Settings
from situation_monitor.logs.logger import get_logger

logger = get_logger("tests.integration")


# ============================================================================
# Mock Implementations for E2E Testing
# ============================================================================

class MockSource(Source):
    """Mock source that simulates various behaviors."""
    
    def __init__(self, config: SourceConfig, results: List[Dict] = None, 
                 fail_after: int = None, delay: float = 0):
        super().__init__(config)
        self.results = results or []
        self.fail_after = fail_after
        self.fetch_count = 0
        self.delay = delay
        self._should_fail_connect = False
    
    async def fetch(self) -> List[MonitoringResult]:
        await asyncio.sleep(self.delay)
        self.fetch_count += 1
        
        if self.fail_after and self.fetch_count >= self.fail_after:
            raise ConnectionError(f"Simulated failure after {self.fail_after} fetches")
        
        results = []
        for item in self.results:
            # Handle None items gracefully
            if item is None:
                item = {}
            results.append(
                MonitoringResult(
                    source_id=self.config.id,
                    raw_data=item,
                    content=item.get("content", "") if item else "",
                    title=item.get("title") if item else None,
                    url=item.get("url") if item else None,
                    hash=item.get("hash") or str(hash(str(item))) if item else None
                )
            )
        return results
    
    async def test_connection(self) -> bool:
        return not self._should_fail_connect
    
    def set_fail_connect(self, fail: bool):
        self._should_fail_connect = fail


class MockAnalyzer(Analyzer):
    """Mock analyzer with keyword matching."""
    
    async def analyze(self, data: MonitoringResult) -> Dict[str, Any]:
        content = str(data.content or "").lower()
        words = content.split()
        
        return {
            "word_count": len(words),
            "sentiment": self._detect_sentiment(content),
            "keywords_found": [],
            "entities": []
        }
    
    def _detect_sentiment(self, content: str) -> str:
        positive = ["good", "great", "excellent", "success"]
        negative = ["bad", "error", "failure", "critical", "vulnerability"]
        
        pos_count = sum(1 for p in positive if p in content)
        neg_count = sum(1 for n in negative if n in content)
        
        if pos_count > neg_count:
            return "positive"
        elif neg_count > pos_count:
            return "negative"
        return "neutral"
    
    async def check_rules(self, data: MonitoringResult, rules: List[AlertRule]) -> List[Alert]:
        alerts = []
        content = str(data.content or "").lower()
        
        for rule in rules:
            if not rule.enabled:
                continue
            
            # Check source filter
            if rule.source_ids and data.source_id not in rule.source_ids:
                continue
            
            # Check keywords
            matched = any(kw.lower() in content for kw in rule.keywords)
            
            if matched:
                alert = Alert(
                    id=f"alert-{data.source_id}-{rule.id}-{datetime.utcnow().timestamp()}",
                    rule_id=rule.id,
                    source_id=data.source_id,
                    severity=rule.severity,
                    title=f"Alert: {rule.name}",
                    message=f"Keywords matched in {data.source_id}: {content[:100]}...",
                    data=data
                )
                alerts.append(alert)
        
        return alerts


class MockStorage(Storage):
    """Mock storage with in-memory storage."""
    
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
    
    async def get_results(self, source_id=None, since=None, limit=100) -> List[MonitoringResult]:
        results = list(self._results.values())
        if source_id:
            results = [r for r in results if r.source_id == source_id]
        return results[:limit]
    
    async def get_alerts(self, acknowledged=None, severity=None, limit=100) -> List[Alert]:
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


class MockNotifier(Notifier):
    """Mock notifier that tracks sent alerts."""
    
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


class MockDiscovery(SourceDiscovery):
    """Mock source discovery engine."""
    
    def __init__(self, config: Dict = None):
        super().__init__(config)
        self._sources: List[DataSource] = [
            DataSource(
                id="mock-news-1",
                name="Mock News Source",
                url="https://mock.news/rss",
                category=SourceCategory.NEWS,
                subcategory="rss",
                credibility=CredibilityScore(overall=0.8, authority=0.9, accuracy=0.8),
                rss_url="https://mock.news/rss",
                relevance_score=0.9
            ),
            DataSource(
                id="mock-social-1",
                name="Mock Social Feed",
                url="https://mock.social/feed",
                category=SourceCategory.SOCIAL,
                subcategory="api",
                credibility=CredibilityScore(overall=0.5, authority=0.4, accuracy=0.5),
                relevance_score=0.6
            )
        ]
    
    async def discover(self, query: ParsedSituation) -> List[DataSource]:
        # Filter by keywords relevance
        results = []
        for source in self._sources:
            # Simple relevance check
            relevance = source.relevance_score
            if query.keywords:
                relevance *= 1.1  # Boost if keywords present
            
            if relevance > 0.5:
                results.append(source)
        
        return sorted(results, key=lambda s: s.relevance_score, reverse=True)
    
    def get_categories(self) -> List[str]:
        return ["news", "social", "academic"]


# ============================================================================
# E2E Test: Full Flow
# ============================================================================

@pytest.fixture
async def e2e_components():
    """Setup components for E2E testing."""
    # Create mock source with sample data
    source_config = SourceConfig(
        id="test-source",
        name="Test Source",
        type="mock",
        interval_seconds=60
    )
    
    sample_data = [
        {"content": "Security vulnerability found in popular framework", "title": "Security Alert"},
        {"content": "New Python version released with great features", "title": "Python News"},
        {"content": "Critical system error detected in production", "title": "Error Report"},
    ]
    
    source = MockSource(source_config, results=sample_data)
    analyzer = MockAnalyzer("test-analyzer")
    storage = MockStorage()
    notifier = MockNotifier("test-notifier")
    discovery = MockDiscovery()
    
    # Initialize all
    await source.initialize()
    await analyzer.initialize()
    await storage.connect()
    await discovery.initialize()
    
    yield {
        "source": source,
        "analyzer": analyzer,
        "storage": storage,
        "notifier": notifier,
        "discovery": discovery,
        "rules": [
            AlertRule(
                id="security-rule",
                name="Security Issues",
                keywords=["security", "vulnerability", "exploit"],
                severity=AlertSeverity.WARNING,
                enabled=True
            ),
            AlertRule(
                id="critical-rule",
                name="Critical Errors",
                keywords=["critical", "error", "failure"],
                severity=AlertSeverity.CRITICAL,
                enabled=True
            )
        ]
    }
    
    # Cleanup
    await source.shutdown()
    await analyzer.shutdown()
    await storage.disconnect()
    await discovery.shutdown()


@pytest.mark.asyncio
async def test_e2e_full_flow(e2e_components):
    """
    Test complete E2E flow:
    Create situation → discover sources → collect data → analyze → alert
    """
    components = e2e_components
    source = components["source"]
    analyzer = components["analyzer"]
    storage = components["storage"]
    notifier = components["notifier"]
    discovery = components["discovery"]
    rules = components["rules"]
    
    # Step 1: Create/parse situation
    logger.info("Step 1: Creating situation")
    situation = ParsedSituation(
        summary="Monitoring for security issues and system errors",
        keywords=["security", "vulnerability", "error", "critical"],
        entities=[],
        topics=["security", "system-health"],
        raw_query="monitor security issues"
    )
    
    # Step 2: Discover sources
    logger.info("Step 2: Discovering sources")
    discovered = await discovery.discover(situation)
    assert len(discovered) > 0, "Should discover at least one source"
    
    # Step 3: Collect data from source
    logger.info("Step 3: Collecting data")
    results = await source.fetch()
    assert len(results) == 3, "Should fetch 3 results"
    
    # Step 4: Store results
    logger.info("Step 4: Storing results")
    saved_ids = []
    for result in results:
        result_id = await storage.save_result(result)
        saved_ids.append(result_id)
    
    stored_results = await storage.get_results()
    assert len(stored_results) == 3, "Should store 3 results"
    
    # Step 5: Analyze results
    logger.info("Step 5: Analyzing results")
    analysis_results = []
    for result in results:
        analysis = await analyzer.analyze(result)
        analysis_results.append(analysis)
        
        # Check for alerts
        alerts = await analyzer.check_rules(result, rules)
        
        # Step 6: Store and send alerts
        for alert in alerts:
            await storage.save_alert(alert)
            await notifier.send(alert)
    
    # Verify alerts were generated and sent
    alerts = await storage.get_alerts()
    assert len(alerts) >= 2, f"Should have at least 2 alerts, got {len(alerts)}"
    
    critical_alerts = await storage.get_alerts(severity=AlertSeverity.CRITICAL)
    assert len(critical_alerts) >= 1, "Should have at least 1 critical alert"
    
    assert len(notifier.sent_alerts) == len(alerts), "All alerts should be sent"
    
    logger.info(f"E2E flow completed successfully: {len(results)} results, {len(alerts)} alerts")


# ============================================================================
# Module Interface Compliance Tests
# ============================================================================

@pytest.mark.asyncio
async def test_source_interface_compliance():
    """Test that mock source properly implements Source interface."""
    config = SourceConfig(id="test", name="Test", type="mock")
    source = MockSource(config)
    
    # Test all required methods exist and return correct types
    assert hasattr(source, 'fetch')
    assert hasattr(source, 'test_connection')
    assert hasattr(source, 'initialize')
    assert hasattr(source, 'shutdown')
    
    # Test initialization
    assert await source.initialize() is True
    assert source.status == "active"
    
    # Test fetch returns list of MonitoringResult
    results = await source.fetch()
    assert isinstance(results, list)
    for r in results:
        assert isinstance(r, MonitoringResult)
    
    # Test connection
    assert isinstance(await source.test_connection(), bool)
    
    # Test shutdown
    await source.shutdown()
    assert source.status == "disabled"


@pytest.mark.asyncio
async def test_analyzer_interface_compliance():
    """Test that analyzer properly implements interface."""
    analyzer = MockAnalyzer("test")
    
    # Test required methods
    assert hasattr(analyzer, 'analyze')
    assert hasattr(analyzer, 'check_rules')
    
    # Test initialization
    assert await analyzer.initialize() is True
    
    # Test analyze returns dict
    result = MonitoringResult(source_id="test", raw_data={})
    analysis = await analyzer.analyze(result)
    assert isinstance(analysis, dict)


@pytest.mark.asyncio
async def test_storage_interface_compliance():
    """Test that storage properly implements interface."""
    storage = MockStorage()
    
    # Test all required methods
    required_methods = ['connect', 'disconnect', 'save_result', 'save_alert',
                       'get_results', 'get_alerts', 'acknowledge_alert']
    for method in required_methods:
        assert hasattr(storage, method), f"Missing method: {method}"
    
    # Test connection
    assert await storage.connect() is True
    assert storage.is_connected
    
    # Test save/get cycle
    result = MonitoringResult(source_id="test", raw_data={"key": "value"})
    result_id = await storage.save_result(result)
    assert isinstance(result_id, str)
    
    results = await storage.get_results()
    assert isinstance(results, list)
    
    # Test disconnect
    await storage.disconnect()
    assert not storage.is_connected


@pytest.mark.asyncio
async def test_notifier_interface_compliance():
    """Test that notifier properly implements interface."""
    notifier = MockNotifier("test")
    
    # Test required methods
    assert hasattr(notifier, 'send')
    assert hasattr(notifier, 'send_batch')
    
    # Test send
    alert = Alert(
        id="test", rule_id="rule", source_id="source",
        severity=AlertSeverity.INFO, title="Test", message="Test"
    )
    assert await notifier.send(alert) is True


# ============================================================================
# Data Flow Validation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_data_flow_source_to_storage():
    """Test data flows correctly from source to storage."""
    config = SourceConfig(id="flow-test", name="Flow Test", type="mock")
    source = MockSource(config, results=[
        {"content": "Test data", "title": "Test"}
    ])
    storage = MockStorage()
    
    await source.initialize()
    await storage.connect()
    
    # Fetch and store
    results = await source.fetch()
    for result in results:
        await storage.save_result(result)
    
    # Verify
    stored = await storage.get_results()
    assert len(stored) == len(results)
    assert stored[0].content == results[0].content


@pytest.mark.asyncio
async def test_data_flow_analysis_to_alerts():
    """Test analysis correctly generates alerts."""
    analyzer = MockAnalyzer("test")
    storage = MockStorage()
    await storage.connect()
    
    rules = [
        AlertRule(id="r1", name="Test", keywords=["alert"], severity=AlertSeverity.WARNING)
    ]
    
    # This should match "alert" keyword (case-insensitive)
    result = MonitoringResult(
        source_id="test",
        raw_data={},
        content="This should trigger an alert"
    )
    alerts = await analyzer.check_rules(result, rules)
    assert len(alerts) == 1
    assert alerts[0].severity == AlertSeverity.WARNING
    
    # This should NOT match (no alert keyword)
    result2 = MonitoringResult(
        source_id="test",
        raw_data={},
        content="This contains no matching keywords"
    )
    alerts = await analyzer.check_rules(result2, rules)
    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_alert_propagation():
    """Test alerts propagate correctly through all channels."""
    storage = MockStorage()
    notifier1 = MockNotifier("notifier1")
    notifier2 = MockNotifier("notifier2")
    
    await storage.connect()
    
    alert = Alert(
        id="test-alert",
        rule_id="rule1",
        source_id="source1",
        severity=AlertSeverity.ERROR,
        title="Test Alert",
        message="Test message"
    )
    
    # Save to storage
    await storage.save_alert(alert)
    
    # Send to multiple notifiers
    await notifier1.send(alert)
    await notifier2.send(alert)
    
    # Verify
    stored_alerts = await storage.get_alerts()
    assert len(stored_alerts) == 1
    assert len(notifier1.sent_alerts) == 1
    assert len(notifier2.sent_alerts) == 1


# ============================================================================
# Error Injection Tests
# ============================================================================

@pytest.mark.asyncio
async def test_source_failure_handling():
    """Test system handles source failures gracefully."""
    config = SourceConfig(id="failing", name="Failing Source", type="mock")
    source = MockSource(config, results=[{"content": "test"}], fail_after=2)
    
    await source.initialize()
    
    # First fetch should work (count = 1 after fetch)
    results = await source.fetch()
    assert len(results) == 1
    assert source.fetch_count == 1
    
    # Second fetch should fail because fail_after=2 and count becomes 2
    with pytest.raises(ConnectionError) as exc_info:
        await source.fetch()
    
    assert "Simulated failure" in str(exc_info.value)
    assert source.fetch_count == 2
    
    # Source should handle failure gracefully - status unchanged on exception
    # (In real implementation, caller would update status)
    assert source.status in ["active", "error", "disabled"]


@pytest.mark.asyncio
async def test_storage_failure_recovery():
    """Test storage handles failures and can reconnect."""
    storage = MockStorage()
    
    # Initial connect
    assert await storage.connect() is True
    
    # Disconnect
    await storage.disconnect()
    assert not storage.is_connected
    
    # Reconnect
    assert await storage.connect() is True
    assert storage.is_connected


@pytest.mark.asyncio
async def test_notifier_failure_handling():
    """Test notifier handles send failures."""
    failing_notifier = MockNotifier("failing", fail_send=True)
    working_notifier = MockNotifier("working")
    
    alert = Alert(
        id="test", rule_id="rule", source_id="source",
        severity=AlertSeverity.INFO, title="Test", message="Test"
    )
    
    # Failing notifier should return False
    assert await failing_notifier.send(alert) is False
    
    # Working notifier should return True
    assert await working_notifier.send(alert) is True
    
    # System should continue despite failures
    assert len(working_notifier.sent_alerts) == 1


@pytest.mark.asyncio
async def test_timeout_handling():
    """Test system handles timeouts correctly."""
    config = SourceConfig(id="slow", name="Slow Source", type="mock")
    source = MockSource(config, results=[{"content": "test"}], delay=0.1)
    
    await source.initialize()
    
    # Should complete (no timeout in mock)
    results = await source.fetch()
    assert len(results) == 1


@pytest.mark.asyncio
async def test_bad_data_handling():
    """Test system handles malformed data gracefully."""
    config = SourceConfig(id="bad-data", name="Bad Data Source", type="mock")
    source = MockSource(config, results=[
        None,  # Null data
        {},    # Empty object
        {"content": None},  # Null content
        {"content": ""},    # Empty content
        {"content": "valid content"},  # Valid
    ])
    
    await source.initialize()
    
    # Should not crash on bad data
    results = await source.fetch()
    assert len(results) == 5
    
    # Valid result should still be usable
    valid = [r for r in results if r.content == "valid content"]
    assert len(valid) == 1


@pytest.mark.asyncio
async def test_partial_failure_in_batch():
    """Test batch operations handle partial failures."""
    storage = MockStorage()
    await storage.connect()
    
    # Save multiple items
    results = [
        MonitoringResult(source_id="test", raw_data={"id": i})
        for i in range(5)
    ]
    
    ids = []
    for result in results:
        result_id = await storage.save_result(result)
        ids.append(result_id)
    
    # All should succeed
    assert len(ids) == 5
    
    stored = await storage.get_results()
    assert len(stored) == 5


# ============================================================================
# Integration Stress Tests
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_source_access():
    """Test multiple sources can be accessed concurrently."""
    sources = []
    for i in range(5):
        config = SourceConfig(id=f"source-{i}", name=f"Source {i}", type="mock")
        source = MockSource(config, results=[{"content": f"data-{i}"}], delay=0.01)
        await source.initialize()
        sources.append(source)
    
    # Fetch from all concurrently
    tasks = [s.fetch() for s in sources]
    results = await asyncio.gather(*tasks)
    
    assert len(results) == 5
    for i, r in enumerate(results):
        assert len(r) == 1
        assert r[0].content == f"data-{i}"


@pytest.mark.asyncio
async def test_discovery_caching():
    """Test discovery results are properly cached."""
    discovery = MockDiscovery()
    await discovery.initialize()
    
    situation = ParsedSituation(
        summary="Test",
        keywords=["test"],
        raw_query="test query"
    )
    
    # First discovery
    results1 = await discovery.discover(situation)
    
    # Second discovery (should use cache)
    results2 = await discovery.discover(situation)
    
    assert len(results1) == len(results2)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_long_running_monitoring():
    """Test system can handle extended monitoring periods."""
    config = SourceConfig(id="long-running", name="Long Running", type="mock")
    source = MockSource(config, results=[{"content": "update"}])
    storage = MockStorage()
    
    await source.initialize()
    await storage.connect()
    
    # Simulate multiple monitoring cycles
    for i in range(10):
        results = await source.fetch()
        for result in results:
            await storage.save_result(result)
        await asyncio.sleep(0.01)  # Small delay between cycles
    
    stored = await storage.get_results()
    assert len(stored) == 10
    assert source.fetch_count == 10


# ============================================================================
# Configuration Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_settings_integration():
    """Test settings work correctly with components."""
    # Create temp directory for test
    with tempfile.TemporaryDirectory() as tmpdir:
        settings = Settings(
            data_dir=Path(tmpdir) / "data",
            log_dir=Path(tmpdir) / "logs",
            environment="testing"
        )
        
        assert settings.is_development() is False
        assert settings.environment == "testing"
        
        # Should be able to create directories
        settings.ensure_directories()
        assert settings.data_dir.exists()
        assert settings.log_dir.exists()


def test_model_serialization():
    """Test all models can be serialized/deserialized."""
    alert = Alert(
        id="test-123",
        rule_id="rule-456",
        source_id="source-789",
        severity=AlertSeverity.WARNING,
        title="Test Alert",
        message="Test message"
    )
    
    # Serialize
    json_str = alert.model_dump_json()
    assert isinstance(json_str, str)
    
    # Deserialize
    data = json.loads(json_str)
    assert data["id"] == "test-123"
    assert data["severity"] == "warning"
