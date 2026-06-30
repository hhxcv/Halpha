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

        async function refreshLive() {
          await loadLivePayload();
          renderLive();
        }

        function renderLive() {
          renderLiveSummary();
          renderLiveSourceMatrix();
          renderLiveIntelligenceStream();
          renderLiveReportHistory();
          renderLiveSystemRuntime();
          renderLiveOperationsTimeline();
        }

        function renderLiveSummary() {
          const live = state.live || {};
          const collections = liveCollections();
          const activeJobs = Array.isArray(live.active_jobs) ? live.active_jobs : [];
          const nextRefresh = nextCollectionAttempt(collections);
          const latestSuccess = latestCollectionSuccess(collections);
          const schedule = state.schedule || {};
          const alertCounts = liveAlertCounts();
          const triggeredReports = triggeredReportCount(schedule);
          const liveStatus = live.status || "unavailable";
          const enabled = live.scheduler?.enabled === true;
          const newestAge = latestSuccess ? ageLabel(latestSuccess) : "No successful refresh";

          document.querySelector("#live-summary").innerHTML = [
            metricCell("Live state", label(enabled ? liveStatus : "disabled"), enabled ? "Core scheduler" : "disabled in config"),
            metricCell("Active refresh", activeJobs.length, activeJobs.length === 1 ? "job" : "jobs"),
            metricCell("Newest data", newestAge, latestSuccess ? formatTimestamp(latestSuccess) : "no success yet"),
            metricCell("Next refresh", nextRefresh ? formatTimestamp(nextRefresh) : "not scheduled", nextRefresh ? "source cadence" : "no due target"),
            metricCell("Next daily report", schedule.enabled ? formatTimestamp(schedule.next_run_at) : "disabled", schedule.status || "schedule"),
            metricCell("Triggered reports", triggeredReports, alertCounts.records ? `${formatNumber(alertCounts.records)} alert records` : "trigger rules pending"),
          ].join("");
        }

        function renderLiveSourceMatrix() {
          const groups = groupedCollections();
          document.querySelector("#live-source-matrix").innerHTML = DATA_TYPE_ORDER.map((dataType) => {
            const items = groups.get(dataType) || [];
            const summary = collectionGroupSummary(dataType, items);
            return `
              <article class="live-source-card ${escapeHtml(summary.statusClass)}">
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
                  ${liveFact("Latest job", summary.latestJob)}
                  ${liveFact("Issues", summary.issueCount)}
                </div>
                <div class="live-target-list">
                  ${summary.targetsDetail.map((target) => `<span class="live-target-chip">${escapeHtml(target)}</span>`).join("") || `<span class="muted">No configured target.</span>`}
                </div>
              </article>`;
          }).join("");
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
          document.querySelector("#live-intelligence-stream").innerHTML = items.length ? items.map((record) => {
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
          }).join("") : `<div class="empty-state">No bounded alert or Live warning records are available yet.</div>`;
        }

        function renderLiveReportHistory() {
          const schedule = state.schedule || {};
          const dispatches = Array.isArray(schedule.dispatches) ? schedule.dispatches : [];
          const latestDispatch = dispatches[0] || {};
          const linkedReports = Array.isArray(schedule.linked_report_refs) ? schedule.linked_report_refs : [];
          document.querySelector("#live-report-history").innerHTML = [
            detailRow("Daily schedule", schedule.enabled ? "enabled" : "disabled"),
            detailRow("Next daily report", schedule.enabled ? formatTimestamp(schedule.next_run_at) : "n/a"),
            detailRow("Latest dispatch", latestDispatch.scheduled_for ? `${formatTimestamp(latestDispatch.scheduled_for)} / ${latestDispatch.status || "unknown"}` : "n/a"),
            detailRow("Latest job", schedule.last_job_id || latestDispatch.job_id || "n/a"),
            detailRow("Linked report", linkedReports[0] || latestDispatch.report_ref || "n/a"),
            detailRow("Triggered reports", triggeredReportCount(schedule)),
          ].join("");
        }

        function renderLiveSystemRuntime() {
          const services = state.services?.services || {};
          const core = services.core || {};
          const systemMonitor = services.monitor || {};
          document.querySelector("#live-system-runtime").innerHTML = [
            detailRow("Core service", label(core.lifecycle_status || core.status || "unknown")),
            detailRow("Core heartbeat", formatTimestamp(core.heartbeat_at)),
            detailRow("System Monitor", label(systemMonitor.lifecycle_status || systemMonitor.status || "unknown")),
            detailRow("System Monitor heartbeat", formatTimestamp(systemMonitor.heartbeat_at)),
            detailRow("Config conflict", systemMonitor.config_conflict ? "yes" : "no"),
            detailRow("Last runtime error", systemMonitor.last_error?.message || core.last_error?.message || "none"),
          ].join("");
        }

        function renderLiveOperationsTimeline() {
          const live = state.live || {};
          const jobs = [...(Array.isArray(live.active_jobs) ? live.active_jobs : []), ...(Array.isArray(live.recent_jobs) ? live.recent_jobs : [])]
            .map((job) => ({
              time: job.finished_at || job.started_at || job.created_at,
              status: job.status,
              title: liveJobTitle(job),
              detail: `${job.intent || "job"} / ${durationBetween(job.started_at, job.finished_at)}`,
            }));
          const cycles = (Array.isArray(state.liveCycles) ? state.liveCycles : []).slice(0, 8).map((cycle) => ({
            time: cycle.finished_at || cycle.started_at,
            status: cycle.status,
            title: `Historical cycle ${cycle.cycle_id || ""}`.trim(),
            detail: `Warnings ${text(cycle.warning_count, "0")} / Errors ${text(cycle.error_count, "0")}`,
          }));
          const rows = [...jobs, ...cycles]
            .sort((left, right) => timestampMs(right.time) - timestampMs(left.time))
            .slice(0, 12);
          document.querySelector("#live-operations-timeline").innerHTML = rows.length ? rows.map((row) => {
            const status = statusClass(row.status || "unknown");
            return `<li class="timeline-row">
              <div class="timeline-time">${escapeHtml(formatTimestamp(row.time).split(",")[1] || formatTimestamp(row.time))}</div>
              <div class="timeline-node ${escapeHtml(status)}">${escapeHtml(status === "failed" ? "x" : status === "warning" ? "!" : "ok")}</div>
              <div class="timeline-body"><strong>${escapeHtml(row.title)}</strong><span>${escapeHtml(row.detail || "n/a")}</span></div>
              <span class="status-pill ${escapeHtml(status)}">${escapeHtml(row.status || "unknown")}</span>
            </li>`;
          }).join("") : `<li class="empty-state">No Live refresh jobs or historical cycles are available yet.</li>`;
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
            if (!groups.has(dataType)) {
              groups.set(dataType, []);
            }
            groups.get(dataType).push(item);
          });
          return groups;
        }

        function collectionGroupSummary(dataType, items) {
          const enabled = items.filter((item) => item.enabled === true);
          const errors = items.flatMap((item) => Array.isArray(item.errors) ? item.errors : []);
          const warnings = items.flatMap((item) => Array.isArray(item.warnings) ? item.warnings : []);
          const lastSuccess = latestCollectionSuccess(items);
          const nextAttempt = nextCollectionAttempt(items);
          const latestJob = latestCollectionJob(items);
          const status = errors.length ? "failed" : warnings.length ? "warning" : enabled.length ? "available" : "disabled";
          const targetsDetail = items.slice(0, 9).map((item) => targetLabel(item));
          if (items.length > targetsDetail.length) {
            targetsDetail.push(`+${items.length - targetsDetail.length} more`);
          }
          return {
            statusClass: statusClass(status),
            statusLabel: status === "disabled" ? "disabled" : status,
            scope: enabled.length ? `${enabled.length} enabled / ${items.length} configured` : `${items.length || 0} configured`,
            targets: `${enabled.length}/${items.length || 0}`,
            cadence: collectionCadence(items),
            lastSuccess: lastSuccess ? formatTimestamp(lastSuccess) : "n/a",
            nextAttempt: nextAttempt ? formatTimestamp(nextAttempt) : "n/a",
            latestJob: latestJob ? `${latestJob.latest_job_status || "unknown"} / ${latestJob.latest_job_id || "n/a"}` : "n/a",
            issueCount: errors.length + warnings.length,
            targetsDetail,
          };
        }

        function collectionCadence(items) {
          const values = uniqueNumbers(items.map((item) => item.cadence_seconds));
          if (!values.length) return "n/a";
          if (values.length === 1) return durationSeconds(values[0]);
          return `${values.length} cadences`;
        }

        function targetLabel(item) {
          const target = item.target || {};
          if (target.symbol && target.timeframe) {
            return `${target.source || "source"} ${target.symbol} ${target.timeframe}`;
          }
          return target.source || target.source_scope || item.target_key || item.data_type || "target";
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

        function liveAlertCounts() {
          return state.liveAlerts?.alert_archive?.fields?.counts || state.liveAlerts?.alert_archive?.counts || {};
        }

        function alertRecords() {
          return state.liveAlerts?.alert_archive?.fields?.sample_records || [];
        }

        function triggeredReportCount(schedule) {
          const refs = Array.isArray(schedule.linked_report_refs) ? schedule.linked_report_refs.length : 0;
          const dispatches = Array.isArray(schedule.dispatches) ? schedule.dispatches.filter((item) => item.report_ref).length : 0;
          return Math.max(refs, dispatches);
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

        function wire() {
          // Live overview is read-only in this slice. Actions are owned by later Live issues.
        }

        return {
          alertCount,
          refreshLive,
          renderLive,
          renderLiveSummary,
          renderLiveSourceMatrix,
          renderLiveIntelligenceStream,
          renderLiveReportHistory,
          renderLiveOperationsTimeline,
          wire,
        };
      }

      window.HalphaDashboardLive = {
        createLiveWorkflow,
      };
    })();
