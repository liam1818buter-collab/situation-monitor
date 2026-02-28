"""
Tests for configuration management.
"""

import os
import pytest
import tempfile
from pathlib import Path

from situation_monitor.config.yaml_loader import YamlConfigLoader, create_default_configs
from situation_monitor.config.settings import Settings, reload_settings
from situation_monitor.core.models import SourceConfig, AlertRule, AlertSeverity


# ============================================================================
# YAML Config Loader Tests
# ============================================================================

@pytest.fixture
def temp_config_dir():
    """Create a temporary config directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_sources_yaml(temp_config_dir):
    """Create a sample sources.yaml file."""
    content = """
sources:
  - id: test-rss
    name: Test RSS Feed
    type: rss
    url: https://example.com/feed.xml
    interval_seconds: 300
    enabled: true
    tags:
      - test
      - rss
  - id: test-api
    name: Test API
    type: api
    url: https://api.example.com/data
    interval_seconds: 60
    enabled: false
"""
    filepath = temp_config_dir / "sources.yaml"
    filepath.write_text(content)
    return filepath


@pytest.fixture
def sample_rules_yaml(temp_config_dir):
    """Create a sample rules.yaml file."""
    content = """
rules:
  - id: security-rule
    name: Security Alerts
    source_ids:
      - test-rss
    keywords:
      - security
      - vulnerability
    severity: warning
    enabled: true
    cooldown_seconds: 3600
"""
    filepath = temp_config_dir / "rules.yaml"
    filepath.write_text(content)
    return filepath


class TestYamlConfigLoader:
    """Tests for YAML configuration loading."""
    
    def test_load_sources(self, temp_config_dir, sample_sources_yaml):
        """Test loading source configurations."""
        loader = YamlConfigLoader(temp_config_dir)
        sources = loader.load_sources()
        
        assert len(sources) == 2
        
        # Check first source
        rss = sources[0]
        assert isinstance(rss, SourceConfig)
        assert rss.id == "test-rss"
        assert rss.name == "Test RSS Feed"
        assert rss.type == "rss"
        assert rss.enabled is True
        assert "test" in rss.tags
    
    def test_load_rules(self, temp_config_dir, sample_rules_yaml):
        """Test loading alert rules."""
        loader = YamlConfigLoader(temp_config_dir)
        rules = loader.load_rules()
        
        assert len(rules) == 1
        
        rule = rules[0]
        assert isinstance(rule, AlertRule)
        assert rule.id == "security-rule"
        assert rule.severity == AlertSeverity.WARNING
        assert "security" in rule.keywords
        assert rule.source_ids == ["test-rss"]
    
    def test_get_source_by_id(self, temp_config_dir, sample_sources_yaml):
        """Test retrieving source by ID."""
        loader = YamlConfigLoader(temp_config_dir)
        loader.load_sources()
        
        source = loader.get_source("test-rss")
        assert source is not None
        assert source.name == "Test RSS Feed"
        
        missing = loader.get_source("nonexistent")
        assert missing is None
    
    def test_get_rule_by_id(self, temp_config_dir, sample_rules_yaml):
        """Test retrieving rule by ID."""
        loader = YamlConfigLoader(temp_config_dir)
        loader.load_rules()
        
        rule = loader.get_rule("security-rule")
        assert rule is not None
        assert rule.name == "Security Alerts"
    
    def test_load_missing_file(self, temp_config_dir):
        """Test loading from non-existent file."""
        loader = YamlConfigLoader(temp_config_dir)
        
        # Should return empty list, not raise
        sources = loader.load_sources()
        assert sources == []
        
        rules = loader.load_rules()
        assert rules == []
    
    def test_profile_specific_config(self, temp_config_dir):
        """Test loading profile-specific configuration."""
        # Create production profile config
        prod_dir = temp_config_dir / "production"
        prod_dir.mkdir()
        
        prod_sources = prod_dir / "sources.yaml"
        prod_sources.write_text("""
sources:
  - id: prod-source
    name: Production Source
    type: api
    enabled: true
