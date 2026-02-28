import aiohttp
from ...core.base import Notifier, Alert
from ...core.config import settings


class DiscordChannel(Notifier):
    async def send(self, alert: Alert) -> bool:
        if not settings.discord_webhook_url:
            return False
        
        # Color based on severity
        colors = {
            'INFO': 3447003,      # Blue
            'WARNING': 15158332,  # Orange
            'CRITICAL': 15158332  # Red
        }
        
        payload = {
            "embeds": [{
                "title": f"Situation Monitor Alert - {alert.severity}",
                "description": alert.message,
                "color": colors.get(alert.severity, 3447003),
                "timestamp": alert.created_at.isoformat()
            }]
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(settings.discord_webhook_url, json=payload) as resp:
                    return resp.status == 204
        except Exception as e:
            print(f"Discord send failed: {e}")
            return False
