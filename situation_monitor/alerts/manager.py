from typing import List, Optional
from datetime import datetime, timedelta
from ..core.base import Notifier, Alert, AnalysisResult
from ..core.config import settings


class AlertManager:
    def __init__(self):
        self.channels: List[Notifier] = []
        self.last_alert: dict = {}  # situation_id -> timestamp
        self._setup_channels()
    
    def _setup_channels(self):
        """Setup enabled channels from config"""
        from .channels.email import EmailChannel
        from .channels.discord import DiscordChannel
        from .channels.webhook import WebhookChannel
        
        # Add channels if configured
        if settings.smtp_host and settings.smtp_user:
            self.channels.append(EmailChannel())
        if settings.discord_webhook_url:
            self.channels.append(DiscordChannel())
        
        # Webhook always added as fallback
        self.channels.append(WebhookChannel())
    
    def should_alert(self, situation_id: str, analysis: AnalysisResult) -> bool:
        """Check if we should send an alert (rate limiting)"""
        now = datetime.utcnow()
        last = self.last_alert.get(situation_id)
        cooldown = timedelta(minutes=settings.alert_cooldown_minutes)
        
        if last and (now - last) < cooldown:
            return False
        
        # Alert on significant sentiment changes or high impact
        if abs(analysis.sentiment) > 0.8:  # Strong positive or negative
            return True
        if len(analysis.entities) > 5:  # Many entities detected
            return True
        
        return False
    
    async def send_alert(self, alert: Alert):
        """Send alert to all configured channels"""
        for channel in self.channels:
            try:
                await channel.send(alert)
            except Exception as e:
                print(f"Failed to send via {channel.__class__.__name__}: {e}")
        
        self.last_alert[alert.situation_id] = datetime.utcnow()
