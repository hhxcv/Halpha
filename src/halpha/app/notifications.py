"""Small direct SMTP transport for owner-requested test messages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
import ssl

from pydantic import SecretStr

from halpha.configuration import EmailConfig


class NotificationDeliveryError(RuntimeError):
    """Sanitized notification delivery failure."""


@dataclass(frozen=True)
class NotificationContent:
    subject: str
    body: str


def _safe_header(value: str, field: str) -> str:
    if not value or "\r" in value or "\n" in value:
        raise NotificationDeliveryError(f"EMAIL_{field}_INVALID")
    return value


class StdlibSMTPTransport:
    """STARTTLS-only SMTP transport with no persistent delivery workflow."""

    def __init__(
        self,
        config: EmailConfig,
        password: SecretStr,
        *,
        smtp_factory: Callable[..., smtplib.SMTP] = smtplib.SMTP,
        ssl_context_factory: Callable[[], ssl.SSLContext] = ssl.create_default_context,
    ) -> None:
        if not config.delivery_enabled:
            raise NotificationDeliveryError("EMAIL_DELIVERY_DISABLED")
        self._config = config
        self._password = password
        self._smtp_factory = smtp_factory
        self._ssl_context_factory = ssl_context_factory

    def send(self, *, recipient: str, content: NotificationContent) -> None:
        config = self._config
        host = config.smtp_host
        username = config.smtp_username
        sender = config.sender
        if host is None or username is None or sender is None:
            raise NotificationDeliveryError("EMAIL_DELIVERY_CONFIGURATION_INCOMPLETE")
        message = EmailMessage()
        message["From"] = _safe_header(sender, "SENDER")
        message["To"] = _safe_header(recipient, "RECIPIENT")
        message["Subject"] = _safe_header(content.subject, "SUBJECT")
        message.set_content(content.body)
        try:
            with self._smtp_factory(
                host,
                config.smtp_port,
                timeout=config.timeout_seconds,
            ) as client:
                client.ehlo()
                client.starttls(context=self._ssl_context_factory())
                client.ehlo()
                client.login(username, self._password.get_secret_value())
                client.send_message(message)
        except Exception as exc:
            raise NotificationDeliveryError(
                f"SMTP_DELIVERY_FAILED type={type(exc).__name__}"
            ) from None
