"""FastAPI composition root for the B01 local owner workbench."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import html
import json
from pathlib import Path
import secrets as stdlib_secrets
import time
from typing import Any
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from pwdlib import PasswordHash
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from halpha.app.projection import (
    PostgreSQLWorkbenchProjection,
    ProjectionUnavailable,
    WorkbenchProjection,
)
from halpha.app.planning_api import (
    ActivationPayload,
    CapitalLimitPayload,
    ControlPayload,
    PlanDraftPayload,
    PlanningApiUnavailable,
    PostgreSQLPlanningApi,
    TaskAcknowledgePayload,
)
from halpha.app.outcomes_api import (
    OutcomesApiUnavailable,
    PostgreSQLOutcomesApi,
    ReviewCompletionPayload,
    ReviewRefreshPayload,
)
from halpha.app.notifications import (
    NotificationContent,
    NotificationDeliveryError,
    StdlibSMTPTransport,
)
from halpha.app.secrets import AppSecrets
from halpha.app.security import (
    CsrfMiddleware,
    LocalRequestBoundaryMiddleware,
    LoginRateLimiter,
    OWNER_SESSION_MARKER,
    SESSION_ABSOLUTE_LIFETIME_SECONDS,
    session_is_current,
)
from halpha.build_manifest import manifest_sha256, verify_manifest
from halpha.capital.repository import CapitalConflict
from halpha.configuration import HalphaSettings, app_settings, settings_digest
from halpha.planning.repository import PlanningConflict
from halpha.planning.transitions import ControlIntent
from halpha.outcomes.repository import OutcomeConflict
from halpha.user_workbench.repository import CommandConflict


class WebConfigurationError(RuntimeError):
    """Sanitized failure to construct the authenticated local web surface."""


class FrozenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SessionResponse(FrozenResponse):
    status: str
    absolute_expires_in_seconds: int | None = None


class OverviewResponse(FrozenResponse):
    environment_kind: str
    environment_id: str
    account_id: str
    profile: str
    authority_class: str
    runtime_real_write_gate: str
    construction_package: str
    construction_status: str
    server_fact_cutoff: str
    view_retrieved_at: str
    open_task_count: int
    open_activation_count: int
    database_name: str


class SettingsStatusResponse(FrozenResponse):
    environment_kind: str
    environment_id: str
    account_id: str
    profile: str
    authority_class: str
    bind: str
    port: int
    database_name: str
    database_available: bool
    database_reason_code: str | None
    server_fact_cutoff: str | None
    config_digest: str
    build_manifest_status: str
    build_manifest_digest: str | None
    build_manifest_violations: list[str]
    live_write_build_capability: str
    b05_package_eligibility: str
    runtime_real_write_gate: str
    construction_package: str
    construction_status: str
    email_delivery_enabled: bool
    email_configuration_status: str
    view_retrieved_at: str


class TestEmailPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_password: str


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _environment_kind(settings: HalphaSettings) -> str:
    return "DEMO" if settings.release.profile == "BINANCE_DEMO" else "LIVE"


def _manifest_status(repo_root: Path, settings: HalphaSettings) -> dict[str, Any]:
    path = repo_root / settings.release.build_manifest_path
    if not path.is_file():
        return {"status": "MISSING", "digest": None, "violations": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError("manifest root")
        violations = verify_manifest(repo_root, payload)
        return {
            "status": "VERIFIED" if not violations else "DRIFT",
            "digest": manifest_sha256(payload),
            "violations": violations,
        }
    except Exception as exc:
        return {
            "status": "INVALID",
            "digest": sha256(path.read_bytes()).hexdigest(),
            "violations": [f"MANIFEST_READ_FAILED_{type(exc).__name__.upper()}"],
        }


def _csrf_token(request: Request) -> str:
    getter = request.scope.get("csrftoken")
    if not callable(getter):
        raise WebConfigurationError("CSRF_SCOPE_TOKEN_MISSING")
    return str(getter())


_STOP_CATEGORIES = (
    "NEW_FUNDING",
    "PROTECTION",
    "RISK_REDUCTION_OR_ORDER_MANAGEMENT",
    "ALL_WRITES",
)


def _operation_value(value: Any, *, fallback: str = "UNKNOWN") -> str:
    if value is None or value == "":
        return fallback
    return html.escape(str(value))


def _money_value(value: Any, quote_asset: Any) -> str:
    if value is None or value == "":
        return "UNKNOWN"
    try:
        normalized = format(Decimal(str(value)).normalize(), "f")
    except (InvalidOperation, ValueError):
        normalized = str(value)
    if "." in normalized:
        normalized = normalized.rstrip("0").rstrip(".")
    unit = str(quote_asset or "").strip()
    return html.escape(f"{normalized} {unit}".strip())


def _operations_activation_document(activation: dict[str, Any]) -> str:
    activation_id = _operation_value(activation.get("activation_id"))
    raw_activation_id = html.escape(str(activation.get("activation_id", "")), quote=True)
    instrument = _operation_value(activation.get("instrument_ref"))
    state_version = int(activation.get("state_version", 0))
    lifecycle = str(activation.get("lifecycle", "UNKNOWN"))
    run_state = str(activation.get("run_state", "UNKNOWN"))
    pause_reason = str(activation.get("pause_reason") or "NONE")
    stopped = {str(item) for item in activation.get("stopped_categories", [])}
    stop_rows = "".join(
        f"<div><dt>{html.escape(category)}</dt>"
        f'<dd class="{"stopped" if category in stopped else "clear"}">'
        f'{"STOPPED" if category in stopped else "CLEAR"}</dd></div>'
        for category in _STOP_CATEGORIES
    )
    receipts = activation.get("receipts") or []
    receipt_rows = "".join(
        "<tr>"
        f"<td>{_operation_value(receipt.get('intent'))}</td>"
        f'<td><span class="receipt-state">{_operation_value(receipt.get("state"))}</span></td>'
        f"<td><code>{_operation_value(receipt.get('receipt_id'))}</code></td>"
        f"<td>{_operation_value(receipt.get('reason_code'), fallback='—')}</td>"
        f"<td>{_operation_value(receipt.get('updated_at'))}</td>"
        "</tr>"
        for receipt in receipts
    ) or '<tr><td colspan="5" class="empty-cell">No command receipts for this activation.</td></tr>'
    actions = activation.get("execution_actions") or []
    action_rows = "".join(
        "<tr>"
        f"<td>{_operation_value(action.get('action_kind'))}</td>"
        f"<td>{_operation_value(action.get('state'))}</td>"
        f"<td><code>{_operation_value(action.get('client_order_id'), fallback='—')}</code></td>"
        f"<td>{_operation_value(action.get('updated_at'))}</td>"
        "</tr>"
        for action in actions
    ) or '<tr><td colspan="4" class="empty-cell">No persisted execution action.</td></tr>'
    venue_facts = activation.get("venue_facts") or []
    venue_rows = "".join(
        "<tr>"
        f"<td>{_operation_value(fact.get('kind'))}</td>"
        f"<td>{_operation_value(fact.get('source_object_id'), fallback='—')}</td>"
        f"<td>{_operation_value(fact.get('cutoff'))}</td>"
        "</tr>"
        for fact in venue_facts
    ) or '<tr><td colspan="3" class="empty-cell">No attributed position or order fact.</td></tr>'

    resume_initially_available = (
        lifecycle == "RUNNING"
        and run_state == "PAUSED"
        and pause_reason == "WRITER_CONTINUITY_LOST"
    )
    resume_reason = (
        "Preview current reconciliation, authorization, facts, and stops before resuming."
        if resume_initially_available
        else "Available only for RUNNING activations paused by WRITER_CONTINUITY_LOST."
    )
    terminal = lifecycle in {"USER_TAKEOVER", "COMPLETED"}
    exiting = lifecycle == "EXITING"
    quote_asset = activation.get("quote_asset")

    def control(
        intent: str,
        label: str,
        consequence: str,
        disabled: bool,
        disabled_reason: str,
    ) -> str:
        disabled_attr = " disabled" if disabled else ""
        return f"""
          <div class="control-row">
            <div><strong>{html.escape(label)}</strong><p>{html.escape(consequence)}</p></div>
            <button type="button" class="control-button" data-intent="{html.escape(intent, quote=True)}"{disabled_attr}>Preview</button>
            <small>{html.escape(disabled_reason)}</small>
          </div>
        """

    open_responsibility = "NONE OBSERVED"
    if lifecycle == "EXITING":
        open_responsibility = "EXIT CLOSURE PENDING"
    elif run_state == "PAUSED" and pause_reason == "WRITER_CONTINUITY_LOST":
        open_responsibility = "RECOVERY DECISION REQUIRED"
    elif any(str(receipt.get("state")) == "PROCESSING" for receipt in receipts):
        open_responsibility = "COMMAND EFFECT PENDING"
    elif lifecycle == "UNKNOWN":
        open_responsibility = "FACT RECONCILIATION REQUIRED"

    return f"""
      <article class="activation" data-activation-id="{raw_activation_id}" data-state-version="{state_version}">
        <div class="activation-head">
          <div><p class="eyebrow">PLAN ACTIVATION</p><h2>{instrument} · {_operation_value(activation.get('direction'))}</h2></div>
          <code>{activation_id}</code>
        </div>
        <dl class="primary-facts">
          <div><dt>Lifecycle</dt><dd>{_operation_value(lifecycle)}</dd></div>
          <div><dt>Run state</dt><dd>{_operation_value(run_state)}</dd></div>
          <div><dt>Pause reason</dt><dd>{_operation_value(pause_reason)}</dd></div>
          <div><dt>Protection</dt><dd>{_operation_value(activation.get('protection_state'))}</dd></div>
          <div><dt>Authorization until</dt><dd>{_operation_value(activation.get('authorization_valid_until'))}</dd></div>
          <div><dt>Open responsibility</dt><dd>{html.escape(open_responsibility)}</dd></div>
          <div><dt>Venue fact cutoff</dt><dd>{_operation_value(activation.get('latest_venue_cutoff'))}</dd></div>
          <div><dt>State version</dt><dd>{state_version}</dd></div>
        </dl>
        <div class="detail-grid">
          <section aria-label="{instrument} capital and position projection">
            <h3>Capital / position projection</h3>
            <dl class="compact-facts">
              <div><dt>Allocation</dt><dd>{_operation_value(activation.get('allocation_status'))}</dd></div>
              <div><dt>Margin</dt><dd>{_money_value(activation.get('current_margin'), quote_asset)} / {_money_value(activation.get('max_margin'), quote_asset)}</dd></div>
              <div><dt>Notional</dt><dd>{_money_value(activation.get('current_notional'), quote_asset)} / {_money_value(activation.get('max_notional'), quote_asset)}</dd></div>
              <div><dt>Activation loss</dt><dd>{_money_value(activation.get('activation_loss'), quote_asset)} / {_money_value(activation.get('max_allowed_loss'), quote_asset)}</dd></div>
              <div><dt>Max loss latch</dt><dd>{'REACHED' if activation.get('max_loss_reached') else 'CLEAR'}</dd></div>
              <div><dt>Account</dt><dd>{_operation_value(activation.get('account_ref'))}</dd></div>
            </dl>
          </section>
          <section aria-label="{instrument} CAP stop categories">
            <h3>CAP stop categories</h3>
            <dl class="compact-facts stop-facts">{stop_rows}</dl>
          </section>
        </div>
        <details>
          <summary>Execution actions and attributed venue facts</summary>
          <div class="table-grid">
            <div><h3>Execution actions / orders</h3><div class="table-scroll" role="region" aria-label="{instrument} execution actions and orders" tabindex="0"><table><thead><tr><th>Kind</th><th>State</th><th>Client order ID</th><th>Updated</th></tr></thead><tbody>{action_rows}</tbody></table></div></div>
            <div><h3>Position / order facts</h3><div class="table-scroll" role="region" aria-label="{instrument} position and order facts" tabindex="0"><table><thead><tr><th>Kind</th><th>Venue object</th><th>Cutoff</th></tr></thead><tbody>{venue_rows}</tbody></table></div></div>
          </div>
        </details>
        <section class="controls" aria-label="{instrument} limited activation controls">
          <h3>Limited controls</h3>
          {control('RESUME_ACTIVATION', 'Resume activation', 'Clear only a writer-continuity pause after authoritative reconciliation succeeds.', not resume_initially_available, resume_reason)}
          {control('EXIT_STRATEGY', 'Exit strategy', 'Enter exit responsibility and stop new funding. This does not mean the account is already flat.', terminal or exiting, 'Unavailable after exit has begun, takeover, or completion.' if terminal or exiting else 'Requires current preview and owner reauthentication.')}
          {control('USER_TAKEOVER', 'User takeover', 'Persist responsibility transfer and stop later automatic writes. It does not cancel, protect, or close venue exposure.', terminal, 'Unavailable after takeover or completion.' if terminal else 'Requires current preview and owner reauthentication.')}
          <div class="command-status" role="status" aria-live="polite">No command submitted from this page load.</div>
        </section>
        <details class="receipts" open>
          <summary>Original command receipts</summary>
          <div class="table-scroll" role="region" aria-label="{instrument} original command receipts" tabindex="0"><table><thead><tr><th>Intent</th><th>State</th><th>Receipt ID</th><th>Reason</th><th>Updated</th></tr></thead><tbody>{receipt_rows}</tbody></table></div>
        </details>
      </article>
    """


def _operations_script() -> str:
    return r"""
