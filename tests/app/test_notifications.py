from __future__ import annotations

from pydantic import SecretStr

from halpha.app.notifications import (
    NotificationContent,
    StdlibSMTPTransport,
)
from halpha.configuration import EmailConfig


def _enabled_config() -> EmailConfig:
    return EmailConfig(
        delivery_enabled=True,
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_username="owner@example.test",
        sender="halpha@example.test",
        owner_recipient="owner@example.test",
    )


class _SMTP:
    def __init__(self, *args, **kwargs) -> None:
        self.calls = [("connect", args, kwargs)]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def ehlo(self):
        self.calls.append(("ehlo",))

    def starttls(self, *, context):
        self.calls.append(("starttls", context))

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        self.calls.append(("send", message))


def test_smtp_transport_requires_starttls_before_login_and_send() -> None:
    clients: list[_SMTP] = []

    def factory(*args, **kwargs):
        client = _SMTP(*args, **kwargs)
        clients.append(client)
        return client

    transport = StdlibSMTPTransport(
        _enabled_config(),
        SecretStr("smtp-password"),
        smtp_factory=factory,
        ssl_context_factory=lambda: object(),
    )
    transport.send(
        recipient="owner@example.test",
        content=NotificationContent(subject="Halpha event", body="Fact summary"),
    )
    names = [call[0] for call in clients[0].calls]
    assert names == ["connect", "ehlo", "starttls", "ehlo", "login", "send"]