""")
        
        loader = YamlConfigLoader(temp_config_dir)
        loader._profile = "production"
        
        sources = loader.load_sources()
        assert len(sources) == 1
        assert sources[0].id == "prod-source"
    
    def test_save_sources(self, temp_config_dir):
        """Test saving sources to YAML."""
        loader = YamlConfigLoader(temp_config_dir)
        
        sources = [
            SourceConfig(
                id="save-test",
                name="Save Test Source",
                type="rss",
                url="https://test.com",
                interval_seconds=120,
                enabled=True,
                tags=["test"]
            )
        ]
        
        loader.save_sources(sources)
        
        # Verify file was created
        filepath = temp_config_dir / "sources.yaml"
        assert filepath.exists()
        
        # Reload and verify
        loader2 = YamlConfigLoader(temp_config_dir)
        loaded = loader2.load_sources()
        assert len(loaded) == 1
        assert loaded[0].id == "save-test"
    
    def test_save_rules(self, temp_config_dir):
        """Test saving rules to YAML."""
        loader = YamlConfigLoader(temp_config_dir)
        
        rules = [
            AlertRule(
                id="save-rule",
                name="Save Test Rule",
                keywords=["test"],
                severity=AlertSeverity.INFO,
                enabled=True
            )
        ]
        
        loader.save_rules(rules)
        
        # Reload and verify
        loaded = loader.load_rules()
        assert len(loaded) == 1
        assert loaded[0].id == "save-rule"
    
    def test_invalid_source_handling(self, temp_config_dir):
        """Test graceful handling of invalid source data."""
        # Create YAML with one valid and one invalid source
        content = """
sources:
  - id: valid-source
    name: Valid Source
    type: rss
  - id: invalid
    # Missing required 'name' field
    type: rss
"""
        filepath = temp_config_dir / "sources.yaml"
        filepath.write_text(content)
        
        loader = YamlConfigLoader(temp_config_dir)
        sources = loader.load_sources()
        
        # Should load valid source even if others fail
        assert len(sources) == 1
        assert sources[0].id == "valid-source"


# ============================================================================
# Default Config Creation Tests
# ============================================================================

class TestDefaultConfigs:
    """Tests for default configuration creation."""
    
    def test_create_default_configs(self, temp_config_dir):
        """Test creating default configuration files."""
        create_default_configs(temp_config_dir)
        
        # Check files were created
        assert (temp_config_dir / "sources.yaml").exists()
        assert (temp_config_dir / "rules.yaml").exists()
    
    def test_create_does_not_overwrite(self, temp_config_dir):
        """Test that create_default_configs doesn't overwrite existing files."""
        # Create existing file
        existing_content = "# Existing custom config\n"
        sources_file = temp_config_dir / "sources.yaml"
        sources_file.write_text(existing_content)
        
        create_default_configs(temp_config_dir)
        
        # Should preserve existing content
        assert sources_file.read_text() == existing_content


# ============================================================================
# Settings Environment Tests
# ============================================================================

class TestSettingsEnvironment:
    """Tests for environment-based settings."""
    
    def test_env_prefix(self):
        """Test that SM_ prefix is used."""
        os.environ["SM_DEBUG"] = "true"
        os.environ["SM_LOG_LEVEL"] = "DEBUG"
        
        settings = reload_settings()
        
        assert settings.debug is True
        assert settings.log_level == "DEBUG"
        
        # Cleanup
        del os.environ["SM_DEBUG"]
        del os.environ["SM_LOG_LEVEL"]
    
    def test_env_type_conversion(self):
        """Test environment variable type conversion."""
        os.environ["SM_DEFAULT_INTERVAL"] = "600"
        os.environ["SM_MAX_RETRIES"] = "5"
        
        settings = reload_settings()
        
        assert settings.default_interval == 600
        assert settings.max_retries == 5
        
        # Cleanup
        del os.environ["SM_DEFAULT_INTERVAL"]
        del os.environ["SM_MAX_RETRIES"]
    
    def test_ensure_directories(self, temp_config_dir):
        """Test directory creation."""
        settings = Settings(
            data_dir=temp_config_dir / "data",
            log_dir=temp_config_dir / "logs",
            config_dir=temp_config_dir / "config"
        )
        
        settings.ensure_directories()
        
        assert settings.data_dir.exists()
        assert settings.log_dir.exists()
        assert settings.config_dir.exists()
