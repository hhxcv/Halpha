"""FastAPI composition root for the local owner workbench."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import html
from pathlib import Path
from time import monotonic
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, ValidationError
import psycopg
from starlette.middleware.trustedhost import TrustedHostMiddleware

from halpha.app.projection import (
    PostgreSQLWorkbenchProjection,
    ProjectionUnavailable,
    WorkbenchProjection,
)
from halpha.public_market import (
    BinancePublicMarketContext,
    MarketContext,
    MarketContextProvider,
    MarketContextUnavailable,
    MarketInterval,
    MarketWindow,
    binance_public_market_identity,
)
from halpha.public_market_stream import (
    BinancePublicMarketStream,
    PublicMarketStreamProvider,
)
from halpha.public_instrument_rules import (
    BinancePublicInstrumentRules,
    InstrumentRulesProvider,
    InstrumentRulesUnavailable,
    binance_public_instrument_rules_identity,
)
from halpha.app.planning_api import (
    ActivationPayload,
    ControlPayload,
    PlanCreatePayload,
    PlanDraftPayload,
    PlanningApiUnavailable,
    PostgreSQLPlanningApi,
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
    allowed_local_origin,
)
from halpha.capital.repository import CapitalConflict
from halpha.configuration import HalphaSettings, app_settings
from halpha.live_write_gate import LiveWriteGateStatus, evaluate_live_write_gate
from halpha.product_build import calculate_product_build_id
from halpha.planning.repository import PlanningConflict
from halpha.planning.order_schedule import (
    OrderSchedulePreview,
    OrderScheduleSpec,
    SinglePrice,
    compile_order_schedule,
    validate_current_order_schedule_support,
)
from halpha.planning.registry import DecisionBasisKind, Direction
from halpha.planning.transitions import ControlIntent
from halpha.outcomes.repository import OutcomeConflict
from halpha.user_workbench.repository import CommandConflict


ACTIVATION_SCHEDULE_PREVIEW_TTL_SECONDS = 60


class WebConfigurationError(RuntimeError):
    """Sanitized failure to construct the local web surface."""


class FrozenResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OverviewResponse(FrozenResponse):
    environment_kind: str
    environment_id: str
    account_id: str
    profile: str
    authority_class: str
    runtime_real_write_gate: str
    server_fact_cutoff: str
    view_retrieved_at: str
    open_activation_count: int
    database_name: str


class OrderSchedulePreviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule_ref: str
    decision_basis_kind: DecisionBasisKind = DecisionBasisKind.DIRECT_EXECUTION
    venue_ref: str = "BINANCE_USDM"
    instrument_ref: str
    direction: Direction
    max_notional: str
    reference_price: str | None = None
    spec: OrderScheduleSpec


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
    product_build_id: str
    app_executor_product_build_consistent: bool | None
    executor_status: str
    executor_status_checked_at: str
    configured_runtime_real_write_gate: str
    runtime_real_write_gate: str
    live_write_gate_violations: list[str]
    authorized_activation_id: str | None
    email_delivery_enabled: bool
    email_configuration_status: str
    view_retrieved_at: str


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _environment_kind(settings: HalphaSettings) -> str:
    return "DEMO" if settings.release.profile == "BINANCE_DEMO" else "LIVE"


def _csrf_token(request: Request) -> str:
    getter = request.scope.get("csrftoken")
    if not callable(getter):
        raise WebConfigurationError("CSRF_SCOPE_TOKEN_MISSING")
    return str(getter())


def _operation_value(value: Any, *, fallback: str = "UNKNOWN") -> str:
    if value is None or value == "":
        return fallback
    return html.escape(str(value))


_USER_VISIBLE_TIME_ZONE = ZoneInfo("Asia/Shanghai")


def _operation_time(value: Any, *, fallback: str = "UNKNOWN") -> str:
    if value is None or value == "":
        return fallback
    if isinstance(value, datetime):
        parsed = value
    else:
        token = str(value).strip()
        if token.endswith("Z"):
            token = f"{token[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(token)
        except ValueError:
            return fallback
    if parsed.utcoffset() is None:
        return fallback
    return html.escape(
        f"{parsed.astimezone(_USER_VISIBLE_TIME_ZONE):%Y-%m-%d %H:%M:%S} UTC+8"
    )


def _operations_activation_document(activation: dict[str, Any]) -> str:
    activation_id = _operation_value(activation.get("activation_id"))
    raw_activation_id = html.escape(str(activation.get("activation_id", "")), quote=True)
    instrument = _operation_value(activation.get("instrument_ref"))
    state_version = int(activation.get("state_version", 0))
    lifecycle = str(activation.get("lifecycle", "UNKNOWN"))
    run_state = str(activation.get("run_state", "UNKNOWN"))
    pause_reason = str(activation.get("pause_reason") or "NONE")
    stopped = {str(item) for item in activation.get("stopped_categories", [])}
    terminal = lifecycle in {"USER_TAKEOVER", "COMPLETED"}
    new_risk_stopped = bool(
        {"NEW_RISK", "ALL_EXCHANGE_CHANGES"}.intersection(stopped)
    ) or lifecycle in {"EXITING", "USER_TAKEOVER"}
    exiting = lifecycle == "EXITING"

    def control(
        intent: str,
        label: str,
        consequence: str,
        disabled: bool,
        disabled_reason: str = "",
        tone: str = "",
    ) -> str:
        disabled_attr = " disabled" if disabled else ""
        reason = f"<small>{html.escape(disabled_reason)}</small>" if disabled_reason else ""
        return f"""
          <section class="control {html.escape(tone)}">
            <h3>{html.escape(label)}</h3>
            <p>{html.escape(consequence)}</p>
            {reason}
            <button type="button" class="control-button" data-intent="{html.escape(intent, quote=True)}"{disabled_attr}>查看后果</button>
          </section>
        """

    run_state_text = run_state
    if pause_reason != "NONE":
        run_state_text = f"{run_state} · {pause_reason}"
    new_risk_text = "已停止" if new_risk_stopped else "未记录停止"

    return f"""
      <article class="activation" data-activation-id="{raw_activation_id}" data-state-version="{state_version}">
        <div class="activation-head">
          <div><h2>{instrument} · {_operation_value(activation.get('direction'))}</h2><code>{activation_id}</code></div>
          <span class="state">{_operation_value(lifecycle)}</span>
        </div>
        <dl class="activation-facts">
          <div><dt>运行状态</dt><dd>{_operation_value(run_state_text)}</dd></div>
          <div><dt>新增风险</dt><dd class="{'stopped' if new_risk_stopped else ''}">{new_risk_text}</dd></div>
          <div><dt>保护状态</dt><dd>{_operation_value(activation.get('protection_state'))}</dd></div>
          <div><dt>场所事实截止</dt><dd>{_operation_time(activation.get('latest_venue_cutoff'))}</dd></div>
        </dl>
        <div class="controls" aria-label="{instrument} 故障控制">
          {control('STOP_NEW_RISK', '停止新增风险', '停止新的开仓和加仓；已有保护和退出责任继续。', terminal or new_risk_stopped, '当前已停止新增风险。' if new_risk_stopped else '接管或完成后不可用。' if terminal else '')}
          {control('EXIT_STRATEGY', '退出策略', '由 Halpha 进入退出责任；接受命令不代表 Binance 仓位已经平仓。', terminal or exiting, '当前已经进入退出。' if exiting else '接管或完成后不可用。' if terminal else '')}
          {control('USER_TAKEOVER', '用户接管', '停止 Halpha 后续自动交易操作；撤单、保护和平仓需在 Binance 核对处理。', terminal, '当前已经接管或完成。' if terminal else '', 'danger')}
        </div>
        <div class="command-status" role="status" aria-live="polite" tabindex="-1">尚未提交控制命令。</div>
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
    consequence: dialog.querySelector('[data-preview="consequence"]'),
    boundary: dialog.querySelector('[data-preview="boundary"]'),
    error: dialog.querySelector('.dialog-error'),
    confirm: dialog.querySelector('[data-action="confirm"]'),
  };
  let pending = null;

  const labels = {
    STOP_NEW_RISK: '停止新增风险',
    EXIT_STRATEGY: '退出策略',
    USER_TAKEOVER: '用户接管',
  };
  const endpoint = (activationId, intent) => {
    const suffix = {
      STOP_NEW_RISK: 'stop-new-risk',
      EXIT_STRATEGY: 'exit',
      USER_TAKEOVER: 'takeover',
    }[intent];
    return `/api/v1/activations/${encodeURIComponent(activationId)}/${suffix}`;
  };
  const boundary = (intent) => ({
    STOP_NEW_RISK: '只停止新的开仓和加仓；不会撤单、平仓，也不会停止已有保护和退出责任。',
    EXIT_STRATEGY: '命令被接受只表示 Halpha 进入退出责任，不表示 Binance 仓位已经平仓。',
    USER_TAKEOVER: '持久化成功后 Halpha 不再发起新的交易操作；现有订单、保护和仓位必须在 Binance 核对。',
  })[intent] || 'UNKNOWN';
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
  const lockControls = (article) => {
    article.querySelectorAll('.control-button').forEach((button) => { button.disabled = true; });
  };
  const receiptMessage = (receipt) => {
    const reason = receipt.reason_code ? ` · ${receipt.reason_code}` : '';
    const boundary = receipt.state === 'PROCESSING'
      ? '命令仍在处理中，不代表 Binance 已经发生变化。'
      : '这是 Halpha 命令结果；Binance 结果仍需在官方入口核对。';
    return `${receipt.state} · 回执 ${receipt.receipt_id}${reason}。${boundary}`;
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
      setStatus(article, `回执 ${receiptId} 查询结果未知：${error.message}。请保留该回执，不要提交替代命令。`, 'danger');
    }
  };

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('.control-button');
    if (!button || button.disabled) return;
    const article = button.closest('.activation');
    const activationId = article.dataset.activationId;
    const intent = button.dataset.intent;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    setStatus(article, `正在读取“${labels[intent]}”的当前后果…`);
    try {
      const response = await fetch(`/api/v1/activations/${encodeURIComponent(activationId)}/control-preview?intent=${encodeURIComponent(intent)}`, {
        method: 'POST', credentials: 'same-origin',
        headers: {'Accept': 'application/json', 'X-CSRFToken': csrf}
      });
      if (!response.ok) throw await responseError(response);
      const preview = await response.json();
      const activation = preview.activation || {};
      pending = {
        article, activationId, intent,
        expectedVersion: Number(activation.state_version),
        idempotencyKey: crypto.randomUUID(),
        trigger: button,
      };
      fields.intent.textContent = labels[intent] || intent;
      fields.target.textContent = activationId;
      fields.state.textContent = `${activation.lifecycle} / ${activation.run_state}${activation.pause_reason ? ` / ${activation.pause_reason}` : ''}`;
      fields.protection.textContent = activation.protection_state || 'UNKNOWN';
      fields.consequence.textContent = preview.consequence || 'UNKNOWN';
      fields.boundary.textContent = boundary(intent);
      fields.error.textContent = '';
      fields.confirm.textContent = `确认${labels[intent] || intent}`;
      fields.confirm.disabled = false;
      setStatus(article, '已读取当前后果，尚未提交命令。');
      dialog.showModal();
      fields.confirm.focus();
    } catch (error) {
      setStatus(article, `无法读取当前后果：${error.message}。没有提交命令。`, 'danger');
    } finally {
      button.removeAttribute('aria-busy');
      if (!pending) button.disabled = false;
    }
  });

  dialog.querySelector('[data-action="cancel"]').addEventListener('click', () => {
    const trigger = pending?.trigger;
    dialog.close(); pending = null;
    if (trigger) { trigger.disabled = false; trigger.focus(); }
  });
  dialog.addEventListener('cancel', () => {
    const trigger = pending?.trigger;
    pending = null;
    if (trigger) { trigger.disabled = false; window.setTimeout(() => trigger.focus(), 0); }
  });
  dialog.querySelector('form').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!pending || fields.confirm.disabled) return;
    fields.confirm.disabled = true;
    fields.error.textContent = '';
    setStatus(pending.article, `正在提交“${labels[pending.intent]}”…`);
    try {
      const response = await fetch(endpoint(pending.activationId, pending.intent), {
        method: 'POST', credentials: 'same-origin',
        headers: {
          'Accept': 'application/json', 'Content-Type': 'application/json',
          'X-CSRFToken': csrf, 'Idempotency-Key': pending.idempotencyKey,
        },
        body: JSON.stringify({
          expected_version: pending.expectedVersion,
          takeover_scope: {},
        }),
      });
      if (!response.ok) throw await responseError(response);
      const receipt = await response.json();
      lockControls(pending.article);
      setStatus(pending.article, receiptMessage(receipt), receipt.state === 'REJECTED' ? 'danger' : '');
      const article = pending.article;
      const receiptId = receipt.receipt_id;
      dialog.close(); pending = null;
      article.querySelector('.command-status')?.focus();
      if (receipt.state === 'PROCESSING') pollReceipt(article, receiptId);
    } catch (error) {
      const knownRejection = Number(error.status) >= 400 && Number(error.status) < 500;
      if (knownRejection) {
        fields.error.textContent = `命令未被接受：${error.message}。没有建立回执，请关闭并刷新页面。`;
        setStatus(pending.article, `命令未被接受：${error.message}。没有建立回执。`, 'danger');
      } else {
        fields.error.textContent = `提交结果未知：${error.message}。再次确认会沿用同一请求，不会建立替代命令。`;
        setStatus(pending.article, `提交结果未知；已保留同一请求身份。不要从其他入口重复提交。`, 'danger');
      }
      fields.confirm.disabled = false;
    }
  });
})();
"""


def _operations_document(
    *,
    settings: HalphaSettings,
    csrf_token: str,
    summary: dict[str, Any] | None = None,
) -> str:
    account = html.escape(settings.release.account_id)
    environment_kind = _environment_kind(settings)
    environment = html.escape(environment_kind)
    venue_url = (
        "https://demo.binance.com/"
        if environment_kind == "DEMO"
        else "https://www.binance.com/"
    )
    current = summary or {
        "database_available": False,
        "server_fact_cutoff": None,
        "activations": [],
    }
    db_state = "可用" if current.get("database_available") else "不可用"
    cutoff = _operation_time(current.get("server_fact_cutoff"))
    activations = list(current.get("activations") or [])
    activation_documents = "".join(
        _operations_activation_document(activation) for activation in activations
    )
    if not activation_documents:
        empty_reason = (
            "当前无法读取 Halpha 数据库事实，所有控制保持关闭。请停止 Executor，并在 Binance 官方入口核对订单和仓位。"
            if not current.get("database_available")
            else "当前环境没有未结束的策略运行。"
        )
        activation_documents = f"""
          <section class="empty-state" aria-labelledby="empty-title">
            <h2 id="empty-title">无需接管</h2>
            <p>{html.escape(empty_reason)}</p>
          </section>
        """
    script = '<script src="/operations.js" defer></script>'
    body = f"""
      <header class="statusbar">
        <strong>Halpha</strong>
        <span class="env">{environment}</span>
        <span class="account">账户 · {account}</span>
        <a href="{venue_url}" target="_blank" rel="noreferrer">打开 Binance 官方入口</a>
      </header>
      <main class="workspace">
        <section class="page-head" aria-labelledby="state-title">
          <h1 id="state-title">故障接管</h1>
          <p>主界面不可用时，仅用这里停止、退出或接管；需要手工处理时再打开 Binance。</p>
        </section>
        <dl class="summary-facts">
          <div><dt>数据库</dt><dd>{db_state}</dd></div>
          <div><dt>事实截止</dt><dd>{cutoff}</dd></div>
          <div><dt>未结束策略</dt><dd>{len(activations) if current.get('database_available') else 'UNKNOWN'}</dd></div>
        </dl>
        <aside class="effect-boundary" aria-label="控制边界">
          页面只记录 Halpha 的停止、退出或接管决定；命令被接受不代表 Binance 已经撤单、保护或平仓。
        </aside>
        <section class="activation-list" aria-label="未结束策略">{activation_documents}</section>
      </main>
      <dialog id="control-dialog" aria-labelledby="dialog-title">
        <form method="dialog">
          <div class="dialog-head"><h2 id="dialog-title">确认故障控制</h2></div>
          <dl class="dialog-facts">
            <div><dt>操作</dt><dd data-preview="intent">—</dd></div>
            <div><dt>策略运行</dt><dd data-preview="target">—</dd></div>
            <div><dt>当前状态</dt><dd data-preview="state">—</dd></div>
            <div><dt>保护状态</dt><dd data-preview="protection">—</dd></div>
          </dl>
          <section class="dialog-consequence"><h3>后果</h3><p data-preview="consequence"></p><p data-preview="boundary"></p></section>
          <p class="dialog-error" role="alert" aria-live="assertive"></p>
          <div class="dialog-actions"><button type="button" class="secondary" data-action="cancel">取消</button><button type="submit" data-action="confirm">确认操作</button></div>
        </form>
      </dialog>
    """
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="halpha-csrf" content="{html.escape(csrf_token, quote=True)}">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='12' fill='%23FFD43B'/%3E%3Cpath d='M17 14h9v14h12V14h9v36h-9V36H26v14h-9z' fill='%23111827'/%3E%3C/svg%3E">
  <title>Halpha 故障接管</title>
  <style>
    :root {{ color-scheme:light; font-family:Inter,"Segoe UI",sans-serif; background:#f7f8fb; color:#111827; --line:#dbe1ea; --muted:#4b5563; --faint:#8892a1; --accent:#ffd43b; --accent-border:#e0b800; --accent-text:#c2410c; --success:#236553; --success-bg:#eef7f3; --success-border:#bfdccd; --warning:#7a4100; --warning-bg:#fff7dd; --warning-border:#ebcb72; --danger:#873631; --danger-bg:#fff1ef; --danger-border:#e7b8b3; --info:#3a4f82; --info-bg:#f0f4ff; --info-border:#cbd6f3; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; min-width:320px; min-height:100vh; background:#f7f8fb; }}
    code,dd,.account {{ font-family:"Cascadia Mono",Consolas,ui-monospace,monospace; font-variant-numeric:tabular-nums; }}
    .statusbar {{ min-height:64px; display:flex; align-items:center; gap:16px; padding:10px 24px; border-bottom:1px solid var(--line); background:#fff; }}
    .statusbar strong {{ margin-right:2px; font-size:20px; }} .statusbar .env {{ border:1px solid var(--accent-border); border-radius:999px; padding:4px 9px; background:var(--accent); font-size:12px; font-weight:800; }}
    .statusbar .account {{ min-width:0; margin-right:auto; color:var(--muted); font-size:12px; overflow-wrap:anywhere; }} .statusbar a {{ border:1px solid var(--line); border-radius:10px; padding:9px 12px; color:#111827; background:#fff; font-size:13px; font-weight:700; text-decoration:none; }} .statusbar a:hover {{ background:#f2f4f7; }}
    .workspace {{ width:min(920px,calc(100% - 32px)); margin:28px auto 56px; }}
    h1 {{ margin:0; font-size:28px; line-height:1.15; }} h2 {{ margin:0; font-size:18px; }} h3 {{ margin:0; font-size:14px; }} p {{ margin:6px 0 0; color:var(--muted); line-height:1.5; }}
    .page-head {{ margin-bottom:18px; }} .page-head p {{ max-width:720px; }}
    .summary-facts,.activation-facts,.dialog-facts {{ margin:0; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1px; overflow:hidden; border:1px solid var(--line); border-radius:14px; background:var(--line); }}
    .activation-facts {{ grid-template-columns:repeat(4,minmax(0,1fr)); }} .dialog-facts {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
    dl div {{ min-width:0; padding:11px 12px; background:#fff; }} dt {{ color:var(--muted); font-size:11px; }} dd {{ margin:5px 0 0; font-size:12px; font-weight:700; line-height:1.4; overflow-wrap:anywhere; }} dd.stopped {{ color:var(--danger); }}
    .effect-boundary {{ margin:16px 0; border:1px solid var(--warning-border); border-left:3px solid #f59e0b; border-radius:10px; padding:10px 12px; background:var(--warning-bg); color:var(--warning); font-size:12px; line-height:1.5; }}
    .activation-list {{ display:grid; gap:14px; }} .activation {{ min-width:0; overflow:hidden; border:1px solid var(--line); border-radius:14px; background:#fff; }}
    .activation-head {{ display:flex; justify-content:space-between; align-items:center; gap:16px; padding:14px 16px; }} .activation-head code {{ display:block; margin-top:5px; color:var(--muted); font-size:10px; overflow-wrap:anywhere; }} .state {{ border:1px solid var(--line); border-radius:999px; padding:4px 8px; color:var(--muted); font-size:11px; font-weight:800; }}
    .controls {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); border-top:1px solid var(--line); }} .control {{ display:flex; min-width:0; flex-direction:column; align-items:flex-start; padding:14px 16px; border-right:1px solid var(--line); }} .control:last-child {{ border-right:0; }} .control p,.control small {{ font-size:12px; }} .control small {{ min-height:18px; margin-top:5px; color:var(--danger); }} .control button {{ margin-top:auto; }}
    button {{ min-height:38px; border:1px solid var(--accent-border); border-radius:10px; padding:8px 13px; background:var(--accent); color:#111827; font:700 13px/1.2 inherit; cursor:pointer; }} button:hover:not(:disabled) {{ background:#ffdf5a; }} button:active:not(:disabled) {{ transform:scale(.985); }} button:disabled {{ border-color:var(--line); background:#f2f4f7; color:var(--faint); cursor:not-allowed; }} button.secondary {{ border-color:var(--line); background:#fff; }} .control.danger button:not(:disabled) {{ border-color:var(--danger-border); background:#fff; color:var(--danger); }}
    a:focus-visible,button:focus-visible {{ outline:3px solid #ffe98a; outline-offset:2px; }} .command-status {{ border-top:1px solid var(--line); padding:11px 16px; color:var(--muted); background:#f9fafb; font:600 12px/1.5 ui-monospace,Consolas,monospace; overflow-wrap:anywhere; }} .command-status[data-tone="danger"] {{ color:var(--danger); background:var(--danger-bg); }}
    .empty-state {{ border:1px dashed #b9c3d0; border-radius:14px; padding:24px; background:#fff; }} .empty-state p {{ margin-bottom:0; }}
    dialog {{ width:min(620px,calc(100% - 28px)); max-height:calc(100vh - 40px); overflow:auto; padding:0; border:1px solid #b9c3d0; border-radius:14px; background:#fff; color:#111827; }} dialog::backdrop {{ background:#1118278c; }} dialog form {{ padding:20px; }} .dialog-head {{ margin-bottom:14px; }} .dialog-consequence {{ margin-top:14px; border-left:3px solid #f59e0b; padding:11px 13px; background:var(--warning-bg); color:var(--warning); }} .dialog-consequence p {{ color:inherit; font-size:12px; }} .dialog-error {{ min-height:20px; margin:10px 0; color:var(--danger); font-size:12px; }} .dialog-actions {{ display:flex; justify-content:flex-end; gap:10px; }}
    @media (max-width:700px) {{ .statusbar {{ flex-wrap:wrap; gap:8px 10px; padding:10px 14px; }} .statusbar .account {{ order:4; flex-basis:100%; }} .workspace {{ width:calc(100% - 24px); margin-top:20px; }} .summary-facts,.activation-facts,.dialog-facts,.controls {{ grid-template-columns:1fr; }} .control {{ border-right:0; border-bottom:1px solid var(--line); }} .control:last-child {{ border-bottom:0; }} .activation-head {{ align-items:flex-start; flex-direction:column; }} .statusbar a {{ margin-left:auto; }} }}
    @media (prefers-reduced-motion:reduce) {{ * {{ transition:none!important; }} }}
  </style>
</head>
<body>{body}{script}</body>
</html>"""


