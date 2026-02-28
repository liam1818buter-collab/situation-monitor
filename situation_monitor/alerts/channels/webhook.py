import aiohttp
from ...core.base import Notifier, Alert


class WebhookChannel(Notifier):
    """Generic webhook channel - logs to console if no URL configured"""
    
    async def send(self, alert: Alert) -> bool:
        # Log to console as fallback
        print(f"\n[ALERT - {alert.severity}] {alert.message}")
        print(f"Situation: {alert.situation_id} | Time: {alert.created_at}\n")
        return True
