"""SMTP delivery used by every outbound email; HTML bodies come from
foundation/email_templates.py::render_email().

When SMTP_HOST is unset, the message (including any link) is written to the
audit log instead of being sent, so nothing is silently lost
(see docs/business-rules.md §Password reset)."""

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from app.foundation.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class EmailNotConfiguredError(Exception):
    pass


def send_html_email(*, to: str, subject: str, html_body: str, text_body: str) -> None:
    """Like send_email(), but multipart/alternative: branded HTML plus a
    plain-text fallback, since some clients and spam filters penalize
    HTML-only mail."""
    if not settings.smtp_host:
        raise EmailNotConfiguredError("SMTP is not configured (smtp_host is empty)")

    message = EmailMessage()
    message["Subject"] = subject
    # Always send with the brand as display name, not a bare address.
    from_name, from_address = parseaddr(settings.smtp_from_address)
    message["From"] = formataddr((from_name or "SOSNET", from_address))
    message["To"] = to
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def send_html_email_best_effort(*, context: str, to: str, subject: str, html_body: str, text_body: str) -> bool:
    """Send a notification about work that is already committed (order paid,
    wallet credited, ticket opened, account invited). Never raises; returns
    whether the mail went out.

    Any SMTP failure (login, timeout, DNS, TLS) is swallowed so it cannot turn
    a completed operation into a 500 and prompt the user to retry it, which
    for a wallet top-up would credit twice (each click gets a new idempotency
    key).

    Not for password-reset links or OTP codes: there the email is the
    deliverable and must fail loudly."""
    try:
        send_html_email(to=to, subject=subject, html_body=html_body, text_body=text_body)
        return True
    except EmailNotConfiguredError:
        logger.warning("%s: email to %s not sent (SMTP not configured)", context, to)
        return False
    except Exception:
        logger.exception("%s: email to %s failed", context, to)
        return False
