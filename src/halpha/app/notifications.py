"""Transactional-outbox dispatch boundary and stdlib SMTP transport."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from email.message import EmailMessage
import smtplib
import ssl
from typing import Any, Callable, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from pydantic import SecretStr

from halpha.configuration import EmailConfig
from halpha.domain_values import content_digest


class NotificationDeliveryError(RuntimeError):
    """Sanitized notification delivery failure."""


class NotificationRepositoryError(RuntimeError):
    """Sanitized transactional-outbox persistence failure."""


@dataclass(frozen=True)
class ClaimedNotification:
    notification_id: UUID
    source_identity: str
    recipient_route_ref: str
    content_digest: str
    attempt_count: int
    claim_version: int


@dataclass(frozen=True)
class NotificationContent:
    subject: str
    body: str


class NotificationRepository(Protocol):
    def claim_due(self, *, now: datetime) -> ClaimedNotification | None: ...

    def mark_delivered(self, claim: ClaimedNotification, *, delivered_at: datetime) -> None: ...

    def record_failure(
        self,
        claim: ClaimedNotification,
        *,
        failed_at: datetime,
        retry_after_seconds: int | None,
        abandon: bool,
    ) -> None: ...


class NotificationContentProvider(Protocol):
    def materialize(self, claim: ClaimedNotification) -> NotificationContent: ...


class NotificationTransport(Protocol):
    def send(self, *, recipient: str, content: NotificationContent) -> None: ...


@dataclass(frozen=True, repr=False)
class PostgreSQLNotificationRepository:
    """Claim and advance the existing Notification record family atomically."""

    database_name: str
    environment_id: str
    password: SecretStr
    host: str = "127.0.0.1"
    port: int = 5432

    @property
    def role_name(self) -> str:
        return f"{self.database_name}_app"

    def _connect(self) -> psycopg.Connection[Any]:
        try:
            return psycopg.connect(
                host=self.host,
                port=self.port,
                dbname=self.database_name,
                user=self.role_name,
                password=self.password.get_secret_value(),
                connect_timeout=2,
            )
        except Exception as exc:
            raise NotificationRepositoryError(
                f"NOTIFICATION_DATABASE_UNAVAILABLE type={type(exc).__name__}"
            ) from None

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise NotificationRepositoryError("NOTIFICATION_TIMESTAMP_MUST_BE_AWARE")

    def claim_due(self, *, now: datetime) -> ClaimedNotification | None:
        self._require_aware(now)
        try:
            with self._connect() as connection, connection.transaction():
                row = connection.execute(
                    """
                    WITH candidate AS (
                        SELECT notification_id
                        FROM halpha.notification
                        WHERE environment_id = %s
                          AND state = 'PENDING'
                          AND (next_attempt_at IS NULL OR next_attempt_at <= %s)
                        ORDER BY COALESCE(next_attempt_at, created_at), created_at, notification_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE halpha.notification AS notification
                    SET claim_version = notification.claim_version + 1,
                        updated_at = %s
                    FROM candidate
                    WHERE notification.notification_id = candidate.notification_id
                      AND notification.environment_id = %s
                    RETURNING notification.notification_id,
                              notification.source_identity,
                              notification.recipient_route_ref,
                              notification.content_digest,
                              notification.attempt_count,
                              notification.claim_version
                    """,
                    (self.environment_id, now, now, self.environment_id),
                ).fetchone()
        except NotificationRepositoryError:
            raise
        except Exception as exc:
            raise NotificationRepositoryError(
                f"NOTIFICATION_CLAIM_FAILED type={type(exc).__name__}"
            ) from None
        if row is None:
            return None
        return ClaimedNotification(
            notification_id=row[0],
            source_identity=str(row[1]),
            recipient_route_ref=str(row[2]),
            content_digest=str(row[3]),
            attempt_count=int(row[4]),
            claim_version=int(row[5]),
        )

    def mark_delivered(
        self,
        claim: ClaimedNotification,
        *,
        delivered_at: datetime,
    ) -> None:
        self._require_aware(delivered_at)
        try:
            with self._connect() as connection, connection.transaction():
                cursor = connection.execute(
                    """
                    UPDATE halpha.notification
                    SET state = 'DELIVERED',
                        state_version = state_version + 1,
                        next_attempt_at = NULL,
                        updated_at = %s
                    WHERE environment_id = %s
                      AND notification_id = %s
                      AND state = 'PENDING'
                      AND claim_version = %s
                    """,
                    (
                        delivered_at,
                        self.environment_id,
                        claim.notification_id,
                        claim.claim_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise NotificationRepositoryError("NOTIFICATION_CLAIM_STALE")
        except NotificationRepositoryError:
            raise
        except Exception as exc:
            raise NotificationRepositoryError(
                f"NOTIFICATION_DELIVERY_COMMIT_FAILED type={type(exc).__name__}"
            ) from None

    def record_failure(
        self,
        claim: ClaimedNotification,
        *,
        failed_at: datetime,
        retry_after_seconds: int | None,
        abandon: bool,
    ) -> None:
        self._require_aware(failed_at)
        if abandon != (retry_after_seconds is None):
            raise NotificationRepositoryError("NOTIFICATION_RETRY_STATE_INVALID")
        if retry_after_seconds is not None and retry_after_seconds <= 0:
            raise NotificationRepositoryError("NOTIFICATION_RETRY_DELAY_INVALID")
        next_attempt_at = (
            None
            if retry_after_seconds is None
            else failed_at + timedelta(seconds=retry_after_seconds)
        )
        try:
            with self._connect() as connection, connection.transaction():
                row = connection.execute(
                    """
                    UPDATE halpha.notification
                    SET state = %s,
                        state_version = state_version + 1,
                        attempt_count = attempt_count + 1,
                        next_attempt_at = %s,
                        updated_at = %s
                    WHERE environment_id = %s
                      AND notification_id = %s
                      AND state = 'PENDING'
                      AND claim_version = %s
                    RETURNING task_ref, source_identity, state_version
                    """,
                    (
                        "ABANDONED" if abandon else "PENDING",
                        next_attempt_at,
                        failed_at,
                        self.environment_id,
                        claim.notification_id,
                        claim.claim_version,
                    ),
                ).fetchone()
                if row is None:
                    raise NotificationRepositoryError("NOTIFICATION_CLAIM_STALE")
                if abandon and row[0] is None:
                    responsibility_key = f"notification:{row[1]}:delivery-abandoned"
                    task_id = uuid5(
                        NAMESPACE_URL,
                        f"urn:halpha:{self.environment_id}:task:{responsibility_key}",
                    )
                    task_fields = {
                        "task_id": task_id,
                        "environment_id": self.environment_id,
                        "owner_scope": "local-owner",
                        "responsibility_key": responsibility_key,
                        "priority": "HIGH",
                        "due_at": None,
                        "source_kind": "NOTIFICATION",
                        "source_ref": str(claim.notification_id),
                        "source_version": int(row[2]),
                        "source_digest": claim.content_digest,
                        "state": "OPEN",
                        "state_version": 1,
                        "resolution_ref": None,
                        "created_at": failed_at,
                        "updated_at": failed_at,
                    }
                    connection.execute(
                        """
                        INSERT INTO halpha.task (
                          task_id, environment_id, owner_scope, responsibility_key,
                          priority, due_at, source_kind, source_ref, source_version,
                          source_digest, state, state_version, resolution_ref,
                          content_digest, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (environment_id, responsibility_key) DO NOTHING
                        """,
                        (
                            task_fields["task_id"],
                            task_fields["environment_id"],
                            task_fields["owner_scope"],
                            task_fields["responsibility_key"],
                            task_fields["priority"],
                            task_fields["due_at"],
                            task_fields["source_kind"],
                            task_fields["source_ref"],
                            task_fields["source_version"],
                            task_fields["source_digest"],
                            task_fields["state"],
                            task_fields["state_version"],
                            task_fields["resolution_ref"],
                            content_digest(task_fields),
                            task_fields["created_at"],
                            task_fields["updated_at"],
                        ),
                    )
                    persisted_task = connection.execute(
                        """
                        SELECT task_id FROM halpha.task
                        WHERE environment_id = %s AND responsibility_key = %s
                        """,
                        (self.environment_id, responsibility_key),
                    ).fetchone()
                    if persisted_task is None:
                        raise NotificationRepositoryError(
                            "NOTIFICATION_ABANDONED_TASK_MISSING"
                        )
                    connection.execute(
                        """
                        UPDATE halpha.notification SET task_ref = %s
                        WHERE environment_id = %s AND notification_id = %s
                        """,
                        (
                            persisted_task[0],
                            self.environment_id,
                            claim.notification_id,
                        ),
                    )
        except NotificationRepositoryError:
            raise
        except Exception as exc:
            raise NotificationRepositoryError(
                f"NOTIFICATION_FAILURE_COMMIT_FAILED type={type(exc).__name__}"
            ) from None


def _safe_header(value: str, field: str) -> str:
    if not value or "\r" in value or "\n" in value:
        raise NotificationDeliveryError(f"EMAIL_{field}_INVALID")
    return value


class StdlibSMTPTransport:
    """STARTTLS-only SMTP transport; a delivery attempt has no business rollback power."""

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
            with self._smtp_factory(host, config.smtp_port, timeout=config.timeout_seconds) as client:
                client.ehlo()
                client.starttls(context=self._ssl_context_factory())
                client.ehlo()
                client.login(username, self._password.get_secret_value())
                client.send_message(message)
        except NotificationDeliveryError:
            raise
        except Exception as exc:
            raise NotificationDeliveryError(
                f"SMTP_DELIVERY_FAILED type={type(exc).__name__}"
            ) from None


class NotificationDispatcher:
    def __init__(
        self,
        config: EmailConfig,
        repository: NotificationRepository,
        content_provider: NotificationContentProvider,
        transport: NotificationTransport,
    ) -> None:
        self._config = config
        self._repository = repository
        self._content_provider = content_provider
        self._transport = transport

    def dispatch_one(self, *, now: datetime) -> str:
        if not self._config.delivery_enabled:
            return "DISABLED"
        claim = self._repository.claim_due(now=now)
        if claim is None:
            return "IDLE"
        if claim.recipient_route_ref != self._config.owner_route_ref:
            self._repository.record_failure(
                claim,
                failed_at=now,
                retry_after_seconds=None,
                abandon=True,
            )
            return "ABANDONED"
        content = self._content_provider.materialize(claim)
        try:
            recipient = self._config.owner_recipient
            if recipient is None:
                raise NotificationDeliveryError("EMAIL_OWNER_RECIPIENT_MISSING")
            self._transport.send(recipient=recipient, content=content)
        except Exception:
            next_attempt = claim.attempt_count + 1
            abandon = next_attempt >= self._config.max_attempts
            retry = (
                None
                if abandon
                else self._config.retry_delays_seconds[next_attempt - 1]
            )
            self._repository.record_failure(
                claim,
                failed_at=now,
                retry_after_seconds=retry,
                abandon=abandon,
            )
            return "ABANDONED" if abandon else "RETRY_SCHEDULED"
        self._repository.mark_delivered(claim, delivered_at=now)
        return "DELIVERED"
