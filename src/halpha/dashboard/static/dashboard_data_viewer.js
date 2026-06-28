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
        const renderStrategyOhlcvPreview = deps.renderStrategyOhlcvPreview;
        const syncDateRangePicker = deps.syncDateRangePicker || (() => {});

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
        const EVENT_LIKE_TYPES = ["text_event", "macro_calendar", "onchain_flow", "derivatives_market", "market_anomaly"];
        const COLLECTABLE_TYPES = ["ohlcv", ...EVENT_LIKE_TYPES];
        const TYPE_LABELS = {
          ohlcv: "OHLCV",
          text_event: "Text events",
          macro_calendar: "Macro calendar",
          onchain_flow: "On-chain flow",
          derivatives_market: "Derivatives market",
          market_anomaly: "Market anomalies",
        };
        const EXPORT_FORMATS = {
          ohlcv: ["csv", "parquet"],
          text_event: ["json", "csv"],
          macro_calendar: ["json", "csv"],
          onchain_flow: ["json", "csv"],
          derivatives_market: ["json", "csv"],
          market_anomaly: ["json", "csv"],
        };
        const INTEL_PREVIEW_PAGE_SIZE = 30;
        const INTEL_PREVIEW_FETCH_STEP = 100;
        const INTEL_PREVIEW_MAX_LIMIT = 500;

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
          ensureStrategyDefaultRange();
          renderStoreSummary("strategy", "ohlcv");
          renderCapabilityState("strategy", "ohlcv");
        }

        function renderIntelligenceViewer() {
          const dataType = selectedIntelligenceDataType();
          const switchedType = state.dataViewerIntelType !== dataType;
          state.dataViewerIntelType = dataType;
          syncIntelligenceDataControls();
          if (switchedType) {
            state.dataViewerIntelTimeline = null;
            state.dataViewerIntelPreview = null;
            resetIntelligencePreviewState();
            state.intelPreviewKeyword = "";
            state.intelPreviewCategory = "";
            applyIntelligenceRangePreset("intel-collect", true);
            applyIntelligenceRangePreset("intel-preview", true);
          } else {
            ensureIntelligenceDefaultRange("intel-collect", false);
            ensureIntelligenceDefaultRange("intel-preview", false);
          }
          renderStoreSummary("intel", dataType);
          renderCapabilityState("intel", dataType);
          setHtml("#intel-data-coverage", `<div class="message">Loading coverage timeline.</div>`);
          setHtml("#intel-data-preview-panel", `<div class="message">Loading preview records.</div>`);
          queueIntelligenceDataLoad();
        }

        function syncStrategyDataInputs() {
          const symbol = node("#strategy-symbol")?.value || "";
          const timeframe = node("#strategy-timeframe")?.value || "";
          setValueIfEmpty("#strategy-data-symbol", symbol);
          setValueIfEmpty("#strategy-data-timeframe", timeframe);
        }

        function syncIntelligenceDataControls() {
          const dataType = selectedIntelligenceDataType();
          const collectable = COLLECTABLE_TYPES.includes(dataType);
          setDisabled("#intel-data-collect", !collectable);
          const title = node("#intel-data-viewer .panel-title");
          if (title) {
            title.innerHTML = `${escapeHtml(TYPE_LABELS[dataType] || dataType)} <span id="intel-data-status" class="status-pill pending">loading</span>`;
          }
          syncIntelPreviewAsOfControls();
        }

        function resetIntelligencePreviewState() {
          state.selectedIntelPreviewIndex = 0;
          state.intelPreviewDisplayLimit = INTEL_PREVIEW_PAGE_SIZE;
          state.intelPreviewFetchLimit = INTEL_PREVIEW_FETCH_STEP;
          state.intelPreviewLoadingMore = false;
          state.intelDatePickerOpen = false;
          state.intelCalendarMonth = null;
        }

        function selectedIntelligenceDataType() {
          const selectedTab = state.selectedIntelTab;
          const value = EVENT_LIKE_TYPES.includes(selectedTab) ? selectedTab : (node("#intel-data-type")?.value || "text_event");
          const typeNode = node("#intel-data-type");
          if (typeNode && Array.from(typeNode.options).some((option) => option.value === value)) {
            typeNode.value = value;
          }
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
          hideSummaryStrip(summarySelector);
          if (!summary) {
            setStatus(statusSelector, state.dataViewerSummary?.status || "missing", "No summary");
            renderIssueControl(scope, null);
            return;
          }
          const coverage = summary.coverage || {};
          setStatus(statusSelector, summary.status || coverage.state_status || "unknown", summary.status || "unknown");
          renderIssueControl(scope, summary);
        }

        function hideSummaryStrip(selector) {
          const target = node(selector);
          if (!target) return;
          target.innerHTML = "";
          target.classList.add("hidden");
        }

        function renderIssueControl(scope, summary) {
          const target = node(scope === "strategy" ? "#strategy-data-issues" : "#intel-data-issues");
          if (!target) return;
          const issues = storeIssues(summary);
          const errorCount = issues.filter((issue) => issue.kind === "error").length;
          const warningCount = issues.filter((issue) => issue.kind === "warning").length;
          const issueStatus = errorCount ? "error" : warningCount ? "warning" : "ok";
          const issueCopy = issues.length
            ? `${formatNumber(issues.length)} ${issues.length === 1 ? "issue" : "issues"}`
            : "0 issues";
          const details = issues.length
            ? `<ul class="data-viewer-issue-list">${issues.map((issue) => `
                <li class="data-viewer-issue-item ${escapeHtml(statusClass(issue.kind))}">
                  <span class="status-pill ${escapeHtml(statusClass(issue.kind))}">${escapeHtml(label(issue.kind))}</span>
                  <p>${escapeHtml(issue.message)}</p>
                </li>
              `).join("")}</ul>`
            : `<div class="empty-state">No current issues for this data store.</div>`;
          target.innerHTML = `
            <div class="data-viewer-issue-widget">
              <button class="ghost-button data-viewer-issue-button ${escapeHtml(statusClass(issueStatus))}" type="button" data-data-viewer-issues="${escapeHtml(scope)}" aria-expanded="false">
                Issues <span class="data-viewer-issue-count">${escapeHtml(formatNumber(issues.length))}</span>
              </button>
              <div class="data-viewer-issue-popover hidden" data-data-viewer-issue-panel="${escapeHtml(scope)}" role="dialog" aria-label="${escapeHtml(issueCopy)}">
                <div class="data-viewer-issue-popover-head">
                  <strong>${escapeHtml(issueCopy)}</strong>
                  <span>${escapeHtml(errorCount ? `${formatNumber(errorCount)} errors` : warningCount ? `${formatNumber(warningCount)} warnings` : "clear")}</span>
                </div>
                ${details}
              </div>
            </div>
          `;
        }

        function storeIssues(summary) {
          if (!summary) return [];
          const errors = Array.isArray(summary.errors) ? summary.errors : [];
          const warnings = Array.isArray(summary.warnings) ? summary.warnings : [];
          return [
            ...errors.map((message) => ({kind: "error", message: String(message)})),
            ...warnings.map((message) => ({kind: "warning", message: String(message)})),
          ].filter((issue) => issue.message.trim());
        }

        function toggleIssuePopover(scope) {
          const button = node(`[data-data-viewer-issues="${scope}"]`);
          const panel = node(`[data-data-viewer-issue-panel="${scope}"]`);
          if (!button || !panel) return;
          const shouldOpen = panel.classList.contains("hidden");
          closeIssuePopovers();
          panel.classList.toggle("hidden", !shouldOpen);
          button.setAttribute("aria-expanded", shouldOpen ? "true" : "false");
        }

        function closeIssuePopovers() {
          document.querySelectorAll("[data-data-viewer-issue-panel]").forEach((panel) => panel.classList.add("hidden"));
          document.querySelectorAll("[data-data-viewer-issues]").forEach((button) => button.setAttribute("aria-expanded", "false"));
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
          setDisabled("#intel-data-collect", !collectable);
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
          const request = {...baseRequest, limit: scope === "strategy" ? 1000 : 25, sort_order: "asc"};
          setHtml(panelSelector(scope, "preview"), `<div class="message">Loading bounded preview.</div>`);
          try {
            const payload = await postJson(endpoints.dataViewerPreview, request);
            state[scopeStateKey(scope, "preview")] = payload;
            if (scope === "strategy" && payload?.data_type === "ohlcv" && typeof renderStrategyOhlcvPreview === "function") {
              renderStrategyOhlcvPreview(payload, request);
            }
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
          const format = scope === "strategy" ? node("#strategy-data-format")?.value : "json";
          setHtml(panelSelector(scope, "job"), `<div class="message">Creating bounded export under data/exports.</div>`);
          try {
            const payload = await postJson(endpoints.dataViewerExport, {...request, format: format || "csv"});
            state[scopeStateKey(scope, "export")] = payload;
            renderExport(scope, payload);
          } catch (error) {
            renderError(panelSelector(scope, "job"), error.message);
          }
        }

        function queueIntelligenceDataLoad() {
          queueIntelligenceCollectTimelineLoad();
          queueIntelligencePreviewLoad();
        }

        function queueIntelligenceCollectTimelineLoad() {
          window.clearTimeout(state.intelligenceTimelineTimer);
          state.intelligenceTimelineTimer = window.setTimeout(loadIntelligenceCollectTimeline, 220);
        }

        function queueIntelligencePreviewLoad() {
          window.clearTimeout(state.intelligencePreviewTimer);
          state.intelligencePreviewTimer = window.setTimeout(loadIntelligencePreviewPanel, 220);
        }

        async function loadIntelligenceDataPanels() {
          if (state.selectedIntelTab === "overview") return;
          await Promise.all([loadIntelligenceCollectTimeline(), loadIntelligencePreviewPanel()]);
        }

        async function loadIntelligenceCollectTimeline() {
          if (state.selectedIntelTab === "overview") return;
          const request = collectionViewerRequest("intel");
          if (!request) return;
          setHtml("#intel-data-coverage", `<div class="message">Loading coverage timeline.</div>`);
          const timelineRequest = {...request, limit: 200};
          try {
            const payload = await postJson(endpoints.dataViewerTimeline, timelineRequest);
            state.dataViewerIntelTimeline = payload;
            renderTimeline("intel", payload);
          } catch (error) {
            renderError("#intel-data-coverage", error.message || "Timeline failed.");
          }
        }

        async function loadIntelligencePreviewPanel() {
          if (state.selectedIntelTab === "overview") return;
          const request = viewerRequest("intel");
          if (!request) return;
          setHtml("#intel-data-preview-panel", `<div class="message">Loading preview records.</div>`);
          const previewLimit = Math.min(INTEL_PREVIEW_MAX_LIMIT, Math.max(INTEL_PREVIEW_PAGE_SIZE, Number(state.intelPreviewFetchLimit) || INTEL_PREVIEW_FETCH_STEP));
          const previewRequest = {...request, limit: previewLimit, sort_order: "desc"};
          try {
            const payload = await postJson(endpoints.dataViewerPreview, previewRequest);
            state.dataViewerIntelPreview = payload;
            renderPreview("intel", payload);
          } catch (error) {
            renderError("#intel-data-preview-panel", error.message || "Preview failed.");
          }
        }

        function viewerRequest(scope) {
          const request = scope === "strategy" ? strategyRequest() : intelligencePreviewRequest();
          if (!request.start || !request.end) {
            renderError(panelSelector(scope, scope === "intel" ? "preview" : "coverage"), "start and end are required.");
            return null;
          }
          return request;
        }

        function collectionViewerRequest(scope) {
          const request = scope === "strategy" ? strategyRequest() : intelligenceCollectRequest();
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

        function intelligencePreviewRequest() {
          return removeEmpty({
            data_type: selectedIntelligenceDataType(),
            start: value("#intel-preview-start"),
            end: value("#intel-preview-end"),
            as_of: intelligencePreviewAsOf(),
          });
        }

        function intelligenceCollectRequest() {
          return removeEmpty({
            data_type: selectedIntelligenceDataType(),
            start: value("#intel-collect-start"),
            end: value("#intel-collect-end"),
          });
        }

        function collectionRequest(scope) {
          const request = collectionViewerRequest(scope);
          if (!request) return null;
          const validationPanel = scope === "intel" ? panelSelector(scope, "job") : panelSelector(scope, "plan");
          if (!COLLECTABLE_TYPES.includes(request.data_type)) {
            renderError(validationPanel, "data collection jobs currently do not support this data type.", "warning");
            return null;
          }
          if (scope === "strategy" && !request.source) {
            renderError(validationPanel, "source is required for collection.", "warning");
            return null;
          }
          return {
            ...request,
            max_exact_windows: 3,
            merge_gap_threshold_seconds: 0,
            min_fetch_window_seconds: 0,
          };
        }

        function renderTimeline(scope, payload) {
          const selector = panelSelector(scope, "coverage");
          const intervals = Array.isArray(payload?.intervals) ? payload.intervals : [];
          if (payload?.errors?.length) {
            renderError(selector, payload.errors.join("; "), statusClass(payload.status) === "failed" ? "error" : "warning");
            return;
          }
          if (scope === "intel") {
            renderIntelligenceTimeline(selector, payload, intervals);
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

        function renderIntelligenceTimeline(selector, payload, intervals) {
          const start = payload?.requested_start;
          const end = payload?.requested_end;
          if (!intervals.length) {
            setHtml(selector, `<div class="empty-state">No coverage intervals matched this range. This is not the same as no_data; the collection state has no matching evidence for the requested filters.</div>`);
            return;
          }
          const segments = intervals.map((interval) => timelineSegment(interval, start, end)).join("");
          const legend = ["collected", "no_data", "partial", "failed", "unknown"].map((status) => `<span class="timeline-legend-item"><span class="timeline-legend-dot ${escapeHtml(statusClass(status))} ${escapeHtml(status)}"></span>${escapeHtml(coverageStateCopy(status))}</span>`).join("");
          const meta = `${formatNumber(intervals.length)} interval${intervals.length === 1 ? "" : "s"} / ${escapeHtml(formatTimestamp(start))} to ${escapeHtml(formatTimestamp(end))}`;
          setHtml(selector, `
            <div class="intel-timeline-card">
              <div class="intel-timeline-meta">${meta}</div>
              <div class="intel-timeline-track">${segments}</div>
              <div class="timeline-legend">${legend}</div>
            </div>`);
        }

        function timelineSegment(interval, start, end) {
          const startMs = Date.parse(start);
          const endMs = Date.parse(end);
          if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) {
            return `<span class="intel-timeline-segment unknown" style="left:0%;width:100%;" title="unknown coverage"></span>`;
          }
          const rawStart = Date.parse(interval.range_start || start);
          const rawEnd = Date.parse(interval.range_end || end);
          const clippedStart = Math.max(startMs, Number.isFinite(rawStart) ? rawStart : startMs);
          const clippedEnd = Math.min(endMs, Number.isFinite(rawEnd) ? rawEnd : endMs);
          const total = Math.max(1, endMs - startMs);
          const left = Math.max(0, Math.min(100, (clippedStart - startMs) / total * 100));
          const width = Math.max(0.8, Math.min(100 - left, (clippedEnd - clippedStart) / total * 100));
          const status = String(interval.status || "unknown").toLowerCase();
          const title = `${coverageStateCopy(status)}: ${formatTimestamp(interval.range_start)} to ${formatTimestamp(interval.range_end)} / records: ${formatNumber(interval.record_count || 0)}`;
          return `<span class="intel-timeline-segment ${escapeHtml(statusClass(status))} ${escapeHtml(status)}" style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%;" title="${escapeHtml(title)}"></span>`;
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
          if (scope === "intel") {
            renderIntelligencePreview(selector, payload, records, header);
            return;
          }
          if (!records.length) {
            setHtml(selector, `${header}<div class="empty-state">No records matched this bounded query. Check the timeline to distinguish no_data from not_collected, partial, failed, stale, or unknown coverage.</div>`);
            return;
          }
          if (scope === "strategy" && payload.data_type === "ohlcv") {
            setHtml(
              selector,
              `${header}<div class="message">Loaded ${escapeHtml(formatNumber(records.length))} bounded candles into the Strategy Lab chart.</div>`,
            );
            return;
          }
          const columns = previewColumns(payload.data_type, records);
          const rows = records.slice(0, 25).map((record) => columns.map((column) => previewCell(record[column])));
          setHtml(selector, `${header}${table(columns, rows)}`);
        }

        function renderIntelligencePreview(selector, payload, records, header) {
          const categoryOptions = previewCategoryOptions(records, payload.data_type);
          if (state.intelPreviewCategory && !categoryOptions.some((option) => option.value === state.intelPreviewCategory)) {
            state.intelPreviewCategory = "";
          }
          const keyword = String(state.intelPreviewKeyword || "").trim().toLowerCase();
          const category = String(state.intelPreviewCategory || "").trim();
          const filtered = records.filter((record) => {
            if (category && recordCategory(record, payload.data_type) !== category) return false;
            if (!keyword) return true;
            return JSON.stringify(record || {}).toLowerCase().includes(keyword);
          });
          if (!filtered.length) {
            setHtml(selector, `
              <div class="intelligence-preview-layout">
                <aside class="intel-preview-sidebar">
                  ${previewFilterControls(categoryOptions, 0, records.length)}
                  <div class="intel-list-toolbar">
                    <button class="ghost-button compact-button" type="button" id="intel-date-jump-toggle">Jump date</button>
                    <span>0 / ${escapeHtml(formatNumber(records.length))} records</span>
                  </div>
                  ${state.intelDatePickerOpen ? renderDateJumpCalendar(records, payload.data_type) : ""}
                  <div class="intel-preview-list" aria-label="Filtered intelligence records">
                    <div class="empty-state">No records matched the current preview filters. Clear the search or category filter to restore the loaded list.</div>
                  </div>
                </aside>
                <article class="intel-preview-main">
                  <div class="empty-state">No selected record.</div>
                </article>
                <aside class="intel-preview-properties">
                  <h3 class="subsection-title">Properties</h3>
                  <div class="empty-state">No record properties.</div>
                </aside>
              </div>`);
            wireIntelligencePreviewFilters(selector, payload, records, header);
            return;
          }
          state.selectedIntelPreviewIndex = Math.min(Math.max(0, Number(state.selectedIntelPreviewIndex) || 0), filtered.length - 1);
          state.intelPreviewDisplayLimit = Math.min(
            filtered.length,
            Math.max(INTEL_PREVIEW_PAGE_SIZE, Number(state.intelPreviewDisplayLimit) || INTEL_PREVIEW_PAGE_SIZE, state.selectedIntelPreviewIndex + 1),
          );
          ensureIntelCalendarMonth(filtered, payload.data_type);
          const visible = filtered.slice(0, state.intelPreviewDisplayLimit);
          const selected = filtered[state.selectedIntelPreviewIndex];
          const query = payload?.query || {};
          const matched = Number(query.matched_record_count ?? query.record_count ?? filtered.length) || filtered.length;
          const fetchLimit = Number(state.intelPreviewFetchLimit) || INTEL_PREVIEW_FETCH_STEP;
          const canFetchMore = Boolean(query.truncated) && fetchLimit < INTEL_PREVIEW_MAX_LIMIT;
          const moreAvailable = state.intelPreviewDisplayLimit < filtered.length || canFetchMore;
          const limited = Boolean(query.truncated) && !canFetchMore;
          setHtml(selector, `
            <div class="intelligence-preview-layout">
              <aside class="intel-preview-sidebar">
                ${previewFilterControls(categoryOptions, filtered.length, records.length)}
                <div class="intel-list-toolbar">
                  <button class="ghost-button compact-button" type="button" id="intel-date-jump-toggle">Jump date</button>
                  <span>${escapeHtml(formatNumber(visible.length))} / ${escapeHtml(formatNumber(matched))} records</span>
                </div>
                ${state.intelDatePickerOpen ? renderDateJumpCalendar(filtered, payload.data_type) : ""}
                <div class="intel-preview-list" aria-label="Filtered intelligence records">
                ${previewListItemsWithDates(visible, payload.data_type)}
                  ${moreAvailable ? `<div class="intel-list-more">${state.intelPreviewLoadingMore ? "Loading more records" : "Scroll for more records"}</div>` : limited ? `<div class="intel-list-more">Bounded preview limit reached</div>` : ""}
                </div>
              </aside>
              <article class="intel-preview-main">
                ${previewRecordBody(selected, payload.data_type)}
              </article>
              <aside class="intel-preview-properties">
                ${previewRecordProperties(selected, payload)}
              </aside>
            </div>`);
          const root = node(selector);
          wireIntelligencePreviewFilters(selector, payload, records, header);
          root?.querySelectorAll("[data-intel-preview-index]").forEach((button) => {
            button.addEventListener("click", () => {
              state.selectedIntelPreviewIndex = Number(button.dataset.intelPreviewIndex) || 0;
              renderIntelligencePreview(selector, payload, records, header);
            });
          });
          root?.querySelector("#intel-date-jump-toggle")?.addEventListener("click", () => {
            state.intelDatePickerOpen = !state.intelDatePickerOpen;
            renderIntelligencePreview(selector, payload, records, header);
          });
          root?.querySelectorAll("[data-intel-calendar-shift]").forEach((button) => {
            button.addEventListener("click", () => {
              state.intelCalendarMonth = shiftCalendarMonth(state.intelCalendarMonth, Number(button.dataset.intelCalendarShift) || 0);
              renderIntelligencePreview(selector, payload, records, header);
            });
          });
          root?.querySelectorAll("[data-intel-jump-date]").forEach((button) => {
            button.addEventListener("click", () => {
              const dateKey = button.dataset.intelJumpDate || "";
              const index = filtered.findIndex((record) => recordDateKey(record, payload.data_type) === dateKey);
              if (index < 0) return;
              state.selectedIntelPreviewIndex = index;
              state.intelPreviewDisplayLimit = Math.max(Number(state.intelPreviewDisplayLimit) || INTEL_PREVIEW_PAGE_SIZE, index + INTEL_PREVIEW_PAGE_SIZE);
              state.intelDatePickerOpen = false;
              renderIntelligencePreview(selector, payload, records, header);
              window.requestAnimationFrame(() => {
                root?.querySelector(`[data-intel-date-heading="${dateKey}"]`)?.scrollIntoView({block: "start"});
              });
            });
          });
          root?.querySelector(".intel-preview-list")?.addEventListener("scroll", (event) => {
            const list = event.currentTarget;
            if (!list || state.intelPreviewLoadingMore) return;
            if (list.scrollTop + list.clientHeight < list.scrollHeight - 48) return;
            state.intelPreviewLoadingMore = true;
            if (state.intelPreviewDisplayLimit >= filtered.length && canFetchMore) {
              loadMoreIntelligencePreview(selector, payload, records, header);
              return;
            }
            window.setTimeout(() => {
              state.intelPreviewDisplayLimit = Math.min(filtered.length, (Number(state.intelPreviewDisplayLimit) || INTEL_PREVIEW_PAGE_SIZE) + INTEL_PREVIEW_PAGE_SIZE);
              state.intelPreviewLoadingMore = false;
              renderIntelligencePreview(selector, payload, records, header);
            }, 80);
          });
        }

        async function loadMoreIntelligencePreview(selector, payload, records, header) {
          const request = viewerRequest("intel");
          if (!request) {
            state.intelPreviewLoadingMore = false;
            return;
          }
          state.intelPreviewFetchLimit = Math.min(INTEL_PREVIEW_MAX_LIMIT, (Number(state.intelPreviewFetchLimit) || INTEL_PREVIEW_FETCH_STEP) + INTEL_PREVIEW_FETCH_STEP);
          try {
            const nextPayload = await postJson(endpoints.dataViewerPreview, {...request, limit: state.intelPreviewFetchLimit, sort_order: "desc"});
            state.dataViewerIntelPreview = nextPayload;
            state.intelPreviewDisplayLimit = Math.min(
              Array.isArray(nextPayload.records) ? nextPayload.records.length : 0,
              (Number(state.intelPreviewDisplayLimit) || INTEL_PREVIEW_PAGE_SIZE) + INTEL_PREVIEW_PAGE_SIZE,
            );
            state.intelPreviewLoadingMore = false;
            renderPreview("intel", nextPayload);
          } catch (error) {
            state.intelPreviewLoadingMore = false;
            renderError(selector, error.message);
          }
        }

        function previewListItemsWithDates(records, dataType) {
          let currentDate = "";
          return records.map((record, index) => {
            const dateKey = recordDateKey(record, dataType);
            const heading = dateKey && dateKey !== currentDate
              ? `<div class="intel-date-heading" data-intel-date-heading="${escapeHtml(dateKey)}">${escapeHtml(formatDateHeading(dateKey))}</div>`
              : "";
            if (dateKey) currentDate = dateKey;
            return `${heading}${previewListItem(record, dataType, index)}`;
          }).join("");
        }

        function previewListItem(record, dataType, index) {
          const active = index === state.selectedIntelPreviewIndex;
          const time = recordTime(record, dataType);
          const category = recordCategory(record, dataType);
          const sourceLabel = [recordSource(record), categoryLabel(category)].filter(Boolean).join(" / ");
          const temporalState = macroCalendarTemporalState(record, dataType);
          const temporalClass = temporalState ? ` macro-event-${temporalState.key}` : "";
          return `
            <button class="intel-preview-row${temporalClass} ${active ? "active" : ""}" type="button" data-intel-preview-index="${index}">
              <strong>${escapeHtml(recordTitle(record, dataType))}</strong>
              <span>${escapeHtml(formatTimestamp(time))}${temporalState ? `<em class="macro-event-state">${escapeHtml(temporalState.label)}</em>` : ""}</span>
              <small>${escapeHtml(sourceLabel || dataType)}</small>
            </button>`;
        }

        function previewFilterControls(categoryOptions, filteredCount, totalCount) {
          const categoryValue = String(state.intelPreviewCategory || "");
          const keywordValue = String(state.intelPreviewKeyword || "");
          const categoryRows = [`<option value="">All categories</option>`].concat(categoryOptions.map((option) => (
            `<option value="${escapeHtml(option.value)}" ${option.value === categoryValue ? "selected" : ""}>${escapeHtml(option.label)} (${escapeHtml(formatNumber(option.count))})</option>`
          )));
          return `
            <div class="intel-list-filterbar">
              <div class="field">
                <label for="intel-preview-category-filter">Category</label>
                <select id="intel-preview-category-filter" class="select-input">${categoryRows.join("")}</select>
              </div>
              <div class="field">
                <label for="intel-preview-keyword">Search loaded records</label>
                <input id="intel-preview-keyword" class="text-input" type="search" value="${escapeHtml(keywordValue)}" placeholder="filter title, source, or content">
              </div>
              <div class="intel-filter-actions">
                <button class="ghost-button compact-button" type="button" id="intel-preview-clear-filters">Clear filters</button>
                <span>${escapeHtml(formatNumber(filteredCount))} / ${escapeHtml(formatNumber(totalCount))} loaded</span>
              </div>
            </div>`;
        }

        function wireIntelligencePreviewFilters(selector, payload, records, header) {
          const root = node(selector);
          root?.querySelector("#intel-preview-category-filter")?.addEventListener("change", (event) => {
            state.intelPreviewCategory = event.target.value || "";
            resetIntelligencePreviewListPosition();
            renderIntelligencePreview(selector, payload, records, header);
          });
          root?.querySelector("#intel-preview-keyword")?.addEventListener("input", (event) => {
            state.intelPreviewKeyword = event.target.value || "";
            window.clearTimeout(state.intelPreviewFilterTimer);
            state.intelPreviewFilterTimer = window.setTimeout(() => {
              resetIntelligencePreviewListPosition();
              renderIntelligencePreview(selector, payload, records, header);
            }, 220);
          });
          root?.querySelector("#intel-preview-clear-filters")?.addEventListener("click", () => {
            state.intelPreviewKeyword = "";
            state.intelPreviewCategory = "";
            resetIntelligencePreviewListPosition();
            renderIntelligencePreview(selector, payload, records, header);
          });
        }

        function resetIntelligencePreviewListPosition() {
          state.selectedIntelPreviewIndex = 0;
          state.intelPreviewDisplayLimit = INTEL_PREVIEW_PAGE_SIZE;
          state.intelDatePickerOpen = false;
          state.intelCalendarMonth = null;
        }

        function previewCategoryOptions(records, dataType) {
          const counts = new Map();
          records.forEach((record) => {
            const category = recordCategory(record, dataType);
            counts.set(category, (counts.get(category) || 0) + 1);
          });
          return Array.from(counts.entries())
            .sort(([left], [right]) => categoryLabel(left).localeCompare(categoryLabel(right)))
            .map(([value, count]) => ({value, label: categoryLabel(value), count}));
        }

        function recordCategory(record, dataType) {
          const raw = dataType === "market_anomaly"
            ? record?.data_class || record?.severity || record?.source_kind
            : dataType === "derivatives_market"
            ? record?.data_class || record?.market_type || record?.endpoint
            : dataType === "onchain_flow"
              ? record?.data_class || record?.endpoint
              : dataType === "macro_calendar"
                ? record?.data_class || record?.event_type || record?.region
                : record?.event_type || record?.source_type || record?.input_type;
          return raw ? String(raw) : "unclassified";
        }

        function categoryLabel(value) {
          return value === "unclassified" ? "Unclassified" : label(value);
        }

        function previewRecordBody(record, dataType) {
          const title = recordTitle(record, dataType);
          const time = recordTime(record, dataType);
          const summary = recordSummary(record, dataType);
          const facts = recordPrimaryFacts(record, dataType);
          const metrics = recordMetricFacts(record);
          return `
            <div class="intel-readable-record">
              ${macroCalendarTemporalBanner(record, dataType)}
              <div class="muted">${escapeHtml(formatTimestamp(time))}</div>
              <h2>${escapeHtml(title)}</h2>
              <p>${escapeHtml(summary || "No narrative summary is recorded for this item.")}</p>
              ${metrics.length ? `<section class="intel-record-section"><h3>Key metrics</h3><div class="intel-metric-grid">${metrics.map(([key, val, unit]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(formatMetricValue(val, key, unit))}</strong>${unit ? `<small>${escapeHtml(unit)}</small>` : ""}</div>`).join("")}</div></section>` : ""}
              ${facts.length ? `<section class="intel-record-section"><h3>Record context</h3><div class="intel-fact-grid">${facts.map(([key, val]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(text(val))}</strong></div>`).join("")}</div></section>` : ""}
            </div>`;
        }

        function macroCalendarTemporalState(record, dataType) {
          if (dataType !== "macro_calendar") return null;
          const raw = record?.scheduled_at || recordTime(record, dataType);
          const timestamp = Date.parse(raw);
          if (!Number.isFinite(timestamp)) {
            return {
              key: "unknown",
              label: "Time unknown",
              title: "Event time unknown",
              body: "This macro calendar item does not include a parseable scheduled time.",
              scheduledAt: "",
            };
          }
          const scheduledAt = new Date(timestamp).toISOString();
          if (timestamp > Date.now()) {
            return {
              key: "future",
              label: "Future event",
              title: "Future scheduled event",
              body: `Scheduled for ${formatTimestamp(scheduledAt)}. Results may still be unavailable until the event is released.`,
              scheduledAt,
            };
          }
          return {
            key: "past",
            label: "Past event",
            title: "Past macro event",
            body: `Scheduled for ${formatTimestamp(scheduledAt)}. This item is already part of the historical event window.`,
            scheduledAt,
          };
        }

        function macroCalendarTemporalBanner(record, dataType) {
          const temporalState = macroCalendarTemporalState(record, dataType);
          if (!temporalState) return "";
          return `
            <div class="macro-event-banner ${escapeHtml(temporalState.key)}">
              <span class="status-pill ${escapeHtml(temporalState.key)}">${escapeHtml(temporalState.label)}</span>
              <div>
                <strong>${escapeHtml(temporalState.title)}</strong>
                <small>${escapeHtml(temporalState.body)}</small>
              </div>
            </div>`;
        }

        function previewRecordProperties(record, payload) {
          const entries = Object.entries(record || {})
            .filter((entry) => entry[1] !== null && entry[1] !== undefined && entry[1] !== "")
            .slice(0, 28)
            .map(([key, val]) => [key, propertyValue(val)]);
          const rows = [
            ["Data type", TYPE_LABELS[payload.data_type] || payload.data_type],
            ["Query status", payload.status || "unknown"],
            ["Source", recordSource(record) || payload.source || "n/a"],
            ...entries,
          ];
          return `<h3 class="subsection-title">Properties</h3><table class="kv-table">${rows.map(([key, val]) => `<tr><td>${escapeHtml(key)}</td><td>${escapeHtml(text(val))}</td></tr>`).join("")}</table>`;
        }

        function recordTitle(record, dataType) {
          if (dataType === "onchain_flow") {
            const title = [label(record?.data_class || "on-chain flow"), record?.asset, record?.chain ? `on ${record.chain}` : ""].filter(Boolean).join(" ");
            if (title) return title;
          }
          if (dataType === "derivatives_market") {
            const title = [record?.symbol, label(record?.data_class || "derivatives"), record?.period].filter(Boolean).join(" ");
            if (title) return title;
          }
          if (dataType === "market_anomaly") {
            const title = [record?.symbol, label(record?.data_class || "market anomaly"), record?.timeframe].filter(Boolean).join(" ");
            if (record?.title) return record.title;
            if (title) return title;
          }
          if (dataType === "macro_calendar") {
            const title = [record?.event_name || record?.title || record?.name, record?.currency || record?.country].filter(Boolean).join(" / ");
            if (title) return title;
          }
          return text(
            record?.title
              ?? record?.event_name
              ?? record?.name
              ?? record?.metric
              ?? record?.event_type
              ?? record?.raw_item_id
              ?? record?.id,
            TYPE_LABELS[dataType] || dataType,
          );
        }

        function recordSummary(record, dataType) {
          const direct = record?.summary ?? record?.description ?? record?.text ?? record?.content ?? record?.body;
          if (direct) return String(direct);
          const metrics = recordMetricFacts(record);
          if (dataType === "onchain_flow" && metrics.length) {
            return `${label(record?.data_class || "on-chain flow")} observation for ${text(record?.asset, "asset")} on ${text(record?.chain, "chain")} at ${formatTimestamp(recordTime(record, dataType))}.`;
          }
          if (dataType === "derivatives_market" && metrics.length) {
            return `${label(record?.data_class || "derivatives")} snapshot for ${text(record?.symbol, "symbol")} ${record?.period ? `(${record.period})` : ""} at ${formatTimestamp(recordTime(record, dataType))}.`;
          }
          if (dataType === "market_anomaly" && metrics.length) {
            return `${label(record?.data_class || "market anomaly")} for ${text(record?.symbol, "symbol")} ${record?.timeframe ? `(${record.timeframe})` : ""} observed at ${formatTimestamp(recordTime(record, dataType))}.`;
          }
          const facts = recordPrimaryFacts(record, dataType);
          return facts.map(([key, val]) => `${key}: ${text(val)}`).join(" / ");
        }

        function recordPrimaryFacts(record, dataType) {
          const keys = {
            text_event: ["source", "source_name", "event_type", "status", "url"],
            macro_calendar: ["region", "country", "currency", "importance", "actual", "forecast", "previous"],
            onchain_flow: ["source", "asset", "chain", "data_class", "endpoint", "status"],
            derivatives_market: ["source", "symbol", "market_type", "data_class", "period", "endpoint", "status"],
            market_anomaly: ["source_kind", "source", "symbol", "market_type", "data_class", "timeframe", "severity", "direction", "status"],
          }[dataType] || [];
          return keys
            .filter((key) => record?.[key] !== null && record?.[key] !== undefined && record?.[key] !== "")
            .slice(0, 8)
            .map((key) => [label(key), record[key]]);
        }

        function recordTime(record, dataType) {
          return record?.published_at
            || record?.source_published_at
            || record?.scheduled_at
            || record?.observed_at
            || record?.as_of
            || record?.open_time
            || record?.collected_at
            || record?.created_at
            || record?.updated_at
            || "";
        }

        function recordMetricFacts(record) {
          const metrics = record?.metrics && typeof record.metrics === "object" ? record.metrics : {};
          const units = record?.units && typeof record.units === "object" ? record.units : {};
          return Object.entries(metrics)
            .filter((entry) => entry[1] !== null && entry[1] !== undefined && entry[1] !== "")
            .slice(0, 8)
            .map(([key, val]) => [label(key), val, units[key] || ""]);
        }

        function recordSource(record) {
          return record?.source || record?.source_name || record?.provider || record?.exchange || "";
        }

        function formatMetricValue(value, key, unit) {
          const numeric = Number(value);
          if (!Number.isFinite(numeric)) return text(value);
          const rawKey = String(key || "").toLowerCase();
          if (String(unit || "").toLowerCase() === "percent") {
            return `${numeric.toFixed(4)}%`;
          }
          if (String(unit || "").toLowerCase() === "ratio" || rawKey.includes("rate")) {
            return `${(numeric * 100).toFixed(4)}%`;
          }
          if (Math.abs(numeric) >= 1000) return formatNumber(numeric);
          return numeric.toLocaleString(undefined, {maximumFractionDigits: 8});
        }

        function recordDateKey(record, dataType) {
          const raw = recordTime(record, dataType);
          const parsed = Date.parse(raw);
          if (Number.isFinite(parsed)) return new Date(parsed).toISOString().slice(0, 10);
          return "";
        }

        function formatDateHeading(dateKey) {
          const parsed = Date.parse(`${dateKey}T00:00:00Z`);
          return Number.isFinite(parsed) ? formatTimestamp(new Date(parsed).toISOString()).split(",")[0] : dateKey;
        }

        function ensureIntelCalendarMonth(records, dataType) {
          if (state.intelCalendarMonth) return state.intelCalendarMonth;
          const dateKey = recordDateKey(records[state.selectedIntelPreviewIndex] || records[0], dataType);
          state.intelCalendarMonth = dateKey ? dateKey.slice(0, 7) : new Date().toISOString().slice(0, 7);
          return state.intelCalendarMonth;
        }

        function shiftCalendarMonth(monthKey, delta) {
          const [year, month] = String(monthKey || new Date().toISOString().slice(0, 7)).split("-").map((part) => Number(part));
          const date = new Date(Date.UTC(year || new Date().getUTCFullYear(), (month || 1) - 1 + delta, 1));
          return date.toISOString().slice(0, 7);
        }

        function renderDateJumpCalendar(records, dataType) {
          const dateSet = new Set(records.map((record) => recordDateKey(record, dataType)).filter(Boolean));
          const monthKey = ensureIntelCalendarMonth(records, dataType);
          const [year, month] = monthKey.split("-").map((part) => Number(part));
          const first = new Date(Date.UTC(year, month - 1, 1));
          const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
          const leading = first.getUTCDay();
          const cells = [];
          for (let index = 0; index < leading; index += 1) cells.push(`<span class="intel-calendar-empty"></span>`);
          for (let day = 1; day <= daysInMonth; day += 1) {
            const dateKey = `${monthKey}-${String(day).padStart(2, "0")}`;
            const enabled = dateSet.has(dateKey);
            cells.push(`<button class="intel-calendar-day ${enabled ? "has-data" : ""}" type="button" ${enabled ? `data-intel-jump-date="${escapeHtml(dateKey)}"` : "disabled"}>${day}</button>`);
          }
          const monthLabel = first.toLocaleString(undefined, {month: "long", year: "numeric", timeZone: "UTC"});
          return `
            <div class="intel-date-picker">
              <div class="intel-calendar-head">
                <button class="ghost-button compact-button" type="button" data-intel-calendar-shift="-1">Prev</button>
                <strong>${escapeHtml(monthLabel)}</strong>
                <button class="ghost-button compact-button" type="button" data-intel-calendar-shift="1">Next</button>
              </div>
              <div class="intel-calendar-weekdays">${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => `<span>${day}</span>`).join("")}</div>
              <div class="intel-calendar-grid">${cells.join("")}</div>
            </div>`;
        }

        function propertyValue(value) {
          if (Array.isArray(value)) return value.map((item) => typeof item === "object" ? JSON.stringify(item) : String(item)).join(", ").slice(0, 240);
          if (typeof value === "object") return JSON.stringify(value).slice(0, 240);
          return String(value).slice(0, 240);
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
          const jobLogs = job?.logs || {};
          const refRows = Object.entries(refs).map(([key, value]) => [key, value]);
          const logRows = Object.entries(jobLogs)
            .filter(([key]) => key.endsWith("_ref") || key.endsWith("_truncated"))
            .map(([key, value]) => [key, value]);
          const expanded = node(selector)?.querySelector(".operation-progress")?.dataset.expanded === "true";
          const percent = jobProgressPercent(status);
          const logLines = dataViewerJobLogLines(job, refRows, logRows);
          const visibleLogLines = logLines.slice().reverse();
          setHtml(selector, `
            <div class="operation-progress" data-expanded="${expanded ? "true" : "false"}">
              <div class="operation-progress-top">
                <div>
                  <strong>Collection job ${escapeHtml(label(status))}</strong>
                  <span>${escapeHtml(job?.job_id || "pending")}</span>
                </div>
                <span>${escapeHtml(`${percent}%`)}</span>
              </div>
              <div class="operation-progress-track"><span class="${escapeHtml(statusClass(status))}" style="width:${percent}%;"></span></div>
              <div class="operation-log-header">
                <span>${escapeHtml(visibleLogLines[0] || "No log lines yet.")}</span>
                <button class="ghost-button compact-button" type="button" data-data-viewer-job-log-toggle>${expanded ? "Collapse" : "Expand logs"}</button>
              </div>
              <pre class="operation-log ${expanded ? "expanded" : ""}">${escapeHtml(visibleLogLines.join("\n") || "No log lines yet.")}</pre>
              ${job?.job_id ? `<button class="ghost-button compact-button" type="button" data-data-viewer-refresh-job="${escapeHtml(scope)}" data-job-id="${escapeHtml(job.job_id)}">Refresh job</button>` : ""}
            </div>
            ${refRows.length ? table(["Result ref", "Artifact"], refRows) : `<div class="message">No result refs recorded yet.</div>`}
            ${logRows.length ? table(["Log field", "Value"], logRows) : ""}
          `);
          const progressNode = node(selector)?.querySelector(".operation-progress");
          progressNode?.querySelector("[data-data-viewer-job-log-toggle]")?.addEventListener("click", () => {
            progressNode.dataset.expanded = expanded ? "false" : "true";
            renderJob(scope, job);
          });
          wireJobRefreshButtons();
        }

        function jobProgressPercent(status) {
          const normalized = String(status || "").toLowerCase();
          if (terminalJobStatus(normalized)) return 100;
          if (normalized === "running") return 66;
          if (normalized === "queued" || normalized === "created" || normalized === "creating") return 18;
          if (normalized === "cancel_requested") return 85;
          return 35;
        }

        function dataViewerJobLogLines(job, refRows, logRows) {
          const lines = [];
          const status = label(job?.status || "created");
          lines.push(`${status} collection job ${job?.job_id || "pending"}.`);
          if (job?.intent) lines.push(`intent: ${job.intent}`);
          if (job?.command?.[0] === "internal") lines.push("execution: internal dashboard service");
          refRows.forEach(([key, value]) => lines.push(`${key}: ${value}`));
          logRows.forEach(([key, value]) => lines.push(`${key}: ${value}`));
          (Array.isArray(job?.warnings) ? job.warnings : []).slice(0, 6).forEach((warning) => lines.push(`warning: ${warning}`));
          (Array.isArray(job?.errors) ? job.errors : []).slice(0, 6).forEach((error) => lines.push(`error: ${error}`));
          return lines;
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
          if (!start || !end) return;
          if (start.value && end.value) {
            syncDateRangePicker(`#${prefix}-start`, `#${prefix}-end`);
            return;
          }
          const now = new Date();
          const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 3600 * 1000);
          if (!start.value) start.value = toIsoMinute(sevenDaysAgo);
          if (!end.value) end.value = toIsoMinute(now);
          syncDateRangePicker(`#${prefix}-start`, `#${prefix}-end`);
        }

        function ensureIntelligenceDefaultRange(prefix, force = false) {
          const start = node(`#${prefix}-start`);
          const end = node(`#${prefix}-end`);
          if (!start || !end) return;
          if (!force && start.value && end.value) {
            syncDateRangePicker(`#${prefix}-start`, `#${prefix}-end`);
            return;
          }
          applyIntelligenceRangePreset(prefix, force);
          if (!start.value || !end.value) ensureDefaultRange(prefix);
          syncDateRangePicker(`#${prefix}-start`, `#${prefix}-end`);
        }

        function applyIntelligenceRangePreset(prefix, force = false) {
          const range = node(`#${prefix}-range`);
          const start = node(`#${prefix}-start`);
          const end = node(`#${prefix}-end`);
          if (!range || !start || !end) return;
          if (!force && start.value && end.value) {
            syncDateRangePicker(`#${prefix}-start`, `#${prefix}-end`);
            return;
          }
          const value = range.value || "all";
          if (value === "custom") {
            syncDateRangePicker(`#${prefix}-start`, `#${prefix}-end`);
            return;
          }
          const coverage = storeSummary(selectedIntelligenceDataType())?.coverage || {};
          const anchor = parseIsoDate(coverage.range_end) || new Date();
          if (value === "all" && coverage.range_start && coverage.range_end) {
            start.value = coverage.range_start;
            end.value = coverage.range_end;
            syncDateRangePicker(`#${prefix}-start`, `#${prefix}-end`);
            return;
          }
          const days = value === "1d" ? 1 : value === "7d" ? 7 : value === "30d" ? 30 : value === "180d" ? 180 : 7;
          end.value = toIsoMinute(anchor);
          start.value = toIsoMinute(new Date(anchor.getTime() - days * 24 * 3600 * 1000));
          syncDateRangePicker(`#${prefix}-start`, `#${prefix}-end`);
        }

        function parseIsoDate(value) {
          const date = value ? new Date(value) : null;
          return date && Number.isFinite(date.getTime()) ? date : null;
        }

        function ensureStrategyDefaultRange(force = false) {
          const start = node("#strategy-data-start");
          const end = node("#strategy-data-end");
          if (!start || !end || (!force && start.value && end.value)) return;
          const coverage = storeSummary("ohlcv")?.coverage || {};
          if (coverage.range_start && (force || !start.value)) {
            start.value = coverage.range_start;
          }
          if (coverage.range_end && (force || !end.value)) {
            end.value = coverage.range_end;
          }
          if (!start.value || !end.value) {
            ensureDefaultRange("strategy-data");
          }
        }

        function toIsoMinute(date) {
          return date.toISOString().replace(/\.\d{3}Z$/, "Z");
        }

        function intelligencePreviewAsOf() {
          const mode = value("#intel-preview-as-of-mode");
          if (mode === "range_end") return value("#intel-preview-end");
          if (mode === "custom") return datetimeLocalUtc("#intel-preview-as-of");
          return "";
        }

        function datetimeLocalUtc(selector) {
          const raw = value(selector);
          if (!raw) return "";
          if (raw.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(raw)) return raw;
          const normalized = raw.length === 16 ? `${raw}:00` : raw;
          return `${normalized}Z`;
        }

        function syncIntelPreviewAsOfControls() {
          const customField = node("#intel-preview-as-of-custom-field");
          const customMode = value("#intel-preview-as-of-mode") === "custom";
          customField?.classList.toggle("hidden", !customMode);
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
          node("#strategy-data-timeline")?.addEventListener("click", () => loadTimeline("strategy"));
          node("#strategy-data-preview")?.addEventListener("click", () => loadPreview("strategy"));
          node("#strategy-data-plan")?.addEventListener("click", () => loadCollectionPlan("strategy"));
          node("#strategy-data-collect")?.addEventListener("click", () => submitCollectionJob("strategy"));
          node("#strategy-data-export")?.addEventListener("click", () => exportData("strategy"));
          node("#intel-data-collect")?.addEventListener("click", () => submitCollectionJob("intel"));
          node("#intel-data-type")?.addEventListener("change", () => {
            state.dataViewerIntelTimeline = null;
            state.dataViewerIntelPreview = null;
            state.dataViewerIntelPlan = null;
            state.intelPreviewKeyword = "";
            state.intelPreviewCategory = "";
            resetIntelligencePreviewState();
            renderIntelligenceViewer();
          });
          ["#strategy-data-source", "#strategy-data-symbol", "#strategy-data-timeframe", "#strategy-data-start", "#strategy-data-end", "#strategy-data-as-of"].forEach((selector) => {
            node(selector)?.addEventListener("change", renderStrategyViewer);
          });
          node("#intel-collect-range")?.addEventListener("change", () => {
            applyIntelligenceRangePreset("intel-collect", true);
            queueIntelligenceCollectTimelineLoad();
          });
          ["#intel-collect-start", "#intel-collect-end"].forEach((selector) => {
            node(selector)?.addEventListener("change", () => {
              queueIntelligenceCollectTimelineLoad();
            });
          });
          node("#intel-collect-reset")?.addEventListener("click", () => {
            const range = node("#intel-collect-range");
            if (range) range.value = "all";
            applyIntelligenceRangePreset("intel-collect", true);
            queueIntelligenceCollectTimelineLoad();
          });
          node("#intel-preview-range")?.addEventListener("change", () => {
            resetIntelligencePreviewState();
            applyIntelligenceRangePreset("intel-preview", true);
            queueIntelligencePreviewLoad();
          });
          ["#intel-preview-start", "#intel-preview-end", "#intel-preview-as-of-mode", "#intel-preview-as-of"].forEach((selector) => {
            node(selector)?.addEventListener("change", () => {
              syncIntelPreviewAsOfControls();
              resetIntelligencePreviewState();
              queueIntelligencePreviewLoad();
            });
          });
          node("#intel-preview-reset")?.addEventListener("click", () => {
            const range = node("#intel-preview-range");
            if (range) range.value = "all";
            ["#intel-preview-as-of-mode", "#intel-preview-as-of"].forEach((selector) => {
              const target = node(selector);
              if (target) target.value = "";
            });
            state.intelPreviewKeyword = "";
            state.intelPreviewCategory = "";
            syncIntelPreviewAsOfControls();
            applyIntelligenceRangePreset("intel-preview", true);
            resetIntelligencePreviewState();
            queueIntelligencePreviewLoad();
          });
          document.addEventListener("click", (event) => {
            const eventTarget = event.target instanceof Element ? event.target : null;
            if (!eventTarget) return;
            const issueButton = eventTarget.closest("[data-data-viewer-issues]");
            if (issueButton) {
              event.preventDefault();
              event.stopPropagation();
              toggleIssuePopover(issueButton.dataset.dataViewerIssues);
              return;
            }
            if (!eventTarget.closest(".data-viewer-issue-widget")) {
              closeIssuePopovers();
            }
          });
          document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") closeIssuePopovers();
          });
        }

        return {
          DATA_VIEWER_STATUS_VOCABULARY,
          ensureStrategyDefaultRange,
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
