    (function () {
      function createLiveWorkflow(deps) {
        const state = deps.state;
        const loadLivePayload = deps.loadLivePayload;
        const escapeHtml = deps.escapeHtml;
        const text = deps.text;
        const statusClass = deps.statusClass;
        const formatTimestamp = deps.formatTimestamp;
        const formatNumber = deps.formatNumber;
        const label = deps.label;
        const metricCell = deps.metricCell;
        const detailRow = deps.detailRow;
        const durationBetween = deps.durationBetween;

        const DATA_TYPE_LABELS = {
          ohlcv: "OHLCV",
          text_event: "Text events",
          macro_calendar: "Macro calendar",
          onchain_flow: "On-chain flow",
          derivatives_market: "Derivatives",
          market_anomaly: "Anomalies",
        };
        const DATA_TYPE_ORDER = ["ohlcv", "text_event", "macro_calendar", "onchain_flow", "derivatives_market", "market_anomaly"];
        const TRANSIENT_JOB_STATUSES = new Set(["queued", "creating", "running", "cancel_requested", "pending"]);
        const FAILED_JOB_STATUSES = new Set(["failed", "error", "blocked"]);
        const SKIPPED_JOB_STATUSES = new Set(["skipped", "cancelled", "unsupported"]);
        const ATTENTION_STATUSES = new Set(["blocked", "cancelled", "degraded", "failed", "missing", "partial", "stale", "suppressed_cooldown", "suppressed_duplicate", "warning"]);

        async function refreshLive() {
          await loadLivePayload();
          renderLive();
        }

        function renderLive() {
          ensureLiveFilterDefaults();
          ensureLiveHistoryFilterDefaults();
          ensureLiveMode();
          renderLiveModeTabs();
          renderLiveSummary();
          renderLiveSourceMatrix();
          renderLiveIntelligenceStrip();
          renderLiveIntelligenceStream();
          renderLiveReportHistory();
          renderLiveSystemRuntime();
          renderLiveTargetDetail();
          renderLiveTriggeredReports();
          renderLiveAlertArchive();
          renderLiveHistoryFilters();
          renderLiveJobLane();
          renderLiveOperationsTimeline();
          renderLiveEventDrawer();
          applyLiveModeVisibility();
        }

        function renderLiveSummary() {
          const live = state.live || {};
          const collections = liveCollections();
          const activeJobs = liveJobs().filter((job) => TRANSIENT_JOB_STATUSES.has(String(job.status || "")));
          const nextRefresh = nextCollectionAttempt(collections);
          const latestSuccess = latestCollectionSuccess(collections);
          const schedule = state.schedule || {};
          const alertCounts = liveAlertCounts();
          const triggeredReports = triggeredReportCount(schedule);
          const liveStatus = live.status || "unavailable";
          const enabled = live.scheduler?.enabled === true;
          const newestAge = latestSuccess ? ageLabel(latestSuccess) : "No successful refresh";

          setHtml("#live-summary", [
            metricCell("Live state", label(enabled ? liveStatus : "disabled"), enabled ? "Core scheduler" : "disabled in config"),
            metricCell("Active refresh", activeJobs.length, activeJobs.length === 1 ? "job" : "jobs"),
            metricCell("Newest data", newestAge, latestSuccess ? formatTimestamp(latestSuccess) : "no success yet"),
            metricCell("Next refresh", nextRefresh ? formatTimestamp(nextRefresh) : "not scheduled", nextRefresh ? "source cadence" : "no due target"),
            metricCell("Next daily report", schedule.enabled ? formatTimestamp(schedule.next_run_at) : "disabled", schedule.status || "schedule"),
            metricCell("Triggered reports", triggeredReports, alertCounts.records ? `${formatNumber(alertCounts.records)} alert records` : "trigger rules pending"),
          ].join(""));
        }

        function renderLiveModeTabs() {
          document.querySelectorAll("[data-live-mode]").forEach((button) => {
            button.classList.toggle("active", button.dataset.liveMode === state.liveMode);
          });
        }

        function applyLiveModeVisibility() {
          const mode = state.liveMode || "now";
          document.querySelectorAll("[data-live-panel]").forEach((panel) => {
            const panelName = panel.dataset.livePanel;
            const visible = panelName === mode || (mode === "now" && panelName !== "sources" && panelName !== "reports" && panelName !== "history");
            panel.hidden = !visible;
          });
          document.querySelector(".live-intelligence-strip-panel")?.toggleAttribute("hidden", mode !== "now");
          document.querySelector(".live-stream-panel")?.toggleAttribute("hidden", mode !== "now");
          document.querySelector(".live-side")?.toggleAttribute("hidden", mode !== "now" && mode !== "sources");
        }

        function renderLiveSourceMatrix() {
          const groups = groupedCollections();
          const visibleTypes = visibleDataTypes();
          const html = visibleTypes.map((dataType) => {
            const items = groups.get(dataType) || [];
            const filteredItems = items.filter(matchesLiveFilters);
            const summary = collectionGroupSummary(dataType, items);
            const rows = filteredItems.length
              ? filteredItems.map((item) => liveTargetRow(item)).join("")
              : `<div class="empty-state compact">No targets match current filters.</div>`;
            return `
              <article class="live-source-card ${escapeHtml(summary.statusClass)}" data-live-source-card="${escapeHtml(dataType)}">
                <div class="live-source-card-head">
                  <div>
                    <h3>${escapeHtml(DATA_TYPE_LABELS[dataType] || label(dataType))}</h3>
                    <p>${escapeHtml(summary.scope)}</p>
                  </div>
                  <span class="status-pill ${escapeHtml(summary.statusClass)}">${escapeHtml(summary.statusLabel)}</span>
                </div>
                <div class="live-source-stats">
                  ${liveFact("Targets", summary.targets)}
                  ${liveFact("Cadence", summary.cadence)}
                  ${liveFact("Last success", summary.lastSuccess)}
                  ${liveFact("Next attempt", summary.nextAttempt)}
                  ${liveFact("Active jobs", summary.activeJobs)}
                  ${liveFact("Issues", summary.issueCount)}
                </div>
                <div class="live-target-table" role="table" aria-label="${escapeHtml(DATA_TYPE_LABELS[dataType] || label(dataType))} targets">
                  <div class="live-target-row live-target-head" role="row">
                    <span>Target</span><span>Status</span><span>Last success</span><span>Next</span>
                  </div>
                  ${rows}
                </div>
              </article>`;
          }).join("");
          setHtml("#live-source-matrix", html);
          ensureSelectedLiveTarget();
        }

        function renderLiveIntelligenceStrip() {
          const groups = groupedCollections();
          const alert = alertRecords()[0] || null;
          setHtml("#live-intelligence-strip", DATA_TYPE_ORDER.map((dataType) => {
            const items = groups.get(dataType) || [];
            const latest = latestCollection(items);
            const status = latest ? collectionStatus(latest) : {status: "missing", label: "missing", statusClass: "missing"};
            const headline = dataType === "text_event" && alert
              ? (alert.title || alert.message || "Latest alert record")
              : latestIntelligenceHeadline(dataType, latest);
            const meta = [
              latest?.last_success_at ? formatTimestamp(latest.last_success_at) : null,
              latest?.latest_terminal_status ? `terminal ${latest.latest_terminal_status}` : null,
              latest?.source_refs?.[0] ? latest.source_refs[0] : null,
            ].filter(Boolean).join(" / ");
            return `
              <article class="live-intel-card">
                <div class="live-stream-title">${statusPill(status.status, status.label)}<strong>${escapeHtml(DATA_TYPE_LABELS[dataType])}</strong></div>
                <p>${escapeHtml(headline)}</p>
                <span>${escapeHtml(meta || "No bounded summary available yet.")}</span>
              </article>`;
          }).join(""));
        }

        function renderLiveIntelligenceStream() {
          const records = alertRecords();
          const warnings = liveCollections()
            .flatMap((item) => (Array.isArray(item.warnings) ? item.warnings : []).map((warning) => ({
              created_at: item.updated_at,
              status: "warning",
              title: warning,
              source: DATA_TYPE_LABELS[item.data_type] || label(item.data_type),
              detail: item.target_key || item.data_type,
            })));
          const errors = liveCollections()
            .flatMap((item) => (Array.isArray(item.errors) ? item.errors : []).map((error) => ({
              created_at: item.updated_at,
              status: "failed",
              title: error,
              source: DATA_TYPE_LABELS[item.data_type] || label(item.data_type),
              detail: item.target_key || item.data_type,
            })));
          const items = [...records, ...errors, ...warnings]
            .sort((left, right) => timestampMs(right.created_at || right.timestamp) - timestampMs(left.created_at || left.timestamp))
            .slice(0, 12);
          setHtml("#live-intelligence-stream", items.length ? items.map((record) => {
            const status = statusClass(record.status || record.priority || "warning");
            const title = record.title || record.message || record.alert_key || record.decision_id || "Live signal";
            const subtitle = [
              record.symbol,
              record.timeframe,
              record.priority,
              record.attention_decision,
              record.source,
            ].filter(Boolean).join(" / ");
            const refs = Array.isArray(record.source_artifacts) ? record.source_artifacts : [];
            return `
              <article class="live-stream-row">
                <span class="live-stream-time">${escapeHtml(formatTimestamp(record.created_at || record.timestamp))}</span>
                <div class="live-stream-body">
                  <div class="live-stream-title">${statusPill(status, status)}<strong>${escapeHtml(title)}</strong></div>
                  <p>${escapeHtml(subtitle || record.detail || "bounded Live evidence")}</p>
                  ${refs.length ? `<div class="live-ref-list">${refs.slice(0, 3).map((ref) => `<span>${escapeHtml(ref)}</span>`).join("")}</div>` : ""}
                </div>
              </article>`;
          }).join("") : `<div class="empty-state">No bounded alert or Live warning records are available yet.</div>`);
        }

        function renderLiveReportHistory() {
          const schedule = state.schedule || {};
          const dispatches = Array.isArray(schedule.dispatches) ? schedule.dispatches : [];
          const latestDispatch = dispatches[0] || {};
          const linkedReports = Array.isArray(schedule.linked_report_refs) ? schedule.linked_report_refs : [];
          setHtml("#live-report-history", [
            detailRow("Daily schedule", schedule.enabled ? "enabled" : "disabled"),
            detailRow("Next daily report", schedule.enabled ? formatTimestamp(schedule.next_run_at) : "n/a"),
            detailRow("Latest dispatch", latestDispatch.scheduled_for ? `${formatTimestamp(latestDispatch.scheduled_for)} / ${latestDispatch.status || "unknown"}` : "n/a"),
            detailRow("Latest job", schedule.last_job_id || latestDispatch.job_id || "n/a"),
            detailRow("Linked report", linkedReports[0] || latestDispatch.report_ref || "n/a"),
            detailRow("Triggered reports", triggeredReportCount(schedule)),
          ].join(""));
        }

        function renderLiveSystemRuntime() {
          const services = state.services?.services || {};
          const core = services.core || {};
          const systemMonitor = services.monitor || {};
          setHtml("#live-system-runtime", [
            detailRow("Core service", label(core.lifecycle_status || core.status || "unknown")),
            detailRow("Core heartbeat", formatTimestamp(core.heartbeat_at)),
            detailRow("System Monitor", label(systemMonitor.lifecycle_status || systemMonitor.status || "unknown")),
            detailRow("System Monitor heartbeat", formatTimestamp(systemMonitor.heartbeat_at)),
            detailRow("Config conflict", systemMonitor.config_conflict ? "yes" : "no"),
            detailRow("Last runtime error", systemMonitor.last_error?.message || core.last_error?.message || "none"),
          ].join(""));
        }

        function renderLiveTargetDetail() {
          ensureSelectedLiveTarget();
          const item = selectedCollection();
          if (!item) {
            setHtml("#live-target-detail", `<div class="empty-state">Select a target to inspect bounded refresh state.</div>`);
            return;
          }
          const status = collectionStatus(item);
          const target = item.target || {};
          const refs = Array.isArray(item.source_refs) ? item.source_refs : [];
          const warnings = Array.isArray(item.warnings) ? item.warnings : [];
          const errors = Array.isArray(item.errors) ? item.errors : [];
          setHtml("#live-target-detail", `
            <div class="live-target-detail-head">
              ${statusPill(status.status, status.label)}
              <strong>${escapeHtml(targetLabel(item))}</strong>
            </div>
            <div class="compact-list">
              ${detailRow("Data type", DATA_TYPE_LABELS[item.data_type] || label(item.data_type))}
              ${detailRow("Target key", item.target_key || "n/a")}
              ${Object.entries(target).map(([key, value]) => detailRow(label(key), text(value))).join("")}
              ${detailRow("Enabled", item.enabled === true ? "yes" : "no")}
              ${detailRow("Cadence", durationSeconds(item.cadence_seconds))}
              ${detailRow("Lookback", durationSeconds(item.lookback_seconds))}
              ${detailRow("Lookahead", durationSeconds(item.lookahead_seconds))}
              ${detailRow("Last attempt", formatTimestamp(item.last_attempt_at))}
              ${detailRow("Last success", formatTimestamp(item.last_success_at))}
              ${detailRow("Next attempt", formatTimestamp(item.next_attempt_at))}
              ${detailRow("Latest job", item.latest_job_id || "n/a")}
              ${detailRow("Latest job status", item.latest_job_status || "n/a")}
              ${detailRow("Terminal job", item.latest_terminal_job_id || "n/a")}
              ${detailRow("Terminal status", item.latest_terminal_status || "n/a")}
              ${detailRow("Consecutive failures", item.consecutive_failures ?? 0)}
            </div>
            ${renderRefList("Source refs", refs)}
            ${renderMessageList("Warnings", warnings, "warning")}
            ${renderMessageList("Errors", errors, "failed")}
          `);
        }

        function renderLiveJobLane() {
          const jobs = liveJobs().slice(0, 10);
          setHtml("#live-job-lane", jobs.length ? `
            <div class="live-job-lane-head">
              <strong>Recent collection jobs</strong>
              <span>${escapeHtml(`${jobs.length} visible`)}</span>
            </div>
            <div class="live-job-table" role="table" aria-label="Recent Live collection jobs">
              <div class="live-job-row live-job-head" role="row">
                <span>Job</span><span>Target</span><span>Status</span><span>Created</span><span>Duration</span><span>Result</span>
              </div>
              ${jobs.map((job) => liveJobRow(job)).join("")}
            </div>
          ` : `<div class="empty-state">No Live collection jobs are available yet.</div>`);
        }

        function renderLiveTriggeredReports() {
          const history = state.liveHistory || {};
          const rows = Array.isArray(history.triggered_reports) ? history.triggered_reports : [];
          if (!rows.length) {
            const empty = history.empty_states?.triggers_disabled
              ? "Live trigger rules are disabled."
              : "No trigger decisions or trigger-created reports are available yet.";
            setHtml("#live-triggered-reports", `<div class="empty-state">${escapeHtml(empty)}</div>`);
            return;
          }
          setHtml("#live-triggered-reports", `
            <div class="live-review-table" role="table" aria-label="Live triggered report review">
              <div class="live-review-row live-review-head" role="row">
                <span>Trigger</span><span>Status</span><span>Evidence</span><span>Cooldown</span><span>Linked report</span><span>Issues</span>
              </div>
              ${rows.map((row) => {
                const status = statusClass(row.status || "unknown");
                const issues = [...(Array.isArray(row.errors) ? row.errors : []), ...(Array.isArray(row.warnings) ? row.warnings : [])];
                const link = row.linked_report_ref || row.linked_run_id || row.linked_job_id || "missing";
                return `<button class="live-review-row" type="button" data-live-trigger-decision="${escapeHtml(row.decision_id || "")}" role="row">
                  <span><strong>${escapeHtml(row.trigger_id || "trigger")}</strong><small>${escapeHtml(formatTimestamp(row.evaluated_at))}</small></span>
                  <span>${statusPill(status, row.status || "unknown")}</span>
                  <span>${escapeHtml(row.evidence_summary || row.reason_summary || "n/a")}</span>
                  <span>${escapeHtml(row.cooldown_until ? formatTimestamp(row.cooldown_until) : "n/a")}</span>
                  <span class="${escapeHtml(row.artifact_state === "missing" ? "live-ref-missing" : "")}">${escapeHtml(link)}</span>
                  <span>${issues.length ? escapeHtml(issues[0]) : "none"}</span>
                </button>`;
              }).join("")}
            </div>
          `);
        }

        function renderLiveAlertArchive() {
          const archive = state.liveHistory?.alert_archive || {};
          const counts = archive.counts || {};
          const rows = Array.isArray(archive.records) ? archive.records : [];
          const countHtml = `
            <div class="summary-strip columns-4 live-alert-counts">
              ${metricCell("Emitted", counts.emitted ?? 0, "alerts")}
              ${metricCell("Duplicates", counts.suppressed_duplicate ?? 0, "suppressed")}
              ${metricCell("Cooldown", counts.suppressed_cooldown ?? 0, "suppressed")}
              ${metricCell("Skipped", counts.skipped ?? 0, "records")}
            </div>`;
          if (!rows.length) {
            setHtml("#live-alert-archive", `${countHtml}<div class="empty-state">No alert archive records are available yet.</div>`);
            return;
          }
          setHtml("#live-alert-archive", `
            ${countHtml}
            <div class="live-alert-list" aria-label="Recent alert archive records">
              ${rows.slice(0, 16).map((record) => {
                const status = statusClass(record.status || "unknown");
                const reasons = Array.isArray(record.suppression_reasons) && record.suppression_reasons.length
                  ? record.suppression_reasons.join(", ")
                  : record.attention_decision || "n/a";
                const ref = record.source_report_ref || record.source_run_id || (Array.isArray(record.source_artifacts) ? record.source_artifacts[0] : "") || "n/a";
                return `<article class="live-alert-row">
                  <div>${statusPill(status, record.status || "unknown")}<strong>${escapeHtml(record.alert_key || record.record_id || "alert")}</strong></div>
                  <p>${escapeHtml([record.symbol, record.timeframe, record.priority].filter(Boolean).join(" / ") || "bounded alert record")}</p>
                  <span>${escapeHtml(formatTimestamp(record.created_at))}</span>
                  <span>${escapeHtml(reasons)}</span>
                  <span>${escapeHtml(ref)}</span>
                </article>`;
              }).join("")}
            </div>
          `);
        }

        function renderLiveHistoryFilters() {
          const options = state.liveHistory?.filter_options || {};
          const filters = liveHistoryFilters();
          fillSelect("#live-history-filter-data-type", "All data types", options.data_types, filters.dataType, DATA_TYPE_LABELS);
          fillSelect("#live-history-filter-trigger", "All triggers", options.trigger_ids, filters.triggerId);
          fillSelect("#live-history-filter-kind", "All events", options.event_kinds, filters.eventKind);
          fillSelect("#live-history-filter-status", "All states", options.statuses, filters.status);
          const start = document.querySelector("#live-history-filter-start");
          const end = document.querySelector("#live-history-filter-end");
          const reportLinked = document.querySelector("#live-history-filter-report-linked");
          const attention = document.querySelector("#live-history-filter-attention");
          if (start) start.value = filters.start || "";
          if (end) end.value = filters.end || "";
          if (reportLinked) reportLinked.checked = filters.reportLinkedOnly === true;
          if (attention) attention.checked = filters.attentionOnly === true;
        }

        function renderLiveOperationsTimeline() {
          const rows = filteredLiveHistoryEvents();
          setHtml("#live-operations-timeline", rows.length ? rows.slice(0, 200).map((row) => {
            const status = statusClass(row.status || "unknown");
            const marker = status === "failed" ? "x" : status === "warning" || status === "stale" || status === "degraded" ? "!" : "ok";
            const meta = [
              row.event_kind ? label(row.event_kind) : null,
              row.data_type ? (DATA_TYPE_LABELS[row.data_type] || label(row.data_type)) : null,
              row.trigger_id,
              row.job_id,
              row.run_id,
              row.report_ref,
            ].filter(Boolean);
            const refs = Array.isArray(row.artifact_refs) ? row.artifact_refs : [];
            return `<li class="timeline-row live-history-row" data-live-event-id="${escapeHtml(row.event_id || "")}">
              <div class="timeline-time">${escapeHtml(formatTimestamp(row.timestamp))}</div>
              <div class="timeline-node ${escapeHtml(status)}">${escapeHtml(marker)}</div>
              <button class="timeline-body live-history-event-button" type="button" data-live-event-id="${escapeHtml(row.event_id || "")}">
                <strong>${escapeHtml(row.title || "Live event")}</strong>
                <span>${escapeHtml(row.summary || "n/a")}</span>
                <small>${escapeHtml(meta.join(" / ") || "bounded event")}</small>
                ${refs.length ? `<div class="live-ref-list">${refs.slice(0, 3).map((ref) => `<span>${escapeHtml(ref)}</span>`).join("")}</div>` : ""}
              </button>
              <span class="status-pill ${escapeHtml(status)}">${escapeHtml(row.status || "unknown")}</span>
            </li>`;
          }).join("") : `<li class="empty-state">No Live history matches current filters.</li>`);
        }

        function renderLiveEventDrawer() {
          if (!state.liveEventDrawerOpen) return;
          const event = selectedLiveEvent();
          const title = document.querySelector("#live-event-drawer-title");
          if (title) title.textContent = event?.title || "Event details";
          if (!event) {
            setHtml("#live-event-drawer-body", `<div class="empty-state">The selected Live event is no longer in the bounded history payload.</div>`);
            return;
          }
          const detail = event.detail || {};
          const metadata = detail.metadata || {};
          const refs = Array.isArray(detail.source_refs) ? detail.source_refs : [];
          const warnings = Array.isArray(detail.warnings) ? detail.warnings : [];
          const errors = Array.isArray(detail.errors) ? detail.errors : [];
          const rows = [
            ["Timestamp", formatTimestamp(event.timestamp)],
            ["Event kind", label(event.event_kind)],
            ["Status", event.status || "unknown"],
            ["Data type", event.data_type ? DATA_TYPE_LABELS[event.data_type] || label(event.data_type) : "n/a"],
            ["Trigger", event.trigger_id || "n/a"],
            ["Job", event.job_id || "n/a"],
            ["Run", event.run_id || "n/a"],
            ["Report", event.report_ref || "n/a"],
            ["Artifact state", event.artifact_state || "n/a"],
          ];
          setHtml("#live-event-drawer-body", `
            <div class="drawer-chip-row">
              ${statusPill(event.status || "unknown", event.status || "unknown")}
              <span class="chip">${escapeHtml(label(event.event_kind || "event"))}</span>
            </div>
            <p class="drawer-summary">${escapeHtml(event.summary || "n/a")}</p>
            <div class="compact-list">${rows.map(([key, value]) => detailRow(key, value)).join("")}</div>
            ${renderMetadataBlock("Metadata", metadata)}
            ${renderRefList("Source and artifact refs", refs)}
            ${renderMessageList("Warnings", warnings, "warning")}
            ${renderMessageList("Errors", errors, "failed")}
          `);
        }

        function openLiveEventDrawer(eventId) {
          state.selectedLiveEventId = eventId || "";
          state.liveEventDrawerOpen = true;
          renderLiveEventDrawer();
          document.querySelector("#live-event-drawer")?.classList.remove("hidden");
          const backdrop = document.querySelector("#live-event-drawer-backdrop");
          if (backdrop) {
            backdrop.classList.remove("hidden");
            backdrop.setAttribute("aria-hidden", "false");
          }
        }

        function closeLiveEventDrawer() {
          state.liveEventDrawerOpen = false;
          document.querySelector("#live-event-drawer")?.classList.add("hidden");
          const backdrop = document.querySelector("#live-event-drawer-backdrop");
          if (backdrop) {
            backdrop.classList.add("hidden");
            backdrop.setAttribute("aria-hidden", "true");
          }
        }

        function selectedLiveEvent() {
          const events = Array.isArray(state.liveHistory?.timeline) ? state.liveHistory.timeline : [];
          return events.find((event) => event.event_id === state.selectedLiveEventId) || null;
        }

        function filteredLiveHistoryEvents() {
          const events = Array.isArray(state.liveHistory?.timeline) ? state.liveHistory.timeline : [];
          const filters = liveHistoryFilters();
          const start = filters.start ? new Date(filters.start).getTime() : NaN;
          const end = filters.end ? new Date(filters.end).getTime() : NaN;
          return events.filter((event) => {
            const time = timestampMs(event.timestamp);
            if (Number.isFinite(start) && time < start) return false;
            if (Number.isFinite(end) && time > end) return false;
            if (filters.dataType !== "all" && event.data_type !== filters.dataType) return false;
            if (filters.triggerId !== "all" && event.trigger_id !== filters.triggerId) return false;
            if (filters.eventKind !== "all" && event.event_kind !== filters.eventKind) return false;
            if (filters.status !== "all" && event.status !== filters.status) return false;
            if (filters.reportLinkedOnly && !liveEventHasReportLink(event)) return false;
            if (filters.attentionOnly && !ATTENTION_STATUSES.has(String(event.status || ""))) return false;
            return true;
          });
        }

        function liveEventHasReportLink(event) {
          return Boolean(event.report_ref || event.run_id || event.event_kind === "trigger_report_job" || event.event_kind === "scheduled_report_job" || event.event_kind === "scheduled_report_dispatch");
        }

        function alertCount(payload) {
          const counts = payload?.alert_archive?.fields?.counts || payload?.alert_archive?.counts || {};
          return Number(counts.records || counts.emitted || 0);
        }

        function liveCollections() {
          return Array.isArray(state.live?.collections) ? state.live.collections : [];
        }

        function groupedCollections() {
          const groups = new Map(DATA_TYPE_ORDER.map((dataType) => [dataType, []]));
          liveCollections().forEach((item) => {
            const dataType = item.data_type || "unknown";
            if (!groups.has(dataType)) groups.set(dataType, []);
            groups.get(dataType).push(item);
          });
          return groups;
        }

        function collectionGroupSummary(dataType, items) {
          const enabled = items.filter((item) => item.enabled === true);
          const statuses = items.map(collectionStatus);
          const groupStatus = worstStatus(statuses);
          const lastSuccess = latestCollectionSuccess(items);
          const nextAttempt = nextCollectionAttempt(items);
          const latestJob = latestCollectionJob(items);
          const issueCount = items.reduce((total, item) => total + messageCount(item), 0);
          const activeJobs = items.filter((item) => TRANSIENT_JOB_STATUSES.has(String(item.latest_job_status || ""))).length;
          return {
            statusClass: statusClass(groupStatus.status),
            statusLabel: groupStatus.label,
            scope: enabled.length ? `${enabled.length} enabled / ${items.length} configured` : `${items.length || 0} configured`,
            targets: `${enabled.length}/${items.length || 0}`,
            cadence: collectionCadence(items),
            lastSuccess: lastSuccess ? formatTimestamp(lastSuccess) : "n/a",
            nextAttempt: nextAttempt ? formatTimestamp(nextAttempt) : "n/a",
            latestJob: latestJob ? `${latestJob.latest_job_status || "unknown"} / ${latestJob.latest_job_id || "n/a"}` : "n/a",
            activeJobs,
            issueCount,
          };
        }

        function collectionStatus(item) {
          const latestStatus = String(item.latest_job_status || "").toLowerCase();
          const terminalStatus = String(item.latest_terminal_status || "").toLowerCase();
          const errors = Array.isArray(item.errors) ? item.errors : [];
          const warnings = Array.isArray(item.warnings) ? item.warnings : [];
          if (item.enabled !== true) return {status: "disabled", label: "disabled", statusClass: "skipped", reason: "target disabled"};
          if (errors.length || FAILED_JOB_STATUSES.has(terminalStatus) || Number(item.consecutive_failures || 0) > 0) {
            return {status: "failed", label: "failed", statusClass: "failed", reason: errors[0] || terminalStatus || "collection failed"};
          }
          if (TRANSIENT_JOB_STATUSES.has(latestStatus)) {
            return {status: latestStatus === "running" ? "running" : "pending", label: latestStatus || "pending", statusClass: latestStatus === "running" ? "running" : "pending", reason: item.latest_job_id || "job pending"};
          }
          if (SKIPPED_JOB_STATUSES.has(terminalStatus)) {
            return {status: "skipped", label: terminalStatus || "skipped", statusClass: "skipped", reason: terminalStatus || "job skipped"};
          }
          if (!item.last_attempt_at && !item.latest_job_id) {
            return {status: "missing", label: "missing", statusClass: "missing", reason: "no collection attempt recorded"};
          }
          if (isStale(item)) return {status: "stale", label: "stale", statusClass: "stale", reason: "next attempt is overdue"};
          if (warnings.length) return {status: "warning", label: "warning", statusClass: "warning", reason: warnings[0]};
          if (item.last_success_at) return {status: "available", label: "available", statusClass: "available", reason: "latest success recorded"};
          return {status: "pending", label: "pending", statusClass: "pending", reason: "awaiting terminal job state"};
        }

        function matchesLiveFilters(item) {
          const filters = liveFilters();
          const status = collectionStatus(item);
          if (filters.dataType !== "all" && item.data_type !== filters.dataType) return false;
          if (filters.status !== "all" && status.status !== filters.status && status.statusClass !== filters.status) return false;
          if (filters.activeOnly && !TRANSIENT_JOB_STATUSES.has(String(item.latest_job_status || ""))) return false;
          if (filters.attentionOnly && !ATTENTION_STATUSES.has(status.status)) return false;
          return true;
        }

        function liveTargetRow(item) {
          const status = collectionStatus(item);
          const selected = state.selectedLiveTargetKey === item.target_key;
          return `<button class="live-target-row ${selected ? "active" : ""}" type="button" data-live-target-key="${escapeHtml(item.target_key || "")}" role="row">
            <span>${escapeHtml(targetLabel(item))}</span>
            <span>${statusPill(status.status, status.label)}</span>
            <span>${escapeHtml(item.last_success_at ? formatTimestamp(item.last_success_at) : "n/a")}</span>
            <span>${escapeHtml(item.next_attempt_at ? formatTimestamp(item.next_attempt_at) : "n/a")}</span>
          </button>`;
        }

        function liveJobRow(job) {
          const requester = job.requester || {};
          const status = statusClass(job.status || "unknown");
          const errors = Array.isArray(job.errors) ? job.errors : [];
          const warnings = Array.isArray(job.warnings) ? job.warnings : [];
          const refs = job.result_refs && typeof job.result_refs === "object" ? Object.values(job.result_refs).filter(Boolean) : [];
          const result = errors[0] || warnings[0] || refs[0] || "n/a";
          return `<div class="live-job-row" role="row">
            <span>${escapeHtml(job.job_id || "n/a")}</span>
            <span>${escapeHtml(requester.target_key || requester.data_type || "n/a")}</span>
            <span>${statusPill(status, job.status || "unknown")}</span>
            <span>${escapeHtml(formatTimestamp(job.created_at))}</span>
            <span>${escapeHtml(durationBetween(job.started_at, job.finished_at))}</span>
            <span>${escapeHtml(result)}</span>
          </div>`;
        }

        function latestIntelligenceHeadline(dataType, item) {
          if (!item) return "No target state available.";
          if (dataType === "ohlcv") return `Coverage freshness for ${targetLabel(item)}.`;
          if (dataType === "macro_calendar") return "Configured catalyst collection window.";
          if (dataType === "onchain_flow") return "Latest chain metric refresh state.";
          if (dataType === "derivatives_market") return "Latest derivatives metric refresh state.";
          if (dataType === "market_anomaly") return "Latest anomaly detector refresh state.";
          return `Latest refresh state for ${targetLabel(item)}.`;
        }

        function visibleDataTypes() {
          const filters = liveFilters();
          return filters.dataType === "all" ? DATA_TYPE_ORDER : DATA_TYPE_ORDER.filter((dataType) => dataType === filters.dataType);
        }

        function liveFilters() {
          ensureLiveFilterDefaults();
          return state.liveFilters;
        }

        function liveHistoryFilters() {
          ensureLiveHistoryFilterDefaults();
          return state.liveHistoryFilters;
        }

        function ensureLiveMode() {
          if (!["now", "sources", "reports", "history"].includes(state.liveMode)) {
            state.liveMode = "now";
          }
        }

        function ensureLiveFilterDefaults() {
          state.liveFilters = {
            dataType: state.liveFilters?.dataType || "all",
            status: state.liveFilters?.status || "all",
            activeOnly: state.liveFilters?.activeOnly === true,
            attentionOnly: state.liveFilters?.attentionOnly === true,
          };
        }

        function ensureLiveHistoryFilterDefaults() {
          state.liveHistoryFilters = {
            start: state.liveHistoryFilters?.start || "",
            end: state.liveHistoryFilters?.end || "",
            dataType: state.liveHistoryFilters?.dataType || "all",
            triggerId: state.liveHistoryFilters?.triggerId || "all",
            eventKind: state.liveHistoryFilters?.eventKind || "all",
            status: state.liveHistoryFilters?.status || "all",
            reportLinkedOnly: state.liveHistoryFilters?.reportLinkedOnly === true,
            attentionOnly: state.liveHistoryFilters?.attentionOnly === true,
          };
        }

        function ensureSelectedLiveTarget() {
          const collections = liveCollections();
          if (collections.some((item) => item.target_key === state.selectedLiveTargetKey)) return;
          const attention = collections.find((item) => ATTENTION_STATUSES.has(collectionStatus(item).status));
          state.selectedLiveTargetKey = (attention || collections[0] || {}).target_key || "";
        }

        function selectedCollection() {
          return liveCollections().find((item) => item.target_key === state.selectedLiveTargetKey) || null;
        }

        function liveJobs() {
          const live = state.live || {};
          return [...(Array.isArray(live.active_jobs) ? live.active_jobs : []), ...(Array.isArray(live.recent_jobs) ? live.recent_jobs : [])]
            .sort((left, right) => timestampMs(right.finished_at || right.started_at || right.created_at) - timestampMs(left.finished_at || left.started_at || left.created_at));
        }

        function alertRecords() {
          return state.liveAlerts?.alert_archive?.fields?.sample_records || [];
        }

        function liveAlertCounts() {
          return state.liveAlerts?.alert_archive?.fields?.counts || state.liveAlerts?.alert_archive?.counts || {};
        }

        function triggeredReportCount(schedule) {
          const refs = Array.isArray(schedule.linked_report_refs) ? schedule.linked_report_refs.length : 0;
          const dispatches = Array.isArray(schedule.dispatches) ? schedule.dispatches.filter((item) => item.report_ref).length : 0;
          return Math.max(refs, dispatches);
        }

        function collectionCadence(items) {
          const values = uniqueNumbers(items.map((item) => item.cadence_seconds));
          if (!values.length) return "n/a";
          if (values.length === 1) return durationSeconds(values[0]);
          return `${values.length} cadences`;
        }

        function targetLabel(item) {
          const target = item.target || {};
          if (target.symbol && target.timeframe) return `${target.source || "source"} ${target.symbol} ${target.timeframe}`;
          return target.source || target.source_scope || item.target_key || item.data_type || "target";
        }

        function latestCollection(items) {
          return [...items].sort((left, right) => timestampMs(right.last_success_at || right.updated_at) - timestampMs(left.last_success_at || left.updated_at))[0] || null;
        }

        function latestCollectionSuccess(items) {
          const times = items.map((item) => item.last_success_at).filter(Boolean).sort((a, b) => timestampMs(b) - timestampMs(a));
          return times[0] || null;
        }

        function nextCollectionAttempt(items) {
          const times = items
            .filter((item) => item.enabled === true)
            .map((item) => item.next_attempt_at)
            .filter(Boolean)
            .sort((a, b) => timestampMs(a) - timestampMs(b));
          return times[0] || null;
        }

        function latestCollectionJob(items) {
          return items
            .filter((item) => item.latest_job_id || item.latest_job_status)
            .sort((a, b) => timestampMs(b.updated_at) - timestampMs(a.updated_at))[0] || null;
        }

        function isStale(item) {
          if (!item.next_attempt_at || TRANSIENT_JOB_STATUSES.has(String(item.latest_job_status || ""))) return false;
          const next = timestampMs(item.next_attempt_at);
          return next > 0 && next + 60000 < Date.now();
        }

        function messageCount(item) {
          return (Array.isArray(item.errors) ? item.errors.length : 0) + (Array.isArray(item.warnings) ? item.warnings.length : 0);
        }

        function worstStatus(statuses) {
          const priority = ["failed", "stale", "warning", "running", "pending", "missing", "available", "disabled"];
          for (const status of priority) {
            const found = statuses.find((item) => item.status === status || item.statusClass === status);
            if (found) return found;
          }
          return {status: "missing", label: "missing", statusClass: "missing"};
        }

        function renderRefList(title, refs) {
          if (!refs.length) return "";
          return `<div class="live-detail-block"><strong>${escapeHtml(title)}</strong><div class="live-ref-list">${refs.slice(0, 8).map((ref) => `<span>${escapeHtml(ref)}</span>`).join("")}</div></div>`;
        }

        function renderMessageList(title, messages, status) {
          if (!messages.length) return "";
          return `<div class="live-detail-block"><strong>${escapeHtml(title)}</strong>${messages.slice(0, 5).map((message) => `<p class="live-message ${escapeHtml(statusClass(status))}">${escapeHtml(message)}</p>`).join("")}</div>`;
        }

        function renderMetadataBlock(title, metadata) {
          const entries = Object.entries(metadata || {}).slice(0, 24);
          if (!entries.length) return "";
          return `<div class="live-detail-block"><strong>${escapeHtml(title)}</strong><div class="compact-list">
            ${entries.map(([key, value]) => detailRow(label(key), metadataValue(value))).join("")}
          </div></div>`;
        }

        function metadataValue(value) {
          if (value === null || value === undefined || value === "") return "n/a";
          if (Array.isArray(value)) return value.map((item) => metadataValue(item)).join(", ") || "n/a";
          if (typeof value === "object") return Object.entries(value).slice(0, 8).map(([key, item]) => `${label(key)}: ${metadataValue(item)}`).join(" / ") || "n/a";
          return String(value);
        }

        function fillSelect(selector, allLabel, values, current, labels) {
          const node = document.querySelector(selector);
          if (!node) return;
          const items = Array.isArray(values) ? values.filter(Boolean) : [];
          const selected = current || "all";
          node.innerHTML = [
            `<option value="all">${escapeHtml(allLabel)}</option>`,
            ...items.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml((labels && labels[value]) || label(value))}</option>`),
          ].join("");
          node.value = items.includes(selected) ? selected : "all";
        }

        function liveJobTitle(job) {
          const requester = job.requester || {};
          const targetKey = requester.target_key || requester.data_type || job.kind || "Live job";
          return `Live refresh ${targetKey}`;
        }

        function liveFact(labelText, value) {
          return `<div class="live-fact"><span>${escapeHtml(labelText)}</span><strong>${escapeHtml(text(value, "n/a"))}</strong></div>`;
        }

        function statusPill(status, value) {
          return `<span class="status-pill ${escapeHtml(statusClass(status))}">${escapeHtml(label(value || status))}</span>`;
        }

        function ageLabel(value) {
          const time = timestampMs(value);
          if (!time) return "n/a";
          const diff = Math.max(0, Date.now() - time);
          if (diff < 60 * 1000) return "just now";
          if (diff < 3600 * 1000) return `${Math.floor(diff / 60000)}m ago`;
          if (diff < 24 * 3600 * 1000) return `${Math.floor(diff / 3600000)}h ago`;
          return `${Math.floor(diff / 86400000)}d ago`;
        }

        function durationSeconds(seconds) {
          const value = Number(seconds);
          if (!Number.isFinite(value) || value <= 0) return "n/a";
          if (value < 60) return `${value}s`;
          if (value < 3600) return `${Math.round(value / 60)}m`;
          if (value < 86400) return `${Math.round(value / 3600)}h`;
          return `${Math.round(value / 86400)}d`;
        }

        function timestampMs(value) {
          const time = value ? new Date(value).getTime() : NaN;
          return Number.isFinite(time) ? time : 0;
        }

        function uniqueNumbers(values) {
          return Array.from(new Set(values.map(Number).filter((value) => Number.isFinite(value) && value > 0))).sort((a, b) => a - b);
        }

        function setHtml(selector, html) {
          const node = document.querySelector(selector);
          if (node) node.innerHTML = html;
        }

        function wire() {
          document.querySelector("#live-mode-tabs")?.addEventListener("click", (event) => {
            const button = event.target.closest("[data-live-mode]");
            if (!button) return;
            state.liveMode = button.dataset.liveMode || "now";
            renderLiveModeTabs();
            applyLiveModeVisibility();
          });
          document.querySelector("#live-filter-data-type")?.addEventListener("change", (event) => {
            state.liveFilters.dataType = event.currentTarget.value || "all";
            renderLive();
          });
          document.querySelector("#live-filter-status")?.addEventListener("change", (event) => {
            state.liveFilters.status = event.currentTarget.value || "all";
            renderLive();
          });
          document.querySelector("#live-filter-active")?.addEventListener("change", (event) => {
            state.liveFilters.activeOnly = event.currentTarget.checked;
            renderLive();
          });
          document.querySelector("#live-filter-attention")?.addEventListener("change", (event) => {
            state.liveFilters.attentionOnly = event.currentTarget.checked;
            renderLive();
          });
          document.querySelector("#live-filter-clear")?.addEventListener("click", () => {
            state.liveFilters = {dataType: "all", status: "all", activeOnly: false, attentionOnly: false};
            const dataType = document.querySelector("#live-filter-data-type");
            const status = document.querySelector("#live-filter-status");
            const active = document.querySelector("#live-filter-active");
            const attention = document.querySelector("#live-filter-attention");
            if (dataType) dataType.value = "all";
            if (status) status.value = "all";
            if (active) active.checked = false;
            if (attention) attention.checked = false;
            renderLive();
          });
          document.querySelector("#live-source-matrix")?.addEventListener("click", (event) => {
            const button = event.target.closest("[data-live-target-key]");
            if (!button) return;
            state.selectedLiveTargetKey = button.dataset.liveTargetKey || "";
            renderLiveSourceMatrix();
            renderLiveTargetDetail();
          });
          document.querySelector("#live-history-filter-bar")?.addEventListener("change", (event) => {
            const target = event.target;
            const filters = liveHistoryFilters();
            if (target.id === "live-history-filter-start") filters.start = target.value || "";
            if (target.id === "live-history-filter-end") filters.end = target.value || "";
            if (target.id === "live-history-filter-data-type") filters.dataType = target.value || "all";
            if (target.id === "live-history-filter-trigger") filters.triggerId = target.value || "all";
            if (target.id === "live-history-filter-kind") filters.eventKind = target.value || "all";
            if (target.id === "live-history-filter-status") filters.status = target.value || "all";
            if (target.id === "live-history-filter-report-linked") filters.reportLinkedOnly = target.checked === true;
            if (target.id === "live-history-filter-attention") filters.attentionOnly = target.checked === true;
            renderLiveOperationsTimeline();
          });
          document.querySelector("#live-history-filter-clear")?.addEventListener("click", () => {
            state.liveHistoryFilters = {
              start: "",
              end: "",
              dataType: "all",
              triggerId: "all",
              eventKind: "all",
              status: "all",
              reportLinkedOnly: false,
              attentionOnly: false,
            };
            renderLiveHistoryFilters();
            renderLiveOperationsTimeline();
          });
          document.querySelector("#live-operations-timeline")?.addEventListener("click", (event) => {
            const button = event.target.closest("[data-live-event-id]");
            if (!button) return;
            openLiveEventDrawer(button.dataset.liveEventId || "");
          });
          document.querySelector("#live-triggered-reports")?.addEventListener("click", (event) => {
            const button = event.target.closest("[data-live-trigger-decision]");
            if (!button) return;
            const decisionId = button.dataset.liveTriggerDecision || "";
            state.liveMode = "history";
            renderLiveModeTabs();
            applyLiveModeVisibility();
            openLiveEventDrawer(decisionId ? `trigger_decision:${decisionId}` : "");
          });
          document.querySelector("#live-event-drawer-close")?.addEventListener("click", () => closeLiveEventDrawer());
          document.querySelector("#live-event-drawer-backdrop")?.addEventListener("click", () => closeLiveEventDrawer());
        }

        return {
          alertCount,
          refreshLive,
          renderLive,
          renderLiveSummary,
          renderLiveSourceMatrix,
          renderLiveIntelligenceStrip,
          renderLiveIntelligenceStream,
          renderLiveReportHistory,
          renderLiveTriggeredReports,
          renderLiveAlertArchive,
          renderLiveHistoryFilters,
          renderLiveJobLane,
          renderLiveOperationsTimeline,
          renderLiveEventDrawer,
          closeLiveEventDrawer,
          wire,
        };
      }

      window.HalphaDashboardLive = {
        createLiveWorkflow,
      };
    })();
