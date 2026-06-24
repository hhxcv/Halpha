    (function () {
      function createMonitorWorkflow(deps) {
        const state = deps.state;
        const endpoints = deps.endpoints;
        const loadMonitorPayload = deps.loadMonitorPayload;
        const postJson = deps.postJson;
        const postJob = deps.postJob;
        const showToast = deps.showToast;
        const escapeHtml = deps.escapeHtml;
        const text = deps.text;
        const statusClass = deps.statusClass;
        const formatTimestamp = deps.formatTimestamp;
        const label = deps.label;
        const metricCell = deps.metricCell;
        const detailRow = deps.detailRow;
        const table = deps.table;
        const durationBetween = deps.durationBetween;

        async function refreshMonitor() {
          await loadMonitorPayload();
          renderMonitor();
        }

        function renderMonitor() {
          const health = state.monitor?.health?.fields || {};
          const monitorSettings = state.monitor?.settings || {};
          const service = health.service || {};
          const sourceStates = Array.isArray(health.source_states) ? health.source_states : [];
          const latest = state.monitor?.latest_cycle || {};
          const alerts = alertCount(state.monitorAlerts);
          const schedule = state.schedule || {};
          const scheduleSettings = schedule.settings || {};
          const reportGeneration = schedule.report_generation || {};
          const authorization = schedule.codex_authorization || {};
          const dispatches = Array.isArray(schedule.dispatches) ? schedule.dispatches : [];
          const latestDispatch = dispatches[0] || {};
          const services = state.services?.services || {};
          const monitorService = services.monitor || {};
          const scheduleService = services.schedule || {};
          document.querySelector("#monitor-hero").innerHTML = [
            metricCell("Monitor service", label(monitorService.lifecycle_status || monitorService.status || "unknown"), monitorService.config_conflict ? "config conflict" : "process health"),
            metricCell("Last cycle", formatTimestamp(latest.finished_at || latest.started_at), latest.status || "n/a"),
            metricCell("Schedule service", label(scheduleService.lifecycle_status || scheduleService.status || "unknown"), schedule.enabled ? "schedule enabled" : "schedule config disabled"),
            metricCell("Next report", schedule.enabled ? formatTimestamp(schedule.next_run_at) : "Disabled", schedule.status || "schedule"),
            metricCell("Alerts today", alerts, "recent archive"),
            metricCell("Error state", health.error_count ? `${health.error_count} errors` : "None", "active errors"),
          ].join("");
          document.querySelector("#monitor-timeline").innerHTML = state.monitorCycles.slice(0, 8).map((cycle) => {
            const status = statusClass(cycle.status);
            return `<li class="timeline-row"><div class="timeline-time">${escapeHtml(formatTimestamp(cycle.finished_at || cycle.started_at).split(",")[1] || formatTimestamp(cycle.finished_at || cycle.started_at))}</div><div class="timeline-node ${status}">${status === "failed" ? "x" : status === "warning" ? "!" : "ok"}</div><div class="timeline-body"><strong>${escapeHtml(label(cycle.status || "Cycle"))}</strong><span>Checks: ${escapeHtml(text(cycle.product_run?.stage_count, "n/a"))} Warnings: ${escapeHtml(text(cycle.warning_count, "0"))} Errors: ${escapeHtml(text(cycle.error_count, "0"))}</span></div><span class="status-pill ${status}">${escapeHtml(cycle.status || "unknown")}</span></li>`;
          }).join("") || `<li class="empty-state">No monitor cycles yet.</li>`;
          const sourceRows = sourceStates.map((source) => detailRow(
            `Source ${source.source_key || "unknown"}`,
            `${label(source.status || "unknown")} / next ${formatTimestamp(source.next_attempt_at)}`,
          ));
          document.querySelector("#monitor-config").innerHTML = [
            detailRow("Monitor process health", label(monitorService.process_health || monitorService.lifecycle_status || "unknown")),
            detailRow("Monitor instance", monitorService.instance_id || "n/a"),
            detailRow("Monitor started", formatTimestamp(monitorService.started_at)),
            detailRow("Monitor heartbeat", formatTimestamp(monitorService.heartbeat_at)),
            detailRow("Monitor heartbeat freshness", label(monitorService.heartbeat_freshness || "unknown")),
            detailRow("Monitor stop requested", formatTimestamp(monitorService.stop_requested_at)),
            detailRow("Monitor terminal state", formatTimestamp(monitorService.terminal_at)),
            detailRow("Monitor last error", monitorService.last_error?.message || "none"),
            detailRow("Monitor config conflict", monitorService.config_conflict ? "yes" : "no"),
            detailRow("Monitor interval", text(monitorSettings.interval_seconds, "n/a")),
            detailRow("Retry backoff cap", text(monitorSettings.failure_backoff_max_seconds, "n/a")),
            detailRow("Cycle state", label(service.status || "missing")),
            detailRow("Consecutive failures", text(service.consecutive_failures, "0")),
            detailRow("Alert cooldown", text(monitorSettings.cooldown_seconds ?? state.monitorAlerts?.cooldown?.fields?.cooldown_seconds, "n/a")),
            ...sourceRows,
            detailRow("Schedule process health", label(scheduleService.process_health || scheduleService.lifecycle_status || "unknown")),
            detailRow("Schedule instance", scheduleService.instance_id || "n/a"),
            detailRow("Schedule started", formatTimestamp(scheduleService.started_at)),
            detailRow("Schedule heartbeat", formatTimestamp(scheduleService.heartbeat_at)),
            detailRow("Schedule heartbeat freshness", label(scheduleService.heartbeat_freshness || "unknown")),
            detailRow("Schedule stop requested", formatTimestamp(scheduleService.stop_requested_at)),
            detailRow("Schedule terminal state", formatTimestamp(scheduleService.terminal_at)),
            detailRow("Schedule last error", scheduleService.last_error?.message || "none"),
            detailRow("Schedule config conflict", scheduleService.config_conflict ? "yes" : "no"),
            detailRow("Daily report time", scheduleSettings.time_of_day || "n/a"),
            detailRow("Daily report timezone", scheduleSettings.timezone || "n/a"),
            detailRow("Daily report mode", reportGeneration.generates_report ? "Codex report" : "No-Codex run"),
            detailRow("Daily report status", schedule.enabled ? "enabled" : "disabled"),
            detailRow("Daily report authorization", authorization.valid ? "valid" : "not authorized"),
            detailRow("Latest schedule dispatch", latestDispatch.scheduled_for ? `${formatTimestamp(latestDispatch.scheduled_for)} / ${latestDispatch.status || "unknown"}` : "n/a"),
            detailRow("Latest schedule job", schedule.last_job_id || latestDispatch.job_id || "n/a"),
            detailRow("Latest linked report", (Array.isArray(schedule.linked_report_refs) && schedule.linked_report_refs[0]) || latestDispatch.report_ref || "n/a"),
            detailRow("Watched assets", "configured in Settings"),
            detailRow("Notification channels", "Local only"),
          ].join("");
          renderMonitorAlertsTable();
          renderMonitorJobsTable();
        }

        function alertCount(payload) {
          const counts = payload?.alert_archive?.fields?.counts || payload?.alert_archive?.counts || {};
          return Number(counts.records || counts.emitted || 0);
        }

        function renderMonitorAlertsTable() {
          const records = state.monitorAlerts?.alert_archive?.fields?.sample_records || [];
          document.querySelector("#monitor-alert-table").innerHTML = records.length ? table(["Time", "Severity", "Alert", "Status"], records.slice(0, 5).map((record) => [
            formatTimestamp(record.created_at || record.timestamp),
            record.severity || record.status || "warning",
            record.title || record.message || record.alert_key || "Monitor alert",
            record.status || "new",
          ])) : `<div class="message">No recent alerts.</div>`;
        }

        function renderMonitorJobsTable() {
          const jobs = state.jobs.filter((job) => String(job.kind || "").includes("monitor") || String(job.intent || "").includes("monitor")).slice(0, 5);
          document.querySelector("#monitor-job-table").innerHTML = jobs.length ? table(["Time", "Job", "Status", "Duration"], jobs.map((job) => [
            formatTimestamp(job.created_at),
            job.intent || job.kind,
            job.status,
            durationBetween(job.started_at, job.finished_at),
          ])) : `<div class="message">No monitor jobs yet.</div>`;
        }

        async function serviceAction(role, action) {
          try {
            const result = await postJson(`${endpoints.services}/${role}/${action}`, {});
            await loadMonitorPayload();
            renderMonitor();
            const service = result.service || {};
            const status = result.status || service.status || "updated";
            const conflict = service.config_conflict ? " Config conflict is active." : "";
            document.querySelector("#monitor-control-result").innerHTML = `<div class="message">${escapeHtml(label(role))} ${escapeHtml(action)}: ${escapeHtml(label(status))}.${escapeHtml(conflict)}</div>`;
            if (Array.isArray(result.errors) && result.errors.length) {
              document.querySelector("#monitor-control-result").innerHTML = `<div class="message error">${escapeHtml(result.errors[0])}</div>`;
            }
            showToast(`${label(role)} service ${label(status)}.`);
          } catch (error) {
            document.querySelector("#monitor-control-result").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
          }
        }

        async function startMonitorJob(intent) {
          await loadMonitorPayload();
          try {
            const job = await postJob(intent, {});
            document.querySelector("#monitor-control-result").innerHTML = `<div class="message">Job ${escapeHtml(job.job_id || "")}: ${escapeHtml(job.status || "created")}</div>`;
          } catch (error) {
            document.querySelector("#monitor-control-result").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
          }
        }

        async function enableDailyReport() {
          try {
            const result = await postJson(`${endpoints.schedule}/enable`, {job_intent: "run_no_codex"});
            state.schedule = result;
            renderMonitor();
            showToast(`No-Codex daily run schedule ${result.status || "updated"}.`);
          } catch (error) {
            showToast(`Schedule update failed: ${error.message}`);
          }
        }

        function showMonitorSchedule() {
          const schedule = state.schedule || {};
          const settings = schedule.settings || {};
          const reportGeneration = schedule.report_generation || {};
          document.querySelector("#monitor-config").scrollIntoView({behavior: "smooth", block: "center"});
          document.querySelector("#monitor-control-result").innerHTML = `<div class="message">Daily report schedule: ${escapeHtml(schedule.enabled ? "enabled" : "disabled")}. Mode: ${escapeHtml(reportGeneration.generates_report ? "Codex report" : "No-Codex run")}. Time: ${escapeHtml(settings.time_of_day || "n/a")} ${escapeHtml(settings.timezone || "")}.</div>`;
        }

        function wire() {
          document.querySelectorAll("[data-service-role][data-service-action]").forEach((button) => {
            button.addEventListener("click", () => serviceAction(button.dataset.serviceRole, button.dataset.serviceAction));
          });
          document.querySelectorAll("[data-monitor-job]").forEach((button) => button.addEventListener("click", () => startMonitorJob(button.dataset.monitorJob)));
          document.querySelector("#enable-daily-report").addEventListener("click", enableDailyReport);
          document.querySelector("#schedule-monitor-button").addEventListener("click", showMonitorSchedule);
        }

        return {
          alertCount,
          enableDailyReport,
          refreshMonitor,
          renderMonitor,
          renderMonitorAlertsTable,
          renderMonitorJobsTable,
          serviceAction,
          showMonitorSchedule,
          startMonitorJob,
          wire,
        };
      }

      window.HalphaDashboardMonitor = {
        createMonitorWorkflow,
      };
    })();