(() => {
  'use strict';
  const dialog = document.querySelector('#control-dialog');
  if (!dialog) return;
  const csrf = document.querySelector('meta[name="halpha-csrf"]')?.content || '';
  const fields = {
    intent: dialog.querySelector('[data-preview="intent"]'),
    target: dialog.querySelector('[data-preview="target"]'),
    state: dialog.querySelector('[data-preview="state"]'),
    protection: dialog.querySelector('[data-preview="protection"]'),
    digest: dialog.querySelector('[data-preview="digest"]'),
    consequence: dialog.querySelector('[data-preview="consequence"]'),
    boundary: dialog.querySelector('[data-preview="boundary"]'),
    error: dialog.querySelector('.dialog-error'),
    password: dialog.querySelector('#control-password'),
    confirm: dialog.querySelector('[data-action="confirm"]'),
  };
  let pending = null;

  const endpoint = (activationId, intent) => {
    const suffix = {
      RESUME_ACTIVATION: 'resume',
      EXIT_STRATEGY: 'exit',
      USER_TAKEOVER: 'takeover',
    }[intent];
    return `/api/v1/activations/${encodeURIComponent(activationId)}/${suffix}`;
  };
  const responseError = async (response) => {
    let code;
    try {
      const payload = await response.json();
      code = payload?.detail?.code || payload?.detail || `HTTP_${response.status}`;
    } catch (_) {
      code = `HTTP_${response.status}`;
    }
    const error = new Error(String(code));
    error.status = response.status;
    return error;
  };
  const setStatus = (article, message, tone = '') => {
    const status = article.querySelector('.command-status');
    status.textContent = message;
    status.dataset.tone = tone;
  };
  const receiptMessage = (receipt) => {
    const reason = receipt.reason_code ? ` · ${receipt.reason_code}` : '';
    const boundary = receipt.state === 'PROCESSING'
      ? 'Processing is not a venue result; inspect the same receipt and venue facts.'
      : 'This receipt is the command result; venue effects still require venue facts.';
    return `${receipt.state} · Receipt ${receipt.receipt_id}${reason}. ${boundary}`;
  };
  const pollReceipt = async (article, receiptId, attempt = 0) => {
    if (attempt >= 30 || !document.body.contains(article)) return;
    try {
      const response = await fetch(`/api/v1/receipts/${encodeURIComponent(receiptId)}`, {
        credentials: 'same-origin', headers: {'Accept': 'application/json'}
      });
      if (!response.ok) throw await responseError(response);
      const receipt = await response.json();
      setStatus(article, receiptMessage(receipt), receipt.state === 'REJECTED' ? 'danger' : '');
      if (receipt.state === 'PROCESSING') {
        window.setTimeout(() => pollReceipt(article, receiptId, attempt + 1), 2000);
      }
    } catch (error) {
      setStatus(article, `Receipt lookup unknown for ${receiptId}: ${error.message}. Keep this receipt ID; do not create a replacement command.`, 'danger');
    }
  };

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('.control-button');
    if (!button || button.disabled) return;
    const article = button.closest('.activation');
    const activationId = article.dataset.activationId;
    const intent = button.dataset.intent;
    button.disabled = true;
    setStatus(article, `Loading current ${intent} consequence preview…`);
    try {
      const response = await fetch(`/api/v1/activations/${encodeURIComponent(activationId)}/control-preview?intent=${encodeURIComponent(intent)}`, {
        method: 'POST', credentials: 'same-origin',
        headers: {'Accept': 'application/json', 'X-CSRFToken': csrf}
      });
      if (!response.ok) throw await responseError(response);
      const preview = await response.json();
      const activation = preview.activation || {};
      const reconciliationDigest = preview.reconciliation_digest || null;
      pending = {
        article, activationId, intent,
        expectedVersion: Number(activation.state_version),
        reconciliationDigest,
        idempotencyKey: crypto.randomUUID(),
      };
      fields.intent.textContent = intent;
      fields.target.textContent = activationId;
      fields.state.textContent = `${activation.lifecycle} / ${activation.run_state}${activation.pause_reason ? ` / ${activation.pause_reason}` : ''}`;
      fields.protection.textContent = activation.protection_state || 'UNKNOWN';
      fields.digest.textContent = preview.preview_digest || 'UNKNOWN';
      fields.consequence.textContent = preview.consequence || 'UNKNOWN';
      fields.boundary.textContent = intent === 'USER_TAKEOVER'
        ? 'Takeover stops later automatic writes only after persistence. It does not cancel, protect, or close venue exposure.'
        : intent === 'EXIT_STRATEGY'
          ? 'Acceptance enters exit responsibility. HTTP success or PROCESSING does not mean the account is flat.'
          : 'Resume clears only WRITER_CONTINUITY_LOST. It cannot clear CAP stops, expired authorization, unknown facts, maximum loss, exit, or takeover.';
      fields.error.textContent = '';
      fields.password.value = '';
      fields.confirm.textContent = `Submit ${intent}`;
      fields.confirm.disabled = intent === 'RESUME_ACTIVATION' && !reconciliationDigest;
      if (fields.confirm.disabled) {
        fields.error.textContent = 'Resume is denied: no authoritative reconciliation digest is available in the current preview.';
      }
      setStatus(article, `Preview ${preview.preview_digest || 'UNKNOWN'} loaded at ${preview.previewed_at || 'UNKNOWN'}; no command submitted.`);
      dialog.showModal();
      fields.password.focus();
    } catch (error) {
      setStatus(article, `Preview unavailable: ${error.message}. No command was submitted.`, 'danger');
    } finally {
      button.disabled = false;
    }
  });

  dialog.querySelector('[data-action="cancel"]').addEventListener('click', () => {
    dialog.close(); pending = null;
  });
  dialog.addEventListener('cancel', () => { pending = null; });
  dialog.querySelector('form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!pending || fields.confirm.disabled) return;
    const password = fields.password.value;
    if (!password) { fields.error.textContent = 'Owner password is required.'; return; }
    fields.confirm.disabled = true;
    fields.error.textContent = '';
    setStatus(pending.article, `Submitting ${pending.intent} with idempotency key ${pending.idempotencyKey}…`);
    try {
      const response = await fetch(endpoint(pending.activationId, pending.intent), {
        method: 'POST', credentials: 'same-origin',
        headers: {
          'Accept': 'application/json', 'Content-Type': 'application/json',
          'X-CSRFToken': csrf, 'Idempotency-Key': pending.idempotencyKey,
        },
        body: JSON.stringify({
          expected_version: pending.expectedVersion,
          owner_password: password,
          takeover_scope: {},
        }),
      });
      if (!response.ok) throw await responseError(response);
      const receipt = await response.json();
      setStatus(pending.article, receiptMessage(receipt), receipt.state === 'REJECTED' ? 'danger' : '');
      const article = pending.article;
      const receiptId = receipt.receipt_id;
      dialog.close(); pending = null;
      if (receipt.state === 'PROCESSING') pollReceipt(article, receiptId);
    } catch (error) {
      const knownRejection = Number(error.status) >= 400 && Number(error.status) < 500;
      if (knownRejection) {
        fields.error.textContent = `Command was not accepted: ${error.message}. No Receipt was created; correct the request and retry this confirmation.`;
        setStatus(pending.article, `Command rejected before acceptance: ${error.message}. No Receipt was created.`, 'danger');
      } else {
        fields.error.textContent = `Submission outcome is unknown: ${error.message}. The same idempotency key is retained; retry this confirmation, not a new command.`;
        setStatus(pending.article, `Submission outcome unknown for idempotency key ${pending.idempotencyKey}. Do not create a new command.`, 'danger');
      }
      fields.confirm.disabled = false;
    }
  });
})();
"""


def _operations_document(
    *,
    settings: HalphaSettings,
    authenticated: bool,
    csrf_token: str,
    summary: dict[str, Any] | None = None,
    login_error: str | None = None,
) -> str:
    profile = html.escape(settings.release.profile)
    account = html.escape(settings.release.account_id)
    environment = html.escape(_environment_kind(settings))
    script = ""
    if not authenticated:
        error = (
            f'<p class="alert" role="alert">{html.escape(login_error)}</p>'
            if login_error
            else ""
        )
        body = f"""
          <main class="login-shell">
            <section class="login-panel" aria-labelledby="login-title">
              <p class="eyebrow">LOCAL FALLBACK ENTRY</p>
              <h1 id="login-title">Halpha operations</h1>
              <p class="subtle">Use the same local-owner credential as the workbench.</p>
              {error}
              <form action="/api/v1/session/login" method="post">
                <input type="hidden" name="csrftoken" value="{html.escape(csrf_token)}">
                <input type="text" name="username" value="local-owner" autocomplete="username" readonly tabindex="-1" aria-hidden="true" style="position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap">
                <label for="password">Local owner password</label>
                <input id="password" name="password" type="password" autocomplete="current-password" required autofocus>
                <button type="submit">Sign in</button>
              </form>
              <p class="boundary">127.0.0.1 only · no emergency credential · no remote control</p>
            </section>
          </main>
        """
    else:
        current = summary or {
            "database_available": False,
            "server_fact_cutoff": None,
            "activations": [],
        }
        db_state = "AVAILABLE" if current.get("database_available") else "UNKNOWN"
        cutoff = html.escape(str(current.get("server_fact_cutoff") or "UNKNOWN"))
        activations = list(current.get("activations") or [])
        activation_documents = "".join(
            _operations_activation_document(activation) for activation in activations
        )
        if not activation_documents:
            empty_reason = (
                "Database facts are unavailable. Controls remain closed until authoritative facts return."
                if not current.get("database_available")
                else "No non-completed activation exists in this environment."
            )
            activation_documents = f"""
              <section class="empty-state" aria-labelledby="empty-title">
                <p class="eyebrow">NO OPERABLE ACTIVATION</p>
                <h2 id="empty-title">Nothing to control</h2>
                <p>{html.escape(empty_reason)}</p>
              </section>
            """
        script = '<script src="/operations.js" defer></script>'
        body = f"""
          <header class="statusbar">
            <strong>Halpha operations</strong>
            <span class="env">ENV · {environment}</span>
            <span>ACCOUNT · {account}</span>
            <span class="gate">REAL WRITE · CLOSED</span>
            <span class="cutoff">SERVER FACT CUTOFF · {cutoff}</span>
          </header>
          <main class="workspace">
            <section class="page-head" aria-labelledby="state-title">
              <div>
                <p class="eyebrow">B02 · SAME-PROCESS LIMITED ENTRY</p>
                <h1 id="state-title">Recovery operations</h1>
                <p>Current state, limited controls, and original command receipts. This is the same App control path, not an emergency control plane.</p>
              </div>
              <dl class="summary-facts">
                <div><dt>Profile</dt><dd>{profile}</dd></div>
                <div><dt>Database</dt><dd>{db_state}</dd></div>
                <div><dt>Open activations</dt><dd>{len(activations) if current.get('database_available') else 'UNKNOWN'}</dd></div>
              </dl>
            </section>
            <aside class="effect-boundary" aria-label="Command effect boundary">
              <strong>A Receipt is not a venue result.</strong>
              <span>HTTP success accepts a command. <code>PROCESSING</code> means responsibility remains open; only authoritative venue facts establish external effects.</span>
            </aside>
            <section class="activation-list" aria-label="Open activations">{activation_documents}</section>
            <form class="logout" action="/api/v1/session/logout" method="post">
              <input type="hidden" name="csrftoken" value="{html.escape(csrf_token)}">
              <button class="secondary" type="submit">Sign out</button>
            </form>
          </main>
          <dialog id="control-dialog" aria-labelledby="dialog-title">
            <form method="dialog">
              <div class="dialog-head"><p class="eyebrow">CURRENT CONSEQUENCE PREVIEW</p><h2 id="dialog-title">Confirm limited control</h2></div>
              <dl class="dialog-facts">
                <div><dt>Intent</dt><dd data-preview="intent">—</dd></div>
                <div><dt>Target</dt><dd data-preview="target">—</dd></div>
                <div><dt>Current state</dt><dd data-preview="state">—</dd></div>
                <div><dt>Protection</dt><dd data-preview="protection">—</dd></div>
                <div><dt>Preview digest</dt><dd data-preview="digest">—</dd></div>
              </dl>
              <section class="dialog-consequence"><h3>Consequence</h3><p data-preview="consequence"></p><p data-preview="boundary"></p></section>
              <label for="control-password">Reauthenticate with local owner password</label>
              <input id="control-password" type="password" autocomplete="current-password" required>
              <p class="dialog-error" role="alert" aria-live="assertive"></p>
              <div class="dialog-actions"><button type="button" class="secondary" data-action="cancel">Cancel</button><button type="submit" data-action="confirm">Submit command</button></div>
            </form>
          </dialog>
        """
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="halpha-csrf" content="{html.escape(csrf_token, quote=True)}">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='8' fill='%230b1017'/%3E%3Cpath d='M18 14h8v14h12V14h8v36h-8V36H26v14h-8z' fill='%2358a8d8'/%3E%3C/svg%3E">
  <title>Halpha operations</title>
  <style>
    :root {{ color-scheme:dark; font-family:Inter,"Segoe UI",sans-serif; background:#090e14; color:#e6edf5; --line:#293543; --panel:#101720; --panel-2:#141d28; --muted:#8e9bad; --blue:#69b6e5; --danger:#f08b8f; --green:#84d6ad; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; min-height:100vh; background:linear-gradient(180deg,#0c121a 0,#090e14 420px); }}
    code,dd,.statusbar,th,td {{ font-family:ui-monospace,Consolas,"Cascadia Mono",monospace; }}
    .statusbar {{ position:sticky; top:0; z-index:4; min-height:46px; display:flex; flex-wrap:wrap; align-items:center; gap:14px 22px; padding:9px 22px; border-bottom:1px solid var(--line); background:#0d141deF; backdrop-filter:blur(10px); color:#aab7c7; font-size:11px; font-weight:700; letter-spacing:.035em; }} .statusbar>* {{ min-width:0; overflow-wrap:anywhere; }}
    .statusbar strong {{ margin-right:auto; color:#f2f6fb; font:750 14px/1.4 Inter,"Segoe UI",sans-serif; letter-spacing:0; }}
    .statusbar .env {{ color:#9bd8fc; }} .statusbar .gate {{ color:#f1bc71; }} .statusbar .cutoff {{ color:#8795a8; }}
    .workspace {{ width:min(1240px,calc(100% - 32px)); margin:30px auto 60px; }}
    h1 {{ margin:5px 0 8px; font-size:clamp(27px,3vw,38px); letter-spacing:-.035em; }} h2 {{ margin:4px 0; font-size:18px; }} h3 {{ margin:0 0 10px; color:#bcc8d6; font-size:12px; letter-spacing:.045em; text-transform:uppercase; }}
    p {{ color:#98a6b8; line-height:1.55; }} .eyebrow {{ margin:0; color:#75869a; font:750 10px/1.4 ui-monospace,Consolas,monospace; letter-spacing:.13em; }}
    .page-head {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:32px; align-items:end; padding-bottom:20px; }} .page-head p:not(.eyebrow) {{ margin:0; max-width:760px; }}
    .summary-facts,.primary-facts,.compact-facts,.dialog-facts {{ margin:0; display:grid; gap:1px; background:var(--line); border:1px solid var(--line); }}
    .summary-facts {{ grid-template-columns:repeat(3,minmax(120px,1fr)); }} .primary-facts {{ grid-template-columns:repeat(4,minmax(0,1fr)); }} .compact-facts {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
    dl div {{ min-width:0; background:var(--panel); padding:10px 12px; }} dt {{ color:#78879a; font-size:10px; line-height:1.35; text-transform:uppercase; letter-spacing:.055em; }} dd {{ margin:4px 0 0; color:#dbe4ee; font-size:12px; font-weight:650; line-height:1.45; overflow-wrap:anywhere; }}
    .effect-boundary {{ display:flex; gap:10px 16px; align-items:baseline; margin-bottom:18px; border-left:3px solid #d39a4e; padding:10px 13px; background:#1b1712; color:#d8c5a7; font-size:12px; }} .effect-boundary strong {{ color:#f4d39c; white-space:nowrap; }}
    .activation-list {{ display:grid; gap:18px; }} .activation {{ min-width:0; border:1px solid var(--line); border-top:2px solid #477a99; background:#0e151e; box-shadow:0 18px 50px #0003; }}
    .activation-head {{ display:flex; justify-content:space-between; align-items:end; gap:20px; padding:15px 16px 13px; }} .activation-head>code {{ color:#748397; font-size:10px; overflow-wrap:anywhere; text-align:right; }}
    .detail-grid,.table-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:1px; background:var(--line); }} .detail-grid>section,.table-grid>div {{ min-width:0; padding:14px 16px; background:#0d141d; }}
    .stopped {{ color:#ffae88; }} .clear {{ color:var(--green); }}
    details {{ border-top:1px solid var(--line); }} summary {{ cursor:pointer; padding:11px 16px; color:#aebac8; font-size:12px; font-weight:700; }} summary:hover {{ background:#141d28; }}
    .table-scroll {{ overflow-x:auto; }} table {{ width:100%; border-collapse:collapse; font-size:10px; }} th,td {{ padding:8px 10px; border-top:1px solid #23303e; text-align:left; vertical-align:top; white-space:nowrap; }} th {{ color:#76869a; font-size:9px; text-transform:uppercase; letter-spacing:.055em; }} td {{ color:#c8d3df; }} td code {{ color:#8fc8eb; }} .empty-cell {{ color:#718094; white-space:normal; }}
    .controls {{ min-width:0; border-top:1px solid var(--line); padding:14px 16px; }} .control-row {{ min-width:0; display:grid; grid-template-columns:minmax(280px,1fr) 92px minmax(260px,.7fr); gap:12px 18px; align-items:center; padding:10px 0; border-top:1px solid #202c39; }} .control-row>div {{ min-width:0; }} .control-row:first-of-type {{ border-top:0; }} .control-row strong {{ font-size:13px; }} .control-row p,.control-row small {{ margin:2px 0 0; color:#8795a7; font-size:11px; line-height:1.45; overflow-wrap:anywhere; }}
    button {{ border:1px solid #4a97c3; border-radius:3px; padding:9px 14px; background:#51a9dc; color:#06111a; font-weight:800; cursor:pointer; }} button:hover:not(:disabled) {{ background:#72bee9; }} button:disabled {{ border-color:#323e4d; background:#1d2733; color:#677487; cursor:not-allowed; }} button.secondary {{ border-color:#344355; background:#202b38; color:#d6e0ea; }}
    input:focus-visible,button:focus-visible,summary:focus-visible,.table-scroll:focus-visible {{ outline:3px solid #7ac8f7; outline-offset:2px; }} .command-status {{ margin-top:10px; border-left:2px solid #4a8fb8; padding:9px 11px; background:#101b25; color:#9db3c6; font:600 11px/1.5 ui-monospace,Consolas,monospace; overflow-wrap:anywhere; }} .command-status[data-tone="danger"] {{ border-color:var(--danger); color:#f1b1b4; background:#211419; }}
    .receipts {{ border-bottom:0; }} .receipts .table-scroll {{ padding:0 16px 15px; }} .receipt-state {{ color:#9ed8fb; }}
    .empty-state {{ border:1px dashed #344153; padding:30px; background:#0f161f; }} .empty-state h2 {{ font-size:22px; }} .logout {{ margin-top:18px; }}
    .login-shell {{ min-height:100vh; display:grid; place-items:center; padding:24px; }} .login-panel {{ width:min(420px,100%); border-top:2px solid #4798c9; padding-top:24px; }}
    label {{ display:block; color:#b9c5d2; font-size:12px; margin:18px 0 7px; }} input[type=password] {{ width:100%; padding:11px; border:1px solid #354356; border-radius:3px; background:#101720; color:#f2f6fb; font-size:15px; }} .login-panel button {{ margin-top:16px; }}
    .alert {{ border-left:3px solid var(--danger); padding:10px 12px; background:#24161a; }} .subtle,.boundary {{ color:#8f9cad; line-height:1.6; }} .boundary {{ font-size:11px; margin-top:22px; }}
    dialog {{ width:min(720px,calc(100% - 28px)); max-height:calc(100vh - 40px); overflow:auto; padding:0; border:1px solid #405066; border-top:2px solid #69b6e5; background:#0e151e; color:#e6edf5; box-shadow:0 30px 90px #000b; }} dialog::backdrop {{ background:#03070bd9; }} dialog form {{ padding:20px; }} .dialog-head {{ margin-bottom:14px; }} .dialog-facts {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .dialog-facts div:last-child {{ grid-column:1/-1; }} .dialog-consequence {{ margin-top:14px; border-left:3px solid #d39a4e; padding:11px 13px; background:#191711; }} .dialog-consequence p {{ margin:5px 0; font-size:12px; }} .dialog-error {{ min-height:20px; margin:10px 0; color:#f2a4a8; font-size:12px; }} .dialog-actions {{ display:flex; justify-content:flex-end; gap:10px; }}
    @media (max-width:860px) {{ .page-head,.detail-grid,.table-grid {{ grid-template-columns:1fr; }} .summary-facts {{ grid-template-columns:repeat(3,minmax(0,1fr)); }} .primary-facts {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .control-row {{ grid-template-columns:minmax(0,1fr) 92px; }} .control-row small {{ grid-column:1/-1; }} }}
    @media (max-width:560px) {{ .workspace {{ width:min(1240px,calc(100% - 20px)); margin-top:18px; }} .statusbar {{ position:static; gap:7px 12px; padding:9px 10px; }} .statusbar strong,.statusbar .cutoff {{ width:100%; }} .summary-facts,.primary-facts,.compact-facts,.dialog-facts {{ grid-template-columns:1fr; }} .dialog-facts div:last-child {{ grid-column:auto; }} .activation-head {{ align-items:start; flex-direction:column; }} .activation-head>code {{ text-align:left; }} .control-row {{ grid-template-columns:1fr; }} .control-button {{ width:100%; }} .effect-boundary {{ align-items:start; flex-direction:column; }} }}
    @media (prefers-reduced-motion:reduce) {{ * {{ scroll-behavior:auto!important; }} }}
  </style>
</head>
<body>{body}{script}</body>
</html>"""


