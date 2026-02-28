"""
Test configuration for Situation Monitor.
"""

import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "benchmark: marks tests as performance benchmarks")


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def temp_dir():
    """Provide a temporary directory for tests."""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def mock_settings(temp_dir):
    """Provide mock settings for testing."""
    from situation_monitor.config.settings import Settings
    
    settings = Settings(
        environment="testing",
        debug=False,
        log_level="ERROR",
        data_dir=temp_dir / "data",
        log_dir=temp_dir / "logs",
        config_dir=temp_dir / "config",
        storage_backend="memory"
    )
    
    settings.ensure_directories()
    return settings


@pytest.fixture
async def clean_storage():
    """Provide a clean storage instance for each test."""
    from situation_monitor.tests.integration.test_e2e import MockStorage
    
    storage = MockStorage()
    await storage.connect()
    yield storage
    await storage.disconnect()


@pytest.fixture
def sample_source_config():
    """Provide a sample source configuration."""
    from situation_monitor.core.models import SourceConfig
    
    return SourceConfig(
        id="test-source",
        name="Test Source",
        type="mock",
        interval_seconds=60,
        enabled=True,
        tags=["test"]
    )


@pytest.fixture
def sample_alert_rules():
    """Provide sample alert rules."""
    from situation_monitor.core.models import AlertRule, AlertSeverity
    
    return [
        AlertRule(
            id="security-rule",
            name="Security Issues",
            keywords=["security", "vulnerability", "exploit"],
            severity=AlertSeverity.WARNING,
            enabled=True,
            cooldown_seconds=3600
        ),
        AlertRule(
            id="error-rule",
            name="Error Detection",
            keywords=["error", "failure", "critical"],
            severity=AlertSeverity.ERROR,
            enabled=True,
            cooldown_seconds=1800
        ),
        AlertRule(
            id="info-rule",
            name="Informational",
            keywords=["update", "release"],
            severity=AlertSeverity.INFO,
            enabled=True,
            cooldown_seconds=7200
        )
    ]


@pytest.fixture
def sample_monitoring_results():
    """Provide sample monitoring results."""
    from situation_monitor.core.models import MonitoringResult
    from datetime import datetime
    
    return [
        MonitoringResult(
            source_id="test-source",
            timestamp=datetime.utcnow(),
            raw_data={"id": 1, "content": "Security vulnerability found in system"},
            content="Security vulnerability found in system",
            title="Security Alert",
            url="https://example.com/1"
        ),
        MonitoringResult(
            source_id="test-source",
            timestamp=datetime.utcnow(),
            raw_data={"id": 2, "content": "New version released with great features"},
            content="New version released with great features",
            title="Release Notes",
            url="https://example.com/2"
        ),
        MonitoringResult(
            source_id="test-source",
            timestamp=datetime.utcnow(),
            raw_data={"id": 3, "content": "Critical error detected in production"},
            content="Critical error detected in production",
            title="Error Report",
            url="https://example.com/3"
        )
    ]


@pytest.fixture
def sample_alerts():
    """Provide sample alerts."""
    from situation_monitor.core.models import Alert, AlertSeverity
    from datetime import datetime
    
    return [
        Alert(
            id="alert-1",
            rule_id="rule-1",
            source_id="source-1",
            severity=AlertSeverity.INFO,
            title="Info Alert",
            message="This is an informational alert",
            timestamp=datetime.utcnow()
        ),
        Alert(
            id="alert-2",
            rule_id="rule-2",
            source_id="source-1",
            severity=AlertSeverity.WARNING,
            title="Warning Alert",
            message="This is a warning alert",
            timestamp=datetime.utcnow()
        ),
        Alert(
            id="alert-3",
            rule_id="rule-3",
            source_id="source-1",
            severity=AlertSeverity.ERROR,
            title="Error Alert",
            message="This is an error alert",
            timestamp=datetime.utcnow()
        ),
        Alert(
            id="alert-4",
            rule_id="rule-4",
            source_id="source-1",
            severity=AlertSeverity.CRITICAL,
            title="Critical Alert",
            message="This is a critical alert",
            timestamp=datetime.utcnow()
        )
    ]


@pytest.fixture
def sample_parsed_situation():
    """Provide a sample parsed situation."""
    from situation_monitor.core.models import ParsedSituation, SourceCategory
    from datetime import datetime
    
    return ParsedSituation(
        summary="Monitoring for security vulnerabilities",
        keywords=["security", "vulnerability", "CVE"],
        entities=["CVE-2024-1234", "Apache", "Log4j"],
        topics=["cybersecurity", "software"],
        time_context="recent",
        urgency="high",
        preferred_categories=[SourceCategory.NEWS, SourceCategory.INDUSTRY],
        preferred_languages=["en"],
        raw_query="recent security vulnerabilities",
        parsed_at=datetime.utcnow()
    )


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Reset settings cache before each test."""
    from situation_monitor.config.settings import get_settings
    get_settings.cache_clear()
    yield


# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)
