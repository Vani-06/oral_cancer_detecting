import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

log = logging.getLogger("oralsentinel.mail")


def send_email(to: str, subject: str, body: str) -> None:
    """Sends through SMTP when configured. Without SMTP_HOST the message is
    written to the server log instead; in production the reset endpoint
    refuses before getting here, so links are never logged there."""
    if not settings.SMTP_HOST:
        log.warning("SMTP not configured; email to %s not sent. Subject: %s\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.SMTP_FROM, to, subject
    msg.set_content(body)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
        smtp.send_message(msg)
