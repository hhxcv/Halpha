    (function () {
      function createDataViewerWorkflow(deps) {
        const state = deps.state;
        const endpoints = deps.endpoints;
        const fetchJson = deps.fetchJson;
        const postJson = deps.postJson;
        const showToast = deps.showToast;
        const escapeHtml = deps.escapeHtml;
        const text = deps.text;
        const statusClass = deps.statusClass;
        const formatNumber = deps.formatNumber;
        const formatTimestamp = deps.formatTimestamp;
        const label = deps.label;
        const metricCell = deps.metricCell;
        const table = deps.table;
        const terminalJobStatus = deps.terminalJobStatus;

        const DATA_VIEWER_STATUS_VOCABULARY = [
          "collected",
          "no_data",
          "partial",
          "failed",
          "not_collected",
          "stale",
          "warning",
          "error",
          "unsupported",
          "unavailable",
          "unknown",
        ];
        const EVENT_LIKE_TYPES = ["text_event", "macro_calendar", "onchain_flow", "derivatives_market"];
        const COLLECTABLE_TYPES = ["ohlcv", "text_event"];
        const TYPE_LABELS = {
          ohlcv: "OHLCV",
          text_event: "Text events",
          macro_calendar: "Macro calendar",
          onchain_flow: "On-chain flow",
          derivatives_market: "Derivatives market",
        };
        const EXPORT_FORMATS = {
          ohlcv: ["csv", "parquet"],
          text_event: ["json", "csv"],
          macro_calendar: ["json", "csv"],
          onchain_flow: ["json", "csv"],
          derivatives_market: ["json", "csv"],
        };

        async function loadDataViewerSummary() {
          if (!endpoints.dataViewerSummary) {
            state.dataViewerSummary = {
              status: "unsupported",
              stores: [],
              warnings: [],
              errors: ["data viewer summary endpoint is not configured."],
            };
            return state.dataViewerSummary;
          }
          try {
            state.dataViewerSummary = await fetchJson(endpoints.dataViewerSummary);
          } catch (error) {
            state.dataViewerSummary = {
              status: "failed",
              stores: [],
              warnings: [],
              errors: [error.message],
            };
          }
          return state.dataViewerSummary;
        }

        function renderStrategyViewer() {
          syncStrategyDataInputs();
          ensureDefaultRange("strategy-data");
          renderStoreSummary("strategy", "ohlcv");
          renderCapabilityState("strategy", "ohlcv");
        }

        function renderIntelligenceViewer() {
          ensureDefaultRange("intel-data");
          syncIntelligenceDataControls();
          const dataType = selectedIntelligenceDataType();
          renderStoreSummary("intel", dataType);
          renderCapabilityState("intel", dataType);
        }

        function syncStrategyDataInputs() {
          const symbol = node("#strategy-symbol")?.value || "";
          const timeframe = node("#strategy-timeframe")?.value || "";
          setValueIfEmpty("#strategy-data-symbol", symbol);
          setValueIfEmpty("#strategy-data-timeframe", timeframe);
        }

        function syncIntelligenceDataControls() {
          const dataType = selectedIntelligenceDataType();
          fillFormatOptions("#intel-data-format", EXPORT_FORMATS[dataType] || ["json", "csv"]);
          const collectable = COLLECTABLE_TYPES.includes(dataType);
          setDisabled("#intel-data-plan", !collectable);
          setDisabled("#intel-data-collect", !collectable);
          if (dataType === "text_event") {
            setValueIfEmpty("#intel-data-source", "all");
            setValueIfEmpty("#intel-data-identity-key", "source_name");
          }
        }

        function selectedIntelligenceDataType() {
          const value = node("#intel-data-type")?.value || "text_event";
          return EVENT_LIKE_TYPES.includes(value) ? value : "text_event";
        }

        function fillFormatOptions(selector, values) {
          const target = node(selector);
          if (!target) return;
          const current = target.value;
          target.innerHTML = values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value.toUpperCase())}</option>`).join("");
          if (values.includes(current)) {
            target.value = current;
          }
        }

        function storeSummary(dataType) {
          const stores = Array.isArray(state.dataViewerSummary?.stores) ? state.dataViewerSummary.stores : [];
          return stores.find((store) => store.data_type === dataType) || null;
        }

        function renderStoreSummary(scope, dataType) {
          const summary = storeSummary(dataType);
          const statusSelector = scope === "strategy" ? "#strategy-data-status" : "#intel-data-status";
          const summarySelector = scope === "strategy" ? "#strategy-data-summary" : "#intel-data-summary";
          if (!summary) {
            setStatus(statusSelector, state.dataViewerSummary?.status || "missing", "No summary");
            setHtml(summarySelector, `<div class="summary-cell"><div class="summary-label">Store</div><div class="summary-value">n/a</div><div class="summary-note">No shared store summary is available.</div></div>`);
            return;
          }
          const coverage = summary.coverage || {};
          const rangeLabel = coverage.range_start && coverage.range_end
            ? `${formatTimestamp(coverage.range_start)} to ${formatTimestamp(coverage.range_end)}`
            : "No collected range";
          const warningCount = (summary.warnings || []).length;
          const errorCount = (summary.errors || []).length;
          const statusCounts = statusCountLabel(coverage.status_counts || {});
          setStatus(statusSelector, summary.status || coverage.state_status || "unknown", summary.status || "unknown");
          setHtml(summarySelector, [
            metricCell("Records", formatNumber(coverage.record_count || 0), TYPE_LABELS[dataType] || dataType),
            metricCell("Range", rangeLabel, "shared store coverage"),
            metricCell("Coverage states", statusCounts || "none", "collected / gaps / failures"),
            metricCell("Issues", errorCount ? `${errorCount} errors` : warningCount ? `${warningCount} warnings` : "none", firstIssue(summary)),
          ].join(""));
        }

        function renderCapabilityState(scope, dataType) {
          const summary = storeSummary(dataType);
          const collectable = Boolean(summary?.collection_capability?.apply_job);
          const exportFormats = summary?.export_capability?.formats || EXPORT_FORMATS[dataType] || [];
          if (scope === "strategy") {
            fillFormatOptions("#strategy-data-format", exportFormats.length ? exportFormats : ["csv", "parquet"]);
            setDisabled("#strategy-data-plan", !collectable);
            setDisabled("#strategy-data-collect", !collectable);
            return;
          }
          setDisabled("#intel-data-plan", !collectable);
          setDisabled("#intel-data-collect", !collectable);
          if (!collectable) {
            setHtml(
              "#intel-data-plan-panel",
              `<div class="message warning">${escapeHtml(TYPE_LABELS[dataType] || dataType)} collection is unsupported from Dashboard. Timeline, preview, and export remain available when the shared store exists.</div>`,
            );
          } else if (!state.dataViewerIntelPlan) {
            setHtml("#intel-data-plan-panel", `<div class="message">Text-event dry runs use the shared collection planner before submitting a job.</div>`);
          }
        }

        function statusCountLabel(counts) {
          return Object.entries(counts || {})
            .filter((entry) => Number(entry[1]) > 0)
            .map(([status, count]) => `${status}: ${formatNumber(count)}`)
            .join(" / ");
        }

        function firstIssue(summary) {
          const issue = [...(summary.errors || []), ...(summary.warnings || [])][0];
          return issue ? String(issue).slice(0, 120) : "latest coverage state";
        }

        async function loadTimeline(scope) {
          const request = viewerRequest(scope);
          if (!request) return;
          setHtml(panelSelector(scope, "coverage"), `<div class="message">Loading coverage timeline.</div>`);
          try {
            const payload = await postJson(endpoints.dataViewerTimeline, request);
            state[scopeStateKey(scope, "timeline")] = payload;
            renderTimeline(scope, payload);
          } catch (error) {
            renderError(panelSelector(scope, "coverage"), error.message);
          }
        }

        async function loadPreview(scope) {
          const baseRequest = viewerRequest(scope);
          if (!baseRequest) return;
          const request = {...baseRequest, limit: 25, sort_order: "asc"};
          setHtml(panelSelector(scope, "preview"), `<div class="message">Loading bounded preview.</div>`);
          try {
            const payload = await postJson(endpoints.dataViewerPreview, request);
            state[scopeStateKey(scope, "preview")] = payload;
            renderPreview(scope, payload);
          } catch (error) {
            renderError(panelSelector(scope, "preview"), error.message);
          }
        }

        async function loadCollectionPlan(scope) {
          const request = collectionRequest(scope);
          if (!request) return;
          setHtml(panelSelector(scope, "plan"), `<div class="message">Planning efficient collection windows.</div>`);
          try {
            const payload = await postJson(endpoints.dataViewerCollectPlan, request);
            state[scopeStateKey(scope, "plan")] = payload;
            renderPlan(scope, payload);
          } catch (error) {
            renderError(panelSelector(scope, "plan"), error.message);
          }
        }

        async function submitCollectionJob(scope) {
          const request = collectionRequest(scope);
          if (!request) return;
          setHtml(panelSelector(scope, "job"), `<div class="message">Submitting allowlisted collection job.</div>`);
          try {
            const payload = await postJson(endpoints.dataViewerCollectJobs, request);
            state[scopeStateKey(scope, "job")] = payload.job || payload;
            renderJob(scope, payload.job || payload);
            const jobId = payload.job?.job_id;
            if (jobId) {
              pollCollectionJob(scope, jobId);
            }
          } catch (error) {
            renderError(panelSelector(scope, "job"), error.message);
          }
        }

        async function exportData(scope) {
          const request = viewerRequest(scope);
          if (!request) return;
          const format = scope === "strategy" ? node("#strategy-data-format")?.value : node("#intel-data-format")?.value;
          setHtml(panelSelector(scope, "job"), `<div class="message">Creating bounded export under data/exports.</div>`);
          try {
            const payload = await postJson(endpoints.dataViewerExport, {...request, format: format || "csv"});
            state[scopeStateKey(scope, "export")] = payload;
            renderExport(scope, payload);
          } catch (error) {
            renderError(panelSelector(scope, "job"), error.message);
          }
        }

        function viewerRequest(scope) {
          const request = scope === "strategy" ? strategyRequest() : intelligenceRequest();
          if (!request.start || !request.end) {
            renderError(panelSelector(scope, "coverage"), "start and end are required.");
            return null;
          }
          return request;
        }

        function strategyRequest() {
          syncStrategyDataInputs();
          return removeEmpty({
            data_type: "ohlcv",
            source: value("#strategy-data-source"),
            symbol: value("#strategy-data-symbol"),
            timeframe: value("#strategy-data-timeframe"),
            start: value("#strategy-data-start"),
            end: value("#strategy-data-end"),
            as_of: value("#strategy-data-as-of"),
          });
        }

        function intelligenceRequest() {
          const identity = identityFromInputs();
          return removeEmpty({
            data_type: selectedIntelligenceDataType(),
            source: value("#intel-data-source"),
            identity,
            start: value("#intel-data-start"),
            end: value("#intel-data-end"),
            as_of: value("#intel-data-as-of"),
          });
        }

        function collectionRequest(scope) {
          const request = viewerRequest(scope);
          if (!request) return null;
          if (!COLLECTABLE_TYPES.includes(request.data_type)) {
            renderError(panelSelector(scope, "plan"), "data collection jobs currently support ohlcv and text_event only.", "warning");
            return null;
          }
          if (!request.source) {
            renderError(panelSelector(scope, "plan"), "source is required for collection planning.", "warning");
            return null;
          }
          return {
            ...request,
            max_exact_windows: 3,
            merge_gap_threshold_seconds: 0,
            min_fetch_window_seconds: 0,
          };
        }

        function identityFromInputs() {
          const key = value("#intel-data-identity-key");
          const identityValue = value("#intel-data-identity-value");
          if (!key || !identityValue) {
            return {};
          }
          return {[key]: identityValue};
        }

        function renderTimeline(scope, payload) {
          const selector = panelSelector(scope, "coverage");
          const intervals = Array.isArray(payload?.intervals) ? payload.intervals : [];
          if (payload?.errors?.length) {
            renderError(selector, payload.errors.join("; "), statusClass(payload.status) === "failed" ? "error" : "warning");
            return;
          }
          if (!intervals.length) {
            setHtml(selector, `<div class="empty-state">No coverage intervals matched this range. This is not the same as no_data; the collection state has no matching evidence for the requested identity.</div>`);
            return;
          }
          setHtml(selector, intervals.map((interval) => {
            const status = String(interval.status || "unknown");
            const issues = [...(interval.errors || []), ...(interval.warnings || [])].slice(0, 2).join("; ");
            const meta = [
              `Records: ${formatNumber(interval.record_count || 0)}`,
              `Attempts: ${formatNumber(interval.attempt_count || 0)}`,
              interval.latest_success_at ? `Last success: ${formatTimestamp(interval.latest_success_at)}` : "",
              issues,
            ].filter(Boolean).join(" / ");
            return `
              <div class="data-coverage-row">
                ${statusPill(status)}
                <div class="data-coverage-range">
                  ${escapeHtml(formatTimestamp(interval.range_start))} to ${escapeHtml(formatTimestamp(interval.range_end))}
                  <span class="data-coverage-meta">${escapeHtml(meta || coverageStateCopy(status))}</span>
                </div>
                <span class="tag">${escapeHtml(coverageStateCopy(status))}</span>
              </div>`;
          }).join(""));
        }

        function renderPreview(scope, payload) {
          const selector = panelSelector(scope, "preview");
          if (payload?.errors?.length) {
            renderError(selector, payload.errors.join("; "), statusClass(payload.status) === "failed" ? "error" : "warning");
            return;
          }
          const records = Array.isArray(payload?.records) ? payload.records : [];
          const query = payload?.query || {};
          const header = `<div class="message"><strong>${escapeHtml(label(payload?.status || "preview"))}</strong><br>Matched: ${escapeHtml(text(query.matched_record_count ?? query.record_count ?? records.length, records.length))} / Limit: ${escapeHtml(text(payload?.omitted?.record_limit, "25"))}${query.truncated ? " / truncated" : ""}</div>`;
          if (!records.length) {
            setHtml(selector, `${header}<div class="empty-state">No records matched this bounded query. Check the timeline to distinguish no_data from not_collected, partial, failed, stale, or unknown coverage.</div>`);
            return;
          }
          const columns = previewColumns(payload.data_type, records);
          const rows = records.slice(0, 25).map((record) => columns.map((column) => previewCell(record[column])));
          setHtml(selector, `${header}${table(columns, rows)}`);
        }

        function renderPlan(scope, payload) {
          const selector = panelSelector(scope, "plan");
          if (payload?.errors?.length) {
            renderError(selector, payload.errors.map((item) => item.message || item).join("; "), statusClass(payload.status) === "failed" ? "error" : "warning");
            return;
          }
          const plan = payload?.plan || {};
          const windows = Array.isArray(plan.planned_fetch_windows) ? plan.planned_fetch_windows : [];
          const skipped = Array.isArray(plan.skipped_ranges) ? plan.skipped_ranges.length : 0;
          const retry = Array.isArray(plan.retry_ranges) ? plan.retry_ranges.length : 0;
          const header = `<div class="summary-strip data-viewer-summary">
            ${metricCell("Strategy", label(plan.strategy || "unknown"), plan.status || payload?.status || "plan")}
            ${metricCell("Fetch windows", formatNumber(windows.length), "planned")}
            ${metricCell("Skipped ranges", formatNumber(skipped), "already collected or no_data")}
            ${metricCell("Retry ranges", formatNumber(retry), "partial / failed / stale")}
          </div>`;
          if (!windows.length) {
            setHtml(selector, `${header}<div class="message">No collection job is needed for this request.</div>`);
            return;
          }
          setHtml(selector, `${header}${windows.map((window) => `
            <div class="data-plan-row">
              <div>
                <strong>${escapeHtml(formatTimestamp(window.range_start))} to ${escapeHtml(formatTimestamp(window.range_end))}</strong>
                <span class="data-coverage-meta">${escapeHtml(window.reason || "planned fetch")}</span>
              </div>
              ${statusPill(plan.strategy || "warning")}
            </div>`).join("")}`);
        }

        function renderJob(scope, job) {
          const selector = panelSelector(scope, "job");
          const status = job?.status || "created";
          const refs = job?.result_refs || {};
          const logs = job?.logs || {};
          const refRows = Object.entries(refs).map(([key, value]) => [key, value]);
          const logRows = Object.entries(logs)
            .filter(([key]) => key.endsWith("_ref") || key.endsWith("_truncated"))
            .map(([key, value]) => [key, value]);
          setHtml(selector, `
            <div class="message">
              <strong>Collection job ${escapeHtml(label(status))}</strong><br>
              Job: ${escapeHtml(job?.job_id || "pending")}
              ${job?.intent ? `<br>Intent: ${escapeHtml(job.intent)}` : ""}
              ${job?.job_id ? `<br><button class="ghost-button" type="button" data-data-viewer-refresh-job="${escapeHtml(scope)}" data-job-id="${escapeHtml(job.job_id)}">Refresh job</button>` : ""}
            </div>
            ${refRows.length ? table(["Result ref", "Artifact"], refRows) : `<div class="message">No result refs recorded yet.</div>`}
            ${logRows.length ? table(["Log field", "Value"], logRows) : ""}
          `);
          wireJobRefreshButtons();
        }

        function renderExport(scope, payload) {
          const selector = panelSelector(scope, "job");
          if (payload?.errors?.length) {
            renderError(selector, payload.errors.join("; "), statusClass(payload.status) === "failed" ? "error" : "warning");
            return;
          }
          const result = payload?.export || {};
          setHtml(selector, `
            <div class="message">
              <strong>Export ${escapeHtml(label(payload?.status || result.status || "ok"))}</strong><br>
              Output: ${escapeHtml(result.output_path || "n/a")}<br>
              Records: ${escapeHtml(text(result.record_count, "0"))}${result.truncated ? " / truncated" : ""}
            </div>
            ${table(["Field", "Value"], [
              ["Format", result.format || result.output_format || "n/a"],
              ["Metadata", result.metadata_path || "embedded or n/a"],
              ["As of", result.query_parameters?.as_of || "n/a"],
              ["Coverage", result.coverage_diagnostics?.status || "n/a"],
            ])}
          `);
        }

        async function pollCollectionJob(scope, jobId) {
          for (let attempt = 0; attempt < 60; attempt += 1) {
            await wait(3000);
            try {
              const job = await fetchJson(`${endpoints.jobs}/${encodeURIComponent(jobId)}`);
              state[scopeStateKey(scope, "job")] = job;
              renderJob(scope, job);
              if (terminalJobStatus(job.status)) {
                await loadDataViewerSummary();
                if (scope === "strategy") {
                  renderStrategyViewer();
                } else {
                  renderIntelligenceViewer();
                }
                showToast(`Collection job ${job.status || "completed"}.`);
                return;
              }
            } catch (error) {
              renderError(panelSelector(scope, "job"), error.message);
              return;
            }
          }
        }

        async function refreshCollectionJob(scope, jobId) {
          try {
            const job = await fetchJson(`${endpoints.jobs}/${encodeURIComponent(jobId)}`);
            state[scopeStateKey(scope, "job")] = job;
            renderJob(scope, job);
          } catch (error) {
            renderError(panelSelector(scope, "job"), error.message);
          }
        }

        function previewColumns(dataType, records) {
          const preferred = dataType === "ohlcv"
            ? ["open_time", "open", "high", "low", "close", "volume", "collected_at"]
            : ["published_at", "scheduled_at", "as_of", "source", "source_name", "title", "event_type", "status", "raw_item_id"];
          const keys = [];
          records.slice(0, 10).forEach((record) => {
            Object.keys(record || {}).forEach((key) => {
              if (!keys.includes(key)) keys.push(key);
            });
          });
          const ordered = [...preferred.filter((key) => keys.includes(key)), ...keys.filter((key) => !preferred.includes(key))];
          return ordered.slice(0, 8);
        }

        function previewCell(value) {
          if (value === null || value === undefined) return "";
          if (typeof value === "object") return JSON.stringify(value).slice(0, 160);
          return String(value).slice(0, 160);
        }

        function panelSelector(scope, panel) {
          const prefix = scope === "strategy" ? "strategy-data" : "intel-data";
          if (panel === "coverage") return `#${prefix}-coverage`;
          if (panel === "preview") return `#${prefix}-preview-panel`;
          if (panel === "plan") return `#${prefix}-plan-panel`;
          return `#${prefix}-job-panel`;
        }

        function scopeStateKey(scope, key) {
          return scope === "strategy" ? `dataViewerStrategy${capitalize(key)}` : `dataViewerIntel${capitalize(key)}`;
        }

        function capitalize(value) {
          const raw = String(value || "");
          return raw.charAt(0).toUpperCase() + raw.slice(1);
        }

        function statusPill(status, labelText) {
          return `<span class="status-pill ${statusClass(status)}">${escapeHtml(labelText || status)}</span>`;
        }

        function setStatus(selector, status, labelText) {
          const target = node(selector);
          if (!target) return;
          target.className = `status-pill ${statusClass(status)}`;
          target.textContent = labelText || label(status);
        }

        function coverageStateCopy(status) {
          const normalized = String(status || "unknown").toLowerCase();
          if (normalized === "collected") return "collected";
          if (normalized === "no_data") return "collected empty";
          if (normalized === "not_collected") return "not collected";
          if (normalized === "partial") return "partial";
          if (normalized === "failed" || normalized === "error") return "failed";
          if (normalized === "stale") return "stale";
          if (normalized === "unsupported") return "unsupported";
          if (normalized === "unavailable") return "unavailable";
          return "unknown coverage";
        }

        function renderError(selector, message, kind = "error") {
          setHtml(selector, `<div class="message ${kind === "warning" ? "warning" : "error"}">${escapeHtml(message)}</div>`);
        }

        function removeEmpty(value) {
          return Object.fromEntries(Object.entries(value).filter((entry) => {
            const item = entry[1];
            if (item === null || item === undefined || item === "") return false;
            if (typeof item === "object" && !Array.isArray(item) && !Object.keys(item).length) return false;
            return true;
          }));
        }

        function ensureDefaultRange(prefix) {
          const start = node(`#${prefix}-start`);
          const end = node(`#${prefix}-end`);
          if (!start || !end || (start.value && end.value)) return;
          const now = new Date();
          const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 3600 * 1000);
          if (!start.value) start.value = toIsoMinute(sevenDaysAgo);
          if (!end.value) end.value = toIsoMinute(now);
        }

        function toIsoMinute(date) {
          return date.toISOString().replace(/\.\d{3}Z$/, "Z");
        }

        function setValueIfEmpty(selector, value) {
          const target = node(selector);
          if (target && !target.value && value) {
            target.value = value;
          }
        }

        function value(selector) {
          return String(node(selector)?.value || "").trim();
        }

        function node(selector) {
          return document.querySelector(selector);
        }

        function setHtml(selector, html) {
          const target = node(selector);
          if (target) target.innerHTML = html;
        }

        function setDisabled(selector, disabled) {
          const target = node(selector);
          if (target) target.disabled = Boolean(disabled);
        }

        function wireJobRefreshButtons() {
          document.querySelectorAll("[data-data-viewer-refresh-job]").forEach((button) => {
            button.onclick = () => refreshCollectionJob(button.dataset.dataViewerRefreshJob, button.dataset.jobId);
          });
        }

        function wait(ms) {
          return new Promise((resolve) => window.setTimeout(resolve, ms));
        }

        function wire() {
          ensureDefaultRange("strategy-data");
          ensureDefaultRange("intel-data");
          node("#strategy-data-timeline")?.addEventListener("click", () => loadTimeline("strategy"));
          node("#strategy-data-preview")?.addEventListener("click", () => loadPreview("strategy"));
          node("#strategy-data-plan")?.addEventListener("click", () => loadCollectionPlan("strategy"));
          node("#strategy-data-collect")?.addEventListener("click", () => submitCollectionJob("strategy"));
          node("#strategy-data-export")?.addEventListener("click", () => exportData("strategy"));
          node("#intel-data-timeline")?.addEventListener("click", () => loadTimeline("intel"));
          node("#intel-data-preview")?.addEventListener("click", () => loadPreview("intel"));
          node("#intel-data-plan")?.addEventListener("click", () => loadCollectionPlan("intel"));
          node("#intel-data-collect")?.addEventListener("click", () => submitCollectionJob("intel"));
          node("#intel-data-export")?.addEventListener("click", () => exportData("intel"));
          node("#intel-data-type")?.addEventListener("change", () => {
            state.dataViewerIntelTimeline = null;
            state.dataViewerIntelPreview = null;
            state.dataViewerIntelPlan = null;
            renderIntelligenceViewer();
          });
          ["#strategy-data-source", "#strategy-data-symbol", "#strategy-data-timeframe", "#strategy-data-start", "#strategy-data-end", "#strategy-data-as-of"].forEach((selector) => {
            node(selector)?.addEventListener("change", renderStrategyViewer);
          });
          ["#intel-data-source", "#intel-data-identity-key", "#intel-data-identity-value", "#intel-data-start", "#intel-data-end", "#intel-data-as-of"].forEach((selector) => {
            node(selector)?.addEventListener("change", renderIntelligenceViewer);
          });
        }

        return {
          DATA_VIEWER_STATUS_VOCABULARY,
          loadDataViewerSummary,
          renderIntelligenceViewer,
          renderStrategyViewer,
          wire,
        };
      }

      window.HalphaDashboardDataViewer = {
        createDataViewerWorkflow,
      };
    })();
