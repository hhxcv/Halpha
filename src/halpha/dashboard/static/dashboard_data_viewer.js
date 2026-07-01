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

        function loadingSkeleton(lines = 3) {
          return `<div class="empty-state loading-surface">${Array.from({length: lines}, (_, index) => (
            `<span class="skeleton skeleton-line" style="width:${index === lines - 1 ? "52%" : "86%"}"></span>`
          )).join("")}</div>`;
        }

        function timelineSkeleton() {
          return `<div class="loading-surface">
            <span class="skeleton skeleton-line" style="width:48%"></span>
            <span class="skeleton skeleton-line" style="width:100%; height:18px; border-radius:999px;"></span>
            <span class="skeleton skeleton-line" style="width:74%"></span>
          </div>`;
        }

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
            updateIntelligencePropertiesSelection(null, null);
            closeIntelligenceCollectDialog(false);
            applyIntelligenceRangePreset("intel-collect", true);
            applyIntelligenceRangePreset("intel-preview", true);
          } else {
            ensureIntelligenceDefaultRange("intel-collect", false);
            ensureIntelligenceDefaultRange("intel-preview", false);
          }
          renderStoreSummary("intel", dataType);
          renderCapabilityState("intel", dataType);
          setHtml("#intel-data-coverage", timelineSkeleton());
          setHtml("#intel-data-preview-panel", loadingSkeleton(4));
          syncIntelligencePreviewFilterControls([], 0, 0);
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
          node("#intel-data-viewer")?.classList.toggle("macro-calendar-mode", dataType === "macro_calendar");
          node("#intel-data-viewer")?.classList.toggle("onchain-flow-mode", dataType === "onchain_flow");
          node("#intel-data-viewer")?.classList.toggle("derivatives-market-mode", dataType === "derivatives_market");
          node("#intel-data-viewer")?.classList.toggle("market-anomaly-mode", dataType === "market_anomaly");
          const title = node("#intel-data-viewer .panel-title");
          if (title) {
            title.innerHTML = `${escapeHtml(TYPE_LABELS[dataType] || dataType)} <span id="intel-data-status" class="status-pill pending">loading</span>`;
          }
        }

        function resetIntelligencePreviewState() {
          state.selectedIntelPreviewIndex = 0;
          state.intelPreviewDisplayLimit = INTEL_PREVIEW_PAGE_SIZE;
          state.intelPreviewFetchLimit = INTEL_PREVIEW_FETCH_STEP;
          state.intelPreviewLoadingMore = false;
          state.intelDatePickerOpen = false;
          state.intelCalendarMonth = null;
          state.macroCalendarView = "month";
          state.macroCalendarMonth = null;
          state.macroCalendarYear = null;
          state.macroCalendarHighlightedDate = "";
          state.macroCalendarDetailIndex = null;
          state.onchainDataClass = "";
          state.onchainMetricKey = "";
          state.onchainSelectedIndex = null;
          state.derivativesDataClass = "";
          state.derivativesMetricKey = "";
          state.derivativesSelectedIndex = null;
          state.anomalySeverityFilter = "";
          state.anomalySourceKindFilter = "";
          state.anomalySelectedIndex = null;
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
              <button class="ghost-button compact-button data-viewer-issue-button ${escapeHtml(statusClass(issueStatus))}" type="button" data-data-viewer-issues="${escapeHtml(scope)}" aria-expanded="false">
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
          setHtml(panelSelector(scope, "coverage"), timelineSkeleton());
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
          setHtml(panelSelector(scope, "preview"), loadingSkeleton(scope === "strategy" ? 3 : 5));
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
          setHtml(panelSelector(scope, "plan"), loadingSkeleton(3));
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
          setHtml(panelSelector(scope, "job"), loadingSkeleton(2));
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
          setHtml(panelSelector(scope, "job"), loadingSkeleton(2));
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
          setHtml("#intel-data-coverage", timelineSkeleton());
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
          setHtml("#intel-data-preview-panel", loadingSkeleton(5));
          const previewDataType = selectedIntelligenceDataType();
          const previewLimit = ["onchain_flow", "derivatives_market", "market_anomaly"].includes(previewDataType)
            ? INTEL_PREVIEW_MAX_LIMIT
            : Math.min(INTEL_PREVIEW_MAX_LIMIT, Math.max(INTEL_PREVIEW_PAGE_SIZE, Number(state.intelPreviewFetchLimit) || INTEL_PREVIEW_FETCH_STEP));
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
              `${header}<div class="message">Loaded ${escapeHtml(formatNumber(records.length))} bounded candles into the Strategy chart.</div>`,
            );
            return;
          }
          const columns = previewColumns(payload.data_type, records);
          const rows = records.slice(0, 25).map((record) => columns.map((column) => previewCell(record[column])));
          setHtml(selector, `${header}${table(columns, rows)}`);
        }

        function renderIntelligencePreview(selector, payload, records, header) {
          if (payload.data_type === "macro_calendar") {
            renderMacroCalendarPreview(selector, payload, records);
            return;
          }
          if (payload.data_type === "onchain_flow") {
            renderOnchainFlowPreview(selector, payload, records);
            return;
          }
          if (payload.data_type === "derivatives_market") {
            renderDerivativesMarketPreview(selector, payload, records);
            return;
          }
          if (payload.data_type === "market_anomaly") {
            renderMarketAnomalyPreview(selector, payload, records);
            return;
          }
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
            updateIntelligencePropertiesSelection(null, payload);
            syncIntelligencePreviewFilterControls(categoryOptions, 0, records.length);
            setHtml(selector, `
              <div class="intelligence-preview-layout">
                <aside class="intel-preview-sidebar">
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
              </div>`);
            wireIntelligencePreviewList(selector, payload, records, header, filtered, false);
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
          updateIntelligencePropertiesSelection(selected, payload);
          syncIntelligencePreviewFilterControls(categoryOptions, filtered.length, records.length);
          setHtml(selector, `
            <div class="intelligence-preview-layout">
              <aside class="intel-preview-sidebar">
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
            </div>`);
          wireIntelligencePreviewList(selector, payload, records, header, filtered, canFetchMore);
        }

        function renderMacroCalendarPreview(selector, payload, records) {
          const events = macroCalendarRecords(records);
          syncIntelligencePreviewFilterControls([], events.length, records.length);
          if (!events.length) {
            updateIntelligencePropertiesSelection(null, payload);
            setHtml(selector, `
              <div class="macro-calendar-preview empty">
                <aside class="intel-preview-sidebar macro-event-sidebar">
                  <div class="intel-list-toolbar"><strong>Events</strong><span>0 events</span></div>
                  <div class="intel-preview-list" aria-label="Macro calendar events">
                    <div class="empty-state">No macro calendar events are available for the current preview range.</div>
                  </div>
                </aside>
                <article class="macro-calendar-main">
                  <div class="empty-state">Collect or extend macro calendar data to populate this calendar.</div>
                </article>
              </div>`);
            return;
          }
          state.selectedIntelPreviewIndex = Math.min(Math.max(0, Number(state.selectedIntelPreviewIndex) || 0), events.length - 1);
          ensureMacroCalendarViewport(events);
          const selected = events[state.selectedIntelPreviewIndex];
          updateIntelligencePropertiesSelection(selected, payload);
          setHtml(selector, `
            <div class="macro-calendar-preview">
              <aside class="intel-preview-sidebar macro-event-sidebar">
                <div class="intel-list-toolbar"><strong>Events</strong><span>${escapeHtml(formatNumber(events.length))} events</span></div>
                <div class="intel-preview-list macro-event-list" aria-label="Macro calendar events">
                  ${macroEventListItemsWithDates(events)}
                </div>
              </aside>
              <article class="macro-calendar-main">
                ${renderMacroCalendarMain(events)}
              </article>
              ${renderMacroEventDialog(events, payload)}
            </div>`);
          wireMacroCalendarPreview(selector, payload, events);
        }

        function renderOnchainFlowPreview(selector, payload, records) {
          const groups = onchainFlowGroups(records);
          syncIntelligencePreviewFilterControls([], records.length, records.length);
          if (!groups.length) {
            updateIntelligencePropertiesSelection(null, payload);
            setHtml(selector, `
              <div class="onchain-flow-preview empty">
                <div class="empty-state">No on-chain flow records are available for the current preview window.</div>
              </div>`);
            return;
          }
          if (!groups.some((group) => group.key === state.onchainDataClass)) {
            state.onchainDataClass = groups[0].key;
            state.onchainMetricKey = "";
            state.onchainSelectedIndex = null;
          }
          const group = groups.find((item) => item.key === state.onchainDataClass) || groups[0];
          const metricKeys = onchainMetricKeys(group.records);
          if (!metricKeys.length) {
            updateIntelligencePropertiesSelection(group.records[0] || null, payload);
            setHtml(selector, `
              <div class="onchain-flow-preview">
                ${renderOnchainFlowTabs(groups, group.key)}
                <div class="empty-state">This on-chain class does not expose numeric metrics that can be charted.</div>
              </div>`);
            wireOnchainFlowPreview(selector, payload, records, groups, [], []);
            return;
          }
          if (!metricKeys.includes(state.onchainMetricKey)) {
            state.onchainMetricKey = metricKeys[0];
            state.onchainSelectedIndex = null;
          }
          const series = onchainMetricSeries(group.records, state.onchainMetricKey);
          if (!series.length) {
            updateIntelligencePropertiesSelection(group.records[0] || null, payload);
            setHtml(selector, `
              <div class="onchain-flow-preview">
                ${renderOnchainFlowTabs(groups, group.key)}
                ${renderOnchainMetricTabs(metricKeys, state.onchainMetricKey, group.records)}
                <div class="empty-state">No numeric observations matched the selected metric.</div>
              </div>`);
            wireOnchainFlowPreview(selector, payload, records, groups, metricKeys, series);
            return;
          }
          const selectedIndex = ensureOnchainSelectedIndex(series);
          const selectedPoint = series[selectedIndex] || series[series.length - 1];
          updateIntelligencePropertiesSelection(selectedPoint?.record || null, payload);
          setHtml(selector, `
            <div class="onchain-flow-preview">
              ${renderOnchainFlowTabs(groups, group.key)}
              <section class="onchain-chart-card">
                <div class="onchain-chart-top">
                  <div class="onchain-title-stack">
                    <span>${escapeHtml(group.label)}</span>
                    <strong>${escapeHtml(metricLabel(state.onchainMetricKey))}</strong>
                    <small>${escapeHtml(formatNumber(series.length))} loaded observations / ${escapeHtml(onchainRangeLabel(series))}</small>
                  </div>
                  <div class="onchain-date-jump">
                    <label for="onchain-date-jump">Jump time</label>
                    <input id="onchain-date-jump" class="text-input" type="datetime-local" step="60" value="${escapeHtml(onchainDateInputValue(selectedPoint?.time))}">
                    <span class="range-picker-badge">UTC</span>
                    <button class="ghost-button compact-button" type="button" data-onchain-jump>Jump</button>
                  </div>
                </div>
                ${renderOnchainMetricTabs(metricKeys, state.onchainMetricKey, group.records)}
                ${renderOnchainMetricSummary(series, selectedPoint, state.onchainMetricKey)}
                <div class="onchain-chart-frame">
                  <div class="onchain-chart-scroll" aria-label="${escapeHtml(group.label)} ${escapeHtml(metricLabel(state.onchainMetricKey))} time series">
                    ${renderOnchainChart(series, state.onchainMetricKey, selectedIndex)}
                  </div>
                </div>
                <div class="onchain-chart-foot">
                  <span>Drag horizontally to inspect dense observations.</span>
                  <span>Y-axis rescales to the loaded ${escapeHtml(metricLabel(state.onchainMetricKey))} range.</span>
                </div>
              </section>
              ${renderOnchainSelectedPoint(selectedPoint, payload)}
            </div>`);
          wireOnchainFlowPreview(selector, payload, records, groups, metricKeys, series);
        }

        function onchainFlowGroups(records) {
          const groups = new Map();
          (Array.isArray(records) ? records : []).forEach((record) => {
            if (!record || typeof record !== "object") return;
            const key = recordCategory(record, "onchain_flow");
            if (!groups.has(key)) {
              groups.set(key, {key, label: categoryLabel(key), records: [], latestTime: 0});
            }
            const group = groups.get(key);
            group.records.push(record);
            const timestamp = Date.parse(recordTime(record, "onchain_flow"));
            if (Number.isFinite(timestamp)) group.latestTime = Math.max(group.latestTime, timestamp);
          });
          return Array.from(groups.values())
            .map((group) => ({
              ...group,
              metrics: onchainMetricKeys(group.records),
              count: group.records.length,
            }))
            .filter((group) => group.count > 0)
            .sort((left, right) => {
              if (right.latestTime !== left.latestTime) return right.latestTime - left.latestTime;
              return left.label.localeCompare(right.label);
            });
        }

        function onchainMetricKeys(records) {
          const keys = [];
          const seen = new Set();
          (Array.isArray(records) ? records : []).forEach((record) => {
            const metrics = record?.metrics && typeof record.metrics === "object" ? record.metrics : {};
            Object.entries(metrics).forEach(([key, value]) => {
              const numeric = Number(value);
              if (!Number.isFinite(numeric) || seen.has(key)) return;
              seen.add(key);
              keys.push(key);
            });
          });
          return keys;
        }

        function onchainMetricSeries(records, metricKey) {
          return (Array.isArray(records) ? records : [])
            .map((record) => {
              const timestamp = Date.parse(recordTime(record, "onchain_flow"));
              const value = Number(record?.metrics?.[metricKey]);
              return {record, time: recordTime(record, "onchain_flow"), timestamp, value};
            })
            .filter((point) => Number.isFinite(point.timestamp) && Number.isFinite(point.value))
            .sort((left, right) => {
              if (left.timestamp !== right.timestamp) return left.timestamp - right.timestamp;
              return left.value - right.value;
            });
        }

        function ensureOnchainSelectedIndex(series) {
          if (state.onchainSelectedIndex === null || state.onchainSelectedIndex === undefined || state.onchainSelectedIndex === "") {
            state.onchainSelectedIndex = Math.max(0, series.length - 1);
            return state.onchainSelectedIndex;
          }
          const requested = Number(state.onchainSelectedIndex);
          if (Number.isInteger(requested) && requested >= 0 && requested < series.length) {
            return requested;
          }
          state.onchainSelectedIndex = Math.max(0, series.length - 1);
          return state.onchainSelectedIndex;
        }

        function renderOnchainFlowTabs(groups, selectedKey) {
          return `
            <div class="onchain-subtabs" role="tablist" aria-label="On-chain data classes">
              ${groups.map((group) => `
                <button class="tab-button ${group.key === selectedKey ? "active" : ""}" type="button" role="tab" aria-selected="${group.key === selectedKey ? "true" : "false"}" data-onchain-class="${escapeHtml(group.key)}">
                  <span>${escapeHtml(group.label)}</span>
                  <small>${escapeHtml(formatNumber(group.count))}</small>
                </button>
              `).join("")}
            </div>`;
        }

        function renderOnchainMetricTabs(metricKeys, selectedMetric, records) {
          return `
            <div class="onchain-metric-tabs" role="tablist" aria-label="On-chain metrics">
              ${metricKeys.map((key) => {
                const count = onchainMetricSeries(records, key).length;
                return `
                  <button class="ghost-button compact-button ${key === selectedMetric ? "active" : ""}" type="button" role="tab" aria-selected="${key === selectedMetric ? "true" : "false"}" data-onchain-metric="${escapeHtml(key)}">
                    ${escapeHtml(metricLabel(key))}
                    <span>${escapeHtml(formatNumber(count))}</span>
                  </button>`;
              }).join("")}
            </div>`;
        }

        function renderOnchainMetricSummary(series, selectedPoint, metricKey) {
          const values = series.map((point) => point.value);
          const min = Math.min(...values);
          const max = Math.max(...values);
          const avg = values.reduce((total, value) => total + value, 0) / Math.max(1, values.length);
          const unit = selectedPoint?.record?.units?.[metricKey] || "";
          return `
            <div class="onchain-metric-summary">
              ${onchainMetricCard("Selected", selectedPoint?.value, metricKey, unit, formatTimestamp(selectedPoint?.time))}
              ${onchainMetricCard("Min", min, metricKey, unit, "loaded range")}
              ${onchainMetricCard("Max", max, metricKey, unit, "loaded range")}
              ${onchainMetricCard("Average", avg, metricKey, unit, "loaded range")}
            </div>`;
        }

        function onchainMetricCard(title, value, key, unit, note) {
          return `
            <div class="onchain-metric-card">
              <span>${escapeHtml(title)}</span>
              <strong>${escapeHtml(formatMetricValue(value, key, unit))}</strong>
              <small>${escapeHtml(note || unit || "value")}</small>
            </div>`;
        }

        function renderOnchainChart(series, metricKey, selectedIndex) {
          const values = series.map((point) => point.value);
          let min = Math.min(...values);
          let max = Math.max(...values);
          const rawMin = min;
          if (!Number.isFinite(min) || !Number.isFinite(max)) return `<div class="empty-state">Chart data is not numeric.</div>`;
          if (min === max) {
            const padding = Math.abs(max || 1) * 0.05;
            min -= padding;
            max += padding;
          } else {
            const padding = (max - min) * 0.08;
            min -= padding;
            max += padding;
          }
          if (rawMin >= 0) min = Math.max(0, min);
          const height = 320;
          const left = 76;
          const right = 28;
          const top = 24;
          const bottom = 48;
          const step = series.length > 1 ? Math.max(7, Math.min(18, 1600 / series.length)) : 12;
          const width = Math.max(900, Math.min(5200, left + right + Math.max(1, series.length - 1) * step));
          const plotWidth = width - left - right;
          const plotHeight = height - top - bottom;
          const unit = series[selectedIndex]?.record?.units?.[metricKey] || "";
          const xFor = (index) => left + (series.length <= 1 ? plotWidth / 2 : (index / (series.length - 1)) * plotWidth);
          const yFor = (value) => top + ((max - value) / (max - min)) * plotHeight;
          const path = series.map((point, index) => `${index === 0 ? "M" : "L"}${xFor(index).toFixed(2)},${yFor(point.value).toFixed(2)}`).join(" ");
          const area = `${path} L${xFor(series.length - 1).toFixed(2)},${(top + plotHeight).toFixed(2)} L${xFor(0).toFixed(2)},${(top + plotHeight).toFixed(2)} Z`;
          const yTicks = Array.from({length: 5}, (_, index) => min + ((max - min) * index) / 4).reverse();
          const xTickIndexes = Array.from(new Set(Array.from({length: Math.min(6, series.length)}, (_, index) => (
            Math.round((index * (series.length - 1)) / Math.max(1, Math.min(6, series.length) - 1))
          ))));
          const visibleEvery = Math.max(1, Math.ceil(series.length / 120));
          const selectedPoint = series[selectedIndex];
          const selectedX = xFor(selectedIndex);
          const selectedY = yFor(selectedPoint.value);
          return `
            <svg class="onchain-chart-svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}" role="img" aria-label="${escapeHtml(metricLabel(metricKey))} chart">
              <defs>
                <linearGradient id="onchain-area-gradient" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stop-color="#ffd438" stop-opacity="0.28"></stop>
                  <stop offset="100%" stop-color="#ffd438" stop-opacity="0"></stop>
                </linearGradient>
              </defs>
              <rect x="0" y="0" width="${width}" height="${height}" fill="transparent"></rect>
              ${yTicks.map((tick) => {
                const y = yFor(tick);
                return `<g class="onchain-chart-grid"><line x1="${left}" x2="${width - right}" y1="${y.toFixed(2)}" y2="${y.toFixed(2)}"></line><text x="${left - 10}" y="${(y + 4).toFixed(2)}">${escapeHtml(formatChartAxisValue(tick, metricKey, unit))}</text></g>`;
              }).join("")}
              ${xTickIndexes.map((index) => {
                const point = series[index];
                const x = xFor(index);
                return `<g class="onchain-chart-x-tick"><line x1="${x.toFixed(2)}" x2="${x.toFixed(2)}" y1="${top}" y2="${top + plotHeight}"></line><text x="${x.toFixed(2)}" y="${height - 14}">${escapeHtml(shortTime(point.time))}</text></g>`;
              }).join("")}
              <path class="onchain-chart-area" d="${area}"></path>
              <path class="onchain-chart-line" d="${path}"></path>
              <line class="onchain-chart-selected-line" x1="${selectedX.toFixed(2)}" x2="${selectedX.toFixed(2)}" y1="${top}" y2="${top + plotHeight}"></line>
              ${series.map((point, index) => {
                const x = xFor(index);
                const y = yFor(point.value);
                const selected = index === selectedIndex;
                const visible = selected || index % visibleEvery === 0;
                const valueLabel = formatChartAxisValue(point.value, metricKey, unit);
                const tooltipLines = chartPointTooltipLines(point, metricKey, unit);
                const ariaLabel = tooltipLines.join(", ");
                return `
                  <g class="onchain-chart-point" data-onchain-point-index="${index}" aria-label="${escapeHtml(ariaLabel)}">
                    ${visible ? `<circle class="onchain-chart-dot ${selected ? "selected" : ""}" cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="${selected ? 4.5 : 2.2}"></circle>` : ""}
                    <circle class="onchain-chart-hit" cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="10">
                      <title>${escapeHtml(ariaLabel)}</title>
                    </circle>
                    ${renderChartPointHoverLayer({
                      x,
                      y,
                      left,
                      right,
                      top,
                      width,
                      height,
                      plotHeight,
                      valueLabel,
                      lines: tooltipLines,
                    })}
                  </g>`;
              }).join("")}
              <circle class="onchain-chart-dot selected" cx="${selectedX.toFixed(2)}" cy="${selectedY.toFixed(2)}" r="5.5" data-onchain-selected-point></circle>
            </svg>`;
        }

        function chartPointTooltipLines(point, metricKey, unit) {
          const record = point?.record || {};
          const lines = [
            formatTimestamp(point?.time),
            `${metricLabel(metricKey)}: ${formatMetricValue(point?.value, metricKey, unit)}`,
          ];
          const identity = record?.symbol || record?.asset || record?.chain || record?.source;
          if (identity) lines.push(String(identity));
          const dataClass = record?.data_class || record?.category || record?.endpoint;
          if (dataClass) lines.push(label(dataClass));
          return lines.slice(0, 4);
        }

        function renderChartPointHoverLayer({x, y, left, right, top, width, height, plotHeight, valueLabel, lines}) {
          const tooltipWidth = 236;
          const lineHeight = 16;
          const tooltipHeight = 18 + Math.max(1, lines.length) * lineHeight;
          const xText = x < width - right - tooltipWidth - 18 ? x + 14 : x - tooltipWidth - 14;
          const tooltipX = Math.max(left + 8, Math.min(width - right - tooltipWidth - 8, xText));
          const tooltipY = Math.max(top + 8, Math.min(height - tooltipHeight - 12, y - tooltipHeight - 12));
          return `
            <g class="onchain-chart-hover-layer">
              <line class="onchain-chart-hover-line vertical" x1="${x.toFixed(2)}" x2="${x.toFixed(2)}" y1="${top}" y2="${top + plotHeight}"></line>
              <line class="onchain-chart-hover-line horizontal" x1="${left}" x2="${width - right}" y1="${y.toFixed(2)}" y2="${y.toFixed(2)}"></line>
              <rect class="onchain-chart-axis-pill" x="6" y="${(y - 12).toFixed(2)}" width="${Math.max(54, left - 14)}" height="24" rx="6"></rect>
              <text class="onchain-chart-axis-label" x="${left - 14}" y="${(y + 4).toFixed(2)}">${escapeHtml(valueLabel)}</text>
              <rect class="onchain-chart-tooltip-box" x="${tooltipX.toFixed(2)}" y="${tooltipY.toFixed(2)}" width="${tooltipWidth}" height="${tooltipHeight}" rx="8"></rect>
              ${lines.map((line, index) => `
                <text class="onchain-chart-tooltip-text ${index === 0 ? "primary" : ""}" x="${(tooltipX + 12).toFixed(2)}" y="${(tooltipY + 19 + index * lineHeight).toFixed(2)}">${escapeHtml(line)}</text>
              `).join("")}
            </g>`;
        }

        function renderOnchainSelectedPoint(point, payload) {
          if (!point) return `<section class="onchain-selected-card"><div class="empty-state">Select a chart point to inspect its observation.</div></section>`;
          const record = point.record || {};
          const metrics = recordMetricFacts(record);
          const facts = recordPrimaryFacts(record, "onchain_flow");
          return `
            <section class="onchain-selected-card">
              <div class="intel-preview-main-head">
                <div class="intel-preview-title-stack">
                  <div class="muted">${escapeHtml(formatTimestamp(point.time))}</div>
                  <h2>${escapeHtml(recordTitle(record, "onchain_flow"))}</h2>
                </div>
                <button class="ghost-button compact-button intel-properties-trigger" type="button" id="intel-properties-button" title="Open properties for this observation">Properties</button>
              </div>
              ${metrics.length ? `<section class="intel-record-section"><h3>Observation metrics</h3><div class="intel-metric-grid">${metrics.map(([key, val, unit]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(formatMetricValue(val, key, unit))}</strong>${unit ? `<small>${escapeHtml(unit)}</small>` : ""}</div>`).join("")}</div></section>` : ""}
              ${facts.length ? `<section class="intel-record-section"><h3>Record context</h3><div class="intel-fact-grid">${facts.map(([key, val]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(text(val))}</strong></div>`).join("")}</div></section>` : ""}
            </section>`;
        }

        function renderDerivativesMarketPreview(selector, payload, records) {
          const groups = derivativesMarketGroups(records);
          syncIntelligencePreviewFilterControls([], records.length, records.length);
          if (!groups.length) {
            updateIntelligencePropertiesSelection(null, payload);
            setHtml(selector, `
              <div class="derivatives-market-preview empty">
                <div class="empty-state">No derivatives market records are available for the current preview window.</div>
              </div>`);
            return;
          }
          if (!groups.some((group) => group.key === state.derivativesDataClass)) {
            state.derivativesDataClass = groups[0].key;
            state.derivativesMetricKey = "";
            state.derivativesSelectedIndex = null;
          }
          const group = groups.find((item) => item.key === state.derivativesDataClass) || groups[0];
          const metricKeys = numericMetricKeys(group.records);
          if (!metricKeys.length) {
            updateIntelligencePropertiesSelection(group.records[0] || null, payload);
            setHtml(selector, `
              <div class="derivatives-market-preview">
                ${renderDerivativesMarketTabs(groups, group.key)}
                <div class="empty-state">This derivatives class does not expose numeric metrics that can be charted.</div>
              </div>`);
            wireDerivativesMarketPreview(selector, payload, records, groups, [], []);
            return;
          }
          if (!metricKeys.includes(state.derivativesMetricKey)) {
            state.derivativesMetricKey = derivativesDefaultMetric(group.key, metricKeys);
            state.derivativesSelectedIndex = null;
          }
          const series = metricSeries(group.records, state.derivativesMetricKey, "derivatives_market");
          if (!series.length) {
            updateIntelligencePropertiesSelection(group.records[0] || null, payload);
            setHtml(selector, `
              <div class="derivatives-market-preview">
                ${renderDerivativesMarketTabs(groups, group.key)}
                ${renderDerivativesMetricTabs(metricKeys, state.derivativesMetricKey, group.records)}
                <div class="empty-state">No numeric observations matched the selected derivatives metric.</div>
              </div>`);
            wireDerivativesMarketPreview(selector, payload, records, groups, metricKeys, series);
            return;
          }
          const selectedIndex = ensureMetricSelectedIndex("derivativesSelectedIndex", series);
          const selectedPoint = series[selectedIndex] || series[series.length - 1];
          updateIntelligencePropertiesSelection(selectedPoint?.record || null, payload);
          setHtml(selector, `
            <div class="derivatives-market-preview">
              ${renderDerivativesMarketTabs(groups, group.key)}
              <section class="derivatives-board-card">
                <div class="derivatives-board-top">
                  <div class="onchain-title-stack">
                    <span>${escapeHtml(group.label)}</span>
                    <strong>${escapeHtml(metricLabel(state.derivativesMetricKey))}</strong>
                    <small>${escapeHtml(formatNumber(series.length))} loaded observations / ${escapeHtml(onchainRangeLabel(series))}</small>
                  </div>
                  <div class="derivatives-context-strip">
                    ${derivativesContextChip("Symbol", selectedPoint?.record?.symbol || group.symbols.join(", "))}
                    ${derivativesContextChip("Market", selectedPoint?.record?.market_type || "futures")}
                    ${derivativesContextChip("Period", selectedPoint?.record?.period || "snapshot")}
                  </div>
                </div>
                ${renderDerivativesMetricTabs(metricKeys, state.derivativesMetricKey, group.records)}
                ${renderDerivativesMetricSummary(series, selectedPoint, state.derivativesMetricKey)}
                <div class="onchain-chart-frame derivatives-chart-frame">
                  <div class="onchain-chart-scroll derivatives-chart-scroll" aria-label="${escapeHtml(group.label)} ${escapeHtml(metricLabel(state.derivativesMetricKey))} time series">
                    ${renderOnchainChart(series, state.derivativesMetricKey, selectedIndex)}
                  </div>
                </div>
                <div class="onchain-chart-foot">
                  <span>Drag horizontally to inspect snapshots and interval records.</span>
                  <span>Use metric tabs to switch OI, funding, basis, premium, spread, or depth measures.</span>
                </div>
              </section>
              ${renderDerivativesSelectedPoint(selectedPoint, payload)}
            </div>`);
          wireDerivativesMarketPreview(selector, payload, records, groups, metricKeys, series);
        }

        function derivativesMarketGroups(records) {
          const groups = new Map();
          (Array.isArray(records) ? records : []).forEach((record) => {
            if (!record || typeof record !== "object") return;
            const key = recordCategory(record, "derivatives_market");
            if (!groups.has(key)) {
              groups.set(key, {key, label: categoryLabel(key), records: [], latestTime: 0, symbols: new Set()});
            }
            const group = groups.get(key);
            group.records.push(record);
            if (record?.symbol) group.symbols.add(String(record.symbol));
            const timestamp = Date.parse(recordTime(record, "derivatives_market"));
            if (Number.isFinite(timestamp)) group.latestTime = Math.max(group.latestTime, timestamp);
          });
          return Array.from(groups.values())
            .map((group) => ({
              ...group,
              symbols: Array.from(group.symbols).sort(),
              metrics: numericMetricKeys(group.records),
              count: group.records.length,
            }))
            .filter((group) => group.count > 0)
            .sort((left, right) => {
              if (right.latestTime !== left.latestTime) return right.latestTime - left.latestTime;
              return left.label.localeCompare(right.label);
            });
        }

        function renderDerivativesMarketTabs(groups, selectedKey) {
          return `
            <div class="onchain-subtabs derivatives-subtabs" role="tablist" aria-label="Derivatives data classes">
              ${groups.map((group) => `
                <button class="tab-button ${group.key === selectedKey ? "active" : ""}" type="button" role="tab" aria-selected="${group.key === selectedKey ? "true" : "false"}" data-derivatives-class="${escapeHtml(group.key)}">
                  <span>${escapeHtml(group.label)}</span>
                  <small>${escapeHtml(formatNumber(group.count))}</small>
                </button>
              `).join("")}
            </div>`;
        }

        function renderDerivativesMetricTabs(metricKeys, selectedMetric, records) {
          return `
            <div class="onchain-metric-tabs derivatives-metric-tabs" role="tablist" aria-label="Derivatives metrics">
              ${metricKeys.map((key) => {
                const count = metricSeries(records, key, "derivatives_market").length;
                return `
                  <button class="ghost-button compact-button ${key === selectedMetric ? "active" : ""}" type="button" role="tab" aria-selected="${key === selectedMetric ? "true" : "false"}" data-derivatives-metric="${escapeHtml(key)}">
                    ${escapeHtml(metricLabel(key))}
                    <span>${escapeHtml(formatNumber(count))}</span>
                  </button>`;
              }).join("")}
            </div>`;
        }

        function renderDerivativesMetricSummary(series, selectedPoint, metricKey) {
          const values = series.map((point) => point.value);
          const latest = series[series.length - 1];
          const previous = series.length > 1 ? series[series.length - 2] : null;
          const change = previous ? latest.value - previous.value : null;
          const min = Math.min(...values);
          const max = Math.max(...values);
          const unit = selectedPoint?.record?.units?.[metricKey] || latest?.record?.units?.[metricKey] || "";
          return `
            <div class="derivatives-summary-grid">
              ${onchainMetricCard("Selected", selectedPoint?.value, metricKey, unit, formatTimestamp(selectedPoint?.time))}
              ${onchainMetricCard("Latest", latest?.value, metricKey, unit, formatTimestamp(latest?.time))}
              ${onchainMetricCard("Range low", min, metricKey, unit, "loaded range")}
              ${onchainMetricCard("Last step", change, metricKey, unit, previous ? "latest minus previous" : "n/a")}
            </div>`;
        }

        function renderDerivativesSelectedPoint(point, payload) {
          if (!point) return `<section class="derivatives-selected-card"><div class="empty-state">Select a chart point to inspect its derivatives snapshot.</div></section>`;
          const record = point.record || {};
          const metrics = recordMetricFacts(record);
          const facts = recordPrimaryFacts(record, "derivatives_market");
          return `
            <section class="derivatives-selected-card">
              <div class="intel-preview-main-head">
                <div class="intel-preview-title-stack">
                  <div class="muted">${escapeHtml(formatTimestamp(point.time))}</div>
                  <h2>${escapeHtml(recordTitle(record, "derivatives_market"))}</h2>
                </div>
                <button class="ghost-button compact-button intel-properties-trigger" type="button" id="intel-properties-button" title="Open properties for this derivatives record">Properties</button>
              </div>
              ${renderDerivativesPressure(record)}
              ${metrics.length ? `<section class="intel-record-section"><h3>Market metrics</h3><div class="intel-metric-grid">${metrics.map(([key, val, unit]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(formatMetricValue(val, key, unit))}</strong>${unit ? `<small>${escapeHtml(unit)}</small>` : ""}</div>`).join("")}</div></section>` : ""}
              ${facts.length ? `<section class="intel-record-section"><h3>Record context</h3><div class="intel-fact-grid">${facts.map(([key, val]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(text(val))}</strong></div>`).join("")}</div></section>` : ""}
            </section>`;
        }

        function renderDerivativesPressure(record) {
          const metrics = record?.metrics || {};
          const bid = Number(metrics.bid_depth_notional ?? metrics.bid_depth_quantity);
          const ask = Number(metrics.ask_depth_notional ?? metrics.ask_depth_quantity);
          const hasDepth = Number.isFinite(bid) && Number.isFinite(ask) && bid + ask > 0;
          const basis = Number(metrics.basis_rate ?? metrics.premium_rate ?? metrics.funding_rate ?? metrics.last_funding_rate);
          if (!hasDepth && !Number.isFinite(basis)) return "";
          const bidShare = hasDepth ? Math.max(0, Math.min(100, (bid / (bid + ask)) * 100)) : 50;
          const askShare = hasDepth ? 100 - bidShare : 50;
          const tone = Number.isFinite(basis) ? (basis > 0 ? "positive" : basis < 0 ? "negative" : "neutral") : "neutral";
          return `
            <section class="derivatives-pressure-panel ${escapeHtml(tone)}">
              <div>
                <span>Book pressure</span>
                <strong>${hasDepth ? `${bidShare.toFixed(1)}% bid / ${askShare.toFixed(1)}% ask` : "n/a"}</strong>
              </div>
              ${hasDepth ? `<div class="depth-balance" aria-label="Bid and ask depth balance"><span class="bid" style="width:${bidShare.toFixed(2)}%"></span><span class="ask" style="width:${askShare.toFixed(2)}%"></span></div>` : ""}
              <div>
                <span>Carry / premium signal</span>
                <strong>${Number.isFinite(basis) ? formatMetricValue(basis, "rate", "ratio") : "n/a"}</strong>
              </div>
            </section>`;
        }

        function wireDerivativesMarketPreview(selector, payload, records, groups, metricKeys, series) {
          const root = node(selector);
          wireOnchainScrollableTabs(root);
          root?.querySelectorAll("[data-derivatives-class]").forEach((button) => {
            button.addEventListener("click", () => {
              state.derivativesDataClass = button.dataset.derivativesClass || "";
              state.derivativesMetricKey = "";
              state.derivativesSelectedIndex = null;
              renderDerivativesMarketPreview(selector, payload, records);
            });
          });
          root?.querySelectorAll("[data-derivatives-metric]").forEach((button) => {
            button.addEventListener("click", () => {
              state.derivativesMetricKey = button.dataset.derivativesMetric || "";
              state.derivativesSelectedIndex = null;
              renderDerivativesMarketPreview(selector, payload, records);
            });
          });
          root?.querySelectorAll("[data-onchain-point-index]").forEach((point) => {
            point.addEventListener("click", () => {
              state.derivativesSelectedIndex = Number(point.dataset.onchainPointIndex) || 0;
              renderDerivativesMarketPreview(selector, payload, records);
            });
          });
          wireOnchainChartDragScroll(root);
          window.requestAnimationFrame(() => {
            root?.querySelector("[data-onchain-selected-point]")?.scrollIntoView({block: "nearest", inline: "center"});
          });
        }

        function renderMarketAnomalyPreview(selector, payload, records) {
          const anomalies = marketAnomalyRecords(records);
          syncIntelligencePreviewFilterControls([], anomalies.length, records.length);
          if (!anomalies.length) {
            updateIntelligencePropertiesSelection(null, payload);
            setHtml(selector, `
              <div class="market-anomaly-preview empty">
                <div class="empty-state">No market anomaly records are available for the current preview window.</div>
              </div>`);
            return;
          }
          const filtered = anomalies.filter((record) => {
            const severity = String(state.anomalySeverityFilter || "");
            const sourceKind = String(state.anomalySourceKindFilter || "");
            if (severity && String(record?.severity || "unknown") !== severity) return false;
            if (sourceKind && String(record?.source_kind || "unknown") !== sourceKind) return false;
            return true;
          });
          const selectedList = filtered.length ? filtered : anomalies;
          const selectedIndex = ensureAnomalySelectedIndex(selectedList);
          const selected = selectedList[selectedIndex] || selectedList[0];
          updateIntelligencePropertiesSelection(selected || null, payload);
          setHtml(selector, `
            <div class="market-anomaly-preview">
              <section class="anomaly-radar-header">
                <div class="onchain-title-stack">
                  <span>Market anomaly radar</span>
                  <strong>${escapeHtml(formatNumber(filtered.length || anomalies.length))} active signals</strong>
                  <small>${escapeHtml(anomalyRangeLabel(anomalies))}</small>
                </div>
                ${renderAnomalySeverityTabs(anomalies)}
                ${renderAnomalySourceKindTabs(anomalies)}
              </section>
              ${renderAnomalyStats(anomalies)}
              <div class="anomaly-radar-layout">
                <aside class="anomaly-leaderboard">
                  <div class="intel-list-toolbar"><strong>Ranked signals</strong><span>${escapeHtml(formatNumber(selectedList.length))}</span></div>
                  <div class="anomaly-list">${selectedList.slice(0, 80).map((record, index) => renderAnomalyRow(record, index, selectedIndex)).join("")}</div>
                </aside>
                <article class="anomaly-radar-main">
                  ${renderAnomalyHeatmap(selectedList, selectedIndex)}
                  ${renderAnomalyDetail(selected, payload)}
                </article>
              </div>
            </div>`);
          wireMarketAnomalyPreview(selector, payload, records);
        }

        function marketAnomalyRecords(records) {
          return (Array.isArray(records) ? records : []).slice().sort((left, right) => {
            const severityDelta = severityScore(right?.severity) - severityScore(left?.severity);
            if (severityDelta) return severityDelta;
            const valueDelta = anomalyMagnitude(right) - anomalyMagnitude(left);
            if (valueDelta) return valueDelta;
            const rightTime = Date.parse(recordTime(right, "market_anomaly"));
            const leftTime = Date.parse(recordTime(left, "market_anomaly"));
            return (Number.isFinite(rightTime) ? rightTime : 0) - (Number.isFinite(leftTime) ? leftTime : 0);
          });
        }

        function renderAnomalyStats(records) {
          const severities = countBy(records, (record) => String(record?.severity || "unknown"));
          const symbols = new Set(records.map((record) => record?.symbol).filter(Boolean));
          const highCount = (severities.get("high") || 0) + (severities.get("critical") || 0);
          const top = records[0];
          return `
            <div class="anomaly-stat-grid">
              ${anomalyStatCard("High severity", highCount, "needs review")}
              ${anomalyStatCard("Symbols", symbols.size, "affected markets")}
              ${anomalyStatCard("Top signal", top ? `${text(top.symbol, "n/a")} ${formatAnomalyMagnitude(top)}` : "n/a", top ? categoryLabel(recordCategory(top, "market_anomaly")) : "none")}
              ${anomalyStatCard("Sources", countBy(records, (record) => record?.source_kind || record?.source || "unknown").size, "dedupe-aware")}
            </div>`;
        }

        function anomalyStatCard(title, value, note) {
          return `
            <div class="anomaly-stat-card">
              <span>${escapeHtml(title)}</span>
              <strong>${escapeHtml(text(value))}</strong>
              <small>${escapeHtml(note || "")}</small>
            </div>`;
        }

        function renderAnomalySeverityTabs(records) {
          const counts = countBy(records, (record) => String(record?.severity || "unknown"));
          const severities = ["", "critical", "high", "medium", "low", "unknown"].filter((severity) => severity === "" || counts.has(severity));
          return `
            <div class="anomaly-filter-tabs" role="tablist" aria-label="Anomaly severity filter">
              ${severities.map((severity) => {
                const active = String(state.anomalySeverityFilter || "") === severity;
                const labelText = severity ? label(severity) : "All";
                const count = severity ? counts.get(severity) || 0 : records.length;
                return `<button class="ghost-button compact-button ${active ? "active" : ""}" type="button" data-anomaly-severity="${escapeHtml(severity)}">${escapeHtml(labelText)} <span>${escapeHtml(formatNumber(count))}</span></button>`;
              }).join("")}
            </div>`;
        }

        function renderAnomalySourceKindTabs(records) {
          const counts = countBy(records, (record) => String(record?.source_kind || "unknown"));
          if (counts.size <= 1) return "";
          const entries = [["", records.length], ...Array.from(counts.entries()).sort(([left], [right]) => label(left).localeCompare(label(right)))];
          return `
            <div class="anomaly-source-tabs" role="tablist" aria-label="Anomaly source filter">
              ${entries.map(([sourceKind, count]) => {
                const active = String(state.anomalySourceKindFilter || "") === sourceKind;
                return `<button class="ghost-button compact-button ${active ? "active" : ""}" type="button" data-anomaly-source-kind="${escapeHtml(sourceKind)}">${escapeHtml(sourceKind ? label(sourceKind) : "All sources")} <span>${escapeHtml(formatNumber(count))}</span></button>`;
              }).join("")}
            </div>`;
        }

        function renderAnomalyRow(record, index, selectedIndex) {
          const severity = String(record?.severity || "unknown");
          return `
            <button class="anomaly-row ${index === selectedIndex ? "active" : ""} severity-${escapeHtml(severity)}" type="button" data-anomaly-index="${index}">
              <span class="anomaly-row-rank">${escapeHtml(String(index + 1).padStart(2, "0"))}</span>
              <span class="anomaly-row-main">
                <strong>${escapeHtml(recordTitle(record, "market_anomaly"))}</strong>
                <small>${escapeHtml(formatTimestamp(recordTime(record, "market_anomaly")))} / ${escapeHtml(record?.source || "source")}</small>
              </span>
              <span class="anomaly-row-score">${escapeHtml(formatAnomalyMagnitude(record))}</span>
            </button>`;
        }

        function renderAnomalyHeatmap(records, selectedIndex) {
          const top = records.slice(0, 36);
          if (!top.length) return `<section class="anomaly-heatmap-card"><div class="empty-state">No signals matched the current radar filters.</div></section>`;
          return `
            <section class="anomaly-heatmap-card">
              <div class="anomaly-section-head">
                <div>
                  <strong>Signal heatmap</strong>
                  <span>Ranked by severity and observed magnitude.</span>
                </div>
              </div>
              <div class="anomaly-heatmap">
                ${top.map((record, index) => `
                  <button class="anomaly-heatmap-tile severity-${escapeHtml(record?.severity || "unknown")} ${index === selectedIndex ? "active" : ""}" type="button" data-anomaly-index="${index}">
                    <strong>${escapeHtml(record?.symbol || "n/a")}</strong>
                    <span>${escapeHtml(formatAnomalyMagnitude(record))}</span>
                    <small>${escapeHtml(label(record?.timeframe || record?.data_class || "signal"))}</small>
                  </button>
                `).join("")}
              </div>
            </section>`;
        }

        function renderAnomalyDetail(record, payload) {
          if (!record) return `<section class="anomaly-detail-card"><div class="empty-state">Select an anomaly signal to inspect details.</div></section>`;
          const metrics = recordMetricFacts(record);
          const facts = recordPrimaryFacts(record, "market_anomaly");
          const severity = String(record?.severity || "unknown");
          return `
            <section class="anomaly-detail-card severity-${escapeHtml(severity)}">
              <div class="intel-preview-main-head">
                <div class="intel-preview-title-stack">
                  <div class="muted">${escapeHtml(formatTimestamp(recordTime(record, "market_anomaly")))}</div>
                  <h2>${escapeHtml(recordTitle(record, "market_anomaly"))}</h2>
                </div>
                <button class="ghost-button compact-button intel-properties-trigger" type="button" id="intel-properties-button" title="Open properties for this anomaly">Properties</button>
              </div>
              <div class="anomaly-detail-banner">
                <span class="status-pill ${escapeHtml(anomalySeverityStatus(severity))}">${escapeHtml(label(severity))}</span>
                <span>${escapeHtml(label(record?.direction || "unknown"))}</span>
                <strong>${escapeHtml(formatAnomalyMagnitude(record))}</strong>
              </div>
              <p>${escapeHtml(recordSummary(record, "market_anomaly") || "No anomaly summary is recorded for this signal.")}</p>
              ${metrics.length ? `<section class="intel-record-section"><h3>Signal metrics</h3><div class="intel-metric-grid">${metrics.map(([key, val, unit]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(formatMetricValue(val, key, unit))}</strong>${unit ? `<small>${escapeHtml(unit)}</small>` : ""}</div>`).join("")}</div></section>` : ""}
              ${facts.length ? `<section class="intel-record-section"><h3>Signal context</h3><div class="intel-fact-grid">${facts.map(([key, val]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(text(val))}</strong></div>`).join("")}</div></section>` : ""}
            </section>`;
        }

        function wireMarketAnomalyPreview(selector, payload, records) {
          const root = node(selector);
          root?.querySelectorAll("[data-anomaly-severity]").forEach((button) => {
            button.addEventListener("click", () => {
              state.anomalySeverityFilter = button.dataset.anomalySeverity || "";
              state.anomalySelectedIndex = null;
              renderMarketAnomalyPreview(selector, payload, records);
            });
          });
          root?.querySelectorAll("[data-anomaly-source-kind]").forEach((button) => {
            button.addEventListener("click", () => {
              state.anomalySourceKindFilter = button.dataset.anomalySourceKind || "";
              state.anomalySelectedIndex = null;
              renderMarketAnomalyPreview(selector, payload, records);
            });
          });
          root?.querySelectorAll("[data-anomaly-index]").forEach((button) => {
            button.addEventListener("click", () => {
              state.anomalySelectedIndex = Number(button.dataset.anomalyIndex) || 0;
              renderMarketAnomalyPreview(selector, payload, records);
            });
          });
        }

        function numericMetricKeys(records) {
          const keys = [];
          const seen = new Set();
          (Array.isArray(records) ? records : []).forEach((record) => {
            const metrics = record?.metrics && typeof record.metrics === "object" ? record.metrics : {};
            Object.entries(metrics).forEach(([key, value]) => {
              const numeric = Number(value);
              if (!Number.isFinite(numeric) || seen.has(key)) return;
              seen.add(key);
              keys.push(key);
            });
          });
          return keys;
        }

        function metricSeries(records, metricKey, dataType) {
          return (Array.isArray(records) ? records : [])
            .map((record) => {
              const timestamp = Date.parse(recordTime(record, dataType));
              const value = Number(record?.metrics?.[metricKey]);
              return {record, time: recordTime(record, dataType), timestamp, value};
            })
            .filter((point) => Number.isFinite(point.timestamp) && Number.isFinite(point.value))
            .sort((left, right) => {
              if (left.timestamp !== right.timestamp) return left.timestamp - right.timestamp;
              return left.value - right.value;
            });
        }

        function ensureMetricSelectedIndex(stateKey, series) {
          if (state[stateKey] === null || state[stateKey] === undefined || state[stateKey] === "") {
            state[stateKey] = Math.max(0, series.length - 1);
            return state[stateKey];
          }
          const requested = Number(state[stateKey]);
          if (Number.isInteger(requested) && requested >= 0 && requested < series.length) return requested;
          state[stateKey] = Math.max(0, series.length - 1);
          return state[stateKey];
        }

        function ensureAnomalySelectedIndex(records) {
          const length = Array.isArray(records) ? records.length : 0;
          if (!length) return 0;
          const requested = Number(state.anomalySelectedIndex);
          if (Number.isInteger(requested) && requested >= 0 && requested < length) return requested;
          state.anomalySelectedIndex = 0;
          return 0;
        }

        function derivativesDefaultMetric(groupKey, metricKeys) {
          const preferred = {
            funding_rate: ["funding_rate", "last_funding_rate"],
            premium_index: ["premium_rate", "last_funding_rate", "mark_price"],
            basis: ["basis_rate", "basis", "futures_price"],
            open_interest: ["open_interest_value", "open_interest_contracts"],
            spread_depth: ["spread_bps", "depth_imbalance", "bid_depth_notional"],
          }[groupKey] || [];
          return preferred.find((key) => metricKeys.includes(key)) || metricKeys[0];
        }

        function derivativesContextChip(title, value) {
          return `
            <span class="derivatives-context-chip">
              <small>${escapeHtml(title)}</small>
              <strong>${escapeHtml(text(value, "n/a"))}</strong>
            </span>`;
        }

        function countBy(records, getter) {
          const counts = new Map();
          (Array.isArray(records) ? records : []).forEach((record) => {
            const key = String(getter(record) || "unknown");
            counts.set(key, (counts.get(key) || 0) + 1);
          });
          return counts;
        }

        function severityScore(severity) {
          const normalized = String(severity || "").toLowerCase();
          if (normalized === "critical") return 4;
          if (normalized === "high") return 3;
          if (normalized === "medium") return 2;
          if (normalized === "low") return 1;
          return 0;
        }

        function anomalyMagnitude(record) {
          const direct = Number(record?.value);
          if (Number.isFinite(direct)) return Math.abs(direct);
          const metricKey = record?.metric;
          const metricValue = metricKey ? Number(record?.metrics?.[metricKey]) : Number.NaN;
          if (Number.isFinite(metricValue)) return Math.abs(metricValue);
          const metrics = Object.values(record?.metrics || {}).map((value) => Number(value)).filter(Number.isFinite);
          return metrics.length ? Math.max(...metrics.map(Math.abs)) : 0;
        }

        function formatAnomalyMagnitude(record) {
          const key = record?.metric || Object.keys(record?.metrics || {}).find((metricKey) => metricKey.includes("multiplier")) || record?.data_class || "value";
          const value = record?.value ?? record?.metrics?.[key] ?? anomalyMagnitude(record);
          const unit = record?.unit || record?.units?.[key] || "";
          return formatMetricValue(value, key, unit);
        }

        function anomalyRangeLabel(records) {
          if (!records.length) return "no range";
          const sorted = records.slice().sort((left, right) => {
            const leftTime = Date.parse(recordTime(left, "market_anomaly"));
            const rightTime = Date.parse(recordTime(right, "market_anomaly"));
            return (Number.isFinite(leftTime) ? leftTime : 0) - (Number.isFinite(rightTime) ? rightTime : 0);
          });
          return `${formatTimestamp(recordTime(sorted[0], "market_anomaly"))} to ${formatTimestamp(recordTime(sorted[sorted.length - 1], "market_anomaly"))}`;
        }

        function anomalySeverityStatus(severity) {
          const normalized = String(severity || "").toLowerCase();
          if (normalized === "critical" || normalized === "high") return "failed";
          if (normalized === "medium") return "warning";
          if (normalized === "low") return "collected";
          return "unknown";
        }

        function wireOnchainFlowPreview(selector, payload, records, groups, metricKeys, series) {
          const root = node(selector);
          wireOnchainScrollableTabs(root);
          root?.querySelectorAll("[data-onchain-class]").forEach((button) => {
            button.addEventListener("click", () => {
              state.onchainDataClass = button.dataset.onchainClass || "";
              state.onchainMetricKey = "";
              state.onchainSelectedIndex = null;
              renderOnchainFlowPreview(selector, payload, records);
            });
          });
          root?.querySelectorAll("[data-onchain-metric]").forEach((button) => {
            button.addEventListener("click", () => {
              state.onchainMetricKey = button.dataset.onchainMetric || "";
              state.onchainSelectedIndex = null;
              renderOnchainFlowPreview(selector, payload, records);
            });
          });
          root?.querySelectorAll("[data-onchain-point-index]").forEach((point) => {
            point.addEventListener("click", () => {
              state.onchainSelectedIndex = Number(point.dataset.onchainPointIndex) || 0;
              renderOnchainFlowPreview(selector, payload, records);
            });
          });
          const jump = () => {
            const raw = String(root?.querySelector("#onchain-date-jump")?.value || "");
            const target = parseDatetimeLocalUtc(raw);
            if (!Number.isFinite(target) || !series.length) return;
            state.onchainSelectedIndex = nearestOnchainPointIndex(series, target);
            renderOnchainFlowPreview(selector, payload, records);
          };
          root?.querySelector("[data-onchain-jump]")?.addEventListener("click", jump);
          root?.querySelector("#onchain-date-jump")?.addEventListener("keydown", (event) => {
            if (event.key === "Enter") jump();
          });
          wireOnchainChartDragScroll(root);
          window.requestAnimationFrame(() => {
            root?.querySelector("[data-onchain-selected-point]")?.scrollIntoView({block: "nearest", inline: "center"});
          });
        }

        function wireOnchainChartDragScroll(root) {
          root?.querySelectorAll(".onchain-chart-scroll").forEach((scroller) => {
            wireHorizontalDragScroll(scroller, {ignoreSelector: "[data-onchain-point-index]"});
          });
        }

        function wireOnchainScrollableTabs(root) {
          root?.querySelectorAll(".onchain-subtabs, .onchain-metric-tabs").forEach((scroller) => {
            wireHorizontalDragScroll(scroller, {suppressClickAfterDrag: true});
          });
        }

        function wireHorizontalDragScroll(scroller, options = {}) {
          if (!scroller || scroller.dataset.dragScrollWired === "true") return;
          scroller.dataset.dragScrollWired = "true";
          let dragging = false;
          let tracking = false;
          let moved = false;
          let startX = 0;
          let startScroll = 0;
          scroller.addEventListener("pointerdown", (event) => {
            if (options.ignoreSelector && event.target.closest(options.ignoreSelector)) return;
            if (event.button !== undefined && event.button !== 0) return;
            tracking = true;
            moved = false;
            dragging = false;
            startX = event.clientX;
            startScroll = scroller.scrollLeft;
            scroller.setPointerCapture?.(event.pointerId);
          });
          scroller.addEventListener("pointermove", (event) => {
            if (!tracking) return;
            const delta = event.clientX - startX;
            if (!dragging && Math.abs(delta) > 4) {
              dragging = true;
              moved = true;
              scroller.classList.add("dragging");
            }
            if (!dragging) return;
            event.preventDefault();
            scroller.scrollLeft = startScroll - (event.clientX - startX);
          });
          scroller.addEventListener("pointerup", (event) => {
            tracking = false;
            dragging = false;
            scroller.classList.remove("dragging");
            scroller.releasePointerCapture?.(event.pointerId);
            if (options.suppressClickAfterDrag && moved) {
              scroller.dataset.suppressNextClick = "true";
              window.setTimeout(() => {
                delete scroller.dataset.suppressNextClick;
              }, 0);
            }
          });
          scroller.addEventListener("pointercancel", () => {
            tracking = false;
            dragging = false;
            scroller.classList.remove("dragging");
          });
          if (options.suppressClickAfterDrag) {
            scroller.addEventListener("click", (event) => {
              if (scroller.dataset.suppressNextClick !== "true") return;
              event.preventDefault();
              event.stopPropagation();
              delete scroller.dataset.suppressNextClick;
            }, true);
          }
        }

        function nearestOnchainPointIndex(series, targetTimestamp) {
          let bestIndex = 0;
          let bestDistance = Infinity;
          series.forEach((point, index) => {
            const distance = Math.abs(point.timestamp - targetTimestamp);
            if (distance < bestDistance) {
              bestDistance = distance;
              bestIndex = index;
            }
          });
          return bestIndex;
        }

        function parseDatetimeLocalUtc(raw) {
          if (!raw) return Number.NaN;
          const normalized = raw.length === 16 ? `${raw}:00Z` : `${raw}Z`;
          return Date.parse(normalized);
        }

        function onchainDateInputValue(isoValue) {
          const timestamp = Date.parse(isoValue);
          if (!Number.isFinite(timestamp)) return "";
          return new Date(timestamp).toISOString().slice(0, 16);
        }

        function onchainRangeLabel(series) {
          if (!series.length) return "no range";
          return `${formatTimestamp(series[0].time)} to ${formatTimestamp(series[series.length - 1].time)}`;
        }

        function metricLabel(key) {
          return label(key || "metric");
        }

        function formatChartAxisValue(value, key, unit) {
          const numeric = Number(value);
          if (!Number.isFinite(numeric)) return text(value);
          const rawKey = String(key || "").toLowerCase();
          const rawUnit = String(unit || "").toLowerCase();
          if (rawUnit === "percent") return `${numeric.toFixed(2)}%`;
          if (rawUnit === "ratio" || rawKey.includes("rate")) return `${(numeric * 100).toFixed(2)}%`;
          const absolute = Math.abs(numeric);
          const units = [
            [1_000_000_000, "B"],
            [1_000_000, "M"],
            [1_000, "K"],
          ];
          const unitScale = units.find(([scale]) => absolute >= scale);
          if (!unitScale) return numeric.toLocaleString("en-US", {maximumFractionDigits: 2});
          const [scale, suffix] = unitScale;
          return `${(numeric / scale).toLocaleString("en-US", {maximumFractionDigits: 2})}${suffix}`;
        }

        function macroCalendarRecords(records) {
          return (Array.isArray(records) ? records : []).slice().sort((left, right) => {
            const leftTime = Date.parse(recordTime(left, "macro_calendar"));
            const rightTime = Date.parse(recordTime(right, "macro_calendar"));
            const leftScore = Number.isFinite(leftTime) ? leftTime : 0;
            const rightScore = Number.isFinite(rightTime) ? rightTime : 0;
            if (rightScore !== leftScore) return rightScore - leftScore;
            return recordTitle(left, "macro_calendar").localeCompare(recordTitle(right, "macro_calendar"));
          });
        }

        function ensureMacroCalendarViewport(events) {
          const selected = events[state.selectedIntelPreviewIndex] || events[0];
          const selectedDate = recordDateKey(selected, "macro_calendar") || new Date().toISOString().slice(0, 10);
          if (!state.macroCalendarView) state.macroCalendarView = "month";
          if (!state.macroCalendarHighlightedDate) state.macroCalendarHighlightedDate = selectedDate;
          if (!state.macroCalendarMonth) state.macroCalendarMonth = state.macroCalendarHighlightedDate.slice(0, 7);
          if (!state.macroCalendarYear) state.macroCalendarYear = state.macroCalendarMonth.slice(0, 4);
        }

        function macroEventListItemsWithDates(events) {
          let currentDate = "";
          return events.map((record, index) => {
            const dateKey = recordDateKey(record, "macro_calendar");
            const heading = dateKey && dateKey !== currentDate
              ? `<div class="intel-date-heading macro-date-heading" data-intel-date-heading="${escapeHtml(dateKey)}">${escapeHtml(formatDateHeading(dateKey))}</div>`
              : "";
            if (dateKey) currentDate = dateKey;
            return `${heading}${macroEventListItem(record, index)}`;
          }).join("");
        }

        function macroEventListItem(record, index) {
          const active = index === state.selectedIntelPreviewIndex;
          const temporalState = macroCalendarTemporalState(record, "macro_calendar");
          const temporalClass = temporalState ? ` macro-event-${temporalState.key}` : "";
          return `
            <button class="intel-preview-row macro-event-row${temporalClass} ${active ? "active" : ""}" type="button" data-macro-list-index="${index}">
              <strong class="macro-event-list-title"><span>${escapeHtml(recordTitle(record, "macro_calendar"))}</span>${macroEventChips(record)}</strong>
              <span>${escapeHtml(formatTimestamp(recordTime(record, "macro_calendar")))}${temporalState ? `<em class="macro-event-state">${escapeHtml(temporalState.label)}</em>` : ""}</span>
              <small>${escapeHtml([recordSource(record), record?.event_type || record?.data_class].filter(Boolean).join(" / ") || "Macro calendar")}</small>
            </button>`;
        }

        function macroEventChips(record) {
          const chips = [
            record?.importance ? [record.importance, `importance-${macroImportanceClass(record.importance)}`] : null,
            macroRegion(record) ? [macroRegion(record), "region"] : null,
          ].filter(Boolean);
          if (!chips.length) return "";
          return `<span class="macro-event-chip-row">${chips.map(([value, className]) => `<span class="macro-event-chip ${escapeHtml(className)}">${escapeHtml(label(value))}</span>`).join("")}</span>`;
        }

        function renderMacroCalendarMain(events) {
          const byDate = macroRecordsByDate(events);
          const view = state.macroCalendarView === "year" ? "year" : "month";
          return `
            <div class="macro-calendar-shell ${escapeHtml(view)}">
              <div class="macro-calendar-toolbar">
                <div class="macro-calendar-nav">
                  ${view === "month"
                    ? `<button class="ghost-button compact-button" type="button" data-macro-month-shift="-1">Prev</button><strong>${escapeHtml(macroMonthLabel(state.macroCalendarMonth))}</strong><button class="ghost-button compact-button" type="button" data-macro-month-shift="1">Next</button>`
                    : `<button class="ghost-button compact-button" type="button" data-macro-year-shift="-1">Prev</button><strong>${escapeHtml(state.macroCalendarYear || "")}</strong><button class="ghost-button compact-button" type="button" data-macro-year-shift="1">Next</button>`}
                </div>
                <div class="segmented-control macro-calendar-mode-toggle" role="tablist" aria-label="Calendar view">
                  <button class="tab-button ${view === "month" ? "active" : ""}" type="button" data-macro-calendar-view="month">Month</button>
                  <button class="tab-button ${view === "year" ? "active" : ""}" type="button" data-macro-calendar-view="year">Year</button>
                </div>
              </div>
              ${view === "year" ? renderMacroCalendarYearView(events, byDate) : renderMacroCalendarMonthView(events, byDate)}
            </div>`;
        }

        function renderMacroCalendarMonthView(events, byDate) {
          const monthKey = state.macroCalendarMonth || new Date().toISOString().slice(0, 7);
          const [year, month] = monthKey.split("-").map((part) => Number(part));
          const first = new Date(Date.UTC(year, month - 1, 1));
          const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
          const leading = first.getUTCDay();
          const cells = [];
          for (let index = 0; index < leading; index += 1) cells.push(`<div class="macro-month-day empty" aria-hidden="true"></div>`);
          for (let day = 1; day <= daysInMonth; day += 1) {
            const dateKey = `${monthKey}-${String(day).padStart(2, "0")}`;
            cells.push(renderMacroMonthCell(dateKey, day, byDate.get(dateKey) || []));
          }
          return `
            <div class="macro-calendar-weekdays">${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => `<span>${day}</span>`).join("")}</div>
            <div class="macro-month-grid">${cells.join("")}</div>`;
        }

        function renderMacroMonthCell(dateKey, day, entries) {
          const highlighted = dateKey === state.macroCalendarHighlightedDate;
          const importance = macroHighestImportance(entries.map((entry) => entry.record));
          return `
            <div class="macro-month-day ${entries.length ? "has-events" : ""} ${highlighted ? "is-highlighted" : ""} ${escapeHtml(importance ? `importance-${macroImportanceClass(importance)}` : "")}" data-macro-date-cell="${escapeHtml(dateKey)}">
              <button class="macro-day-head" type="button" data-macro-date="${escapeHtml(dateKey)}">
                <span>${escapeHtml(String(day))}</span>
                ${entries.length ? `<small>${escapeHtml(formatNumber(entries.length))}</small>` : ""}
              </button>
              <div class="macro-day-event-stack" aria-label="${escapeHtml(`${dateKey} macro events`)}">
                ${entries.map(({record, index}) => {
                  const tooltip = macroEventTooltip(record);
                  return `
                  <button class="macro-calendar-event importance-${escapeHtml(macroImportanceClass(record?.importance))}" type="button" data-macro-event-index="${index}" title="${escapeHtml(tooltip)}" aria-label="${escapeHtml(tooltip)}">
                    <span>${escapeHtml(shortTime(recordTime(record, "macro_calendar")) || "time n/a")}</span>
                    <strong>${escapeHtml(recordTitle(record, "macro_calendar"))}</strong>
                  </button>`;
                }).join("")}
              </div>
            </div>`;
        }

        function renderMacroCalendarYearView(events, byDate) {
          const year = Number(state.macroCalendarYear) || new Date().getUTCFullYear();
          return `
            <div class="macro-year-grid">
              ${Array.from({length: 12}, (_, index) => renderMacroYearMonth(year, index, byDate)).join("")}
            </div>`;
        }

        function renderMacroYearMonth(year, monthIndex, byDate) {
          const first = new Date(Date.UTC(year, monthIndex, 1));
          const monthKey = first.toISOString().slice(0, 7);
          const daysInMonth = new Date(Date.UTC(year, monthIndex + 1, 0)).getUTCDate();
          const leading = first.getUTCDay();
          const cells = [];
          for (let index = 0; index < leading; index += 1) cells.push(`<span class="macro-year-day empty"></span>`);
          for (let day = 1; day <= daysInMonth; day += 1) {
            const dateKey = `${monthKey}-${String(day).padStart(2, "0")}`;
            const entries = byDate.get(dateKey) || [];
            const importance = macroHighestImportance(entries.map((entry) => entry.record));
            const highlighted = dateKey === state.macroCalendarHighlightedDate;
            cells.push(`
              <button class="macro-year-day ${entries.length ? "has-events" : ""} ${highlighted ? "is-highlighted" : ""} ${escapeHtml(importance ? `importance-${macroImportanceClass(importance)}` : "")}" type="button" data-macro-year-date="${escapeHtml(dateKey)}" ${entries.length ? "" : "disabled"} title="${escapeHtml(`${dateKey}: ${entries.length} events${importance ? ` / highest ${importance}` : ""}`)}">
                <span>${escapeHtml(String(day))}</span>
                ${entries.length ? `<small>${escapeHtml(formatNumber(entries.length))}</small>` : ""}
              </button>`);
          }
          return `
            <section class="macro-year-month">
              <h3>${escapeHtml(first.toLocaleString(undefined, {month: "short", timeZone: "UTC"}))}</h3>
              <div class="macro-year-weekdays">${["S", "M", "T", "W", "T", "F", "S"].map((day) => `<span>${day}</span>`).join("")}</div>
              <div class="macro-year-month-grid">${cells.join("")}</div>
            </section>`;
        }

        function renderMacroEventDialog(events, payload) {
          if (state.macroCalendarDetailIndex === null || state.macroCalendarDetailIndex === undefined || state.macroCalendarDetailIndex === "") return "";
          const index = Number(state.macroCalendarDetailIndex);
          if (!Number.isInteger(index) || index < 0 || index >= events.length) return "";
          const record = events[index];
          const facts = recordPrimaryFacts(record, "macro_calendar");
          const metrics = recordMetricFacts(record);
          return `
            <div class="macro-event-dialog-backdrop" role="presentation" data-macro-dialog-close>
              <section class="macro-event-dialog" role="dialog" aria-modal="true" aria-label="Macro event details">
                <div class="macro-event-dialog-head">
                  <div>
                    <span class="muted">${escapeHtml(formatTimestamp(recordTime(record, "macro_calendar")))}</span>
                    <h2>${escapeHtml(recordTitle(record, "macro_calendar"))}</h2>
                  </div>
                  <button class="icon-button" type="button" data-macro-dialog-close aria-label="Close macro event details">x</button>
                </div>
                ${macroCalendarTemporalBanner(record, "macro_calendar")}
                <p>${escapeHtml(recordSummary(record, "macro_calendar") || "No narrative summary is recorded for this macro event.")}</p>
                ${metrics.length ? `<section class="intel-record-section"><h3>Key metrics</h3><div class="intel-metric-grid">${metrics.map(([key, val, unit]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(formatMetricValue(val, key, unit))}</strong>${unit ? `<small>${escapeHtml(unit)}</small>` : ""}</div>`).join("")}</div></section>` : ""}
                ${facts.length ? `<section class="intel-record-section"><h3>Event context</h3><div class="intel-fact-grid">${facts.map(([key, val]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(text(val))}</strong></div>`).join("")}</div></section>` : ""}
                <section class="intel-record-section"><h3>Properties</h3>${previewRecordProperties(record, payload)}</section>
              </section>
            </div>`;
        }

        function wireMacroCalendarPreview(selector, payload, events) {
          const root = node(selector);
          if (!root) return;
          root.querySelectorAll("[data-macro-list-index]").forEach((button) => {
            button.addEventListener("click", () => {
              selectMacroEvent(events, Number(button.dataset.macroListIndex) || 0, false);
              renderMacroCalendarPreview(selector, payload, events);
              window.requestAnimationFrame(() => {
                root.querySelector(`[data-macro-date-cell="${state.macroCalendarHighlightedDate}"]`)?.scrollIntoView({block: "nearest", inline: "nearest"});
              });
            });
          });
          root.querySelectorAll("[data-macro-event-index]").forEach((button) => {
            button.addEventListener("click", (event) => {
              event.stopPropagation();
              selectMacroEvent(events, Number(button.dataset.macroEventIndex) || 0, true);
              renderMacroCalendarPreview(selector, payload, events);
            });
          });
          root.querySelectorAll("[data-macro-date]").forEach((button) => {
            button.addEventListener("click", () => {
              selectMacroDate(events, button.dataset.macroDate || "");
              renderMacroCalendarPreview(selector, payload, events);
            });
          });
          root.querySelectorAll("[data-macro-year-date]").forEach((button) => {
            button.addEventListener("click", () => {
              const dateKey = button.dataset.macroYearDate || "";
              state.macroCalendarView = "month";
              state.macroCalendarMonth = dateKey.slice(0, 7);
              selectMacroDate(events, dateKey);
              renderMacroCalendarPreview(selector, payload, events);
            });
          });
          root.querySelectorAll("[data-macro-month-shift]").forEach((button) => {
            button.addEventListener("click", () => {
              state.macroCalendarMonth = shiftCalendarMonth(state.macroCalendarMonth, Number(button.dataset.macroMonthShift) || 0);
              state.macroCalendarYear = state.macroCalendarMonth.slice(0, 4);
              renderMacroCalendarPreview(selector, payload, events);
            });
          });
          root.querySelectorAll("[data-macro-year-shift]").forEach((button) => {
            button.addEventListener("click", () => {
              const year = Number(state.macroCalendarYear) || new Date().getUTCFullYear();
              state.macroCalendarYear = String(year + (Number(button.dataset.macroYearShift) || 0));
              renderMacroCalendarPreview(selector, payload, events);
            });
          });
          root.querySelectorAll("[data-macro-calendar-view]").forEach((button) => {
            button.addEventListener("click", () => {
              state.macroCalendarView = button.dataset.macroCalendarView === "year" ? "year" : "month";
              if (state.macroCalendarView === "year") state.macroCalendarYear = (state.macroCalendarMonth || "").slice(0, 4) || state.macroCalendarYear;
              renderMacroCalendarPreview(selector, payload, events);
            });
          });
          root.querySelectorAll("[data-macro-dialog-close]").forEach((target) => {
            target.addEventListener("click", (event) => {
              if (event.currentTarget !== event.target && !event.target.closest("[data-macro-dialog-close]")) return;
              state.macroCalendarDetailIndex = null;
              renderMacroCalendarPreview(selector, payload, events);
            });
          });
          wireMacroCalendarDragScroll(root);
        }

        function selectMacroEvent(events, index, openDialog) {
          const safeIndex = Math.min(Math.max(0, index), events.length - 1);
          const record = events[safeIndex];
          const dateKey = recordDateKey(record, "macro_calendar");
          state.selectedIntelPreviewIndex = safeIndex;
          if (dateKey) {
            state.macroCalendarHighlightedDate = dateKey;
            state.macroCalendarMonth = dateKey.slice(0, 7);
            state.macroCalendarYear = dateKey.slice(0, 4);
          }
          state.macroCalendarView = "month";
          state.macroCalendarDetailIndex = openDialog ? safeIndex : null;
        }

        function selectMacroDate(events, dateKey) {
          if (!dateKey) return;
          state.macroCalendarHighlightedDate = dateKey;
          state.macroCalendarMonth = dateKey.slice(0, 7);
          state.macroCalendarYear = dateKey.slice(0, 4);
          const firstIndex = events.findIndex((record) => recordDateKey(record, "macro_calendar") === dateKey);
          if (firstIndex >= 0) state.selectedIntelPreviewIndex = firstIndex;
          state.macroCalendarDetailIndex = null;
        }

        function macroRecordsByDate(events) {
          const byDate = new Map();
          events.forEach((record, index) => {
            const dateKey = recordDateKey(record, "macro_calendar");
            if (!dateKey) return;
            const entries = byDate.get(dateKey) || [];
            entries.push({record, index});
            byDate.set(dateKey, entries);
          });
          byDate.forEach((entries) => {
            entries.sort((left, right) => {
              const leftTime = Date.parse(recordTime(left.record, "macro_calendar"));
              const rightTime = Date.parse(recordTime(right.record, "macro_calendar"));
              return (Number.isFinite(leftTime) ? leftTime : 0) - (Number.isFinite(rightTime) ? rightTime : 0);
            });
          });
          return byDate;
        }

        function macroHighestImportance(records) {
          return records.reduce((highest, record) => {
            const current = record?.importance || "";
            return macroImportanceRank(current) > macroImportanceRank(highest) ? current : highest;
          }, "");
        }

        function macroImportanceRank(value) {
          const normalized = String(value || "").toLowerCase();
          if (["critical", "highest", "very_high"].includes(normalized)) return 5;
          if (["high", "important"].includes(normalized)) return 4;
          if (["medium", "moderate"].includes(normalized)) return 3;
          if (["low", "minor"].includes(normalized)) return 2;
          return normalized ? 1 : 0;
        }

        function macroImportanceClass(value) {
          const normalized = String(value || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-");
          if (["critical", "highest", "very-high"].includes(normalized)) return "critical";
          if (["high", "important"].includes(normalized)) return "high";
          if (["medium", "moderate"].includes(normalized)) return "medium";
          if (["low", "minor"].includes(normalized)) return "low";
          return "unknown";
        }

        function macroRegion(record) {
          return record?.region || record?.country || record?.currency || "";
        }

        function macroMonthLabel(monthKey) {
          const parsed = Date.parse(`${monthKey || new Date().toISOString().slice(0, 7)}-01T00:00:00Z`);
          if (!Number.isFinite(parsed)) return monthKey || "";
          return new Date(parsed).toLocaleString(undefined, {month: "long", year: "numeric", timeZone: "UTC"});
        }

        function macroEventTooltip(record) {
          const parts = [
            shortTime(recordTime(record, "macro_calendar")),
            recordTitle(record, "macro_calendar"),
            macroRegion(record),
            record?.importance ? label(record.importance) : "",
          ].filter(Boolean);
          return parts.join(" / ");
        }

        function shortTime(raw) {
          const parsed = Date.parse(raw);
          if (!Number.isFinite(parsed)) return "";
          return new Date(parsed).toLocaleTimeString(undefined, {hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC"});
        }

        function wireMacroCalendarDragScroll(root) {
          root.querySelectorAll(".macro-day-event-stack").forEach((stack) => {
            let startY = 0;
            let startScroll = 0;
            let dragging = false;
            stack.addEventListener("pointerdown", (event) => {
              if (event.target.closest("button")) return;
              dragging = true;
              startY = event.clientY;
              startScroll = stack.scrollTop;
              stack.classList.add("dragging");
              stack.setPointerCapture?.(event.pointerId);
            });
            stack.addEventListener("pointermove", (event) => {
              if (!dragging) return;
              stack.scrollTop = startScroll - (event.clientY - startY);
            });
            stack.addEventListener("pointerup", (event) => {
              dragging = false;
              stack.classList.remove("dragging");
              stack.releasePointerCapture?.(event.pointerId);
            });
            stack.addEventListener("pointercancel", () => {
              dragging = false;
              stack.classList.remove("dragging");
            });
          });
        }

        function wireIntelligencePreviewList(selector, payload, records, header, filtered, canFetchMore) {
          const root = node(selector);
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

        function syncIntelligencePreviewFilterControls(categoryOptions, filteredCount, totalCount) {
          const options = categoryOptions || [];
          const categoryValue = String(state.intelPreviewCategory || "");
          const keywordValue = String(state.intelPreviewKeyword || "");
          const categoryRows = [`<option value="">All categories</option>`].concat(options.map((option) => (
            `<option value="${escapeHtml(option.value)}" ${option.value === categoryValue ? "selected" : ""}>${escapeHtml(option.label)} (${escapeHtml(formatNumber(option.count))})</option>`
          )));
          const category = node("#intel-preview-category-filter");
          if (category) {
            category.innerHTML = categoryRows.join("");
            category.value = options.some((option) => option.value === categoryValue) ? categoryValue : "";
          }
          const keyword = node("#intel-preview-keyword");
          if (keyword && document.activeElement !== keyword) {
            keyword.value = keywordValue;
          }
        }

        function refreshIntelligencePreviewFromState() {
          if (state.dataViewerIntelPreview) renderPreview("intel", state.dataViewerIntelPreview);
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
              <div class="intel-preview-main-head">
                <div class="intel-preview-title-stack">
                  <div class="muted">${escapeHtml(formatTimestamp(time))}</div>
                  <h2>${escapeHtml(title)}</h2>
                </div>
                <button class="ghost-button compact-button intel-properties-trigger" type="button" id="intel-properties-button" title="Open properties for this record">Properties</button>
              </div>
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
          return `
            <div class="artifact-summary">
              <span class="status-pill pending">${escapeHtml(TYPE_LABELS[payload.data_type] || payload.data_type || "record")}</span>
              <span class="status-pill ${escapeHtml(statusClass(payload.status || "unknown"))}">${escapeHtml(label(payload.status || "unknown"))}</span>
            </div>
            <table class="kv-table">${rows.map(([key, val]) => `<tr><td>${escapeHtml(key)}</td><td>${escapeHtml(text(val))}</td></tr>`).join("")}</table>`;
        }

        function updateIntelligencePropertiesSelection(record, payload) {
          state.intelPropertiesRecord = record || null;
          state.intelPropertiesPayload = record ? payload : null;
          const button = node("#intel-properties-button");
          if (button) {
            button.disabled = !record;
            button.title = record ? "Open properties for the selected intelligence record" : "Select a preview record to inspect properties";
          }
          if (!record) {
            closeIntelligencePropertiesDrawer(false);
            setHtml("#intel-properties-drawer-body", `<div class="empty-state">Select an intelligence record to inspect its properties.</div>`);
            const title = node("#intel-properties-drawer-title");
            if (title) title.textContent = "Properties";
            return;
          }
          if (state.intelPropertiesDrawerOpen) {
            renderIntelligencePropertiesDrawer();
          }
        }

        function openIntelligencePropertiesDrawer() {
          if (!state.intelPropertiesRecord) return;
          state.intelPropertiesDrawerOpen = true;
          renderIntelligencePropertiesDrawer();
          node("#intel-properties-drawer")?.classList.remove("hidden");
          const backdrop = node("#intel-properties-drawer-backdrop");
          backdrop?.classList.remove("hidden");
          backdrop?.setAttribute("aria-hidden", "false");
          node("#intel-properties-drawer-close")?.focus({preventScroll: true});
        }

        function closeIntelligencePropertiesDrawer(returnFocus = true) {
          state.intelPropertiesDrawerOpen = false;
          node("#intel-properties-drawer")?.classList.add("hidden");
          const backdrop = node("#intel-properties-drawer-backdrop");
          backdrop?.classList.add("hidden");
          backdrop?.setAttribute("aria-hidden", "true");
          if (returnFocus) node("#intel-properties-button")?.focus({preventScroll: true});
        }

        function renderIntelligencePropertiesDrawer() {
          const record = state.intelPropertiesRecord;
          const payload = state.intelPropertiesPayload || {data_type: selectedIntelligenceDataType(), status: "unknown"};
          const title = node("#intel-properties-drawer-title");
          if (title) title.textContent = record ? recordTitle(record, payload.data_type) : "Properties";
          setHtml(
            "#intel-properties-drawer-body",
            record ? previewRecordProperties(record, payload) : `<div class="empty-state">Select an intelligence record to inspect its properties.</div>`,
          );
        }

        function openIntelligenceCollectDialog() {
          state.intelCollectDialogOpen = true;
          const backdrop = node("#intel-collect-dialog-backdrop");
          backdrop?.classList.remove("hidden");
          backdrop?.setAttribute("aria-hidden", "false");
          queueIntelligenceCollectTimelineLoad();
          node("#intel-data-collect")?.focus({preventScroll: true});
        }

        function closeIntelligenceCollectDialog(returnFocus = true) {
          state.intelCollectDialogOpen = false;
          const backdrop = node("#intel-collect-dialog-backdrop");
          backdrop?.classList.add("hidden");
          backdrop?.setAttribute("aria-hidden", "true");
          if (returnFocus) node("#intel-collect-open")?.focus({preventScroll: true});
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
          if (rawKey.includes("multiplier")) {
            return `${numeric.toLocaleString(undefined, {maximumFractionDigits: 2})}x`;
          }
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
          if (!Number.isFinite(parsed)) return dateKey;
          const formatted = formatTimestamp(new Date(parsed).toISOString());
          return formatted.split(/\s+/)[0] || dateKey;
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
          if (job?.command?.[0] === "internal") lines.push("execution: internal core service");
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
          if (selector === "#intel-data-preview-panel") updateIntelligencePropertiesSelection(null, null);
          const isCoveragePanel = String(selector || "").endsWith("-coverage");
          const title = isCoveragePanel ? `<strong>Coverage ${kind === "warning" ? "warning" : "failed"}</strong><br>` : "";
          setHtml(selector, `<div class="message ${kind === "warning" ? "warning" : "error"}">${title}${escapeHtml(message)}</div>`);
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
          node("#intel-collect-open")?.addEventListener("click", openIntelligenceCollectDialog);
          node("#intel-collect-dialog-close")?.addEventListener("click", () => closeIntelligenceCollectDialog());
          node("#intel-collect-dialog-cancel")?.addEventListener("click", () => closeIntelligenceCollectDialog());
          node("#intel-collect-dialog-backdrop")?.addEventListener("click", (event) => {
            if (event.target === event.currentTarget) closeIntelligenceCollectDialog();
          });
          node("#intel-data-collect")?.addEventListener("click", () => submitCollectionJob("intel"));
          node("#intel-properties-drawer-close")?.addEventListener("click", () => closeIntelligencePropertiesDrawer());
          node("#intel-properties-drawer-backdrop")?.addEventListener("click", () => closeIntelligencePropertiesDrawer());
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
          ["#intel-preview-start", "#intel-preview-end"].forEach((selector) => {
            node(selector)?.addEventListener("change", () => {
              resetIntelligencePreviewState();
              queueIntelligencePreviewLoad();
            });
          });
          node("#intel-preview-category-filter")?.addEventListener("change", (event) => {
            state.intelPreviewCategory = event.target.value || "";
            resetIntelligencePreviewListPosition();
            refreshIntelligencePreviewFromState();
          });
          node("#intel-preview-keyword")?.addEventListener("input", (event) => {
            state.intelPreviewKeyword = event.target.value || "";
            window.clearTimeout(state.intelPreviewFilterTimer);
            state.intelPreviewFilterTimer = window.setTimeout(() => {
              resetIntelligencePreviewListPosition();
              refreshIntelligencePreviewFromState();
            }, 220);
          });
          node("#intel-preview-clear-filters")?.addEventListener("click", () => {
            state.intelPreviewKeyword = "";
            state.intelPreviewCategory = "";
            resetIntelligencePreviewListPosition();
            refreshIntelligencePreviewFromState();
          });
          node("#intel-preview-apply-filters")?.addEventListener("click", () => {
            resetIntelligencePreviewState();
            queueIntelligencePreviewLoad();
          });
          document.addEventListener("click", (event) => {
            const eventTarget = event.target instanceof Element ? event.target : null;
            if (!eventTarget) return;
            const propertiesButton = eventTarget.closest("#intel-properties-button");
            if (propertiesButton) {
              event.preventDefault();
              openIntelligencePropertiesDrawer();
              return;
            }
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
            if (event.key === "Escape") {
              closeIssuePopovers();
              if (state.intelCollectDialogOpen) closeIntelligenceCollectDialog();
              if (state.intelPropertiesDrawerOpen) closeIntelligencePropertiesDrawer();
            }
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
