from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import SecretStr

from halpha.app.notifications import (
    ClaimedNotification,
    NotificationContent,
    NotificationDispatcher,
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


class _Repository:
    def __init__(self, attempt_count: int = 0) -> None:
        self.claim = ClaimedNotification(
            notification_id=uuid4(),
            source_identity="task:example:v1",
            recipient_route_ref="owner-primary-email",
            content_digest="a" * 64,
            attempt_count=attempt_count,
            claim_version=1,
        )
        self.delivered = False
        self.failure = None

    def claim_due(self, *, now):
        return self.claim

    def mark_delivered(self, claim, *, delivered_at):
        self.delivered = True

    def record_failure(self, claim, **kwargs):
        self.failure = kwargs


class _Content:
    def materialize(self, claim):
        return NotificationContent(subject="Subject", body="Body")


class _Transport:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def send(self, **kwargs):
        if self.fail:
            raise RuntimeError("transport failed")


def test_dispatcher_delivers_without_changing_source_transaction() -> None:
    repository = _Repository()
    dispatcher = NotificationDispatcher(
        _enabled_config(), repository, _Content(), _Transport()
    )
    assert dispatcher.dispatch_one(now=datetime.now(UTC)) == "DELIVERED"
    assert repository.delivered is True
    assert repository.failure is None


def test_dispatcher_retries_then_abandons_on_third_attempt() -> None:
    first = _Repository(attempt_count=0)
    dispatcher = NotificationDispatcher(
        _enabled_config(), first, _Content(), _Transport(fail=True)
    )
    assert dispatcher.dispatch_one(now=datetime.now(UTC)) == "RETRY_SCHEDULED"
    assert first.failure["retry_after_seconds"] == 60
    assert first.failure["abandon"] is False

    third = _Repository(attempt_count=2)
    dispatcher = NotificationDispatcher(
        _enabled_config(), third, _Content(), _Transport(fail=True)
    )
    assert dispatcher.dispatch_one(now=datetime.now(UTC)) == "ABANDONED"
    assert third.failure["retry_after_seconds"] is None
    assert third.failure["abandon"] is True