def create_app(
    settings: HalphaSettings,
    app_secrets: AppSecrets,
    *,
    repo_root: Path,
    projection: WorkbenchProjection | None = None,
    now: Callable[[], float] = time.time,
    static_dist: Path | None = None,
) -> FastAPI:
    """Construct one authenticated App surface without starting external writers."""

    password_hash = PasswordHash.recommended()
    stored_hash = app_secrets.owner_password_hash.get_secret_value()
    if not any(hasher.identify(stored_hash) for hasher in password_hash.hashers):
        raise WebConfigurationError("OWNER_PASSWORD_HASH_INVALID")

    role_settings = app_settings(settings)
    database = projection or PostgreSQLWorkbenchProjection(
        settings.release.database_name,
        app_secrets.database_password,
        settings.release.environment_id,
    )
    manifest = _manifest_status(repo_root.resolve(), settings)
    rate_limiter = LoginRateLimiter()
    frontend_dist = (static_dist or (repo_root / "frontend" / "dist")).resolve()
    planning_api = PostgreSQLPlanningApi(
        database_name=settings.release.database_name,
        password=app_secrets.database_password,
        environment_id=settings.release.environment_id,
        environment_kind=_environment_kind(settings),
        authority_class=settings.release.authority_class,
        account_ref=settings.release.account_id,
        build_digest=(
            str(manifest["digest"]) if manifest["status"] == "VERIFIED" else None
        ),
    )
    outcomes_api = PostgreSQLOutcomesApi(
        database_name=settings.release.database_name,
        password=app_secrets.database_password,
        environment_id=settings.release.environment_id,
    )

    app = FastAPI(
        title="Halpha local owner API",
        version="0.1.0.dev0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.state.workbench_projection = database

    app.add_middleware(
        SessionMiddleware,
        secret_key=app_secrets.session_signing_secret.get_secret_value(),
        session_cookie="halpha_owner_session",
        max_age=SESSION_ABSOLUTE_LIFETIME_SECONDS,
        same_site="strict",
        https_only=False,
    )
    app.add_middleware(CsrfMiddleware, signing_secret=app_secrets.csrf_signing_secret)
    app.add_middleware(LocalRequestBoundaryMiddleware, port=role_settings.app.port)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    async def require_owner(request: Request) -> None:
        if not session_is_current(request, now=now):
            raise HTTPException(
                status_code=401,
                detail={"code": "OWNER_SESSION_REQUIRED"},
            )

    def require_reauthentication(password: str) -> None:
        try:
            valid = password_hash.verify(password, stored_hash)
        except Exception:
            raise HTTPException(
                status_code=503,
                detail={"code": "OWNER_AUTHENTICATION_UNAVAILABLE"},
            ) from None
        if not valid:
            raise HTTPException(status_code=401, detail={"code": "REAUTHENTICATION_FAILED"})

    def expected_version(if_match: str) -> int:
        value = if_match.strip().removeprefix('W/').strip('"')
        try:
            parsed = int(value)
        except ValueError:
            raise HTTPException(status_code=400, detail={"code": "IF_MATCH_INVALID"}) from None
        if parsed <= 0:
            raise HTTPException(status_code=400, detail={"code": "IF_MATCH_INVALID"})
        return parsed

    def domain_call(operation: Callable[[], Any]) -> Any:
        try:
            return operation()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail={"code": str(exc).strip("'")}) from None
        except (
            ValueError,
            PlanningConflict,
            CapitalConflict,
            CommandConflict,
            OutcomeConflict,
        ) as exc:
            raise HTTPException(status_code=409, detail={"code": str(exc)}) from None
        except PlanningApiUnavailable:
            raise HTTPException(
                status_code=503,
                detail={"code": "PLANNING_DATABASE_UNAVAILABLE"},
            ) from None
        except OutcomesApiUnavailable:
            raise HTTPException(
                status_code=503,
                detail={"code": "OUTCOMES_DATABASE_UNAVAILABLE"},
            ) from None

    async def login_payload(request: Request) -> tuple[str, bool]:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type == "application/json":
            try:
                payload = await request.json()
            except Exception:
                return "", False
            return (str(payload.get("password", "")), False) if isinstance(payload, dict) else ("", False)
        if content_type == "application/x-www-form-urlencoded":
            payload = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
            return payload.get("password", [""])[0], True
        return "", False

    @app.post(
        "/api/v1/session/login",
        response_model=SessionResponse,
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {"password": {"type": "string", "format": "password"}},
                            "required": ["password"],
                            "additionalProperties": False,
                        }
                    }
                },
            }
        },
    )
    async def login(request: Request) -> SessionResponse | RedirectResponse | HTMLResponse:
        supplied, is_form = await login_payload(request)
        csrf_token = _csrf_token(request)
        if not supplied:
            if is_form:
                return HTMLResponse(
                    _operations_document(
                        settings=settings,
                        authenticated=False,
                        csrf_token=csrf_token,
                        login_error="Password is required.",
                    ),
                    status_code=400,
                )
            raise HTTPException(status_code=400, detail={"code": "LOGIN_REQUEST_INVALID"})

        if not rate_limiter.permits_attempt(request):
            retry_after = rate_limiter.retry_after_seconds(request)
            if is_form:
                return HTMLResponse(
                    _operations_document(
                        settings=settings,
                        authenticated=False,
                        csrf_token=csrf_token,
                        login_error="Too many failed attempts. Wait before trying again.",
                    ),
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )
            return JSONResponse(
                {"detail": {"code": "LOGIN_RATE_LIMITED"}},
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )

        try:
            valid = password_hash.verify(supplied, stored_hash)
        except Exception:
            raise HTTPException(
                status_code=503,
                detail={"code": "OWNER_AUTHENTICATION_UNAVAILABLE"},
            ) from None
        if not valid:
            allowed = rate_limiter.record_failure(request)
            if is_form:
                return HTMLResponse(
                    _operations_document(
                        settings=settings,
                        authenticated=False,
                        csrf_token=csrf_token,
                        login_error="Authentication failed.",
                    ),
                    status_code=401 if allowed else 429,
                )
            if not allowed:
                return JSONResponse(
                    {"detail": {"code": "LOGIN_RATE_LIMITED"}},
                    status_code=429,
                    headers={"Retry-After": str(rate_limiter.retry_after_seconds(request))},
                )
            raise HTTPException(status_code=401, detail={"code": "AUTHENTICATION_FAILED"})

        rate_limiter.clear(request)
        request.session.clear()
        request.session.update(
            {
                "owner": OWNER_SESSION_MARKER,
                "issued_at": int(now()),
                "session_id": stdlib_secrets.token_hex(16),
            }
        )
        if is_form:
            return RedirectResponse("/operations", status_code=303)
        return SessionResponse(
            status="AUTHENTICATED",
            absolute_expires_in_seconds=SESSION_ABSOLUTE_LIFETIME_SECONDS,
        )

    @app.post("/api/v1/session/logout", response_model=SessionResponse)
    async def logout(request: Request) -> SessionResponse | RedirectResponse:
        is_form = request.headers.get("content-type", "").startswith(
            "application/x-www-form-urlencoded"
        )
        request.session.clear()
        if is_form:
            return RedirectResponse("/operations", status_code=303)
        return SessionResponse(status="SIGNED_OUT", absolute_expires_in_seconds=None)

    @app.get(
        "/api/v1/overview",
        response_model=OverviewResponse,
        dependencies=[Depends(require_owner)],
    )
    def overview() -> OverviewResponse:
        try:
            summary = database.overview()
        except ProjectionUnavailable:
            raise HTTPException(
                status_code=503,
                detail={"code": "DATABASE_FACTS_UNAVAILABLE"},
            ) from None
        return OverviewResponse(
            environment_kind=_environment_kind(settings),
            environment_id=settings.release.environment_id,
            account_id=settings.release.account_id,
            profile=settings.release.profile,
            authority_class=settings.release.authority_class,
            runtime_real_write_gate="CLOSED",
            construction_package="B04",
            construction_status="IN_PROGRESS",
            server_fact_cutoff=str(summary["server_fact_cutoff"]),
            view_retrieved_at=_utc_now(),
            open_task_count=int(summary["open_task_count"]),
            open_activation_count=int(summary["open_activation_count"]),
            database_name=str(summary["database_name"]),
        )

    @app.get(
        "/api/v1/strategies",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(require_owner)],
    )
    def strategies() -> list[dict[str, Any]]:
        return planning_api.strategies()

    @app.get(
        "/api/v1/strategies/{strategy_id}/schema",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def strategy_schema(strategy_id: str) -> dict[str, Any]:
        return domain_call(lambda: planning_api.strategy_schema(strategy_id))

    @app.get(
        "/api/v1/plans",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(require_owner)],
    )
    def plans() -> list[dict[str, Any]]:
        return domain_call(planning_api.list_plans)

    @app.post(
        "/api/v1/plans",
        response_model=dict[str, Any],
        status_code=201,
        dependencies=[Depends(require_owner)],
    )
    def create_plan(
        payload: PlanDraftPayload,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return domain_call(
            lambda: planning_api.save_new_plan(
                payload,
                idempotency_key=idempotency_key,
                observed_at=datetime.now(UTC),
            )
        )

    @app.put(
        "/api/v1/plans/{plan_id}",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def update_plan(
        plan_id: str,
        payload: PlanDraftPayload,
        if_match: str = Header(alias="If-Match"),
    ) -> dict[str, Any]:
        return domain_call(
            lambda: planning_api.update_plan(
                plan_id,
                payload,
                expected_version=expected_version(if_match),
                observed_at=datetime.now(UTC),
            )
        )

    @app.post(
        "/api/v1/plans/{plan_id}/fix",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def fix_plan(
        plan_id: str,
        idempotency_key: str = Header(alias="Idempotency-Key"),
        if_match: str = Header(alias="If-Match"),
    ) -> dict[str, Any]:
        return domain_call(
            lambda: planning_api.fix_plan(
                plan_id,
                idempotency_key=idempotency_key,
                expected_version=expected_version(if_match),
                observed_at=datetime.now(UTC),
            )
        )

    @app.get(
        "/api/v1/plans/{plan_id}",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def plan(plan_id: str) -> dict[str, Any]:
        return domain_call(lambda: planning_api.get_plan(plan_id))

    @app.get(
        "/api/v1/plan-versions/{plan_version_id}",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def plan_version(plan_version_id: str) -> dict[str, Any]:
        return domain_call(lambda: planning_api.get_plan_version(plan_version_id))

    @app.post(
        "/api/v1/plan-versions/{plan_version_id}/activation-preview",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def activation_preview(plan_version_id: str) -> dict[str, Any]:
        return domain_call(lambda: planning_api.activation_preview(plan_version_id))

    @app.get(
        "/api/v1/capital",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def capital() -> dict[str, Any]:
        return domain_call(planning_api.capital_snapshot)

    @app.get(
        "/api/v1/capital-limits",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(require_owner)],
    )
    def capital_limits() -> list[dict[str, Any]]:
        return list(domain_call(planning_api.capital_snapshot)["limits"])

    @app.post(
        "/api/v1/capital-limits",
        response_model=dict[str, Any],
        status_code=201,
        dependencies=[Depends(require_owner)],
    )
    def create_capital_limit(
        payload: CapitalLimitPayload,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        return domain_call(
            lambda: planning_api.create_capital_limit(
                payload,
                idempotency_key=idempotency_key,
                observed_at=datetime.now(UTC),
            )
        )

    @app.get(
        "/api/v1/allocations",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(require_owner)],
    )
    def allocations() -> list[dict[str, Any]]:
        return list(domain_call(planning_api.capital_snapshot)["allocations"])

    @app.get(
        "/api/v1/activations",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(require_owner)],
    )
    def activations() -> list[dict[str, Any]]:
        return domain_call(planning_api.list_activations)

    @app.post(
        "/api/v1/activations",
        response_model=dict[str, Any],
        status_code=201,
        dependencies=[Depends(require_owner)],
    )
    def create_activation(
        payload: ActivationPayload,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        require_reauthentication(payload.owner_password)
        return domain_call(
            lambda: planning_api.activate(
                payload,
                idempotency_key=idempotency_key,
                observed_at=datetime.now(UTC),
            )
        )

    @app.get(
        "/api/v1/activations/{activation_id}",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def activation(activation_id: str) -> dict[str, Any]:
        return domain_call(lambda: planning_api.activation_detail(activation_id))

    @app.get(
        "/api/v1/activations/{activation_id}/timeline",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(require_owner)],
    )
    def activation_timeline(activation_id: str) -> list[dict[str, Any]]:
        return domain_call(lambda: planning_api.activation_timeline(activation_id))

    @app.post(
        "/api/v1/activations/{activation_id}/control-preview",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def control_preview(activation_id: str, intent: ControlIntent) -> dict[str, Any]:
        return domain_call(lambda: planning_api.control_preview(activation_id, intent))

    def submit_control(
        activation_id: str,
        intent: ControlIntent,
        payload: ControlPayload,
        idempotency_key: str,
    ) -> dict[str, Any]:
        require_reauthentication(payload.owner_password)
        return domain_call(
            lambda: planning_api.submit_control(
                activation_id,
                intent,
                payload,
                idempotency_key=idempotency_key,
                observed_at=datetime.now(UTC),
            )
        )

    @app.post("/api/v1/activations/{activation_id}/stop-new-risk", response_model=dict[str, Any], dependencies=[Depends(require_owner)])
    def stop_new_risk(activation_id: str, payload: ControlPayload, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
        return submit_control(activation_id, ControlIntent.STOP_NEW_RISK, payload, idempotency_key)

    @app.post("/api/v1/activations/{activation_id}/resume-new-risk", response_model=dict[str, Any], dependencies=[Depends(require_owner)])
    def resume_new_risk(activation_id: str, payload: ControlPayload, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
        return submit_control(activation_id, ControlIntent.RESUME_NEW_RISK, payload, idempotency_key)

    @app.post("/api/v1/activations/{activation_id}/resume", response_model=dict[str, Any], dependencies=[Depends(require_owner)])
    def resume_plan_activation(activation_id: str, payload: ControlPayload, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
        return submit_control(activation_id, ControlIntent.RESUME_ACTIVATION, payload, idempotency_key)

    @app.post("/api/v1/activations/{activation_id}/exit", response_model=dict[str, Any], dependencies=[Depends(require_owner)])
    def exit_strategy(activation_id: str, payload: ControlPayload, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
        return submit_control(activation_id, ControlIntent.EXIT_STRATEGY, payload, idempotency_key)

    @app.post("/api/v1/activations/{activation_id}/takeover", response_model=dict[str, Any], dependencies=[Depends(require_owner)])
    def user_takeover(activation_id: str, payload: ControlPayload, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
        return submit_control(activation_id, ControlIntent.USER_TAKEOVER, payload, idempotency_key)

    @app.get(
        "/api/v1/receipts/{receipt_id}",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def receipt(receipt_id: str) -> dict[str, Any]:
        return domain_call(lambda: planning_api.receipt(receipt_id))

    @app.get(
        "/api/v1/tasks",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(require_owner)],
    )
    def tasks() -> list[dict[str, Any]]:
        return domain_call(planning_api.list_tasks)

    @app.post(
        "/api/v1/tasks/{task_id}/acknowledge",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def acknowledge_task(
        task_id: str, payload: TaskAcknowledgePayload
    ) -> dict[str, Any]:
        return domain_call(
            lambda: planning_api.acknowledge_task(
                task_id,
                expected_version=payload.expected_version,
                observed_at=datetime.now(UTC),
            )
        )

    @app.get(
        "/api/v1/reviews",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(require_owner)],
    )
    def reviews() -> list[dict[str, Any]]:
        return domain_call(outcomes_api.list_reviews)

    @app.get(
        "/api/v1/reviews/{review_id}",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def review(review_id: str) -> dict[str, Any]:
        return domain_call(lambda: outcomes_api.read_review(review_id))

    @app.put(
        "/api/v1/reviews/{review_id}",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def refresh_review(
        review_id: str, payload: ReviewRefreshPayload
    ) -> dict[str, Any]:
        return domain_call(lambda: outcomes_api.refresh_review(review_id, payload))

    @app.post(
        "/api/v1/reviews/{review_id}/complete",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def complete_review(
        review_id: str, payload: ReviewCompletionPayload
    ) -> dict[str, Any]:
        require_reauthentication(payload.owner_password)
        return domain_call(lambda: outcomes_api.complete_review(review_id, payload))

    @app.get(
        "/api/v1/improvement-handoffs",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(require_owner)],
    )
    def improvement_handoffs(target_owner: str | None = None) -> list[dict[str, Any]]:
        return domain_call(lambda: outcomes_api.list_handoffs(target_owner))

    @app.get(
        "/api/v1/settings/status",
        response_model=SettingsStatusResponse,
        dependencies=[Depends(require_owner)],
    )
    def settings_status() -> SettingsStatusResponse:
        availability = database.availability()
        return SettingsStatusResponse(
            environment_kind=_environment_kind(settings),
            environment_id=settings.release.environment_id,
            account_id=settings.release.account_id,
            profile=settings.release.profile,
            authority_class=settings.release.authority_class,
            bind=role_settings.app.bind,
            port=role_settings.app.port,
            database_name=settings.release.database_name,
            database_available=bool(availability["database_available"]),
            database_reason_code=availability.get("reason_code"),
            server_fact_cutoff=availability.get("server_fact_cutoff"),
            config_digest=settings_digest(settings),
            build_manifest_status=str(manifest["status"]),
            build_manifest_digest=manifest["digest"],
            build_manifest_violations=list(manifest["violations"]),
            live_write_build_capability="NOT_QUALIFIED",
            b05_package_eligibility="NOT_AUTHORIZED",
            runtime_real_write_gate="CLOSED",
            construction_package="B04",
            construction_status="IN_PROGRESS",
            email_delivery_enabled=settings.email.delivery_enabled,
            email_configuration_status=(
                "CONFIGURED"
                if settings.email.delivery_enabled and app_secrets.smtp_password is not None
                else "DISABLED"
            ),
            view_retrieved_at=_utc_now(),
        )

    @app.post(
        "/api/v1/settings/test-email",
        response_model=dict[str, Any],
        dependencies=[Depends(require_owner)],
    )
    def test_email(payload: TestEmailPayload) -> dict[str, Any]:
        require_reauthentication(payload.owner_password)
        if not settings.email.delivery_enabled or app_secrets.smtp_password is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "EMAIL_DELIVERY_DISABLED"},
            )
        try:
            StdlibSMTPTransport(
                settings.email,
                app_secrets.smtp_password,
            ).send(
                recipient=str(settings.email.owner_recipient),
                content=NotificationContent(
                    subject="Halpha local notification test",
                    body=(
                        "This is a read-only Halpha notification delivery test.\n"
                        f"Environment: {settings.release.environment_id}\n"
                        f"Observed at: {_utc_now()}\n"
                        "No trading command or capital authorization is included."
                    ),
                ),
            )
        except NotificationDeliveryError as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": str(exc)},
            ) from None
        return {
            "status": "DELIVERED",
            "environment_id": settings.release.environment_id,
            "recipient_route_ref": settings.email.owner_route_ref,
            "delivered_at": _utc_now(),
            "business_state_changed": False,
        }

    @app.get("/operations", response_class=HTMLResponse, include_in_schema=False)
    def operations(request: Request) -> HTMLResponse:
        csrf_token = _csrf_token(request)
        authenticated = session_is_current(request, now=now)
        summary: dict[str, Any] | None = None
        if authenticated:
            try:
                summary = database.operations()
            except ProjectionUnavailable:
                summary = {"database_available": False, "activations": []}
        return HTMLResponse(
            _operations_document(
                settings=settings,
                authenticated=authenticated,
                csrf_token=csrf_token,
                summary=summary,
            )
        )

    @app.get("/operations.js", response_class=Response, include_in_schema=False)
    def operations_script() -> Response:
        return Response(
            _operations_script(),
            media_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    assets = frontend_dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/overview", status_code=307)

    @app.get("/{requested_path:path}", include_in_schema=False, response_model=None)
    def frontend(request: Request, requested_path: str) -> FileResponse | HTMLResponse | RedirectResponse:
        segments = requested_path.strip("/").split("/") if requested_path else []
        accepted = (
            segments in (["login"], ["overview"], ["plans"], ["plans", "new"], ["capital"], ["reviews"], ["settings"])
            or (len(segments) == 3 and segments[0] == "plans" and segments[2] == "activate")
            or (len(segments) == 2 and segments[0] in {"activations", "reviews"})
        )
        if not accepted or requested_path.startswith("api/"):
            raise HTTPException(status_code=404, detail={"code": "ROUTE_NOT_FOUND"})
        authenticated = session_is_current(request, now=now)
        if segments == ["login"] and authenticated:
            return RedirectResponse("/overview", status_code=307)
        if segments != ["login"] and not authenticated:
            return RedirectResponse("/login", status_code=307)
        index = frontend_dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse(
            "<!doctype html><html><body><h1>Workbench static artifact unavailable</h1>"
            '<p>The authenticated fallback remains available at <a href="/operations">/operations</a>.</p>'
            "</body></html>",
            status_code=503,
        )

    return app
