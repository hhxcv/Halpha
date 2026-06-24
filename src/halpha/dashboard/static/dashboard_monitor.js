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
          const latest = state.monitor?.latest_cycle || {};
          const alerts = alertCount(state.monitorAlerts);
          const schedule = state.schedule || {};
          const scheduleSettings = schedule.settings || {};
          const reportGeneration = schedule.report_generation || {};
          document.querySelector("#monitor-hero").innerHTML = [
            metricCell("Monitor", latest.status === "running" ? "Running" : label(latest.status || health.latest_cycle_status || "Idle"), "current state"),
            metricCell("Last cycle", formatTimestamp(latest.finished_at || latest.started_at), latest.status || "n/a"),
            metricCell("Next report", schedule.enabled ? formatTimestamp(schedule.next_run_at) : "Disabled", schedule.status || "schedule"),
            metricCell("Alerts today", alerts, "recent archive"),
            metricCell("Error state", health.error_count ? `${health.error_count} errors` : "None", "active errors"),
          ].join("");
          document.querySelector("#monitor-timeline").innerHTML = state.monitorCycles.slice(0, 8).map((cycle) => {
            const status = statusClass(cycle.status);
            return `<li class="timeline-row"><div class="timeline-time">${escapeHtml(formatTimestamp(cycle.finished_at || cycle.started_at).split(",")[1] || formatTimestamp(cycle.finished_at || cycle.started_at))}</div><div class="timeline-node ${status}">${status === "failed" ? "x" : status === "warning" ? "!" : "ok"}</div><div class="timeline-body"><strong>${escapeHtml(label(cycle.status || "Cycle"))}</strong><span>Checks: ${escapeHtml(text(cycle.product_run?.stage_count, "n/a"))} Warnings: ${escapeHtml(text(cycle.warning_count, "0"))} Errors: ${escapeHtml(text(cycle.error_count, "0"))}</span></div><span class="status-pill ${status}">${escapeHtml(cycle.status || "unknown")}</span></li>`;
          }).join("") || `<li class="empty-state">No monitor cycles yet.</li>`;
          document.querySelector("#monitor-config").innerHTML = [
            detailRow("Monitor interval", text(monitorSettings.interval_seconds, "n/a")),
            detailRow("Retry backoff cap", text(monitorSettings.failure_backoff_max_seconds, "n/a")),
            detailRow("Service status", label(service.status || "missing")),
            detailRow("Consecutive failures", text(service.consecutive_failures, "0")),
            detailRow("Alert cooldown", text(monitorSettings.cooldown_seconds ?? state.monitorAlerts?.cooldown?.fields?.cooldown_seconds, "n/a")),
            detailRow("Daily report time", scheduleSettings.time_of_day || "n/a"),
            detailRow("Daily report timezone", scheduleSettings.timezone || "n/a"),
            detailRow("Daily report mode", reportGeneration.generates_report ? "Codex report" : "No-Codex run"),
            detailRow("Daily report status", schedule.enabled ? "enabled" : "disabled"),
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
          showMonitorSchedule,
          startMonitorJob,
          wire,
        };
      }

      window.HalphaDashboardMonitor = {
        createMonitorWorkflow,
      };
    })();
