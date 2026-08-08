"""Outbound email via the Resend REST API.

Uses httpx directly rather than the `resend` SDK — httpx is already a
dependency and is async-native, which matches the rest of the codebase.

Sending is best-effort: if RESEND_API_KEY is unset (local dev) or Resend
returns an error, we log and move on. Callers must not let a failed
notification lose the underlying record.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def send_email(subject: str, html: str, reply_to: str | None = None) -> bool:
    """Send a notification to the configured owner address. Returns success."""
    if not settings.resend_api_key:
        logger.info("RESEND_API_KEY not set — skipping email %r", subject)
        return False

    payload: dict = {
        "from": settings.contact_from_email,
        "to": [settings.contact_to_email],
        "subject": subject,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = reply_to

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                RESEND_ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
        if resp.status_code >= 400:
            logger.error("Resend returned %s: %s", resp.status_code, resp.text)
            return False
        return True
    except Exception:
        logger.exception("Failed to send email %r", subject)
        return False


async def send_contact_notification(name: str, email: str, message: str, source: str) -> bool:
    html = (
        f"<p><strong>From:</strong> {_escape(name)} &lt;{_escape(email)}&gt;</p>"
        f"<p><strong>Source:</strong> {_escape(source)}</p>"
        f"<hr/><p>{_escape(message).replace(chr(10), '<br/>')}</p>"
    )
    return await send_email(
        subject=f"New contact form submission from {name}",
        html=html,
        reply_to=email,
    )
