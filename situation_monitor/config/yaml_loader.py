"""
YAML configuration loader for sources, rules, and monitoring settings.
"""

import yaml
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from situation_monitor.core.models import SourceConfig, AlertRule
from situation_monitor.config.settings import get_settings


class YamlConfigLoader:
    """
    Load and manage YAML configuration files.
    
    Supports separate profiles for different environments.
    """
    
    def __init__(self, config_dir: Optional[Path] = None):
        settings = get_settings()
        self.config_dir = config_dir or settings.config_dir
        self._sources: Dict[str, SourceConfig] = {}
        self._rules: Dict[str, AlertRule] = {}
        self._profile: str = settings.environment
    
    @property
    def profile(self) -> str:
        """Current configuration profile."""
        return self._profile
    
    def _get_profile_path(self, filename: str) -> Path:
        """Get path for a configuration file, considering profile."""
        # Check for profile-specific file first
        profile_path = self.config_dir / self._profile / filename
        if profile_path.exists():
            return profile_path
        
        # Fall back to default
        default_path = self.config_dir / filename
        return default_path
    
    def load_yaml(self, filename: str) -> Dict[str, Any]:
        """
        Load a YAML configuration file.
        
        Args:
            filename: Name of the YAML file.
            
        Returns:
            Parsed YAML content as dictionary.
            
        Raises:
            FileNotFoundError: If file doesn't exist.
            yaml.YAMLError: If file is invalid YAML.
        """
        filepath = self._get_profile_path(filename)
        
        if not filepath.exists():
            raise FileNotFoundError(f"Configuration file not found: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    
    def load_sources(self, filename: str = "sources.yaml") -> List[SourceConfig]:
        """
        Load source configurations from YAML.
        
        Args:
            filename: Name of the sources YAML file.
            
        Returns:
            List of SourceConfig objects.
        """
        try:
            data = self.load_yaml(filename)
            sources_data = data.get('sources', [])
            
            sources = []
            for source_dict in sources_data:
                try:
                    source = SourceConfig(**source_dict)
                    sources.append(source)
                    self._sources[source.id] = source
                except Exception as e:
                    # Log error but continue loading other sources
                    print(f"Error loading source {source_dict.get('id', 'unknown')}: {e}")
            
            return sources
        except FileNotFoundError:
            # Return empty list if file doesn't exist
            return []
    
    def load_rules(self, filename: str = "rules.yaml") -> List[AlertRule]:
        """
        Load alert rules from YAML.
        
        Args:
            filename: Name of the rules YAML file.
            
        Returns:
            List of AlertRule objects.
        """
        try:
            data = self.load_yaml(filename)
            rules_data = data.get('rules', [])
            
            rules = []
            for rule_dict in rules_data:
                try:
                    rule = AlertRule(**rule_dict)
                    rules.append(rule)
                    self._rules[rule.id] = rule
                except Exception as e:
                    print(f"Error loading rule {rule_dict.get('id', 'unknown')}: {e}")
            
            return rules
        except FileNotFoundError:
            return []
    
    def get_source(self, source_id: str) -> Optional[SourceConfig]:
        """Get a source configuration by ID."""
        return self._sources.get(source_id)
    
    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Get an alert rule by ID."""
        return self._rules.get(rule_id)
    
    def save_sources(
        self, 
        sources: List[SourceConfig], 
        filename: str = "sources.yaml"
    ) -> None:
        """
        Save source configurations to YAML.
        
        Args:
            sources: List of SourceConfig objects to save.
            filename: Name of the file to save to.
        """
        filepath = self.config_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            'sources': [s.model_dump() for s in sources]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def save_rules(
        self, 
        rules: List[AlertRule], 
        filename: str = "rules.yaml"
    ) -> None:
        """
        Save alert rules to YAML.
        
        Args:
            rules: List of AlertRule objects to save.
            filename: Name of the file to save to.
        """
        filepath = self.config_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert enums to strings for YAML serialization
        def convert_enums(obj):
            """Recursively convert enum values to strings."""
            if isinstance(obj, dict):
                return {k: convert_enums(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_enums(item) for item in obj]
            elif isinstance(obj, Enum):
                return obj.value
            return obj
        
        data = {
            'rules': [convert_enums(r.model_dump()) for r in rules]
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def create_default_configs(config_dir: Path) -> None:
    """
    Create default configuration files if they don't exist.
    
    Args:
        config_dir: Directory to create configs in.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # Default sources.yaml
    sources_file = config_dir / "sources.yaml"
    if not sources_file.exists():
        default_sources = {
            'sources': [
                {
                    'id': 'example-rss',
                    'name': 'Example RSS Feed',
                    'type': 'rss',
                    'url': 'https://example.com/feed.xml',
                    'interval_seconds': 300,
                    'enabled': False,
                    'tags': ['example', 'rss']
                }
            ]
        }
        with open(sources_file, 'w') as f:
            yaml.dump(default_sources, f, default_flow_style=False)
    
    # Default rules.yaml
    rules_file = config_dir / "rules.yaml"
    if not rules_file.exists():
        default_rules = {
            'rules': [
                {
                    'id': 'example-rule',
                    'name': 'Example Alert Rule',
                    'keywords': ['urgent', 'breaking'],
                    'severity': 'warning',
                    'enabled': False,
                    'cooldown_seconds': 3600
                }
            ]
        }
        with open(rules_file, 'w') as f:
            yaml.dump(default_rules, f, default_flow_style=False)
