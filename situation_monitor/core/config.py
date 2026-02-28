from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = "sqlite:///./situation_monitor.db"
    log_level: str = "INFO"
    default_rate_limit: int = 10
    alert_cooldown_minutes: int = 15
    
    # Email
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_pass: Optional[str] = None
    
    # Discord
    discord_webhook_url: Optional[str] = None
    
    class Config:
        env_file = ".env"

settings = Settings()