def create_app(
    settings: HalphaSettings,
    app_secrets: AppSecrets,
    *,
    repo_root: Path,
    product_build_id: str | None = None,
    projection: WorkbenchProjection | None = None,
    market_context_provider: MarketContextProvider | None = None,
    market_stream_provider: PublicMarketStreamProvider | None = None,
    instrument_rules_provider: InstrumentRulesProvider | None = None,
    static_dist: Path | None = None,
    monotonic_provider: Callable[[], float] | None = None,
) -> FastAPI:
    """Construct one local App surface without starting external writers."""

    role_settings = app_settings(settings)
    database = projection or PostgreSQLWorkbenchProjection(
        settings.release.database_name,
        app_secrets.database_password,
        settings.release.environment_id,
    )
    public_market_context = market_context_provider or BinancePublicMarketContext(
        settings.release.profile,
        proxy_url=settings.app.public_market_proxy_url,
    )
    _, expected_market_source = binance_public_market_identity(settings.release.profile)
    _, expected_instrument_rules_source = binance_public_instrument_rules_identity(
        settings.release.profile
    )

    def require_current_market_source(source: str) -> None:
        if source != expected_market_source:
            raise MarketContextUnavailable("MARKET_SOURCE_ENVIRONMENT_MISMATCH")

    def require_current_instrument_rules_source(source: str) -> None:
        if source != expected_instrument_rules_source:
            raise InstrumentRulesUnavailable(
                "INSTRUMENT_RULES_SOURCE_ENVIRONMENT_MISMATCH"
            )

    public_market_stream = market_stream_provider or BinancePublicMarketStream(
        settings.release.profile,
        proxy_url=settings.app.public_market_proxy_url,
    )
    public_instrument_rules = (
        instrument_rules_provider
        or BinancePublicInstrumentRules(
            settings.release.profile,
            proxy_url=settings.app.public_market_proxy_url,
        )
    )
    current_product_build_id = product_build_id or calculate_product_build_id(
        repo_root.resolve(), settings
    )
    schedule_preview_clock = monotonic_provider or monotonic
    schedule_previews: dict[
        tuple[str, str], tuple[float, OrderSchedulePreview]
    ] = {}

    def remember_schedule_preview(
        plan_version_id: str,
        schedule: OrderSchedulePreview,
    ) -> None:
        now = schedule_preview_clock()
        for key, (expires_at, _) in tuple(schedule_previews.items()):
            if expires_at <= now:
                schedule_previews.pop(key, None)
        schedule_previews[(plan_version_id, schedule.schedule_digest)] = (
            now + ACTIVATION_SCHEDULE_PREVIEW_TTL_SECONDS,
            schedule,
        )

    def recalled_schedule_preview(
        plan_version_id: str,
        expected_digest: str | None,
    ) -> OrderSchedulePreview:
        if expected_digest is None:
            raise ValueError("ACTIVATION_PREVIEW_STALE")
        key = (plan_version_id, expected_digest)
        cached = schedule_previews.get(key)
        if cached is None:
            raise ValueError("ACTIVATION_PREVIEW_STALE")
        expires_at, schedule = cached
        if expires_at <= schedule_preview_clock():
            schedule_previews.pop(key, None)
            raise ValueError("ACTIVATION_PREVIEW_STALE")
        return schedule

    def current_gate_status() -> LiveWriteGateStatus:
        base_status = evaluate_live_write_gate(
            repo_root.resolve(),
            settings,
            current_product_build_id=current_product_build_id,
        )
        if base_status.configured_runtime_real_write_gate != "OPEN":
            return base_status
        try:
            with psycopg.connect(
                host="127.0.0.1",
                port=5432,
                dbname=settings.release.database_name,
                user=f"{settings.release.database_name}_app",
                password=app_secrets.database_password.get_secret_value(),
                connect_timeout=2,
                autocommit=True,
            ) as connection:
                return evaluate_live_write_gate(
                    repo_root.resolve(),
                    settings,
                    current_product_build_id=current_product_build_id,
                    connection=connection,
                )
        except Exception:
            return base_status

    frontend_dist = (static_dist or (repo_root / "frontend" / "dist")).resolve()
    planning_api = PostgreSQLPlanningApi(
        database_name=settings.release.database_name,
        password=app_secrets.database_password,
        environment_id=settings.release.environment_id,
        environment_kind=_environment_kind(settings),
        authority_class=settings.release.authority_class,
        account_ref=settings.release.account_id,
        product_build_id=current_product_build_id,
        profile=settings.release.profile,
        gate_status_provider=current_gate_status,
    )
    outcomes_api = PostgreSQLOutcomesApi(
        database_name=settings.release.database_name,
        password=app_secrets.database_password,
        environment_id=settings.release.environment_id,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            await public_market_stream.close()

    app = FastAPI(
        title="Halpha local owner API",
        version="0.1.0.dev0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
        lifespan=lifespan,
    )
    app.state.workbench_projection = database
    app.state.live_write_gate_status_provider = current_gate_status
    app.state.public_market_stream = public_market_stream

    app.add_middleware(CsrfMiddleware, signing_secret=app_secrets.csrf_signing_secret)
    app.add_middleware(LocalRequestBoundaryMiddleware, port=role_settings.app.port)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

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
        except ValidationError as exc:
            codes = {
                str(error.get("ctx", {}).get("error"))
                for error in exc.errors(include_url=False)
                if error.get("ctx", {}).get("error") is not None
            }
            code = codes.pop() if len(codes) == 1 else "INPUT_VALIDATION_FAILED"
            raise HTTPException(status_code=409, detail={"code": code}) from None
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

    def current_executor_status() -> dict[str, Any]:
        reader = getattr(database, "executor_status", None)
        if not callable(reader):
            return {
                "status": "UNKNOWN",
                "checked_at": _utc_now(),
                "product_build_consistent": None,
            }
        try:
            return dict(reader(current_product_build_id))
        except ProjectionUnavailable:
            return {
                "status": "UNKNOWN",
                "checked_at": _utc_now(),
                "product_build_consistent": None,
            }

    async def compile_activation_schedule(
        preview: dict[str, Any],
        *,
        refresh_rules: bool = False,
    ) -> OrderSchedulePreview | None:
        raw_spec = preview.get("order_schedule_spec")
        if raw_spec is None:
            return None
        instrument_ref = str(preview["instrument_ref"])
        spec = domain_call(lambda: OrderScheduleSpec.model_validate(raw_spec))
        domain_call(
            lambda: validate_current_order_schedule_support(
                DecisionBasisKind(str(preview["decision_basis_kind"])),
                spec,
            )
        )
        try:
            refresh = getattr(public_instrument_rules, "refresh", None)
            rules = (
                await refresh(instrument_ref)
                if refresh_rules and callable(refresh)
                else await public_instrument_rules.fetch(instrument_ref)
            )
            require_current_instrument_rules_source(rules.source)
            price_plan = spec.price_distribution
            reference_price = None
            if isinstance(price_plan, SinglePrice) and price_plan.limit_price is None:
                context = await public_market_context.fetch(instrument_ref, 20)
                require_current_market_source(context.source)
                reference_price = context.reference_price
        except (InstrumentRulesUnavailable, MarketContextUnavailable) as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": str(exc)},
            ) from None
        return compile_order_schedule(
            spec,
            rules,
            venue_ref=str(preview.get("venue_ref", "BINANCE_USDM")),
            instrument_ref=instrument_ref,
            direction=Direction(str(preview["direction"])),
            max_notional=str(preview["trade_amount"]),
            schedule_ref=str(preview["plan_version_id"]),
            reference_price=reference_price,
        )

    @app.get(
        "/api/v1/overview",
        response_model=OverviewResponse,
    )
    def overview() -> OverviewResponse:
        try:
            summary = database.overview()
        except ProjectionUnavailable:
            raise HTTPException(
                status_code=503,
                detail={"code": "DATABASE_FACTS_UNAVAILABLE"},
            ) from None
        gate_status = current_gate_status()
        return OverviewResponse(
            environment_kind=_environment_kind(settings),
            environment_id=settings.release.environment_id,
            account_id=settings.release.account_id,
            profile=settings.release.profile,
            authority_class=settings.release.authority_class,
            runtime_real_write_gate=gate_status.runtime_real_write_gate,
            server_fact_cutoff=str(summary["server_fact_cutoff"]),
            view_retrieved_at=_utc_now(),
            open_activation_count=int(summary["open_activation_count"]),
            database_name=str(summary["database_name"]),
        )

    @app.get(
        "/api/v1/strategies",
        response_model=list[dict[str, Any]],
    )
    def strategies() -> list[dict[str, Any]]:
        return planning_api.strategies()

    @app.get(
        "/api/v1/market-context",
        response_model=MarketContext,
    )
    async def market_context(
        instrument_ref: str = "BTCUSDT-PERP",
        channel_lookback_15m: int = 20,
    ) -> MarketContext:
        try:
            context = await public_market_context.fetch(
                instrument_ref,
                channel_lookback_15m,
            )
            require_current_market_source(context.source)
            return context
        except MarketContextUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": str(exc)},
            ) from None

    @app.get(
        "/api/v1/market-window",
        response_model=MarketWindow,
    )
    async def market_window(
        instrument_ref: str,
        start_at: datetime,
        end_at: datetime,
        interval: MarketInterval = "1m",
    ) -> MarketWindow:
        if start_at.utcoffset() is None or end_at.utcoffset() is None:
            raise HTTPException(
                status_code=422,
                detail={"code": "MARKET_WINDOW_TIMEZONE_REQUIRED"},
            )
        try:
            window = await public_market_context.fetch_window(
                instrument_ref,
                interval,
                start_at,
                end_at,
            )
            require_current_market_source(window.source)
            return window
        except MarketContextUnavailable as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": str(exc)},
            ) from None

    @app.websocket("/api/v1/market-stream")
    async def market_stream(
        websocket: WebSocket,
        instrument_ref: str = "BTCUSDT-PERP",
    ) -> None:
        origin = websocket.headers.get("origin")
        if websocket.headers.get("authorization") is not None:
            await websocket.close(
                code=1008,
                reason="AUTHORIZATION_HEADER_FORBIDDEN",
            )
            return
        if origin is None or not allowed_local_origin(origin, role_settings.app.port):
            await websocket.close(code=1008, reason="LOCAL_ORIGIN_REQUIRED")
            return
        await websocket.accept()
        try:
            async for event in public_market_stream.stream(instrument_ref):
                require_current_market_source(event.source)
                await websocket.send_text(event.model_dump_json())
        except WebSocketDisconnect:
            return
        except MarketContextUnavailable as exc:
            try:
                await websocket.close(code=1013, reason=str(exc)[:120])
            except RuntimeError:
                pass

    @app.post(
        "/api/v1/order-schedules/preview",
        response_model=OrderSchedulePreview,
    )
    async def order_schedule_preview(
        payload: OrderSchedulePreviewPayload,
    ) -> OrderSchedulePreview:
        domain_call(
            lambda: validate_current_order_schedule_support(
                payload.decision_basis_kind,
                payload.spec,
            )
        )
        try:
            rules = await public_instrument_rules.fetch(payload.instrument_ref)
            require_current_instrument_rules_source(rules.source)
            reference_price = payload.reference_price
            price_plan = payload.spec.price_distribution
            if isinstance(price_plan, SinglePrice) and price_plan.limit_price is None:
                context = await public_market_context.fetch(
                    payload.instrument_ref,
                    20,
                )
                require_current_market_source(context.source)
                reference_price = context.reference_price
        except (InstrumentRulesUnavailable, MarketContextUnavailable) as exc:
            raise HTTPException(
                status_code=503,
                detail={"code": str(exc)},
            ) from None
        return compile_order_schedule(
            payload.spec,
            rules,
            venue_ref=payload.venue_ref,
            instrument_ref=payload.instrument_ref,
            direction=payload.direction,
            max_notional=payload.max_notional,
            schedule_ref=payload.schedule_ref,
            reference_price=reference_price,
        )

    @app.get(
        "/api/v1/strategies/{strategy_id}/schema",
        response_model=dict[str, Any],
    )
    def strategy_schema(strategy_id: str) -> dict[str, Any]:
        return domain_call(lambda: planning_api.strategy_schema(strategy_id))

    @app.get(
        "/api/v1/plans",
        response_model=list[dict[str, Any]],
    )
    def plans() -> list[dict[str, Any]]:
        return domain_call(planning_api.list_plans)

    @app.post(
        "/api/v1/plans",
        response_model=dict[str, Any],
        status_code=201,
    )
    def create_plan(
        payload: PlanCreatePayload,
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

    @app.delete(
        "/api/v1/plans/{plan_id}",
        response_model=dict[str, Any],
    )
    def delete_plan(
        plan_id: str,
        if_match: str = Header(alias="If-Match"),
    ) -> dict[str, Any]:
        return domain_call(
            lambda: planning_api.delete_plan(
                plan_id,
                expected_version=expected_version(if_match),
            )
        )

    @app.post(
        "/api/v1/plans/{plan_id}/fix",
        response_model=dict[str, Any],
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
    )
    def plan(plan_id: str) -> dict[str, Any]:
        return domain_call(lambda: planning_api.get_plan(plan_id))

    @app.get(
        "/api/v1/plan-versions/{plan_version_id}",
        response_model=dict[str, Any],
    )
    def plan_version(plan_version_id: str) -> dict[str, Any]:
        return domain_call(lambda: planning_api.get_plan_version(plan_version_id))

    @app.post(
        "/api/v1/plan-versions/{plan_version_id}/activation-preview",
        response_model=dict[str, Any],
    )
    async def activation_preview(plan_version_id: str) -> dict[str, Any]:
        preview = domain_call(lambda: planning_api.activation_preview(plan_version_id))
        schedule = await compile_activation_schedule(preview)
        if schedule is not None:
            remember_schedule_preview(plan_version_id, schedule)
        executor = current_executor_status()
        return {
            **preview,
            "order_schedule_snapshot": (
                schedule.model_dump(mode="json") if schedule is not None else None
            ),
            "expected_schedule_digest": (
                schedule.schedule_digest if schedule is not None else None
            ),
            "executor_status": executor["status"],
            "executor_status_checked_at": executor["checked_at"],
        }

    @app.get(
        "/api/v1/activations",
        response_model=list[dict[str, Any]],
    )
    def activations() -> list[dict[str, Any]]:
        return domain_call(planning_api.list_activations)

    @app.post(
        "/api/v1/activations",
        response_model=dict[str, Any],
        status_code=201,
    )
    async def create_activation(
        payload: ActivationPayload,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        replay = domain_call(
            lambda: planning_api.activation_replay(
                payload,
                idempotency_key=idempotency_key,
            )
        )
        if replay is not None:
            return replay
        if current_executor_status()["status"] != "READY":
            raise HTTPException(
                status_code=409,
                detail={"code": "EXECUTOR_NOT_READY"},
            )
        preview = domain_call(
            lambda: planning_api.activation_preview(payload.plan_version_id)
        )
        cached_schedule = (
            domain_call(
                lambda: recalled_schedule_preview(
                    payload.plan_version_id,
                    payload.expected_schedule_digest,
                )
            )
            if preview.get("order_schedule_spec") is not None
            else None
        )
        schedule = (
            await compile_activation_schedule(preview, refresh_rules=True)
            if cached_schedule is not None
            else None
        )
        if (
            cached_schedule is not None
            and (
                schedule is None
                or schedule.schedule_digest != cached_schedule.schedule_digest
            )
        ):
            raise HTTPException(
                status_code=409,
                detail={"code": "ACTIVATION_PREVIEW_STALE"},
            )
        if schedule is not None and not schedule.valid:
            raise HTTPException(
                status_code=409,
                detail={"code": "ORDER_SCHEDULE_INVALID"},
            )
        result = domain_call(
            lambda: planning_api.activate(
                payload,
                idempotency_key=idempotency_key,
                observed_at=datetime.now(UTC),
                order_schedule_snapshot=schedule,
            )
        )
        if schedule is not None:
            schedule_previews.pop(
                (payload.plan_version_id, schedule.schedule_digest),
                None,
            )
        return result

    @app.get(
        "/api/v1/activations/{activation_id}",
        response_model=dict[str, Any],
    )
    def activation(activation_id: str) -> dict[str, Any]:
        return domain_call(lambda: planning_api.activation_detail(activation_id))

    @app.get(
        "/api/v1/activations/{activation_id}/timeline",
        response_model=list[dict[str, Any]],
    )
    def activation_timeline(activation_id: str) -> list[dict[str, Any]]:
        return domain_call(lambda: planning_api.activation_timeline(activation_id))

    @app.post(
        "/api/v1/activations/{activation_id}/control-preview",
        response_model=dict[str, Any],
    )
    def control_preview(activation_id: str, intent: ControlIntent) -> dict[str, Any]:
        return domain_call(lambda: planning_api.control_preview(activation_id, intent))

    def submit_control(
        activation_id: str,
        intent: ControlIntent,
        payload: ControlPayload,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return domain_call(
            lambda: planning_api.submit_control(
                activation_id,
                intent,
                payload,
                idempotency_key=idempotency_key,
                observed_at=datetime.now(UTC),
            )
        )

    @app.post("/api/v1/activations/{activation_id}/stop-new-risk", response_model=dict[str, Any])
    def stop_new_risk(activation_id: str, payload: ControlPayload, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
        return submit_control(activation_id, ControlIntent.STOP_NEW_RISK, payload, idempotency_key)

    @app.post("/api/v1/activations/{activation_id}/resume", response_model=dict[str, Any])
    def resume_plan_activation(activation_id: str, payload: ControlPayload, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
        return submit_control(activation_id, ControlIntent.RESUME_ACTIVATION, payload, idempotency_key)

    @app.post("/api/v1/activations/{activation_id}/exit", response_model=dict[str, Any])
    def exit_strategy(activation_id: str, payload: ControlPayload, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
        return submit_control(activation_id, ControlIntent.EXIT_STRATEGY, payload, idempotency_key)

    @app.post("/api/v1/activations/{activation_id}/takeover", response_model=dict[str, Any])
    def user_takeover(activation_id: str, payload: ControlPayload, idempotency_key: str = Header(alias="Idempotency-Key")) -> dict[str, Any]:
        return submit_control(activation_id, ControlIntent.USER_TAKEOVER, payload, idempotency_key)

    @app.get(
        "/api/v1/receipts/{receipt_id}",
        response_model=dict[str, Any],
    )
    def receipt(receipt_id: str) -> dict[str, Any]:
        return domain_call(lambda: planning_api.receipt(receipt_id))

    @app.get(
        "/api/v1/reviews",
        response_model=list[dict[str, Any]],
    )
    def reviews() -> list[dict[str, Any]]:
        return domain_call(outcomes_api.list_reviews)

    @app.get(
        "/api/v1/reviews/{review_id}",
        response_model=dict[str, Any],
    )
    def review(review_id: str) -> dict[str, Any]:
        return domain_call(lambda: outcomes_api.read_review(review_id))

    @app.put(
        "/api/v1/reviews/{review_id}",
        response_model=dict[str, Any],
    )
    def refresh_review(
        review_id: str, payload: ReviewRefreshPayload
    ) -> dict[str, Any]:
        return domain_call(lambda: outcomes_api.refresh_review(review_id, payload))

    @app.post(
        "/api/v1/reviews/{review_id}/complete",
        response_model=dict[str, Any],
    )
    def complete_review(
        review_id: str, payload: ReviewCompletionPayload
    ) -> dict[str, Any]:
        return domain_call(lambda: outcomes_api.complete_review(review_id, payload))

    @app.get(
        "/api/v1/settings/status",
        response_model=SettingsStatusResponse,
    )
    def settings_status() -> SettingsStatusResponse:
        availability = database.availability()
        gate_status = current_gate_status()
        executor = current_executor_status()
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
            product_build_id=current_product_build_id,
            app_executor_product_build_consistent=(
                executor["product_build_consistent"]
            ),
            executor_status=str(executor["status"]),
            executor_status_checked_at=str(executor["checked_at"]),
            configured_runtime_real_write_gate=(
                gate_status.configured_runtime_real_write_gate
            ),
            runtime_real_write_gate=gate_status.runtime_real_write_gate,
            live_write_gate_violations=list(gate_status.violations),
            authorized_activation_id=gate_status.authorized_activation_id,
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
    )
    def test_email() -> dict[str, Any]:
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
            "recipient_route_ref": "owner-primary-email",
            "delivered_at": _utc_now(),
            "business_state_changed": False,
        }

    @app.get("/operations", response_class=HTMLResponse, include_in_schema=False)
    def operations(request: Request) -> HTMLResponse:
        csrf_token = _csrf_token(request)
        try:
            summary = database.operations()
        except ProjectionUnavailable:
            summary = {"database_available": False, "activations": []}
        return HTMLResponse(
            _operations_document(
                settings=settings,
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
            segments in (["overview"], ["plans"], ["plans", "new"], ["reviews"], ["settings"])
            or (len(segments) == 3 and segments[0] == "plans" and segments[2] == "activate")
            or (len(segments) == 2 and segments[0] in {"activations", "reviews"})
        )
        if not accepted or requested_path.startswith("api/"):
            raise HTTPException(status_code=404, detail={"code": "ROUTE_NOT_FOUND"})
        index = frontend_dist / "index.html"
        if index.is_file():
            return FileResponse(index)
        return HTMLResponse(
            "<!doctype html><html><body><h1>Workbench static artifact unavailable</h1>"
            '<p>The local fallback remains available at <a href="/operations">/operations</a>.</p>'
            "</body></html>",
            status_code=503,
        )

    return app
