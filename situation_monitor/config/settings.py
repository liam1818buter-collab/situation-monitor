"""
Configuration management for Situation Monitor.
Uses Pydantic Settings for environment variable support.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings with environment variable support.
    
    All settings can be overridden via environment variables
    using the prefix SM_ (e.g., SM_DEBUG=true).
    """
    
    model_config = SettingsConfigDict(
        env_prefix="SM_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Application
    app_name: str = Field(default="Situation Monitor", description="Application name")
    version: str = Field(default="0.1.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    environment: str = Field(default="development", description="Environment (development/production)")
    
    # Paths
    data_dir: Path = Field(default=Path("./data"), description="Data storage directory")
    log_dir: Path = Field(default=Path("./logs"), description="Log directory")
    config_dir: Path = Field(default=Path("./config"), description="Configuration directory")
    
    # Monitoring
    default_interval: int = Field(default=300, ge=10, description="Default monitoring interval in seconds")
    max_concurrent_sources: int = Field(default=10, ge=1, description="Max concurrent source fetches")
    request_timeout: int = Field(default=30, ge=1, description="HTTP request timeout in seconds")
    
    # Rate Limiting
    rate_limit_requests: int = Field(default=60, description="Requests per minute limit")
    rate_limit_burst: int = Field(default=10, description="Burst allowance for rate limiter")
    
    # Retry
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")
    retry_base_delay: float = Field(default=1.0, ge=0, description="Base delay for exponential backoff")
    retry_max_delay: float = Field(default=60.0, ge=0, description="Maximum retry delay")
    
    # Storage
    storage_backend: str = Field(default="sqlite", description="Storage backend (sqlite/json/memory)")
    database_url: Optional[str] = Field(default=None, description="Database connection URL")
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)")
    log_format: str = Field(default="json", description="Log format (json/text)")
    log_file_max_mb: int = Field(default=10, description="Max log file size in MB")
    log_file_backup_count: int = Field(default=5, description="Number of log backups to keep")
    
    # Notifications
    notification_cooldown_seconds: int = Field(default=300, description="Cooldown between duplicate notifications")
    
    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        v = v.lower()
        if v not in ('development', 'production', 'testing'):
            raise ValueError("environment must be development, production, or testing")
        return v
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        v = v.upper()
        if v not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v
    
    @field_validator('data_dir', 'log_dir', 'config_dir')
    @classmethod
    def validate_paths(cls, v: Path) -> Path:
        return v.resolve()
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"
    
    def ensure_directories(self) -> None:
        """Ensure all configured directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Returns:
        Settings instance loaded from environment.
    """
    return Settings()


def reload_settings() -> Settings:
    """
    Force reload settings from environment.
    
    Returns:
        Fresh Settings instance.
    """
    get_settings.cache_clear()
    return get_settings()
