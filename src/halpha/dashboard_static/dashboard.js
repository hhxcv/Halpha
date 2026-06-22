    const app = document.querySelector("#halpha-dashboard-app");
    const displayTimezone = app.dataset.displayTimezone || "Asia/Shanghai";
    const endpoints = {
      overview: app.dataset.overviewEndpoint,
      health: app.dataset.healthEndpoint,
      runs: app.dataset.runsEndpoint,
      preview: app.dataset.previewEndpoint,
      stores: app.dataset.storesEndpoint,
      deletion: app.dataset.deleteEndpoint,
      strategies: app.dataset.strategiesEndpoint,
      monitor: app.dataset.monitorEndpoint,
      monitorCycles: app.dataset.monitorCyclesEndpoint,
      monitorAlerts: app.dataset.monitorAlertsEndpoint,
      jobs: app.dataset.jobsEndpoint,
      schedule: app.dataset.scheduleEndpoint,
      settings: app.dataset.settingsEndpoint,
      textIntel: app.dataset.textIntelligenceEndpoint,
    };

    const state = {
      view: "overview",
      overview: null,
      health: null,
      runs: [],
      selectedReport: null,
      selectedReportDetail: null,
      selectedReportPreview: null,
      reportJob: null,
      generatedReportRunId: null,
      reportSearchTerm: "",
      stores: [],
      deletionPlan: null,
      strategies: null,
      selectedStrategyOutput: null,
      strategyWindow: "all",
      monitor: null,
      monitorCycles: [],
      monitorAlerts: null,
      schedule: null,
      jobs: [],
      intelligence: null,
      selectedIntelTab: "text",
      selectedIntelItem: null,
      settingsProfile: null,
      settingsSection: "Market data",
      settingsChanges: {},
      selectedRunArtifacts: [],
      selectedSharedStores: [],
      validationJob: null,
    };

    function escapeHtml(value) {
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }

    function text(value, fallback = "n/a") {
      if (value === null || value === undefined || value === "") {
        return fallback;
      }
      return String(value);
    }

    function statusClass(status) {
      const normalized = String(status || "unknown").toLowerCase();
      if (["ok", "available", "succeeded", "success", "completed", "running"].includes(normalized)) {
        return normalized;
      }
      if (["failed", "error", "degraded", "blocked"].includes(normalized)) {
        return normalized;
      }
      if (["disabled", "not_generated", "not_run"].includes(normalized)) {
        return "skipped";
      }
      if (["insufficient_data", "unavailable"].includes(normalized)) {
        return "partial";
      }
      if (["warning", "partial", "missing", "skipped", "pending"].includes(normalized)) {
        return normalized;
      }
      return "unknown";
    }

    function label(value) {
      return text(value, "unknown").replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
    }

    function statusPill(status, labelText) {
      return `<span class="status-pill ${statusClass(status)}">${escapeHtml(labelText || label(status))}</span>`;
    }

    function setPill(selector, status, labelText) {
      const node = document.querySelector(selector);
      if (!node) {
        return;
      }
      node.className = `status-pill ${statusClass(status)}`;
      node.textContent = labelText || label(status);
    }

    function metricCell(labelText, value, note = "") {
      return `<div class="summary-cell"><div class="summary-label">${escapeHtml(labelText)}</div><div class="summary-value">${escapeHtml(value)}</div>${note ? `<div class="summary-note">${escapeHtml(note)}</div>` : ""}</div>`;
    }

    function detailRow(key, value) {
      return `<div class="detail-row"><div class="detail-key">${escapeHtml(key)}</div><div class="detail-value">${escapeHtml(text(value))}</div></div>`;
    }

    function pct(value) {
      if (typeof value !== "number" || Number.isNaN(value)) {
        return "n/a";
      }
      return `${value.toFixed(1)}%`;
    }

    function formatNumber(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) {
        return text(value);
      }
      return new Intl.NumberFormat("en-US").format(number);
    }

    function formatBytes(bytes) {
      const number = Number(bytes);
      if (!Number.isFinite(number) || number <= 0) {
        return "n/a";
      }
      const units = ["B", "KB", "MB", "GB", "TB"];
      let value = number;
      let index = 0;
      while (value >= 1024 && index < units.length - 1) {
        value /= 1024;
        index += 1;
      }
      return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[index]}`;
    }

    function looksLikeIsoTimestamp(value) {
      return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value);
    }

    function formatTimestamp(value) {
      if (!value) {
        return "n/a";
      }
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return String(value);
      }
      try {
        return new Intl.DateTimeFormat("en-US", {
          timeZone: displayTimezone,
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        }).format(date);
      } catch (_error) {
        return date.toISOString();
      }
    }

    function durationBetween(start, end) {
      const s = start ? new Date(start).getTime() : NaN;
      const e = end ? new Date(end).getTime() : NaN;
      if (!Number.isFinite(s) || !Number.isFinite(e) || e < s) {
        return "n/a";
      }
      return formatDurationMs(e - s);
    }

    function formatDurationMs(ms) {
      const totalSeconds = Math.round(ms / 1000);
      const minutes = Math.floor(totalSeconds / 60);
      const seconds = totalSeconds % 60;
      const hours = Math.floor(minutes / 60);
      if (hours > 0) {
        return `${hours}h ${minutes % 60}m`;
      }
      if (minutes > 0) {
        return `${minutes}m ${seconds}s`;
      }
      return `${seconds}s`;
    }

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, {
        ...options,
        headers: {
          "Accept": "application/json",
          ...(options.body ? {"Content-Type": "application/json"} : {}),
          ...(options.headers || {}),
        },
      });
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      return response.json();
    }

    async function postJson(url, body) {
      return fetchJson(url, {method: "POST", body: JSON.stringify(body || {})});
    }

    function showToast(message) {
      const toast = document.querySelector("#toast");
      toast.textContent = message;
      toast.classList.add("visible");
      window.setTimeout(() => toast.classList.remove("visible"), 3600);
    }

    function viewFromHash() {
      const raw = (window.location.hash || "#overview").slice(1) || "overview";
      return raw;
    }

    function setView(view) {
      const valid = ["overview", "reports", "strategies", "monitor", "intelligence", "settings"];
      state.view = valid.includes(view) ? view : "overview";
      document.querySelectorAll(".view").forEach((node) => node.classList.toggle("hidden", node.dataset.view !== state.view));
      document.querySelectorAll("[data-view-target]").forEach((node) => {
        const active = node.dataset.viewTarget === state.view;
        node.classList.toggle("active", active);
        if (active) {
          node.setAttribute("aria-current", "page");
        } else {
          node.removeAttribute("aria-current");
        }
      });
      refreshCurrentView();
    }

    async function refreshCurrentView() {
      if (state.view === "overview") return refreshOverview();
      if (state.view === "reports") return refreshReports();
      if (state.view === "strategies") return refreshStrategies();
      if (state.view === "monitor") return refreshMonitor();
      if (state.view === "intelligence") return refreshIntelligence();
      if (state.view === "settings") return refreshSettings();
    }

    async function loadHealth() {
      try {
        state.health = await fetchJson(endpoints.health);
        const ref = state.health?.config?.ref || "Current config";
        document.querySelector("#config-ref").textContent = ref;
        document.querySelector("#sidebar-health-text").textContent = state.health?.status === "ok" ? "All local systems operational." : "Dashboard status needs attention.";
      } catch (error) {
        document.querySelector("#config-ref").textContent = "unavailable";
        document.querySelector("#sidebar-health-text").textContent = error.message;
      }
    }

    async function refreshOverview() {
      await Promise.allSettled([loadHealth(), loadRuns(), loadStores(), loadMonitorPayload()]);
      try {
        state.overview = await fetchJson(endpoints.overview);
      } catch (error) {
        state.overview = {status: "failed", sections: {}, warnings: [error.message], errors: [error.message]};
      }
      renderOverview();
    }

    async function loadRuns() {
      const payload = await fetchJson(endpoints.runs);
      state.runs = Array.isArray(payload.runs) ? payload.runs : [];
      return payload;
    }

    async function loadStores() {
      const payload = await fetchJson(endpoints.stores);
      state.stores = Array.isArray(payload.stores) ? payload.stores : [];
      return payload;
    }

    async function loadJobs() {
      const payload = await fetchJson(endpoints.jobs);
      state.jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
      return payload;
    }

    async function loadDeletionPlan() {
      state.deletionPlan = await fetchJson(endpoints.deletion);
      return state.deletionPlan;
    }

    async function loadMonitorPayload() {
      const [monitor, cycles, alerts, jobs, schedule] = await Promise.allSettled([
        fetchJson(endpoints.monitor),
        fetchJson(endpoints.monitorCycles),
        fetchJson(endpoints.monitorAlerts),
        loadJobs(),
        fetchJson(endpoints.schedule),
      ]);
      state.monitor = monitor.status === "fulfilled" ? monitor.value : null;
      state.monitorCycles = cycles.status === "fulfilled" && Array.isArray(cycles.value.cycles) ? cycles.value.cycles : [];
      state.monitorAlerts = alerts.status === "fulfilled" ? alerts.value : null;
      state.jobs = jobs.status === "fulfilled" && Array.isArray(jobs.value.jobs) ? jobs.value.jobs : [];
      state.schedule = schedule.status === "fulfilled" ? schedule.value : null;
    }

    function renderOverview() {
      const sections = state.overview?.sections || {};
      const latest = sections.latest_run?.fields || {};
      const reportRuns = reportRecords();
      const totalReports = reportRuns.length;
      const successful = reportRuns.filter((item) => ["succeeded", "success", "available"].includes(String(item.status || "").toLowerCase())).length;
      const successRate = totalReports ? (successful / totalReports) * 100 : 0;
      const durations = reportRuns.map((item) => durationMs(item.started_at, item.finished_at)).filter(Number.isFinite);
      const averageDuration = durations.length ? formatDurationMs(durations.reduce((a, b) => a + b, 0) / durations.length) : "n/a";
      const latestReport = reportRuns[0] || {};

      setPill("#overview-report-status", latestReport.status || "missing", latestReport.status || "No report");
      document.querySelector("#overview-report-metrics").innerHTML = [
        reportMetric("Total reports", totalReports, "All time"),
        reportMetric("Daily reports", reportRuns.filter((item) => item.type === "Daily").length, "All time"),
        reportMetric("Monitor-triggered", reportRuns.filter((item) => item.type === "Monitor-triggered").length, "All time"),
        reportMetric("Manual reports", reportRuns.filter((item) => item.type === "Manual").length, "All time"),
      ].join("");
      document.querySelector("#overview-latest-report").innerHTML = [
        detailRow("Latest report", latestReport.title || "No generated report"),
        detailRow("Status", latestReport.status || "n/a"),
        detailRow("Generated", formatTimestamp(latestReport.finished_at)),
        detailRow("Duration", durationBetween(latestReport.started_at, latestReport.finished_at)),
        detailRow("Average duration", averageDuration),
        detailRow("Success rate", totalReports ? pct(successRate) : "n/a"),
      ].join("");
      renderReportTrend("#overview-report-chart", reportRuns);
      document.querySelector("#open-latest-report").onclick = () => {
        setHashView("reports");
        if (latestReport.run_id) {
          selectReport(latestReport.run_id);
        }
      };
      if (!state.reportJob) {
        state.reportJob = latestReportJob();
      }
      renderReportJob(state.reportJob);

      renderRuntime(sections);
      renderOverviewMonitor();
      renderOverviewData();
      renderAttention();
    }

    function reportMetric(title, value, note) {
      return `<div class="report-metric"><div class="summary-label">${escapeHtml(title)}</div><div class="metric-big">${escapeHtml(formatNumber(value))}</div><div class="summary-note">${escapeHtml(note)}</div></div>`;
    }

    function durationMs(start, end) {
      const s = start ? new Date(start).getTime() : NaN;
      const e = end ? new Date(end).getTime() : NaN;
      return Number.isFinite(s) && Number.isFinite(e) && e >= s ? e - s : NaN;
    }

    function renderRuntime(sections) {
      const latest = sections.latest_run?.fields || {};
      const selection = latest.selection || {};
      const now = Date.now();
      const started = latest.started_at || latest.finished_at;
      const startedTime = started ? new Date(started).getTime() : NaN;
      const uptime = Number.isFinite(startedTime) ? formatDurationMs(now - startedTime) : "n/a";
      const storeRecords = state.stores.reduce((sum, store) => sum + numericRecordCount(store), 0);
      const dataSizeLabel = storeRecords ? `${formatNumber(storeRecords)} records` : "n/a";
      document.querySelector("#overview-runtime").innerHTML = [
        detailRow("Overview run source", label(selection.label || "n/a")),
        detailRow("Overview run", latest.run_id || "n/a"),
        detailRow("Latest run", selection.latest_run_id || "n/a"),
        detailRow("Latest successful run", selection.latest_successful_run_id || "n/a"),
        detailRow("Service start time", formatTimestamp(started)),
        detailRow("Historical runtime", state.runs.length ? `${state.runs.length} runs recorded` : "No run history"),
        detailRow("Current uptime", uptime),
        detailRow("Data size", dataSizeLabel),
        detailRow("Memory usage", "not collected"),
        detailRow("Storage usage", storeRecords ? "tracked by record count" : "not collected"),
      ].join("");
    }

    function renderOverviewMonitor() {
      const health = state.monitor?.health?.fields || {};
      const latest = state.monitor?.latest_cycle || {};
      const status = latest.status || health.latest_cycle_status || state.monitor?.status || "partial";
      const schedule = state.schedule || {};
      const scheduleLabel = schedule.enabled
        ? formatTimestamp(schedule.next_run_at)
        : "No daily report scheduled";
      setPill("#overview-monitor-pill", status, status);
      document.querySelector("#overview-monitor").innerHTML = [
        detailRow("Monitor state", label(status)),
        detailRow("Monitor start time", formatTimestamp(health.updated_at || latest.started_at)),
        detailRow("Trigger count", health.cycle_count ?? state.monitorCycles.length),
        detailRow("Last trigger time", formatTimestamp(latest.finished_at || latest.started_at)),
        detailRow("Next scheduled report", scheduleLabel),
        detailRow("Recent alerts", alertCount(state.monitorAlerts)),
      ].join("");
    }

    function renderOverviewData() {
      const stores = state.stores;
      const categories = [
        ["OHLCV", "ohlcv_history"],
        ["Text", "text_event_history"],
        ["Derivatives", "derivatives_market_history"],
        ["On-chain", "onchain_flow_history"],
        ["Macro", "macro_calendar_history"],
        ["Outcomes", "outcome_history"],
      ];
      document.querySelector("#overview-data-cards").innerHTML = categories.map(([labelText, name]) => {
        const store = stores.find((item) => item.name === name) || {};
        const records = numericRecordCount(store);
        return `<div class="data-card"><div class="data-card-title">${escapeHtml(labelText)}</div><div class="data-card-value">${records ? formatNumber(records) : "n/a"}</div>${statusPill(store.status || "missing", store.status || "missing")}</div>`;
      }).join("");
      const warnings = stores.flatMap((store) => store.warnings || []);
      const errors = stores.flatMap((store) => store.errors || []);
      setPill("#overview-data-pill", errors.length ? "failed" : warnings.length ? "warning" : "available", errors.length ? "Issues" : warnings.length ? "Warnings" : "Good");
      document.querySelector("#overview-quality").innerHTML = `
        <div class="summary-strip" style="grid-template-columns: repeat(3, minmax(0, 1fr));">
          ${metricCell("Validation pass", Math.max(0, stores.length - warnings.length - errors.length), "stores")}
          ${metricCell("Warnings", warnings.length, "latest state")}
          ${metricCell("Errors", errors.length, "latest state")}
        </div>`;
    }

    function numericRecordCount(store) {
      const fields = store?.fields || {};
      const candidates = [fields.records, fields.record_count, fields.inserted_records, fields.incoming_records];
      const value = candidates.find((item) => Number.isFinite(Number(item)));
      return value === undefined ? 0 : Number(value);
    }

    function renderAttention() {
      const items = [];
      state.stores.forEach((store) => {
        (store.warnings || []).slice(0, 1).forEach((warning) => items.push({severity: "warning", title: `${store.title || store.name}`, copy: warning, action: "Review data issues", view: "intelligence"}));
        (store.errors || []).slice(0, 1).forEach((error) => items.push({severity: "failed", title: `${store.title || store.name}`, copy: error, action: "Review data issues", view: "intelligence"}));
      });
      (state.monitor?.warnings || []).slice(0, 1).forEach((warning) => items.push({severity: "warning", title: "Monitor warning", copy: warning, action: "Check monitor run", view: "monitor"}));
      if (!items.length) {
        items.push({severity: "available", title: "No urgent issues", copy: "Dashboard has no current high-priority attention item.", action: "Open reports", view: "reports"});
      }
      const visible = items.slice(0, 3);
      setPill("#attention-count", visible.length > 1 ? "warning" : "available", `${visible.length}`);
      document.querySelector("#attention-list").innerHTML = visible.map((item) => `
        <li class="attention-item">
          <div class="attention-title"><span>${escapeHtml(item.title)}</span>${statusPill(item.severity, item.severity)}</div>
          <div class="attention-copy">${escapeHtml(item.copy)}</div>
          <button class="ghost-button" type="button" data-view-shortcut="${escapeHtml(item.view)}" style="width:100%; margin-top:10px;">${escapeHtml(item.action)}</button>
        </li>`).join("");
      wireShortcutButtons();
    }

    async function refreshReports() {
      await Promise.allSettled([loadRuns(), loadJobs()]);
      if (!state.reportJob) {
        state.reportJob = latestReportJob();
      }
      renderReportJob(state.reportJob);
      renderReportLibrary();
      const reports = reportRecords();
      if (!reports.length) {
        state.selectedReport = null;
        document.querySelector("#selected-report-kicker").textContent = "No report selected";
        document.querySelector("#report-reader").innerHTML = `<div class="empty-state">No generated reports are available yet. Use Generate report to create a new report.</div>`;
        document.querySelector("#report-details").innerHTML = "";
        document.querySelector("#report-outline").innerHTML = "";
        document.querySelector("#report-sources").innerHTML = "";
      } else if (!state.selectedReport || !reports.some((item) => item.run_id === state.selectedReport.run_id)) {
        await selectReport(reports[0].run_id);
      } else {
        await selectReport(state.selectedReport.run_id);
      }
    }

    function reportRecords() {
      return state.runs.filter((run) => isAvailableReport(run)).map((run) => {
        const type = reportType(run);
        return {
          ...run,
          type,
          title: reportTitle(run, type),
          report_path: reportPath(run),
        };
      });
    }

    function isAvailableReport(run) {
      const reportState = run?.report_state || {};
      return reportState.status === "available" && Boolean(run?.report || reportState.artifact);
    }

    function reportType(run) {
      const source = `${run.run_dir || ""} ${run.run_id || ""}`.toLowerCase();
      if (source.includes("monitor") || source.includes("cycle")) {
        return "Monitor-triggered";
      }
      if (String(run.codex_status || "").toLowerCase() === "skipped") {
        return "Manual";
      }
      return "Daily";
    }

    function reportTitle(run, type) {
      if (type === "Monitor-triggered") return `Monitor Report ${run.run_id}`;
      if (type === "Manual") return `Manual Research Report ${run.run_id}`;
      return `Daily Market Brief ${run.run_id}`;
    }

    function reportPath(run) {
      if (!run) return "";
      const report = String(run.report || run.report_state?.artifact || "");
      if (report.startsWith("runs/") || report.startsWith("data/")) return report;
      if (report) return joinPath(run.run_dir, report);
      return joinPath(run.run_dir, "report/report.md");
    }

    function renderReportLibrary() {
      const query = document.querySelector("#report-search").value.trim().toLowerCase();
      const records = reportRecords().filter((item) => !query || `${item.title} ${item.run_id}`.toLowerCase().includes(query));
      const groups = ["Daily", "Monitor-triggered", "Manual"];
      document.querySelector("#report-library-groups").innerHTML = groups.map((group) => {
        const items = records.filter((item) => item.type === group);
        return `<section><h3 class="group-title"><span>${escapeHtml(group)}</span><span class="tag">${items.length}</span></h3>${items.slice(0, 12).map((item) => {
          const generated = item.run_id === state.generatedReportRunId;
          return `
          <button class="report-row ${state.selectedReport?.run_id === item.run_id ? "active" : ""}" type="button" data-report-run-id="${escapeHtml(item.run_id)}">
            <span class="report-row-title"><span class="health-dot"></span>${escapeHtml(item.title)}${generated ? ` <span class="tag">new</span>` : ""}</span>
            <span class="report-row-meta">${escapeHtml(formatTimestamp(item.finished_at || item.started_at))}</span>
          </button>`;
        }).join("") || `<div class="message">No ${escapeHtml(group.toLowerCase())} reports.</div>`}</section>`;
      }).join("");
      document.querySelectorAll("[data-report-run-id]").forEach((button) => button.addEventListener("click", () => selectReport(button.dataset.reportRunId)));
    }

    async function selectReport(runId) {
      const run = reportRecords().find((item) => item.run_id === runId) || {run_id: runId};
      state.selectedReport = run;
      state.selectedReportDetail = null;
      renderReportLibrary();
      document.querySelector("#selected-report-kicker").textContent = `${run.type || "Report"} - ${formatTimestamp(run.finished_at || run.started_at)}`;
      document.querySelector("#report-reader").innerHTML = `<div class="empty-state">Loading rendered report.</div>`;
      try {
        state.selectedReportDetail = await fetchJson(`${endpoints.runs}/${encodeURIComponent(runId)}`);
      } catch (_error) {
        state.selectedReportDetail = null;
      }
      renderReportDetails(run, state.selectedReportDetail);
      const path = run.report_path || reportPath(run);
      try {
        const preview = await fetchJson(`${endpoints.preview}?path=${encodeURIComponent(path)}`);
        state.selectedReportPreview = preview;
        renderReportPreview(preview, run);
      } catch (error) {
        document.querySelector("#report-reader").innerHTML = `<div class="empty-state">Report preview is unavailable. ${escapeHtml(error.message)}</div>`;
      }
    }

    function renderReportDetails(run, detail) {
      const refs = reportSourceRefs(run, detail);
      document.querySelector("#report-details").innerHTML = [
        detailRow("Type", run.type),
        detailRow("Run", run.run_id),
        detailRow("Run role", runRole(run)),
        detailRow("Status", run.status),
        detailRow("Duration", durationBetween(run.started_at, run.finished_at)),
        detailRow("Generated", formatTimestamp(run.finished_at || run.started_at)),
        detailRow("Origin", run.codex_status === "skipped" ? "Local pipeline" : "Codex report"),
      ].join("");
      document.querySelector("#report-sources").innerHTML = refs.length
        ? refs.slice(0, 12).map((source) => `<li class="compact-row">${escapeHtml(source)}</li>`).join("")
        : `<li class="message">No source refs recorded for this report.</li>`;
    }

    function runRole(run) {
      const latest = run?.latest_state || {};
      if (latest.is_latest_run && latest.is_latest_successful_run) return "Latest run and latest successful run";
      if (latest.is_latest_run) return "Latest run";
      if (latest.is_latest_successful_run) return "Latest successful run";
      return "Historical run";
    }

    function reportSourceRefs(run, detail) {
      const refs = [];
      if (run?.manifest) refs.push(run.manifest);
      if (run?.report_path) refs.push(run.report_path);
      (detail?.source_artifacts || []).forEach((ref) => refs.push(ref));
      (detail?.artifacts || []).forEach((artifact) => {
        const path = artifact.path || artifact.ref || artifact.artifact;
        if (path) refs.push(path);
      });
      return unique(refs);
    }

    function renderReportPreview(preview, run) {
      const content = typeof preview.preview === "string" ? preview.preview : "";
      if (!content) {
        const messages = [...(preview.warnings || []), ...(preview.errors || [])];
        document.querySelector("#report-reader").innerHTML = `<div class="empty-state">${escapeHtml(messages.join(" ") || "No readable report content is recorded for this run.")}</div>`;
        renderOutline("");
        return;
      }
      const markdown = typeof content === "string" ? content : JSON.stringify(content, null, 2);
      document.querySelector("#report-reader").innerHTML = `<article class="markdown-reader">${markdownToHtml(markdown, state.reportSearchTerm)}</article>`;
      renderOutline(markdown);
    }

    function renderOutline(markdown) {
      const headings = markdown.split(/\r?\n/).filter((line) => /^#{1,3}\s+/.test(line)).slice(0, 12);
      document.querySelector("#report-outline").innerHTML = headings.length ? headings.map((line, index) => {
        const title = line.replace(/^#{1,3}\s+/, "");
        return `<li><a href="#" data-outline-index="${index}">${escapeHtml(title)}</a></li>`;
      }).join("") : `<li class="message">No outline extracted.</li>`;
    }

    async function deleteSelectedReport() {
      if (!state.selectedReport?.run_id) {
        showToast("Select a report first.");
        return;
      }
      const ok = window.confirm("Delete this report's single-run artifacts? Shared data is not deleted.");
      if (!ok) return;
      try {
        const result = await postJson(endpoints.deletion, {
          kind: "run_artifacts",
          run_ids: [state.selectedReport.run_id],
          confirm: "DELETE RUN DATA",
        });
        showToast(`Deletion ${result.status || "submitted"}.`);
        state.selectedReport = null;
        await refreshReports();
      } catch (error) {
        showToast(`Delete failed: ${error.message}`);
      }
    }

    function downloadSelectedReport() {
      const preview = state.selectedReportPreview;
      if (!preview || typeof preview.preview !== "string") {
        showToast("No report text is available to download.");
        return;
      }
      const blob = new Blob([preview.preview], {type: "text/markdown"});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${state.selectedReport?.run_id || "report"}.md`;
      link.click();
      URL.revokeObjectURL(url);
    }

    async function refreshStrategies() {
      try {
        state.strategies = await fetchJson(endpoints.strategies);
      } catch (error) {
        state.strategies = {status: "failed", errors: [error.message], standalone: {backtests: [], experiments: []}, commands: {options: {}}};
      }
      renderStrategyControls();
      renderStrategies();
    }

    function strategyOutputs() {
      const standalone = state.strategies?.standalone || {};
      const backtests = Array.isArray(standalone.backtests) ? standalone.backtests : [];
      const pipeline = state.strategies?.pipeline?.artifacts || [];
      return [...backtests, ...pipeline].filter(Boolean);
    }

    function renderStrategyControls() {
      const options = state.strategies?.commands?.options || {};
      fillSelect("#strategy-symbol", options.symbols || []);
      fillSelect("#strategy-timeframe", options.timeframes || []);
      fillSelect("#strategy-name", options.strategy_names || []);
      ["#strategy-symbol", "#strategy-timeframe", "#strategy-name"].forEach((selector) => {
        document.querySelector(selector).onchange = () => {
          state.selectedStrategyOutput = null;
          renderStrategies();
        };
      });
      document.querySelector("#strategy-range").value = state.strategyWindow;
      document.querySelector("#strategy-range").onchange = () => setStrategyWindow(document.querySelector("#strategy-range").value);
    }

    function fillSelect(selector, values) {
      const node = document.querySelector(selector);
      const current = node.value;
      node.innerHTML = values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
      if (values.includes(current)) node.value = current;
    }

    function renderStrategies() {
      const outputs = strategyOutputs();
      const selected = selectedStrategyOutput(outputs);
      state.selectedStrategyOutput = selected;
      syncStrategyControls(selected);
      const metrics = strategyMetrics(selected);
      document.querySelector("#strategy-metrics").innerHTML = [
        metricCell("Total return", metrics.totalReturn, "strategy"),
        metricCell("Max drawdown", metrics.drawdown, "risk"),
        metricCell("Sharpe", metrics.sharpe, "risk adjusted"),
        metricCell("Win rate", metrics.winRate, "trades"),
        metricCell("Profit factor", metrics.profitFactor, "gross"),
        metricCell("Trades", metrics.trades, "count"),
      ].join("");
      const vis = visibleBacktestVisualization(selected);
      const identityLabel = [vis.symbol, vis.timeframe].filter(Boolean).join(" - ");
      document.querySelector("#strategy-chart-title").textContent = identityLabel ? `${identityLabel} - Halpha` : "No backtest visualization selected";
      document.querySelector("#strategy-chart-meta").textContent = vis.strategy_name
        ? `${vis.strategy_name} - ${vis.status || selected?.status || "partial"}`
        : "Run a backtest or select an artifact with candlestick data.";
      document.querySelector("#strategy-quote-label").textContent = quoteAsset(vis.symbol);
      document.querySelector("#strategy-window-label").textContent = strategyWindowLabel(vis);
      document.querySelector("#strategy-chart-clock").textContent = displayTimezone;
      syncStrategyWindowControls();
      renderCandlestickSvg(vis);
      renderStrategyParams(selected, vis);
      renderRecentTrades(vis);
      renderBacktestRuns(outputs);
      renderStrategyTab("trades");
    }

    function selectedStrategyOutput(outputs) {
      const selectedName = document.querySelector("#strategy-name").value;
      const selectedSymbol = document.querySelector("#strategy-symbol").value;
      const selectedTimeframe = document.querySelector("#strategy-timeframe").value;
      const matchingControls = outputs.find((item) => {
        const identity = strategyIdentity(item);
        return (!selectedName || identity.name === selectedName)
          && (!selectedSymbol || identity.symbol === selectedSymbol)
          && (!selectedTimeframe || identity.timeframe === selectedTimeframe);
      });
      if (matchingControls) return matchingControls;
      if (state.selectedStrategyOutput && outputs.includes(state.selectedStrategyOutput)) return state.selectedStrategyOutput;
      return outputs[0] || null;
    }

    function strategyIdentity(item) {
      const vis = item?.visualization || {};
      const fields = item?.fields || {};
      const inputs = fields.inputs || {};
      return {
        name: vis.strategy_name || inputs.strategy_name || fields.strategy_name || item?.name || "",
        symbol: vis.symbol || inputs.symbol || fields.symbol || "",
        timeframe: vis.timeframe || inputs.timeframe || fields.timeframe || "",
      };
    }

    function syncStrategyControls(item) {
      const identity = strategyIdentity(item);
      setSelectIfPresent("#strategy-name", identity.name);
      setSelectIfPresent("#strategy-symbol", identity.symbol);
      setSelectIfPresent("#strategy-timeframe", identity.timeframe);
    }

    function setSelectIfPresent(selector, value) {
      const node = document.querySelector(selector);
      if (!node || !value) return;
      if (Array.from(node.options).some((option) => option.value === value)) {
        node.value = value;
      }
    }

    function strategyMetrics(item) {
      const fields = item?.fields || {};
      const metrics = fields.metrics || {};
      const strategy = metrics.strategy_metrics || fields.strategy_metrics || {};
      const trade = metrics.trade_summary || fields.trade_summary || {};
      return {
        totalReturn: metricPercent(strategy.net_return_pct ?? strategy.total_return_pct ?? item?.records?.summary?.net_return_pct),
        drawdown: metricPercent(strategy.max_drawdown_pct),
        sharpe: text(strategy.sharpe_ratio ?? strategy.sharpe),
        winRate: metricPercent(trade.win_rate_pct ?? trade.win_rate),
        profitFactor: text(strategy.profit_factor),
        trades: text(trade.trade_count ?? fields.metrics?.trade_summary?.trade_count),
        longTrades: text(trade.long_trade_count ?? trade.long_trades),
        shortTrades: text(trade.short_trade_count ?? trade.short_trades),
        bestTrade: metricPercent(trade.best_trade_pct ?? trade.best_trade_return_pct),
        worstTrade: metricPercent(trade.worst_trade_pct ?? trade.worst_trade_return_pct),
      };
    }

    function metricPercent(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) return "n/a";
      const sign = number > 0 ? "+" : "";
      return `${sign}${number.toFixed(2)}%`;
    }

    function backtestVisualization(item) {
      const vis = item?.visualization || {};
      if (Array.isArray(vis.bars) && vis.bars.length) return vis;
      const identity = strategyIdentity(item);
      return {
        status: item?.status || "missing",
        strategy_name: identity.name,
        symbol: identity.symbol,
        timeframe: identity.timeframe,
        bars: [],
        markers: [],
        equity_curve: [],
      };
    }

    function visibleBacktestVisualization(item) {
      return applyStrategyWindow(backtestVisualization(item), state.strategyWindow);
    }

    function applyStrategyWindow(vis, windowValue) {
      const bars = Array.isArray(vis.bars) ? vis.bars : [];
      const limit = windowValue === "all" ? 0 : Number(windowValue);
      if (!Number.isInteger(limit) || limit <= 0 || bars.length <= limit) {
        return vis;
      }
      const visibleBars = bars.slice(-limit);
      const visibleTimes = new Set(visibleBars.map((bar) => bar.time));
      const markers = Array.isArray(vis.markers)
        ? vis.markers.filter((marker) => visibleTimes.has(marker.time))
        : [];
      const curve = Array.isArray(vis.equity_curve) ? vis.equity_curve.slice(-limit) : [];
      return {...vis, bars: visibleBars, markers, equity_curve: curve};
    }

    function setStrategyWindow(value) {
      state.strategyWindow = ["all", "180", "90", "30"].includes(String(value)) ? String(value) : "all";
      const range = document.querySelector("#strategy-range");
      if (range) range.value = state.strategyWindow;
      syncStrategyWindowControls();
      renderStrategies();
    }

    function syncStrategyWindowControls() {
      document.querySelectorAll("[data-strategy-window]").forEach((button) => {
        button.classList.toggle("active", button.dataset.strategyWindow === state.strategyWindow);
      });
    }

    function strategyName(item) {
      return strategyIdentity(item).name || "No strategy selected";
    }

    function quoteAsset(symbol) {
      const value = String(symbol || "").trim();
      if (!value) return "n/a";
      for (const suffix of ["USDT", "USDC", "USD", "BTC", "ETH"]) {
        if (value.endsWith(suffix) && value.length > suffix.length) {
          return suffix;
        }
      }
      return value;
    }

    function strategyWindowLabel(vis) {
      const bars = Array.isArray(vis.bars) ? vis.bars : [];
      const timeframe = vis.timeframe || "timeframe n/a";
      if (!bars.length) return `${timeframe} / no candle window`;
      const first = bars[0]?.time;
      const last = bars[bars.length - 1]?.time;
      return `${timeframe} / ${bars.length} candles / ${formatTimestamp(first)} to ${formatTimestamp(last)}`;
    }

    function renderCandlestickSvg(vis) {
      const svg = document.querySelector("#backtest-chart");
      const bars = vis.bars || [];
      if (!bars.length) {
        svg.innerHTML = `<text x="490" y="235" fill="#9fb2c7" text-anchor="middle">No backtest visualization available</text>`;
        return;
      }
      const width = 980;
      const height = 470;
      const pad = {left: 44, right: 70, top: 28, bottom: 86};
      const max = Math.max(...bars.map((bar) => Number(bar.high) || 0));
      const min = Math.min(...bars.map((bar) => Number(bar.low) || 0));
      const priceY = (value) => pad.top + (max - value) / Math.max(1, max - min) * (height - pad.top - pad.bottom);
      const x = (index) => pad.left + index * ((width - pad.left - pad.right) / Math.max(1, bars.length - 1));
      const candleWidth = Math.max(3, Math.min(9, (width - pad.left - pad.right) / bars.length * 0.58));
      const maxVolume = Math.max(...bars.map((bar) => Number(bar.volume) || 0), 1);
      const markerByTime = new Map((vis.markers || []).map((marker) => [marker.time, marker]));
      const candleSvg = bars.map((bar, index) => {
        const open = Number(bar.open);
        const close = Number(bar.close);
        const high = Number(bar.high);
        const low = Number(bar.low);
        const up = close >= open;
        const color = up ? "#00a88f" : "#f04438";
        const cx = x(index);
        const yOpen = priceY(open);
        const yClose = priceY(close);
        const yHigh = priceY(high);
        const yLow = priceY(low);
        const bodyY = Math.min(yOpen, yClose);
        const bodyH = Math.max(2, Math.abs(yOpen - yClose));
        const volumeH = (Number(bar.volume) || 0) / maxVolume * 70;
        const volumeY = height - pad.bottom + 64 - volumeH;
        const marker = markerByTime.get(bar.time);
        const markerSvg = marker ? renderTradeMarker(cx, priceY(Number(marker.price) || close), marker) : "";
        return `
          <line x1="${cx}" x2="${cx}" y1="${yHigh}" y2="${yLow}" stroke="${color}" stroke-width="1.2"></line>
          <rect x="${cx - candleWidth / 2}" y="${bodyY}" width="${candleWidth}" height="${bodyH}" fill="${color}" rx="1"></rect>
          <rect x="${cx - candleWidth / 2}" y="${volumeY}" width="${candleWidth}" height="${volumeH}" fill="${color}" opacity="0.42"></rect>
          ${markerSvg}`;
      }).join("");
      const grid = Array.from({length: 6}, (_, index) => {
        const y = pad.top + index * ((height - pad.top - pad.bottom) / 5);
        const price = max - index * ((max - min) / 5);
        return `<line x1="${pad.left}" x2="${width - pad.right}" y1="${y}" y2="${y}" stroke="rgba(255,255,255,0.07)"></line><text x="${width - pad.right + 12}" y="${y + 4}" fill="#9fb2c7" font-size="12">${formatNumber(Math.round(price))}</text>`;
      }).join("");
      const ma50 = renderAverageLine(bars, x, priceY, 12, "#4f8cff");
      const ma200 = renderAverageLine(bars, x, priceY, 34, "#f59e0b");
      svg.innerHTML = `${grid}${ma50}${ma200}${candleSvg}<text x="54" y="24" fill="#dbe7f3" font-size="13">${escapeHtml([vis.symbol, vis.timeframe].filter(Boolean).join(" - ") || "Backtest")}</text><text x="54" y="44" fill="#9fb2c7" font-size="12">MA 50 close  MA 200 close</text>`;
    }

    function renderAverageLine(bars, x, priceY, windowSize, color) {
      const points = [];
      bars.forEach((bar, index) => {
        const slice = bars.slice(Math.max(0, index - windowSize + 1), index + 1);
        const avg = slice.reduce((sum, item) => sum + Number(item.close || 0), 0) / slice.length;
        points.push(`${x(index)},${priceY(avg)}`);
      });
      return `<polyline points="${points.join(" ")}" fill="none" stroke="${color}" stroke-width="2" opacity="0.95"></polyline>`;
    }

    function renderTradeMarker(x, y, marker) {
      const entry = String(marker.kind || marker.label || "").toLowerCase().includes("entry") || String(marker.label || "").toLowerCase().includes("buy");
      const color = entry ? "#00a88f" : "#f04438";
      const labelText = marker.label || (entry ? "Buy" : "Sell");
      const labelY = entry ? y + 28 : y - 24;
      return `<g><line x1="${x}" x2="${x}" y1="${entry ? y + 4 : y - 4}" y2="${entry ? labelY - 10 : labelY + 10}" stroke="${color}" stroke-width="1.4"></line><rect x="${x - 17}" y="${labelY - 11}" width="34" height="22" rx="4" fill="${color}"></rect><text x="${x}" y="${labelY + 4}" fill="#fff" text-anchor="middle" font-size="11" font-weight="800">${escapeHtml(labelText)}</text></g>`;
    }

    function renderStrategyParams(item, vis) {
      const inputs = item?.fields?.inputs || {};
      const rows = {
        "Momentum window": inputs.momentum_window,
        "Volume window": inputs.volume_window,
        "Symbol": vis.symbol || inputs.symbol,
        "Timeframe": vis.timeframe || inputs.timeframe,
        "Stoploss": inputs.stoploss,
        "Take profit": inputs.take_profit,
        "Stake per trade": inputs.stake_per_trade,
        "Time in force": inputs.time_in_force,
      };
      document.querySelector("#strategy-params").innerHTML = Object.entries(rows).map(([key, value]) => `<tr><td>${escapeHtml(key)}</td><td>${escapeHtml(text(value))}</td></tr>`).join("");
    }

    function renderRecentTrades(vis) {
      const markers = (vis.markers || []).slice(-5).reverse();
      document.querySelector("#recent-trades").innerHTML = markers.length ? `<div class="trade-list">${markers.map((marker) => `<div class="trade-row"><span class="status-pill ${String(marker.kind || "").toLowerCase().includes("exit") ? "failed" : "available"}">${escapeHtml(marker.label || marker.kind)}</span><strong>${escapeHtml(formatNumber(marker.price || ""))}</strong><small>${escapeHtml(formatTimestamp(marker.time))}</small></div>`).join("")}</div>` : `<div class="message">No recent trades available.</div>`;
    }

    function renderBacktestRuns(outputs) {
      document.querySelector("#backtest-runs").innerHTML = outputs.slice(0, 4).map((item, index) => `
        <button class="report-row ${item === state.selectedStrategyOutput ? "active" : ""}" type="button" data-backtest-index="${index}">
          <span class="report-row-title">${escapeHtml(strategyName(item))}</span>
          <span class="report-row-meta">${escapeHtml(item.fields?.created_at || item.status || "latest")}</span>
        </button>`).join("") || `<div class="message">No backtest runs yet.</div>`;
      document.querySelectorAll("[data-backtest-index]").forEach((button) => {
        button.addEventListener("click", () => {
          state.selectedStrategyOutput = outputs[Number(button.dataset.backtestIndex)];
          renderStrategies();
        });
      });
    }

    function renderStrategyTab(tab) {
      document.querySelectorAll("[data-strategy-tab]").forEach((button) => button.classList.toggle("active", button.dataset.strategyTab === tab));
      const vis = visibleBacktestVisualization(state.selectedStrategyOutput);
      const metrics = strategyMetrics(state.selectedStrategyOutput);
      if (tab === "trades" || tab === "list") {
        document.querySelector("#strategy-tab-content").innerHTML = `<div class="summary-strip" style="grid-template-columns: repeat(6, minmax(0, 1fr));">
          ${metricCell("Total trades", metrics.trades, "")}
          ${metricCell("Long", metrics.longTrades, "")}
          ${metricCell("Short", metrics.shortTrades, "")}
          ${metricCell("Win rate", metrics.winRate, "")}
          ${metricCell("Best trade", metrics.bestTrade, "")}
          ${metricCell("Worst trade", metrics.worstTrade, "")}
        </div>`;
      } else if (tab === "equity") {
        const curve = Array.isArray(vis.equity_curve) ? vis.equity_curve : [];
        document.querySelector("#strategy-tab-content").innerHTML = curve.length
          ? `<svg viewBox="0 0 900 120" style="width:100%; height:120px;">${lineChartPath(curve.map((point) => point.net_equity ?? point.equity ?? point.value))}</svg>`
          : `<div class="message">No equity curve is available for the selected backtest.</div>`;
      } else {
        document.querySelector("#strategy-tab-content").innerHTML = renderStrategyDiagnostics();
      }
    }

    function renderStrategyDiagnostics() {
      const groups = strategyWarningGroups();
      if (!groups.length) {
        return `<div class="message">No grouped strategy warnings are recorded for the selected data.</div>`;
      }
      return `<table class="kv-table"><tbody>${groups.map((group) => `
        <tr>
          <td>${escapeHtml(group.message || "warning")}</td>
          <td>${escapeHtml(formatNumber(group.count || 0))} occurrence${Number(group.count) === 1 ? "" : "s"}</td>
          <td>${escapeHtml((group.sources || []).slice(0, 2).join("; ") || "source n/a")}</td>
        </tr>`).join("")}</tbody></table>`;
    }

    function strategyWarningGroups() {
      const groups = Array.isArray(state.strategies?.warning_groups) ? state.strategies.warning_groups : [];
      return groups.slice(0, 12);
    }

    function lineChartPath(rawValues) {
      const values = rawValues.map(Number).filter(Number.isFinite);
      if (!values.length) {
        return `<text x="450" y="64" text-anchor="middle" fill="#5d6675">No chart data available</text>`;
      }
      const min = Math.min(...values);
      const max = Math.max(...values);
      const points = values.map((value, index) => {
        const x = 24 + index * (850 / Math.max(1, values.length - 1));
        const y = 100 - ((value - min) / Math.max(1, max - min)) * 80;
        return `${x},${y}`;
      });
      return `<polyline points="${points.join(" ")}" fill="none" stroke="#008575" stroke-width="3"></polyline>`;
    }

    async function startBacktest() {
      const params = {
        strategy_name: document.querySelector("#strategy-name").value,
        symbol: document.querySelector("#strategy-symbol").value,
        timeframe: document.querySelector("#strategy-timeframe").value,
      };
      if (!params.strategy_name || !params.symbol || !params.timeframe) {
        showToast("Select a configured strategy, symbol, and timeframe first.");
        return;
      }
      const job = await postJob("backtest", params);
      showToast(`Backtest ${job.status}.`);
    }

    function downloadSelectedOhlcv() {
      const vis = visibleBacktestVisualization(state.selectedStrategyOutput);
      const bars = Array.isArray(vis.bars) ? vis.bars : [];
      if (!bars.length) {
        showToast("No OHLCV bars are available for the selected backtest.");
        return;
      }
      const columns = ["time", "open", "high", "low", "close", "volume"];
      const csv = [
        columns.join(","),
        ...bars.map((bar) => columns.map((column) => csvCell(bar[column])).join(",")),
      ].join("\n");
      const blob = new Blob([csv], {type: "text/csv"});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${vis.symbol || "ohlcv"}-${vis.timeframe || "window"}-backtest-bars.csv`;
      link.click();
      URL.revokeObjectURL(url);
    }

    function csvCell(value) {
      const textValue = String(value ?? "");
      if (/[",\n\r]/.test(textValue)) {
        return `"${textValue.replace(/"/g, '""')}"`;
      }
      return textValue;
    }

    async function refreshMonitor() {
      await loadMonitorPayload();
      renderMonitor();
    }

    function renderMonitor() {
      const health = state.monitor?.health?.fields || {};
      const monitorSettings = state.monitor?.settings || {};
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
        detailRow("Max cycles before restart", text(monitorSettings.max_cycles, "n/a")),
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

    async function refreshIntelligence() {
      try {
        const [textIntel] = await Promise.all([fetchJson(endpoints.textIntel), loadStores().catch(() => null)]);
        state.intelligence = textIntel;
      } catch (error) {
        state.intelligence = {status: "failed", warnings: [error.message], artifacts: []};
      }
      renderIntelligence();
    }

    function renderIntelligence() {
      const allItems = intelligenceItems();
      renderIntelFilterOptions(allItems);
      const items = filteredIntelligenceItems(allItems);
      if (!state.selectedIntelItem || !items.includes(state.selectedIntelItem)) {
        state.selectedIntelItem = items[0] || null;
      }
      renderIntelKpis(items);
      renderIntelEvents(items);
      renderIntelCharts(items);
      renderIntelDetail(state.selectedIntelItem);
    }

    function renderIntelFilterOptions(items) {
      fillSelect("#intel-asset", ["All assets", ...unique(items.flatMap((item) => intelAssets(item))).sort()]);
      fillSelect("#intel-source", ["All sources", ...unique(items.flatMap((item) => item.sources || [])).sort()]);
    }

    function filteredIntelligenceItems(items) {
      const asset = document.querySelector("#intel-asset").value;
      const range = document.querySelector("#intel-range").value;
      const severity = document.querySelector("#intel-severity").value;
      const source = document.querySelector("#intel-source").value;
      const sort = document.querySelector("#intel-sort").value;
      const filtered = items.filter((item) => {
        if (severity !== "All severities" && item.severity !== severity) return false;
        if (source !== "All sources" && !(item.sources || []).includes(source)) return false;
        if (asset !== "All assets" && !intelAssets(item).includes(asset)) return false;
        if (!withinIntelRange(item.time, range)) return false;
        return true;
      });
      return filtered.sort((left, right) => {
        if (sort === "severity") {
          return severityRank(right.severity) - severityRank(left.severity);
        }
        return timestampMs(right.time) - timestampMs(left.time);
      });
    }

    function intelAssets(item) {
      return unique(item?.assets || []);
    }

    function withinIntelRange(value, range) {
      if (range === "all") return true;
      const days = range === "30d" ? 30 : range === "7d" ? 7 : null;
      if (!days) return true;
      const itemTime = timestampMs(value);
      if (!Number.isFinite(itemTime)) return false;
      return itemTime >= Date.now() - days * 24 * 3600 * 1000;
    }

    function timestampMs(value) {
      const time = value ? new Date(value).getTime() : NaN;
      return Number.isFinite(time) ? time : 0;
    }

    function severityRank(value) {
      return {Low: 1, Medium: 2, High: 3}[value] || 0;
    }

    function resetIntelFilters() {
      document.querySelector("#intel-asset").value = "All assets";
      document.querySelector("#intel-range").value = "all";
      document.querySelector("#intel-severity").value = "All severities";
      document.querySelector("#intel-source").value = "All sources";
      document.querySelector("#intel-sort").value = "latest";
      state.selectedIntelItem = null;
      renderIntelligence();
      showToast("Filters reset.");
    }

    function intelligenceItems() {
      const artifacts = Array.isArray(state.intelligence?.artifacts) ? state.intelligence.artifacts : [];
      if (state.selectedIntelTab === "quality") {
        return state.stores.map((store) => ({
          title: store.title || store.name,
          severity: store.errors?.length ? "High" : store.warnings?.length ? "Medium" : "Low",
          category: "Data quality",
          time: store.fields?.updated_at,
          summary: [...(store.warnings || []), ...(store.errors || [])].join(" ") || `${store.source_label || "Data store"} status.`,
          sources: store.source_artifacts || [],
          assets: [],
          tags: [store.status || "unknown", store.source_label || store.state_scope || "store"],
        }));
      }
      const filtered = artifacts.filter((artifact) => {
        const title = `${artifact.name || ""} ${artifact.fields?.title || ""}`.toLowerCase();
        return state.selectedIntelTab === "text" || title.includes(state.selectedIntelTab);
      });
      if (filtered.length) {
        return filtered.map((artifact) => ({
          title: artifact.fields?.title || artifact.name || "Intelligence artifact",
          severity: artifact.errors?.length ? "High" : artifact.warnings?.length ? "Medium" : "Low",
          category: artifact.name || "Text",
          time: artifact.fields?.updated_at || artifact.fields?.created_at,
          summary: [...(artifact.warnings || []), ...(artifact.errors || [])].join(" ") || `${label(artifact.status)} source-aware intelligence artifact.`,
          sources: artifact.source_artifacts || [],
          assets: intelligenceAssets(artifact),
          tags: [artifact.status || "unknown"],
        }));
      }
      return [];
    }

    function intelligenceAssets(artifact) {
      const fields = artifact?.fields || {};
      const values = [
        fields.symbol,
        fields.asset,
        ...(Array.isArray(fields.symbols) ? fields.symbols : []),
        ...(Array.isArray(fields.assets) ? fields.assets : []),
      ];
      return unique(values).slice(0, 8);
    }

    function renderIntelKpis(items) {
      document.querySelector("#intel-kpis").innerHTML = [
        metricCell("High-impact events", items.filter((item) => item.severity === "High").length, "selected tab"),
        metricCell("Source coverage", unique(items.flatMap((item) => item.sources || [])).length, "sources"),
        metricCell("Warnings", items.filter((item) => item.severity === "Medium").length, "needs review"),
        metricCell("New topics", items.length, "latest window"),
        metricCell("Data quality", state.stores.filter((store) => store.status === "ok" || store.status === "available").length, "healthy stores"),
      ].join("");
    }

    function renderIntelEvents(items) {
      document.querySelector("#intel-events").innerHTML = items.map((item, index) => `
        <button class="event-row ${item === state.selectedIntelItem ? "active" : ""}" type="button" data-intel-index="${index}">
          <span class="muted">${escapeHtml(formatTimestamp(item.time).split(",")[1] || "")}</span>
          <span><span class="event-title">${escapeHtml(item.title)}</span><span class="tag-row">${(item.tags || []).slice(0, 3).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</span></span>
          <span class="status-pill ${item.severity === "High" ? "failed" : item.severity === "Medium" ? "warning" : "available"}">${escapeHtml(item.severity)}</span>
        </button>`).join("") || `<div class="empty-state">No intelligence items for this tab.</div>`;
      document.querySelectorAll("[data-intel-index]").forEach((button) => button.addEventListener("click", () => {
        state.selectedIntelItem = items[Number(button.dataset.intelIndex)];
        renderIntelligence();
      }));
    }

    function renderIntelCharts(items) {
      document.querySelector("#intel-volume-chart").innerHTML = areaChart(items);
      document.querySelector("#intel-severity-chart").innerHTML = donutChart(items);
    }

    function renderIntelDetail(item) {
      if (!item) {
        document.querySelector("#intel-detail").innerHTML = `<div class="empty-state">Select an intelligence item.</div>`;
        return;
      }
      document.querySelector("#intel-detail").innerHTML = `
        <div class="tag-row"><span class="status-pill ${item.severity === "High" ? "failed" : item.severity === "Medium" ? "warning" : "available"}">${escapeHtml(item.severity)}</span><span class="tag">${escapeHtml(item.category)}</span></div>
        <h2 style="font-size: 20px; line-height: 1.25; margin: 16px 0 8px;">${escapeHtml(item.title)}</h2>
        <p class="muted" style="line-height:1.55;">${escapeHtml(item.summary)}</p>
        <div class="summary-strip" style="grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 14px 0;">
          ${metricCell("Severity", item.severity, "")}
          ${metricCell("Sources", (item.sources || []).length, "")}
          ${metricCell("Updated", formatTimestamp(item.time), "")}
        </div>
        <h3>Evidence</h3>
        <ul>${(item.sources || []).length ? item.sources.slice(0, 4).map((source) => `<li>${escapeHtml(source)}</li>`).join("") : `<li class="message">No source refs recorded for this item.</li>`}</ul>
        <h3>Related assets</h3>
        <div class="tag-row">${(item.assets || []).length ? item.assets.map((asset) => `<span class="tag">${escapeHtml(asset)}</span>`).join("") : `<span class="message">No related assets recorded.</span>`}</div>`;
    }

    function areaChart(items) {
      const now = new Date();
      const start = new Date(now.getTime() - 6 * 24 * 3600 * 1000);
      const days = Array.from({length: 7}, (_, index) => {
        const day = new Date(start.getTime() + index * 24 * 3600 * 1000);
        return day.toISOString().slice(0, 10);
      });
      const counts = new Map(days.map((day) => [day, 0]));
      (items || []).forEach((item) => {
        const date = new Date(item.time);
        if (Number.isNaN(date.getTime())) return;
        const key = date.toISOString().slice(0, 10);
        if (counts.has(key)) {
          counts.set(key, counts.get(key) + 1);
        }
      });
      const values = days.map((day) => counts.get(day) || 0);
      if (!values.some((value) => value > 0)) {
        return `<text x="260" y="126" text-anchor="middle" fill="#5d6675">No timestamped intelligence data</text>`;
      }
      const max = Math.max(...values, 1);
      const points = values.map((value, index) => `${40 + index * 70},${210 - value / max * 150}`);
      const area = `40,210 ${points.join(" ")} ${40 + (values.length - 1) * 70},210`;
      return `<polygon points="${area}" fill="#dbeafe"></polygon><polyline points="${points.join(" ")}" fill="none" stroke="#3b82f6" stroke-width="3"></polyline>`;
    }

    function donutChart(items) {
      if (!items.length) {
        return `<text x="150" y="126" text-anchor="middle" fill="#5d6675">No intelligence items</text>`;
      }
      const total = items.length;
      const high = items.filter((item) => item.severity === "High").length;
      const medium = items.filter((item) => item.severity === "Medium").length;
      const low = total - high - medium;
      return `<circle cx="150" cy="120" r="68" fill="none" stroke="#e5e7eb" stroke-width="28"></circle><circle cx="150" cy="120" r="68" fill="none" stroke="#dc2626" stroke-width="28" stroke-dasharray="${high / total * 427} 427" transform="rotate(-90 150 120)"></circle><circle cx="150" cy="120" r="68" fill="none" stroke="#f59e0b" stroke-width="28" stroke-dasharray="${medium / total * 427} 427" stroke-dashoffset="${-(high / total * 427)}" transform="rotate(-90 150 120)"></circle><circle cx="150" cy="120" r="68" fill="none" stroke="#008575" stroke-width="28" stroke-dasharray="${low / total * 427} 427" stroke-dashoffset="${-((high + medium) / total * 427)}" transform="rotate(-90 150 120)"></circle><text x="150" y="116" text-anchor="middle" font-size="24" font-weight="800" fill="#111827">${total}</text><text x="150" y="138" text-anchor="middle" font-size="12" fill="#5d6675">Total</text>`;
    }

    async function refreshSettings() {
      await Promise.allSettled([loadHealth(), loadStores(), loadDeletionPlan(), loadConfigProfile()]);
      renderSettings();
    }

    async function loadConfigProfile() {
      state.settingsProfile = await fetchJson(endpoints.settings);
      return state.settingsProfile;
    }

    function renderSettings() {
      const sections = Array.isArray(state.settingsProfile?.sections) && state.settingsProfile.sections.length
        ? state.settingsProfile.sections
        : ["General", "Market data", "Strategy", "Reports", "Monitor", "Intelligence sources", "Storage", "Dashboard"];
      if (!sections.includes(state.settingsSection)) {
        state.settingsSection = sections[0] || "General";
      }
      document.querySelector("#settings-nav").innerHTML = sections.map((section) => `<button type="button" class="${section === state.settingsSection ? "active" : ""}" data-settings-section="${escapeHtml(section)}">${escapeHtml(section)}<span>&gt;</span></button>`).join("");
      document.querySelectorAll("[data-settings-section]").forEach((button) => button.addEventListener("click", () => {
        state.settingsSection = button.dataset.settingsSection;
        renderSettings();
      }));
      const profileStatus = state.settingsProfile?.status || "loading";
      setPill("#settings-valid-pill", profileStatus, profileStatus === "available" ? "Loaded" : profileStatus);
      document.querySelector("#settings-last-validated").textContent = state.validationJob ? `Last validation job: ${state.validationJob.status || "created"}` : "Last validated: not run";
      document.querySelector("#config-profile").textContent = state.settingsProfile?.config?.ref || state.health?.config?.ref || "Current config";
      document.querySelector("#settings-section-title").textContent = state.settingsSection;
      document.querySelector("#settings-form").innerHTML = settingsForm(state.settingsSection);
      renderChangeSummary();
      renderValidationResults();
      renderStorageMaintenance();
      wireSettingsControls();
      wireCleanupControls();
    }

    function settingsForm(section) {
      const fields = settingsFields().filter((field) => field.section === section);
      if (section === "Storage") {
        return `<div class="message">Use Storage maintenance below to delete single-run artifacts or shared stores. Shared data requires exact store selection and typed confirmation.</div>`;
      }
      if (!fields.length) {
        return `<div class="message">No editable controls are available for this section yet.</div>`;
      }
      return fields.map(settingRow).join("");
    }

    function settingsFields() {
      return Array.isArray(state.settingsProfile?.fields) ? state.settingsProfile.fields : [];
    }

    function settingField(path) {
      return settingsFields().find((field) => field.path === path);
    }

    function settingValue(field) {
      if (Object.prototype.hasOwnProperty.call(state.settingsChanges, field.path)) {
        return state.settingsChanges[field.path];
      }
      return field.value;
    }

    function settingRow(field) {
      return `
        <div class="form-row">
          <div>
            <strong>${escapeHtml(field.label)}</strong>
            ${field.description ? `<small class="muted">${escapeHtml(field.description)}</small>` : ""}
          </div>
          ${settingControl(field)}
        </div>`;
    }

    function settingControl(field) {
      const value = settingValue(field);
      const path = escapeHtml(field.path);
      if (field.control === "toggle") {
        const on = Boolean(value);
        return `<button class="toggle ${on ? "on" : ""}" type="button" role="switch" aria-checked="${on ? "true" : "false"}" aria-label="${escapeHtml(field.label)}" data-setting-path="${path}" data-setting-type="bool"></button>`;
      }
      if (field.control === "select") {
        const options = Array.isArray(field.options) && field.options.length ? field.options : [value];
        return `<select class="select-input" data-setting-path="${path}" data-setting-type="string">${options.map((option) => `<option value="${escapeHtml(option)}" ${String(option) === String(value) ? "selected" : ""}>${escapeHtml(option)}</option>`).join("")}</select>`;
      }
      if (field.control === "number") {
        return `<input class="text-input" type="number" min="1" step="1" value="${escapeHtml(value)}" data-setting-path="${path}" data-setting-type="positive_int">`;
      }
      if (field.control === "multi_select") {
        const values = Array.isArray(value) ? value.map(String) : [];
        const options = Array.isArray(field.options) ? field.options : values;
        return `<div class="chip-row">${options.map((option) => `<label class="chip"><input type="checkbox" ${values.includes(String(option)) ? "checked" : ""} data-setting-path="${path}" data-setting-type="multi_select" data-setting-option="${escapeHtml(option)}"> ${escapeHtml(option)}</label>`).join("")}</div>`;
      }
      if (field.control === "tags") {
        const values = Array.isArray(value) ? value.join(", ") : String(value || "");
        return `<input class="text-input" value="${escapeHtml(values)}" data-setting-path="${path}" data-setting-type="string_list" placeholder="BTCUSDT, ETHUSDT">`;
      }
      return `<input class="text-input" value="${escapeHtml(value)}" data-setting-path="${path}" data-setting-type="string">`;
    }

    function wireSettingsControls() {
      document.querySelectorAll("[data-setting-path]").forEach((node) => {
        if (node.dataset.settingType === "bool") {
          node.addEventListener("click", () => {
            const next = !node.classList.contains("on");
            node.classList.toggle("on", next);
            node.setAttribute("aria-checked", next ? "true" : "false");
            recordSettingChange(node.dataset.settingPath, next);
          });
          return;
        }
        node.addEventListener("change", () => {
          const path = node.dataset.settingPath;
          if (node.dataset.settingType === "multi_select") {
            recordSettingChange(path, multiSelectValues(path));
          } else if (node.dataset.settingType === "positive_int") {
            recordSettingChange(path, Number(node.value));
          } else if (node.dataset.settingType === "string_list") {
            recordSettingChange(path, node.value.split(",").map((item) => item.trim()).filter(Boolean));
          } else {
            recordSettingChange(path, node.value);
          }
        });
      });
    }

    function multiSelectValues(path) {
      return Array.from(document.querySelectorAll("[data-setting-path]"))
        .filter((node) => node.dataset.settingPath === path && node.dataset.settingOption && node.checked)
        .map((node) => node.dataset.settingOption);
    }

    function recordSettingChange(path, value) {
      const field = settingField(path);
      if (!field) {
        return;
      }
      if (valuesEqual(value, field.value)) {
        delete state.settingsChanges[path];
      } else {
        state.settingsChanges[path] = value;
      }
      renderChangeSummary();
    }

    function valuesEqual(left, right) {
      return JSON.stringify(left) === JSON.stringify(right);
    }

    function renderChangeSummary() {
      const paths = Object.keys(state.settingsChanges);
      setPill("#change-count", paths.length ? "warning" : "available", `${paths.length} changes`);
      const saveButton = document.querySelector("#settings-save");
      if (saveButton) {
        saveButton.disabled = !paths.length;
      }
      document.querySelector("#change-summary").innerHTML = paths.length
        ? paths.map((path) => {
          const field = settingField(path);
          const labelText = field?.label || path;
          return `<li class="compact-row"><strong>${escapeHtml(labelText)}</strong><span>${escapeHtml(path)}</span></li>`;
        }).join("")
        : `<li class="message">No pending changes.</li>`;
    }

    function renderValidationResults() {
      if (state.validationJob) {
        renderValidationJob(state.validationJob);
        return;
      }
      document.querySelector("#validation-results").innerHTML = `<div class="message">Use Validate to run the local product validation command. Warnings are shown here without exposing private local values.</div>`;
    }

    function renderStorageMaintenance() {
      renderRunCleanupList();
      renderSharedCleanupList();
    }

    function renderRunCleanupList() {
      const items = state.deletionPlan?.run_artifacts?.items || [];
      state.selectedRunArtifacts = state.selectedRunArtifacts.filter((id) => items.some((item) => item.run_id === id && item.deletable));
      const list = document.querySelector("#run-cleanup-list");
      if (!list) return;
      if (!items.length) {
        list.innerHTML = `<div class="message">No run artifacts are available for cleanup.</div>`;
        return;
      }
      list.innerHTML = items.slice(0, 80).map((item) => `
        <label class="cleanup-option">
          <input type="checkbox" data-run-cleanup="${escapeHtml(item.run_id)}" ${state.selectedRunArtifacts.includes(item.run_id) ? "checked" : ""} ${item.deletable ? "" : "disabled"}>
          <span>
            <strong>${escapeHtml(item.title || item.run_id)}</strong>
            <small>${escapeHtml(formatTimestamp(item.started_at))} / ${escapeHtml(item.run_dir || "")}${item.blocked_reason ? ` / ${escapeHtml(item.blocked_reason)}` : ""}</small>
          </span>
          ${statusPill(item.status || "unknown")}
        </label>`).join("");
    }

    function renderSharedCleanupList() {
      const items = state.deletionPlan?.shared_data?.items || [];
      state.selectedSharedStores = state.selectedSharedStores.filter((name) => items.some((item) => item.name === name && item.deletable));
      const list = document.querySelector("#shared-cleanup-list");
      if (!list) return;
      if (!items.length) {
        list.innerHTML = `<div class="message">No shared data stores are available for cleanup.</div>`;
        return;
      }
      list.innerHTML = items.map((item) => {
        const refs = Array.isArray(item.delete_refs) ? item.delete_refs.filter((ref) => ref.exists).length : 0;
        return `
          <label class="cleanup-option">
            <input type="checkbox" data-shared-cleanup="${escapeHtml(item.name)}" ${state.selectedSharedStores.includes(item.name) ? "checked" : ""} ${item.deletable ? "" : "disabled"}>
            <span>
              <strong>${escapeHtml(item.title || item.name)}</strong>
              <small>${escapeHtml(item.group || "shared")} / ${formatNumber(item.records || 0)} records / ${refs} refs${item.blocked_reason ? ` / ${escapeHtml(item.blocked_reason)}` : ""}</small>
            </span>
            ${statusPill(item.status || "unknown")}
          </label>`;
      }).join("");
    }

    function wireCleanupControls() {
      document.querySelectorAll("[data-run-cleanup]").forEach((node) => {
        node.addEventListener("change", () => {
          state.selectedRunArtifacts = selectedValues("[data-run-cleanup]", "runCleanup");
        });
      });
      document.querySelectorAll("[data-shared-cleanup]").forEach((node) => {
        node.addEventListener("change", () => {
          state.selectedSharedStores = selectedValues("[data-shared-cleanup]", "sharedCleanup");
        });
      });
    }

    function selectedValues(selector, datasetKey) {
      return Array.from(document.querySelectorAll(selector))
        .filter((node) => node.checked && !node.disabled)
        .map((node) => node.dataset[datasetKey])
        .filter(Boolean);
    }

    async function saveSettings() {
      const paths = Object.keys(state.settingsChanges);
      if (!paths.length) {
        showToast("No settings changes to save.");
        return;
      }
      const ok = window.confirm(`Save ${paths.length} setting change(s)? A backup will be created before the config is updated.`);
      if (!ok) {
        showToast("Settings save cancelled.");
        return;
      }
      try {
        const result = await postJson(endpoints.settings, {confirm: true, changes: state.settingsChanges});
        if (result.status === "succeeded") {
          state.settingsProfile = result.profile;
          state.settingsChanges = {};
          renderSettings();
        }
        const errors = Array.isArray(result.errors) ? result.errors : [];
        document.querySelector("#validation-results").innerHTML = `<div class="message ${errors.length ? "error" : ""}"><strong>Config save ${escapeHtml(result.status)}</strong>${result.backup_ref ? `<br>Backup: ${escapeHtml(result.backup_ref)}` : ""}${errors.length ? `<br>${escapeHtml(errors.join("; "))}` : ""}</div>`;
        showToast(`Settings save ${result.status}.`);
      } catch (error) {
        document.querySelector("#validation-results").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      }
    }

    async function backupSettings() {
      try {
        const result = await postJson(`${endpoints.settings}/backup`, {});
        document.querySelector("#validation-results").innerHTML = `<div class="message ${result.status === "succeeded" ? "" : "error"}"><strong>Config backup ${escapeHtml(result.status)}</strong>${result.backup_ref ? `<br>${escapeHtml(result.backup_ref)}` : ""}${Array.isArray(result.errors) && result.errors.length ? `<br>${escapeHtml(result.errors.join("; "))}` : ""}</div>`;
        showToast(`Config backup ${result.status}.`);
      } catch (error) {
        document.querySelector("#validation-results").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      }
    }

    async function postJob(intent, params = {}) {
      const job = await postJson(endpoints.jobs, {intent, params});
      showToast(`${label(intent)} job ${job.status || "created"}.`);
      if (intent === "validate") {
        state.validationJob = job;
        renderValidationJob(job);
      }
      return job;
    }

    async function fetchJob(jobId) {
      return fetchJson(`${endpoints.jobs}/${encodeURIComponent(jobId)}`);
    }

    function latestReportJob() {
      const jobs = Array.isArray(state.jobs) ? state.jobs : [];
      return jobs.find((job) => job.intent === "run") || null;
    }

    function reportJobRefs(job) {
      return job?.result_refs && typeof job.result_refs === "object" ? job.result_refs : {};
    }

    function renderReportJob(job) {
      const nodes = [
        document.querySelector("#overview-report-job-status"),
        document.querySelector("#reports-report-job-status"),
      ].filter(Boolean);
      if (!nodes.length) {
        return;
      }
      if (!job) {
        nodes.forEach((node) => {
          node.classList.add("hidden");
          node.innerHTML = "";
        });
        setReportButtonsDisabled(false);
        return;
      }
      const refs = reportJobRefs(job);
      const status = job.status || "created";
      const runId = refs.run_id || state.generatedReportRunId || "";
      const reportRef = refs.report || "";
      const manifestRef = refs.run_manifest || refs.manifest || "";
      if (runId) {
        state.generatedReportRunId = runId;
      }
      const warnings = Array.isArray(job.warnings) ? job.warnings : [];
      const errors = Array.isArray(job.errors) ? job.errors : [];
      const detail = [
        `Job: ${job.job_id || "pending"}`,
        runId ? `Run: ${runId}` : "",
        reportRef ? `Report: ${reportRef}` : manifestRef ? `Manifest: ${manifestRef}` : "",
      ].filter(Boolean).join(" | ");
      const hint = reportRef
        ? "Report artifact recorded. Open the Reports view to read it."
        : terminalJobStatus(status)
          ? "No report artifact is recorded for this job yet."
          : "The job is still running; the report list will refresh after completion.";
      nodes.forEach((node) => {
        node.className = `message job-status ${errors.length || statusClass(status) === "failed" ? "error" : warnings.length ? "warning" : ""}`.trim();
        node.innerHTML = `
          <strong>Report job ${escapeHtml(label(status))}</strong><br>
          ${escapeHtml(detail)}
          <br>${escapeHtml(hint)}
          ${warnings.length ? `<br>Warnings: ${escapeHtml(warnings.slice(0, 2).join("; "))}` : ""}
          ${errors.length ? `<br>Errors: ${escapeHtml(errors.slice(0, 2).join("; "))}` : ""}
        `;
      });
      setReportButtonsDisabled(!terminalJobStatus(status));
    }

    function setReportButtonsDisabled(disabled) {
      document.querySelectorAll("[data-report-job]").forEach((button) => {
        button.disabled = Boolean(disabled);
      });
    }

    async function startReportJob() {
      const ok = window.confirm("Generate a full Codex report now? This can take a while and will create a new run.");
      if (!ok) {
        showToast("Report generation cancelled.");
        return;
      }
      const pending = {
        job_id: "pending",
        intent: "run",
        kind: "product_run",
        status: "creating",
        created_at: new Date().toISOString(),
        result_refs: {},
        warnings: [],
        errors: [],
      };
      state.reportJob = pending;
      renderReportJob(pending);
      try {
        const job = await postJob("run", {confirm_codex: true});
        state.reportJob = job;
        renderReportJob(job);
        if (job.job_id) {
          pollReportJob(job.job_id);
        }
      } catch (error) {
        state.reportJob = {
          ...pending,
          status: "failed",
          errors: [error.message],
        };
        renderReportJob(state.reportJob);
        showToast(`Report generation failed: ${error.message}`);
      }
    }

    async function pollReportJob(jobId) {
      for (let attempt = 0; attempt < 600; attempt += 1) {
        await wait(3000);
        try {
          const job = await fetchJob(jobId);
          state.reportJob = job;
          renderReportJob(job);
          if (terminalJobStatus(job.status)) {
            await Promise.allSettled([loadRuns(), loadJobs()]);
            renderReportJob(job);
            const runId = reportJobRefs(job).run_id;
            if (runId) {
              state.generatedReportRunId = runId;
              if (state.view === "reports") {
                await refreshReports();
                const report = reportRecords().find((item) => item.run_id === runId);
                if (report) {
                  await selectReport(runId);
                }
              } else if (state.view === "overview") {
                renderOverview();
              }
            }
            showToast(`Report job ${job.status || "completed"}.`);
            return;
          }
        } catch (error) {
          state.reportJob = {
            job_id: jobId,
            intent: "run",
            kind: "product_run",
            status: "failed",
            result_refs: {},
            errors: [error.message],
            warnings: [],
          };
          renderReportJob(state.reportJob);
          return;
        }
      }
      showToast("Report job is still running. Refresh the dashboard to check status.");
    }

    function wait(ms) {
      return new Promise((resolve) => window.setTimeout(resolve, ms));
    }

    function terminalJobStatus(status) {
      return ["succeeded", "failed", "cancelled", "unsupported", "blocked", "not_started"].includes(String(status || "").toLowerCase());
    }

    function renderValidationJob(job) {
      const status = job?.status || "created";
      const jobId = job?.job_id || "pending";
      const errors = Array.isArray(job?.errors) ? job.errors : [];
      const warnings = Array.isArray(job?.warnings) ? job.warnings : [];
      document.querySelector("#validation-results").innerHTML = `
        <div class="message">
          <strong>Validation job ${escapeHtml(status)}</strong><br>
          Job: ${escapeHtml(jobId)}
          ${warnings.length ? `<br>Warnings: ${escapeHtml(warnings.slice(0, 2).join("; "))}` : ""}
          ${errors.length ? `<br>Errors: ${escapeHtml(errors.slice(0, 2).join("; "))}` : ""}
        </div>`;
    }

    async function cancelRunningMonitorJobs() {
      try {
        await loadMonitorPayload();
        const jobs = state.jobs.filter((job) => {
          const kind = String(job.kind || job.intent || "");
          return kind.includes("monitor") && job.cancellable !== false && !terminalJobStatus(job.status);
        });
        if (!jobs.length) {
          document.querySelector("#monitor-control-result").innerHTML = `<div class="message">No running monitor job is attached to this dashboard runtime.</div>`;
          return;
        }
        const results = [];
        for (const job of jobs) {
          results.push(await postJson(`${endpoints.jobs}/${encodeURIComponent(job.job_id)}/cancel`, {}));
        }
        await loadMonitorPayload();
        renderMonitorJobsTable();
        document.querySelector("#monitor-control-result").innerHTML = `<div class="message">Cancel requested for ${results.length} monitor job(s).</div>`;
        showToast(`Monitor stop requested for ${results.length} job(s).`);
      } catch (error) {
        document.querySelector("#monitor-control-result").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      }
    }

    async function startMonitorJob(intent) {
      await loadMonitorPayload();
      const settings = state.monitor?.settings || {};
      const maxCycles = Number(settings.max_cycles);
      const intervalSeconds = Number(settings.interval_seconds);
      const params = intent === "monitor_loop" ? {max_cycles: maxCycles, interval_seconds: intervalSeconds} : {};
      if (intent === "monitor_loop" && (!Number.isInteger(maxCycles) || maxCycles <= 0 || !Number.isInteger(intervalSeconds) || intervalSeconds <= 0)) {
        document.querySelector("#monitor-control-result").innerHTML = `<div class="message error">Monitor loop settings are missing or invalid. Check Settings before starting the monitor.</div>`;
        return;
      }
      try {
        const job = await postJob(intent, params);
        document.querySelector("#monitor-control-result").innerHTML = `<div class="message">Job ${escapeHtml(job.job_id || "")}: ${escapeHtml(job.status || "created")}</div>`;
      } catch (error) {
        document.querySelector("#monitor-control-result").innerHTML = `<div class="message error">${escapeHtml(error.message)}</div>`;
      }
    }

    async function enableDailyReport() {
      try {
        const result = await postJson(`${endpoints.schedule}/enable`, {});
        state.schedule = result;
        renderMonitor();
        showToast(`Daily report schedule ${result.status || "updated"}.`);
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

    async function cleanup(kind) {
      await loadDeletionPlan();
      if (kind === "runs") {
        const selected = state.selectedRunArtifacts.slice();
        if (!selected.length) return showToast("Select at least one run artifact first.");
        const required = state.deletionPlan?.confirmations?.run_artifacts || "DELETE RUN DATA";
        if (window.prompt(`Type ${required} to delete ${selected.length} run artifact set(s).`) !== required) {
          showToast("Run artifact cleanup cancelled.");
          return;
        }
        const result = await postJson(endpoints.deletion, {kind: "run_artifacts", run_ids: selected, confirm: required});
        state.selectedRunArtifacts = [];
        await Promise.allSettled([loadRuns(), loadStores(), loadDeletionPlan()]);
        renderSettings();
        showToast(`Run artifact cleanup ${result.status}.`);
      } else {
        const selected = state.selectedSharedStores.slice();
        if (!selected.length) return showToast("Select at least one shared data store first.");
        const required = state.deletionPlan?.confirmations?.shared_data || "DELETE SHARED DATA";
        if (window.prompt(`Type ${required} to delete ${selected.length} shared store(s).`) !== required) {
          showToast("Shared data cleanup cancelled.");
          return;
        }
        const result = await postJson(endpoints.deletion, {kind: "shared_data", store_names: selected, confirm: required});
        state.selectedSharedStores = [];
        await Promise.allSettled([loadStores(), loadDeletionPlan()]);
        renderSettings();
        showToast(`Shared data cleanup ${result.status}.`);
      }
    }

    function renderReportTrend(selector, reports) {
      const svg = document.querySelector(selector);
      const width = 260;
      const height = 118;
      const now = new Date();
      const start = new Date(now.getTime() - 13 * 24 * 3600 * 1000);
      const days = Array.from({length: 14}, (_, index) => {
        const day = new Date(start.getTime() + index * 24 * 3600 * 1000);
        return day.toISOString().slice(0, 10);
      });
      const counts = new Map(days.map((day) => [day, 0]));
      reports.forEach((run) => {
        const date = new Date(run.finished_at || run.started_at);
        if (Number.isNaN(date.getTime())) return;
        const key = date.toISOString().slice(0, 10);
        if (counts.has(key)) {
          counts.set(key, counts.get(key) + 1);
        }
      });
      const values = days.map((day) => counts.get(day) || 0);
      if (!values.some((value) => value > 0)) {
        svg.innerHTML = `<text x="16" y="16" fill="#111827" font-size="12" font-weight="700">Reports (last 14 days)</text><text x="130" y="64" fill="#5d6675" font-size="12" text-anchor="middle">No reports in this window</text>`;
        return;
      }
      const max = Math.max(...values, 1);
      const bars = values.map((value, index) => {
        const x = 18 + index * 15;
        const h = value / max * 70;
        return `<rect x="${x}" y="${92 - h}" width="9" height="${h}" rx="2" fill="#008575"></rect>`;
      }).join("");
      svg.innerHTML = `<line x1="16" x2="238" y1="92" y2="92" stroke="#dce2ea"></line>${bars}<text x="16" y="16" fill="#111827" font-size="12" font-weight="700">Reports (last 14 days)</text>`;
    }

    function table(headers, rows) {
      return `<div class="table-wrap"><table class="data-table"><thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(text(cell))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    }

    function unique(values) {
      return Array.from(new Set(values.filter(Boolean).map(String)));
    }

    function joinPath(base, path) {
      const left = String(base || "").replace(/\/$/, "");
      const right = String(path || "").replace(/^\//, "");
      return left && right ? `${left}/${right}` : right || left;
    }

    function markdownToHtml(markdown, searchTerm = "") {
      const lines = String(markdown || "").split(/\r?\n/);
      const html = [];
      let listOpen = false;
      let tableLines = [];
      const closeList = () => {
        if (listOpen) {
          html.push("</ul>");
          listOpen = false;
        }
      };
      const flushTable = () => {
        if (!tableLines.length) return;
        const rows = tableLines.map((line) => line.split("|").slice(1, -1).map((cell) => cell.trim()));
        const header = rows[0] || [];
        const body = rows.slice(2);
        html.push(`<div class="markdown-table-wrap"><table><thead><tr>${header.map((cell) => `<th>${renderInline(cell, searchTerm)}</th>`).join("")}</tr></thead><tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${renderInline(cell, searchTerm)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
        tableLines = [];
      };
      lines.forEach((raw) => {
        if (/^\|.*\|$/.test(raw.trim())) {
          closeList();
          tableLines.push(raw.trim());
          return;
        }
        flushTable();
        if (!raw.trim()) {
          closeList();
          return;
        }
        if (raw.startsWith("# ")) {
          closeList();
          html.push(`<h1>${renderInline(raw.slice(2), searchTerm)}</h1>`);
        } else if (raw.startsWith("## ")) {
          closeList();
          html.push(`<h2>${renderInline(raw.slice(3), searchTerm)}</h2>`);
        } else if (raw.startsWith("### ")) {
          closeList();
          html.push(`<h3>${renderInline(raw.slice(4), searchTerm)}</h3>`);
        } else if (raw.startsWith("- ")) {
          if (!listOpen) {
            html.push("<ul>");
            listOpen = true;
          }
          html.push(`<li>${renderInline(raw.slice(2), searchTerm)}</li>`);
        } else {
          closeList();
          html.push(`<p>${renderInline(raw, searchTerm)}</p>`);
        }
      });
      closeList();
      flushTable();
      return html.join("");
    }

    function renderInline(value, searchTerm = "") {
      const escaped = escapeHtml(value);
      const query = String(searchTerm || "").trim();
      if (!query) return escaped;
      const escapedQuery = escapeHtml(query);
      const pattern = new RegExp(escapeRegExp(escapedQuery), "gi");
      return escaped.replace(pattern, (match) => `<mark>${match}</mark>`);
    }

    function escapeRegExp(value) {
      return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function setHashView(view) {
      window.location.hash = view;
      setView(view);
    }

    function wireShortcutButtons() {
      document.querySelectorAll("[data-view-shortcut]").forEach((button) => {
        button.onclick = () => setHashView(button.dataset.viewShortcut);
      });
    }

    function wireGlobalEvents() {
      document.querySelectorAll("[data-view-target]").forEach((node) => node.addEventListener("click", (event) => {
        event.preventDefault();
        setHashView(node.dataset.viewTarget);
      }));
      document.querySelector("#global-refresh").addEventListener("click", refreshCurrentView);
      document.querySelector("#report-search").addEventListener("input", renderReportLibrary);
      document.querySelector("#report-reader-search").addEventListener("input", () => {
        state.reportSearchTerm = document.querySelector("#report-reader-search").value;
        if (state.selectedReportPreview && state.selectedReport) {
          renderReportPreview(state.selectedReportPreview, state.selectedReport);
        }
      });
      document.querySelector("#delete-report-button").addEventListener("click", deleteSelectedReport);
      document.querySelector("#download-report-button").addEventListener("click", downloadSelectedReport);
      document.querySelector("#run-backtest-button").addEventListener("click", startBacktest);
      document.querySelector("#download-ohlcv-button").addEventListener("click", downloadSelectedOhlcv);
      document.querySelectorAll("[data-strategy-window]").forEach((button) => button.addEventListener("click", () => setStrategyWindow(button.dataset.strategyWindow)));
      document.querySelectorAll("[data-strategy-tab]").forEach((button) => button.addEventListener("click", () => renderStrategyTab(button.dataset.strategyTab)));
      document.querySelectorAll("[data-monitor-job]").forEach((button) => button.addEventListener("click", () => startMonitorJob(button.dataset.monitorJob)));
      document.querySelector("#stop-monitor-button").addEventListener("click", cancelRunningMonitorJobs);
      document.querySelector("#enable-daily-report").addEventListener("click", enableDailyReport);
      document.querySelector("#schedule-monitor-button").addEventListener("click", showMonitorSchedule);
      document.querySelectorAll("[data-report-job]").forEach((button) => button.addEventListener("click", startReportJob));
      document.querySelectorAll("[data-job-intent]").forEach((button) => button.addEventListener("click", () => postJob(button.dataset.jobIntent, {})));
      document.querySelectorAll("[data-intel-tab]").forEach((button) => button.addEventListener("click", () => {
        state.selectedIntelTab = button.dataset.intelTab;
        state.selectedIntelItem = null;
        document.querySelectorAll("[data-intel-tab]").forEach((node) => node.classList.toggle("active", node === button));
        renderIntelligence();
      }));
      ["#intel-asset", "#intel-range", "#intel-severity", "#intel-source", "#intel-sort"].forEach((selector) => {
        document.querySelector(selector).addEventListener("change", () => {
          state.selectedIntelItem = null;
          renderIntelligence();
        });
      });
      document.querySelector("#intel-reset").addEventListener("click", resetIntelFilters);
      document.querySelector("#settings-save").addEventListener("click", saveSettings);
      document.querySelector("#settings-backup").addEventListener("click", backupSettings);
      document.querySelector("#cleanup-run-artifacts").addEventListener("click", () => cleanup("runs"));
      document.querySelector("#cleanup-shared-data").addEventListener("click", () => cleanup("shared"));
      window.addEventListener("hashchange", () => setView(viewFromHash()));
      wireShortcutButtons();
    }

    wireGlobalEvents();
    loadHealth();
    setView(viewFromHash());
