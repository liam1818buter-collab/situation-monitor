import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from ...core.base import Notifier, Alert
from ...core.config import settings


class EmailChannel(Notifier):
    async def send(self, alert: Alert) -> bool:
        if not settings.smtp_host or not settings.smtp_user:
            return False
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"[Situation Monitor] {alert.severity}: Alert"
        msg['From'] = settings.smtp_user
        msg['To'] = settings.smtp_user  # Send to self
        
        # Text version
        text = f"Alert: {alert.message}\nSeverity: {alert.severity}\nTime: {alert.created_at}"
        msg.attach(MIMEText(text, 'plain'))
        
        # HTML version
        html = f"""
        <html>
        <body>
            <h2>Situation Monitor Alert</h2>
            <p><strong>Severity:</strong> {alert.severity}</p>
            <p><strong>Message:</strong> {alert.message}</p>
            <p><strong>Time:</strong> {alert.created_at}</p>
        </body>
        </html>
        """
        msg.attach(MIMEText(html, 'html'))
        
        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user,
                password=settings.smtp_pass,
                use_tls=True
            )
            return True
        except Exception as e:
            print(f"Email send failed: {e}")
            return False
