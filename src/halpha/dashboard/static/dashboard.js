    const app = document.querySelector("#halpha-dashboard-app");
    let displayTimezone = app.dataset.displayTimezone || "Asia/Shanghai";
    let pnlColorScheme = app.dataset.pnlColorScheme || "green_profit_red_loss";
    const timestampDisplay = {
      hourCycle: normalizeTimestampHourCycle(app.dataset.timestampHourCycle),
      dateOrder: normalizeTimestampDateOrder(app.dataset.timestampDateOrder),
    };
    const endpoints = {
      overview: app.dataset.overviewEndpoint,
      health: app.dataset.healthEndpoint,
      runs: app.dataset.runsEndpoint,
      preview: app.dataset.previewEndpoint,
      stores: app.dataset.storesEndpoint,
      deletion: app.dataset.deleteEndpoint,
      dataViewerSummary: app.dataset.dataViewerSummaryEndpoint,
      dataViewerTimeline: app.dataset.dataViewerTimelineEndpoint,
      dataViewerPreview: app.dataset.dataViewerPreviewEndpoint,
      dataViewerExport: app.dataset.dataViewerExportEndpoint,
      dataViewerCollectPlan: app.dataset.dataViewerCollectPlanEndpoint,
      dataViewerCollectJobs: app.dataset.dataViewerCollectJobsEndpoint,
      strategies: app.dataset.strategiesEndpoint,
      strategyActions: app.dataset.strategyActionsEndpoint,
      strategyBacktests: app.dataset.strategyBacktestsEndpoint,
      live: app.dataset.liveEndpoint,
      liveCycles: app.dataset.liveCyclesEndpoint,
      liveAlerts: app.dataset.liveAlertsEndpoint,
      liveHistory: app.dataset.liveHistoryEndpoint,
      jobs: app.dataset.jobsEndpoint,
      schedule: app.dataset.scheduleEndpoint,
      services: app.dataset.servicesEndpoint,
      settings: app.dataset.settingsEndpoint,
      configSelect: app.dataset.configSelectEndpoint,
      configImport: app.dataset.configImportEndpoint,
      textIntel: app.dataset.textIntelligenceEndpoint,
    };
    const shared = window.HalphaDashboardShared;
    if (!shared) {
      throw new Error("Halpha dashboard shared helpers did not load.");
    }
    const strategyChart = window.HalphaDashboardStrategyChart;
    if (!strategyChart) {
      throw new Error("Halpha dashboard strategy chart helpers did not load.");
    }
    const dialogs = window.HalphaDashboardDialogs;
    if (!dialogs) {
      throw new Error("Halpha dashboard dialog helpers did not load.");
    }
    const reportsWorkflow = window.HalphaDashboardReports;
    if (!reportsWorkflow) {
      throw new Error("Halpha dashboard report helpers did not load.");
    }
    const liveWorkflowModule = window.HalphaDashboardLive;
    if (!liveWorkflowModule) {
      throw new Error("Halpha dashboard live helpers did not load.");
    }
    const dataViewerWorkflowModule = window.HalphaDashboardDataViewer;
    if (!dataViewerWorkflowModule) {
      throw new Error("Halpha dashboard data viewer helpers did not load.");
    }
    const {
      escapeHtml,
      text,
      statusClass,
      formatNumber,
      joinPath,
      markdownToHtml,
      normalizePnlColorScheme,
      pnlClass,
      pnlColors,
    } = shared;
    const reportHelpers = reportsWorkflow.createReportHelpers({joinPath, unique});
    const {isAvailableReport, reportArtifactFiles, reportArtifactGroups, reportPath, reportSourceRefs} = reportHelpers;
    shared.configureTimestampFormat({
      timeZone: displayTimezone,
      hourCycle: timestampDisplay.hourCycle,
      dateOrder: timestampDisplay.dateOrder,
    });
    applyPnlColorScheme(pnlColorScheme);
    const BACKTEST_CHART_MAX_CANDLES = 1000;
    const VIEW_REFRESH_TTL_MS = 15000;
    const HEALTH_REFRESH_TTL_MS = 15000;
    const SIDEBAR_COLLAPSED_STORAGE_KEY = "halpha.dashboard.sidebarCollapsed";
    const VIEW_TITLES = {
      overview: "Overview",
      reports: "Reports",
      strategies: "Strategy",
      live: "Live",
      intelligence: "Intelligence",
      settings: "Settings",
    };
    const INTELLIGENCE_DATA_TYPES = ["text_event", "macro_calendar", "onchain_flow", "derivatives_market", "market_anomaly"];
    const INTELLIGENCE_OVERVIEW_LIMITS = {
      text_event: 12,
      macro_calendar: 32,
      onchain_flow: 160,
      derivatives_market: 220,
      market_anomaly: 120,
    };

    const state = {
      view: "overview",
      viewLoadedAt: {},
      viewRefreshPromises: {},
      healthLoadedAt: 0,
      healthRequest: null,
      overview: null,
      health: null,
      runs: [],
      selectedReport: null,
      selectedReportDetail: null,
      selectedReportPreview: null,
      selectedReportArtifact: null,
      selectedReportArtifactPreview: null,
      reportDetailsDrawerOpen: false,
      reportJob: null,
      generatedReportRunId: null,
      reportInspectorTab: "reports",
      reportSearchTerm: "",
      stores: [],
      deletionPlan: null,
      strategies: null,
      selectedStrategyOutput: null,
      strategyBacktestDetailOpen: false,
      strategyDataVisualization: null,
      strategyOperationTab: "backtest",
      strategyWindow: "90",
      strategyFocusedMarkerTime: "",
      strategyChartPreviewTimer: null,
      strategyChartPreviewRequest: 0,
      strategyCollectTargets: [],
      strategyCollectTimelineTimer: null,
      strategyCollectTimelineRequest: 0,
      strategyBacktestLogs: [],
      strategyExperimentLogs: [],
      strategyCollectLogs: [],
      strategyExperimentFilters: {family: "all", symbol: "all", timeframe: "all"},
      strategyExperimentSelection: [],
      strategyExperimentSelectionInitialized: false,
      strategyRunFilters: {query: "", strategy: "all", timeframe: "all", start: "", end: ""},
      strategyRunSort: "time_desc",
      strategyRunPageSize: 25,
      strategyRunVisibleCount: 25,
      strategyBacktestDialogOpen: false,
      strategyParamsDrawerOpen: false,
      live: null,
      liveCycles: [],
      liveAlerts: null,
      liveHistory: null,
      liveFilters: {dataType: "all", status: "all", activeOnly: false, attentionOnly: false},
      liveMode: "now",
      liveHistoryFilters: {
        start: "",
        end: "",
        dataType: "all",
        triggerId: "all",
        eventKind: "all",
        status: "all",
        reportLinkedOnly: false,
        attentionOnly: false,
      },
      selectedLiveEventId: "",
      liveEventDrawerOpen: false,
      selectedLiveTargetKey: "",
      schedule: null,
      services: null,
      jobs: [],
      intelligence: null,
      dataViewerSummary: null,
      dataViewerStrategyTimeline: null,
      dataViewerStrategyPreview: null,
      dataViewerStrategyPlan: null,
      dataViewerStrategyJob: null,
      dataViewerIntelTimeline: null,
      dataViewerIntelPreview: null,
      dataViewerIntelPlan: null,
      dataViewerIntelJob: null,
      dataViewerIntelExport: null,
      selectedIntelTab: "overview",
      intelligenceOverviewPreviews: null,
      intelligenceOverviewErrors: {},
      intelligenceOverviewLoading: false,
      intelligenceOverviewRequestId: 0,
      selectedIntelItem: null,
      selectedIntelPreviewIndex: 0,
      intelPreviewDisplayLimit: 30,
      intelPreviewFetchLimit: 100,
      intelPreviewLoadingMore: false,
      intelPreviewKeyword: "",
      intelPreviewCategory: "",
      intelPreviewFilterTimer: null,
      intelDatePickerOpen: false,
      intelCalendarMonth: null,
      macroCalendarView: "month",
      macroCalendarMonth: null,
      macroCalendarYear: null,
      macroCalendarHighlightedDate: "",
      macroCalendarDetailIndex: null,
      onchainDataClass: "",
      onchainMetricKey: "",
      onchainSelectedIndex: null,
      dateRangePickerGlobalWired: false,
      intelligenceViewerTimer: null,
      settingsProfile: null,
      settingsSection: "Market data",
      settingsChanges: {},
      settingsFieldErrors: {},
      settingsConfigError: "",
      settingsLoadingConfig: false,
      selectedRunArtifacts: [],
      selectedSharedStores: [],
      validationJob: null,
    };
    const liveWorkflow = liveWorkflowModule.createLiveWorkflow({
      state,
      endpoints,
      loadLivePayload,
      showToast,
      escapeHtml,
      text,
      statusClass,
      formatNumber,
      formatTimestamp,
      label,
      metricCell,
      detailRow,
      table,
      durationBetween,
      terminalJobStatus,
    });
    const dataViewerWorkflow = dataViewerWorkflowModule.createDataViewerWorkflow({
      state,
      endpoints,
      fetchJson,
      postJson,
      showToast,
      escapeHtml,
      text,
      statusClass,
      formatNumber,
      formatTimestamp,
      label,
      metricCell,
      table,
      terminalJobStatus,
      renderStrategyOhlcvPreview,
      syncDateRangePicker: syncDateRangePickerByInputs,
    });

    function normalizeTimestampHourCycle(value) {
      return value === "12h" ? "12h" : "24h";
    }

    function normalizeTimestampDateOrder(value) {
      return value === "year_last" ? "year_last" : "year_first";
    }

    function applyTimestampDisplayOptions(options = {}) {
      if (typeof options.timeZone === "string" && options.timeZone.trim()) {
        displayTimezone = options.timeZone.trim();
      }
      timestampDisplay.hourCycle = normalizeTimestampHourCycle(options.hourCycle || timestampDisplay.hourCycle);
      timestampDisplay.dateOrder = normalizeTimestampDateOrder(options.dateOrder || timestampDisplay.dateOrder);
      shared.configureTimestampFormat({
        timeZone: displayTimezone,
        hourCycle: timestampDisplay.hourCycle,
        dateOrder: timestampDisplay.dateOrder,
      });
    }

    function applyTimestampDisplayOptionsFromProfile(profile) {
      const fields = Array.isArray(profile?.fields) ? profile.fields : [];
      const valueForPath = (path) => fields.find((field) => field.path === path)?.value;
      applyTimestampDisplayOptions({
        timeZone: valueForPath("dashboard.display_timezone"),
        hourCycle: valueForPath("dashboard.timestamp_hour_cycle"),
        dateOrder: valueForPath("dashboard.timestamp_date_order"),
      });
      applyPnlColorScheme(valueForPath("dashboard.pnl_color_scheme"));
    }

    function applyPnlColorScheme(value) {
      pnlColorScheme = normalizePnlColorScheme(value || pnlColorScheme);
      shared.configurePnlColorScheme(pnlColorScheme);
      const colors = pnlColors(pnlColorScheme);
      document.documentElement.dataset.pnlColorScheme = pnlColorScheme;
      document.body.dataset.pnlColorScheme = pnlColorScheme;
      document.documentElement.style.setProperty("--pnl-profit", colors.profit);
      document.documentElement.style.setProperty("--pnl-loss", colors.loss);
      document.documentElement.style.setProperty("--pnl-profit-soft", colors.profitSoft);
      document.documentElement.style.setProperty("--pnl-loss-soft", colors.lossSoft);
      document.documentElement.style.setProperty("--pnl-up", colors.up);
      document.documentElement.style.setProperty("--pnl-down", colors.down);
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
      const valueHtml = pnlMetricLabel(labelText) ? pnlValueHtml(value) : escapeHtml(value);
      return `<div class="summary-cell"><div class="summary-label">${escapeHtml(labelText)}</div><div class="summary-value">${valueHtml}</div>${note ? `<div class="summary-note">${escapeHtml(note)}</div>` : ""}</div>`;
    }

    function detailRow(key, value) {
      const valueText = text(value);
      const valueHtml = pnlMetricLabel(key) ? pnlValueHtml(valueText) : escapeHtml(valueText);
      return `<div class="detail-row"><div class="detail-key">${escapeHtml(key)}</div><div class="detail-value">${valueHtml}</div></div>`;
    }

    function pnlMetricLabel(labelText) {
      const normalized = String(labelText || "").toLowerCase();
      return [
        "return",
        "drawdown",
        "profit",
        "loss",
        "pnl",
        "excess",
        "best trade",
        "worst trade",
        "buy and hold",
      ].some((needle) => normalized.includes(needle));
    }

    function pnlValueHtml(value) {
      return `<span class="${pnlClass(value)}">${escapeHtml(text(value))}</span>`;
    }

    function pct(value) {
      if (typeof value !== "number" || Number.isNaN(value)) {
        return "n/a";
      }
      return `${value.toFixed(1)}%`;
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
      return shared.formatTimestamp(value, {
        timeZone: displayTimezone,
        hourCycle: timestampDisplay.hourCycle,
        dateOrder: timestampDisplay.dateOrder,
      });
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

    function showToast(message, kind = "info") {
      const toast = document.querySelector("#toast");
      const safeKind = ["info", "success", "warning", "error"].includes(kind) ? kind : "info";
      toast.textContent = message;
      toast.className = `toast visible ${safeKind}`;
      window.setTimeout(() => toast.classList.remove("visible"), 3600);
    }

    const tooltipState = {
      target: null,
      observer: null,
    };

    function initializeTooltips() {
      migrateNativeTooltips(document.body);
      document.addEventListener("pointerover", handleTooltipEnter, true);
      document.addEventListener("pointerout", handleTooltipLeave, true);
      document.addEventListener("focusin", handleTooltipEnter, true);
      document.addEventListener("focusout", handleTooltipLeave, true);
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          hideTooltip();
        }
      });
      window.addEventListener("resize", () => positionTooltip());
      window.addEventListener("scroll", () => positionTooltip(), true);
      tooltipState.observer = new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          if (mutation.type === "attributes" && mutation.target instanceof Element) {
            migrateNativeTooltips(mutation.target);
          }
          mutation.addedNodes.forEach((node) => migrateNativeTooltips(node));
        });
      });
      tooltipState.observer.observe(document.body, {subtree: true, childList: true, attributes: true, attributeFilter: ["title"]});
    }

    function migrateNativeTooltips(root) {
      if (!root) {
        return;
      }
      const nodes = [];
      if (root.nodeType === Node.ELEMENT_NODE && root instanceof Element) {
        nodes.push(root);
        root.querySelectorAll("[title]").forEach((node) => nodes.push(node));
      } else if (root === document || root.nodeType === Node.DOCUMENT_NODE) {
        document.querySelectorAll("[title]").forEach((node) => nodes.push(node));
      }
      nodes.forEach((node) => {
        const title = node.getAttribute("title");
        if (!title) {
          return;
        }
        if (!node.dataset.tooltip) {
          node.dataset.tooltip = title;
        }
        if (!node.getAttribute("aria-label") && node.tagName === "BUTTON") {
          node.setAttribute("aria-label", title);
        }
        node.removeAttribute("title");
      });
    }

    function tooltipTargetFromEvent(event) {
      const target = event.target instanceof Element ? event.target.closest("[data-tooltip]") : null;
      if (target) {
        migrateNativeTooltips(target);
      }
      return target;
    }

    function handleTooltipEnter(event) {
      const target = tooltipTargetFromEvent(event);
      if (!target || !target.dataset.tooltip || target.dataset.tooltip.trim() === "") {
        return;
      }
      if (tooltipState.target === target) {
        return;
      }
      showTooltip(target);
    }

    function handleTooltipLeave(event) {
      const target = tooltipTargetFromEvent(event);
      if (!target || tooltipState.target !== target) {
        return;
      }
      const related = event.relatedTarget;
      if (related instanceof Node && target.contains(related)) {
        return;
      }
      hideTooltip();
    }

    function tooltipNode() {
      let node = document.querySelector("#app-tooltip");
      if (!node) {
        node = document.createElement("div");
        node.id = "app-tooltip";
        node.className = "app-tooltip";
        node.setAttribute("role", "tooltip");
        document.body.appendChild(node);
      }
      return node;
    }

    function showTooltip(target) {
      const tooltip = tooltipNode();
      tooltipState.target = target;
      tooltip.textContent = target.dataset.tooltip || "";
      tooltip.className = "app-tooltip visible";
      target.setAttribute("aria-describedby", "app-tooltip");
      positionTooltip();
    }

    function hideTooltip() {
      if (tooltipState.target) {
        tooltipState.target.removeAttribute("aria-describedby");
      }
      tooltipState.target = null;
      const tooltip = document.querySelector("#app-tooltip");
      if (tooltip) {
        tooltip.className = "app-tooltip";
        tooltip.removeAttribute("style");
      }
    }

    function positionTooltip() {
      const target = tooltipState.target;
      const tooltip = document.querySelector("#app-tooltip");
      if (!target || !tooltip || !tooltip.classList.contains("visible")) {
        return;
      }
      const rect = target.getBoundingClientRect();
      if (rect.width <= 0 && rect.height <= 0) {
        hideTooltip();
        return;
      }
      const spacing = 10;
      const tooltipRect = tooltip.getBoundingClientRect();
      const width = tooltipRect.width || 260;
      const height = tooltipRect.height || 40;
      const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
      const preferredTop = rect.top - height - spacing;
      const placement = preferredTop >= 8 ? "top" : "bottom";
      const top = placement === "top"
        ? Math.max(8, preferredTop)
        : Math.min(viewportHeight - height - 8, rect.bottom + spacing);
      const left = Math.max(8, Math.min(viewportWidth - width - 8, rect.left + rect.width / 2 - width / 2));
      const arrowLeft = Math.max(12, Math.min(width - 12, rect.left + rect.width / 2 - left));
      tooltip.classList.toggle("placement-bottom", placement === "bottom");
      tooltip.style.left = `${left}px`;
      tooltip.style.top = `${top}px`;
      tooltip.style.setProperty("--tooltip-arrow-left", `${arrowLeft}px`);
    }

    function setHtml(selector, html) {
      const node = document.querySelector(selector);
      if (node) {
        node.innerHTML = html;
      }
    }

    function setText(selector, value) {
      const node = document.querySelector(selector);
      if (node) {
        node.textContent = value;
      }
    }

    function skeletonLine(width = "100%", extraClass = "") {
      return `<span class="skeleton skeleton-line ${extraClass}" style="width:${escapeHtml(width)}"></span>`;
    }

    function skeletonValue(width = "42%") {
      return `<span class="skeleton skeleton-value" style="width:${escapeHtml(width)}"></span>`;
    }

    function skeletonRows(count = 4) {
      return `<div class="skeleton-table loading-surface">${Array.from({length: count}, (_, index) => `
        <div class="skeleton-row">
          ${skeletonLine(index % 2 ? "46%" : "62%", "tight")}
          ${skeletonLine(index % 3 ? "72%" : "54%", "tight")}
        </div>`).join("")}</div>`;
    }

    function skeletonCards(count = 4, className = "skeleton-card") {
      return Array.from({length: count}, (_, index) => `
        <div class="${className} loading-surface">
          ${skeletonLine(index % 2 ? "58%" : "72%", "tight")}
          ${skeletonValue(index % 3 ? "34%" : "46%")}
          ${skeletonLine(index % 2 ? "42%" : "56%", "tight")}
        </div>`).join("");
    }

    function skeletonList(count = 3) {
      return `<div class="skeleton-list loading-surface">${Array.from({length: count}, (_, index) => `
        <div class="skeleton-card">
          ${skeletonLine(index % 2 ? "52%" : "68%", "tight")}
          ${skeletonLine("86%", "tight")}
          ${skeletonLine(index % 2 ? "44%" : "58%", "tight")}
        </div>`).join("")}</div>`;
    }

    function skeletonListItems(count = 3) {
      return Array.from({length: count}, (_, index) => `
        <li class="compact-row loading-surface">
          ${skeletonLine(index % 2 ? "62%" : "78%", "tight")}
          ${skeletonLine(index % 2 ? "48%" : "64%", "tight")}
        </li>`).join("");
    }

    function skeletonMessage(lines = 3) {
      return `<div class="empty-state loading-surface">${Array.from({length: lines}, (_, index) => skeletonLine(index === lines - 1 ? "46%" : "82%")).join("")}</div>`;
    }

    function viewFromHash() {
      const raw = (window.location.hash || "#overview").slice(1) || "overview";
      return raw;
    }

    function setView(view) {
      const valid = ["overview", "reports", "strategies", "live", "intelligence", "settings"];
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
      renderGlobalTopbar();
      refreshCurrentView();
    }

    function renderGlobalTopbar() {
      const titleText = VIEW_TITLES[state.view] || VIEW_TITLES.overview;
      const title = document.querySelector("#global-page-title");
      if (title) title.textContent = titleText;
      const intelTabs = document.querySelector("#intel-tabs");
      const strategyTabs = document.querySelector("#strategy-operation-tabs");
      const liveTabs = document.querySelector("#live-mode-tabs");
      const reportGenerate = document.querySelector("#topbar-report-generate");
      intelTabs?.classList.toggle("hidden", state.view !== "intelligence");
      strategyTabs?.classList.toggle("hidden", state.view !== "strategies");
      liveTabs?.classList.toggle("hidden", state.view !== "live");
      reportGenerate?.classList.toggle("hidden", state.view !== "reports");
      intelTabs?.setAttribute("aria-hidden", state.view === "intelligence" ? "false" : "true");
      strategyTabs?.setAttribute("aria-hidden", state.view === "strategies" ? "false" : "true");
      liveTabs?.setAttribute("aria-hidden", state.view === "live" ? "false" : "true");
      refreshTopbarTabHints();
    }

    function setSidebarCollapsed(collapsed, options = {}) {
      const shouldPersist = options.persist !== false;
      app.classList.toggle("sidebar-collapsed", collapsed);
      const button = document.querySelector("#sidebar-collapse-toggle");
      const logoButton = document.querySelector("#brand-logo-toggle");
      if (button) {
        const labelText = collapsed ? "Expand navigation" : "Collapse navigation";
        button.setAttribute("aria-expanded", collapsed ? "false" : "true");
        button.setAttribute("aria-label", labelText);
        button.title = labelText;
      }
      if (logoButton) {
        const labelText = collapsed ? "Expand navigation" : "Collapse navigation";
        logoButton.setAttribute("aria-expanded", collapsed ? "false" : "true");
        logoButton.setAttribute("aria-label", labelText);
        logoButton.title = labelText;
      }
      if (shouldPersist) {
        try {
          window.localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, collapsed ? "1" : "0");
        } catch (error) {
          // Local storage can be unavailable in hardened browser modes.
        }
      }
      refreshTopbarTabHints();
    }

    function initializeSidebarCollapse() {
      let collapsed = false;
      try {
        collapsed = window.localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY) === "1";
      } catch (error) {
        collapsed = false;
      }
      setSidebarCollapsed(collapsed, {persist: false});
      document.querySelector("#sidebar-collapse-toggle")?.addEventListener("click", () => {
        setSidebarCollapsed(!app.classList.contains("sidebar-collapsed"));
      });
      document.querySelector("#brand-logo-toggle")?.addEventListener("click", () => {
        setSidebarCollapsed(!app.classList.contains("sidebar-collapsed"));
      });
    }

    function updateTopbarTabHints(scroller) {
      if (!scroller || scroller.classList.contains("hidden")) {
        return;
      }
      const maxScroll = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
      const canScroll = maxScroll > 2;
      const canScrollLeft = canScroll && scroller.scrollLeft > 2;
      const canScrollRight = canScroll && scroller.scrollLeft < maxScroll - 2;
      scroller.classList.toggle("is-scrollable", canScroll);
      scroller.classList.toggle("can-scroll-left", canScrollLeft);
      scroller.classList.toggle("can-scroll-right", canScrollRight);
    }

    function refreshTopbarTabHints() {
      window.requestAnimationFrame(() => {
        document.querySelectorAll(".topbar-secondary").forEach(updateTopbarTabHints);
      });
    }

    function wireTopbarTabDragging() {
      document.querySelectorAll(".topbar-secondary").forEach((scroller) => {
        let isDragging = false;
        let didDrag = false;
        let startX = 0;
        let lastX = 0;
        let startScrollLeft = 0;
        scroller.addEventListener("scroll", () => updateTopbarTabHints(scroller), {passive: true});
        scroller.addEventListener("pointerdown", (event) => {
          if (event.button !== 0 || scroller.scrollWidth <= scroller.clientWidth + 2) {
            return;
          }
          isDragging = true;
          didDrag = false;
          startX = event.clientX;
          lastX = event.clientX;
          startScrollLeft = scroller.scrollLeft;
        });
        scroller.addEventListener("pointermove", (event) => {
          if (!isDragging) {
            return;
          }
          const delta = event.clientX - startX;
          if (!didDrag && Math.abs(delta) > 3) {
            didDrag = true;
            scroller.classList.add("is-dragging");
            scroller.setPointerCapture?.(event.pointerId);
          }
          lastX = event.clientX;
          if (!didDrag) {
            return;
          }
          event.preventDefault();
          scroller.scrollLeft = startScrollLeft - delta;
          updateTopbarTabHints(scroller);
        });
        const endDrag = (event) => {
          if (!isDragging) {
            return;
          }
          const moved = Math.abs((event?.clientX ?? lastX) - startX);
          if (moved <= 3) {
            didDrag = false;
          }
          isDragging = false;
          scroller.classList.remove("is-dragging");
          if (didDrag) {
            scroller.releasePointerCapture?.(event.pointerId);
          }
          updateTopbarTabHints(scroller);
        };
        scroller.addEventListener("pointerup", endDrag);
        scroller.addEventListener("pointercancel", endDrag);
        scroller.addEventListener("click", (event) => {
          if (!didDrag) {
            return;
          }
          didDrag = false;
          event.preventDefault();
          event.stopPropagation();
        }, true);
      });
    }

    function wireStrategyDetailHeaderDrag() {
      const scroller = document.querySelector(".strategy-detail-heading");
      if (!scroller) return;
      let isDragging = false;
      let didDrag = false;
      let startX = 0;
      let startScrollLeft = 0;
      scroller.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || scroller.scrollWidth <= scroller.clientWidth + 2) {
          return;
        }
        isDragging = true;
        didDrag = false;
        startX = event.clientX;
        startScrollLeft = scroller.scrollLeft;
      });
      scroller.addEventListener("pointermove", (event) => {
        if (!isDragging) return;
        const delta = event.clientX - startX;
        if (!didDrag && Math.abs(delta) > 3) {
          didDrag = true;
          scroller.classList.add("is-dragging");
          scroller.setPointerCapture?.(event.pointerId);
        }
        if (!didDrag) return;
        event.preventDefault();
        scroller.scrollLeft = startScrollLeft - delta;
      });
      const endDrag = (event) => {
        if (!isDragging) return;
        isDragging = false;
        scroller.classList.remove("is-dragging");
        if (didDrag) {
          scroller.releasePointerCapture?.(event.pointerId);
        }
      };
      scroller.addEventListener("pointerup", endDrag);
      scroller.addEventListener("pointercancel", endDrag);
      scroller.addEventListener("click", (event) => {
        if (!didDrag) return;
        didDrag = false;
        event.preventDefault();
        event.stopPropagation();
      }, true);
    }

    async function refreshCurrentView(options = {}) {
      return refreshView(state.view, options);
    }

    async function refreshView(view, options = {}) {
      const force = Boolean(options.force);
      const lastLoaded = state.viewLoadedAt[view] || 0;
      const fresh = lastLoaded && Date.now() - lastLoaded < VIEW_REFRESH_TTL_MS;
      if (!force && fresh) {
        return null;
      }
      if (state.viewRefreshPromises[view]) {
        return state.viewRefreshPromises[view];
      }
      showViewLoading(view);
      const promise = (async () => {
        try {
          if (view === "overview") await refreshOverview();
          if (view === "reports") await refreshReports();
          if (view === "strategies") await refreshStrategies();
          if (view === "live") await liveWorkflow.refreshLive();
          if (view === "intelligence") await refreshIntelligence();
          if (view === "settings") await refreshSettings();
          state.viewLoadedAt[view] = Date.now();
        } finally {
          clearViewLoading(view);
          state.viewRefreshPromises[view] = null;
        }
      })();
      state.viewRefreshPromises[view] = promise;
      return promise;
    }

    function showViewLoading(view) {
      const viewNode = document.querySelector(`[data-view="${view}"]`);
      viewNode?.setAttribute("aria-busy", "true");
      if (view === "overview" && !state.overview && !state.runs.length && !state.stores.length) renderOverviewLoading();
      if (view === "reports" && !state.runs.length) renderReportsLoading();
      if (view === "strategies" && !state.strategies) renderStrategiesLoading();
      if (view === "live" && !state.live) renderLiveLoading();
      if (view === "intelligence" && !state.intelligence && !state.dataViewerSummary) renderIntelligenceLoading();
      if (view === "settings" && !state.settingsProfile) renderSettingsLoading();
    }

    function clearViewLoading(view) {
      const viewNode = document.querySelector(`[data-view="${view}"]`);
      viewNode?.removeAttribute("aria-busy");
    }

    function renderInitialLoadingPlaceholders() {
      renderOverviewLoading();
      renderReportsLoading();
      renderStrategiesLoading();
      renderLiveLoading();
      renderIntelligenceLoading();
      renderSettingsLoading();
    }

    function renderOverviewLoading() {
      setPill("#overview-report-status", "pending", "loading");
      setHtml("#overview-report-metrics", skeletonCards(4, "report-metric"));
      setHtml("#overview-latest-report", skeletonRows(6));
      setHtml("#overview-runtime", skeletonRows(7));
      setPill("#overview-system-monitor-pill", "pending", "loading");
      setHtml("#overview-system-monitor", skeletonRows(7));
      setPill("#overview-data-pill", "pending", "loading");
      setHtml("#overview-data-cards", skeletonCards(6, "data-card"));
      setHtml("#overview-quality", `<div class="summary-strip columns-3">${skeletonCards(3, "summary-cell")}</div>`);
      setPill("#attention-count", "pending", "...");
      setHtml("#attention-list", skeletonListItems(2));
    }

    function renderReportsLoading() {
      setHtml("#report-library-groups", skeletonList(4));
      setHtml("#report-reader", `<article class="markdown-reader loading-surface">${skeletonLine("68%")}${skeletonLine("96%")}${skeletonLine("92%")}${skeletonLine("88%")}${skeletonLine("52%")}</article>`);
      setHtml("#report-outline", skeletonListItems(3));
      setHtml("#report-details-drawer-body", skeletonRows(6));
    }

    function renderStrategiesLoading() {
      setHtml("#strategy-spec-summary", `<div class="loading-surface">${skeletonLine("42%")}${skeletonLine("78%")}</div>`);
      setHtml("#strategy-parameter-controls", skeletonCards(3, "strategy-param-card"));
      setHtml("#strategy-params-drawer-body", skeletonRows(5));
      setHtml("#strategy-operation-tree", skeletonList(3));
      setHtml("#strategy-tab-content", skeletonMessage(4));
      setHtml("#strategy-experiment-results", skeletonMessage(3));
    }

    function renderLiveLoading() {
      setHtml("#live-summary", skeletonCards(6, "summary-cell"));
      setHtml("#live-source-matrix", skeletonCards(6, "live-source-card"));
      setHtml("#live-intelligence-strip", skeletonCards(6, "live-intel-card"));
      setHtml("#live-intelligence-stream", skeletonList(4));
      setHtml("#live-report-history", skeletonRows(6));
      setHtml("#live-system-runtime", skeletonRows(6));
      setHtml("#live-operations-timeline", `<li>${skeletonRows(5)}</li>`);
    }

    function renderIntelligenceLoading() {
      renderIntelligenceOverviewLoading();
      setHtml("#intel-overview-content", `
        <div class="intel-overview-dashboard">
          <section class="panel panel-pad intel-overview-section wide">${skeletonList(4)}</section>
          <section class="panel panel-pad intel-overview-section side">${skeletonList(4)}</section>
          <section class="panel panel-pad intel-overview-section chart">${skeletonMessage(3)}</section>
          <section class="panel panel-pad intel-overview-section chart">${skeletonMessage(3)}</section>
        </div>`);
      setPill("#intel-data-status", "pending", "loading");
      setHtml("#intel-data-summary", skeletonCards(4, "summary-cell"));
      setHtml("#intel-data-coverage", `<div class="data-viewer-timeline loading-surface">${skeletonLine("100%")}${skeletonLine("96%")}</div>`);
      setHtml("#intel-data-preview-panel", skeletonMessage(4));
    }

    function renderSettingsLoading() {
      setHtml("#settings-nav", skeletonList(6));
      setHtml("#settings-form", skeletonRows(7));
      setHtml("#settings-config-select", `<option>Loading configs...</option>`);
    }

    async function loadHealth(options = {}) {
      if (!options.force && state.health && Date.now() - state.healthLoadedAt < HEALTH_REFRESH_TTL_MS) {
        renderHealth();
        return state.health;
      }
      if (state.healthRequest) {
        return state.healthRequest;
      }
      state.healthRequest = (async () => {
        try {
          state.health = await fetchJson(endpoints.health);
          state.healthLoadedAt = Date.now();
          renderHealth();
          return state.health;
        } catch (error) {
          throw error;
        } finally {
          state.healthRequest = null;
        }
      })();
      return state.healthRequest;
    }

    function renderHealth() {
      const loaded = state.health?.config?.loaded !== false;
      if (!loaded && state.view !== "settings") {
        setHashView("settings");
      }
    }

    function liveSidebarState() {
      const live = state.live;
      if (!live) {
        return {tone: "unknown", title: "Live status unavailable", detail: "Live enablement has not loaded yet."};
      }
      const enabled = live.scheduler?.enabled === true;
      const status = String(live.status || (enabled ? "enabled" : "disabled")).toLowerCase();
      const targetCount = Array.isArray(live.collections) ? live.collections.length : 0;
      if (!enabled || ["disabled", "stopped", "unconfigured"].includes(status)) {
        return {tone: "stopped", title: "Live disabled", detail: "Live collection and scheduled review are disabled in config."};
      }
      if (["failed", "crashed", "error"].includes(status)) {
        return {tone: "failed", title: "Live needs attention", detail: "Live collection or scheduling reported an error."};
      }
      if (["partial", "degraded", "stale", "warning"].includes(status)) {
        return {tone: "warning", title: "Live degraded", detail: targetCount ? `${targetCount} configured targets; review Live details.` : "Live is enabled with limited status detail."};
      }
      return {tone: "running", title: "Live enabled", detail: targetCount ? `${targetCount} collection targets configured.` : "Live collection and scheduled review are enabled."};
    }

    function renderSidebarLiveStatus() {
      const dot = document.querySelector("#sidebar-live-dot");
      const title = document.querySelector("#sidebar-live-title");
      const detail = document.querySelector("#sidebar-live-text");
      if (!dot || !title || !detail) {
        return;
      }
      const liveState = liveSidebarState();
      dot.className = `health-dot ${liveState.tone}`;
      title.textContent = liveState.title;
      detail.textContent = liveState.detail;
    }

    async function refreshHealthForView() {
      try {
        await loadHealth();
      } catch (error) {
      }
    }

    async function refreshOverview() {
      await Promise.allSettled([loadHealth(), loadRuns(), loadStores(), loadLivePayload()]);
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

    async function loadLivePayload() {
      const [live, cycles, alerts, history, jobs, schedule, services] = await Promise.allSettled([
        fetchJson(endpoints.live),
        fetchJson(endpoints.liveCycles),
        fetchJson(endpoints.liveAlerts),
        fetchJson(endpoints.liveHistory),
        loadJobs(),
        fetchJson(endpoints.schedule),
        fetchJson(endpoints.services),
      ]);
      state.live = live.status === "fulfilled" ? live.value : null;
      state.liveCycles = cycles.status === "fulfilled" && Array.isArray(cycles.value.cycles) ? cycles.value.cycles : [];
      state.liveAlerts = alerts.status === "fulfilled" ? alerts.value : null;
      state.liveHistory = history.status === "fulfilled" ? history.value : null;
      state.jobs = jobs.status === "fulfilled" && Array.isArray(jobs.value.jobs) ? jobs.value.jobs : [];
      state.schedule = schedule.status === "fulfilled" ? schedule.value : null;
      state.services = services.status === "fulfilled" ? services.value : null;
      renderSidebarLiveStatus();
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
        reportMetric("Triggered reports", reportRuns.filter((item) => item.type === "Monitor-triggered").length, "All time"),
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
      renderOverviewSystemMonitor();
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

    function renderOverviewSystemMonitor() {
      const services = state.services?.services || {};
      const coreService = services.core || {};
      const monitorService = services.monitor || {};
      const status = monitorService.lifecycle_status || monitorService.status || state.live?.status || "partial";
      const schedule = state.schedule || {};
      const scheduleLabel = schedule.enabled
        ? formatTimestamp(schedule.next_run_at)
        : "No daily report scheduled";
      setPill("#overview-system-monitor-pill", status, status);
      document.querySelector("#overview-system-monitor").innerHTML = [
        detailRow("Core service", label(coreService.lifecycle_status || coreService.status || "unknown")),
        detailRow("Core heartbeat", formatTimestamp(coreService.heartbeat_at)),
        detailRow("System Monitor service", label(monitorService.lifecycle_status || monitorService.status || "unknown")),
        detailRow("System Monitor heartbeat", formatTimestamp(monitorService.heartbeat_at)),
        detailRow("Live scheduler", label(state.live?.scheduler?.enabled ? state.live?.status || "available" : "disabled")),
        detailRow("Live collection targets", Array.isArray(state.live?.collections) ? state.live.collections.length : 0),
        detailRow("Recent historical cycles", state.liveCycles.length),
        detailRow("Next scheduled report", scheduleLabel),
        detailRow("Recent alerts", liveWorkflow.alertCount(state.liveAlerts)),
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
        <div class="summary-strip columns-3">
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
      (state.live?.warnings || []).slice(0, 1).forEach((warning) => items.push({severity: "warning", title: "Live warning", copy: warning, action: "Open Live overview", view: "live"}));
      (state.live?.errors || []).slice(0, 1).forEach((error) => items.push({severity: "failed", title: "Live error", copy: error, action: "Open Live overview", view: "live"}));
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
        state.selectedReportDetail = null;
        state.selectedReportPreview = null;
        state.selectedReportArtifact = null;
        state.selectedReportArtifactPreview = null;
        document.querySelector("#selected-report-kicker").textContent = "No report selected";
        document.querySelector("#report-details-button").disabled = true;
        document.querySelector("#report-reader").innerHTML = `<div class="empty-state">No generated reports are available yet. Use Generate report to create a new report.</div>`;
        document.querySelector("#report-outline").innerHTML = "";
        document.querySelector("#report-source-files").innerHTML = "";
        renderReportDetails(null, null);
      } else if (!state.selectedReport || !reports.some((item) => item.run_id === state.selectedReport.run_id)) {
        await selectReport(reports[0].run_id);
      } else {
        await selectReport(state.selectedReport.run_id);
      }
    }

    function reportRecords() {
      const records = reportHelpers.reportRecords(state.runs);
      const jobRecord = reportJobRecord(state.reportJob);
      if (!jobRecord) return records;
      const duplicate = records.some((item) => item.run_id === jobRecord.run_id);
      return duplicate ? records : [jobRecord, ...records];
    }

    function renderReportLibrary() {
      const query = document.querySelector("#report-search").value.trim().toLowerCase();
      const records = reportRecords().filter((item) => !query || `${item.type} ${item.title} ${item.run_id}`.toLowerCase().includes(query));
      document.querySelector("#report-library-groups").innerHTML = records.length
        ? `<div class="report-library-list">${records.slice(0, 36).map((item) => {
          const generated = item.run_id === state.generatedReportRunId;
          return `
          <button class="report-row ${item.is_job_record ? "job" : ""} ${state.selectedReport?.run_id === item.run_id ? "active" : ""}" type="button" data-report-run-id="${escapeHtml(item.run_id)}">
            <span class="report-row-title"><span class="report-source-chip">${escapeHtml(item.type || "Report")}</span><span class="report-row-name">${escapeHtml(item.title)}${generated ? ` <span class="tag">new</span>` : ""}</span></span>
            <span class="report-row-meta">${escapeHtml(formatTimestamp(item.finished_at || item.started_at))}</span>
          </button>`;
        }).join("")}</div>`
        : `<div class="message">No reports matched the current search.</div>`;
      document.querySelectorAll("[data-report-run-id]").forEach((button) => button.addEventListener("click", () => selectReport(button.dataset.reportRunId)));
    }

    function selectReportInspectorTab(tab) {
      const nextTab = ["reports", "outline", "sources"].includes(tab) ? tab : "reports";
      state.reportInspectorTab = nextTab;
      document.querySelectorAll("[data-report-inspector-tab]").forEach((button) => {
        const active = button.dataset.reportInspectorTab === nextTab;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
      });
      document.querySelectorAll("[data-report-inspector-panel]").forEach((panel) => {
        const active = panel.dataset.reportInspectorPanel === nextTab;
        panel.classList.toggle("active", active);
        panel.hidden = !active;
      });
    }

    async function selectReport(runId) {
      const run = reportRecords().find((item) => item.run_id === runId) || {run_id: runId};
      if (run.is_job_record) {
        await selectReportJob(run);
        return;
      }
      state.selectedReport = run;
      state.selectedReportDetail = null;
      state.selectedReportPreview = null;
      state.selectedReportArtifact = null;
      state.selectedReportArtifactPreview = null;
      renderReportLibrary();
      document.querySelector("#selected-report-kicker").textContent = `${run.type || "Report"} - ${formatTimestamp(run.finished_at || run.started_at)}`;
      document.querySelector("#report-details-button").disabled = false;
      document.querySelector("#report-reader").innerHTML = `<div class="empty-state">Loading rendered report.</div>`;
      document.querySelector("#report-source-files").innerHTML = `<div class="message">Loading report sources.</div>`;
      try {
        state.selectedReportDetail = await fetchJson(`${endpoints.runs}/${encodeURIComponent(runId)}`);
      } catch (_error) {
        state.selectedReportDetail = null;
      }
      renderReportDetails(run, state.selectedReportDetail);
      const reportArtifact = reportArtifactFiles(run, state.selectedReportDetail).find((file) => file.pinned || file.category === "report")
        || {ref: run.report_path || reportPath(run), path: "report/report.md", title: "Report", category: "report", category_label: "Report", preview_kind: "markdown", pinned: true};
      renderReportSourceFiles();
      await selectReportArtifact(reportArtifact);
    }

    async function selectReportJob(run) {
      state.selectedReport = run;
      state.selectedReportDetail = null;
      state.selectedReportPreview = null;
      state.selectedReportArtifact = null;
      state.selectedReportArtifactPreview = null;
      renderReportLibrary();
      document.querySelector("#selected-report-kicker").textContent = `${run.type || "Report"} - ${formatTimestamp(run.finished_at || run.started_at)}`;
      document.querySelector("#report-details-button").disabled = false;
      const refs = reportJobRefs(run.job || state.reportJob);
      if (refs.run_id) {
        try {
          state.selectedReportDetail = await fetchJson(`${endpoints.runs}/${encodeURIComponent(refs.run_id)}`);
        } catch (_error) {
          state.selectedReportDetail = null;
        }
      }
      renderReportDetails(run, state.selectedReportDetail);
      renderReportJobSources(run.job || state.reportJob, state.selectedReportDetail);
      renderReportProgress(run.job || state.reportJob, state.selectedReportDetail);
    }

    async function refreshSelectedReportJob(job) {
      if (state.view !== "reports") return;
      const selectedJobId = state.selectedReport?.job_id || state.selectedReport?.job?.job_id;
      if (!selectedJobId || selectedJobId !== job?.job_id) return;
      const record = reportJobRecord(job);
      if (!record) return;
      await selectReportJob(record);
    }

    function renderReportSourceFiles() {
      const target = document.querySelector("#report-source-files");
      if (!target) return;
      if (!state.selectedReport) {
        target.innerHTML = `<div class="message">Select a report to inspect its sources.</div>`;
        return;
      }
      const files = reportArtifactFiles(state.selectedReport, state.selectedReportDetail);
      if (!files.length) {
        target.innerHTML = `<div class="message">No report source files were recorded for this run.</div>`;
        return;
      }
      const selectedRef = state.selectedReportArtifact?.ref || "";
      const pinned = files.filter((file) => file.pinned || file.category === "report").slice(0, 1);
      const groups = reportArtifactGroups(files);
      target.innerHTML = `
        ${pinned.map((file) => reportSourceButton(file, selectedRef, {pinned: true})).join("")}
        ${groups.map((group) => `
          <section class="report-source-group">
            <h3>${escapeHtml(group.label)} <span>${escapeHtml(String(group.items.length))}</span></h3>
            <div class="report-source-group-list">
              ${group.items.map((file) => reportSourceButton(file, selectedRef)).join("")}
            </div>
          </section>`).join("")}
      `;
      target.querySelectorAll("[data-report-artifact-ref]").forEach((button) => {
        button.addEventListener("click", () => {
          const ref = button.dataset.reportArtifactRef || "";
          const artifact = files.find((file) => file.ref === ref);
          if (artifact) selectReportArtifact(artifact);
        });
      });
    }

    function renderReportJobSources(job, detail) {
      const target = document.querySelector("#report-source-files");
      if (!target) return;
      const refs = [];
      const jobRefs = reportJobRefs(job);
      if (jobRefs.run_manifest) refs.push(["Run manifest", jobRefs.run_manifest]);
      if (jobRefs.report) refs.push(["Report", jobRefs.report]);
      const logs = job?.logs && typeof job.logs === "object" ? job.logs : {};
      if (logs.stdout_ref) refs.push(["Stdout log", logs.stdout_ref]);
      if (logs.stderr_ref) refs.push(["Stderr log", logs.stderr_ref]);
      (detail?.source_artifacts || []).forEach((ref) => refs.push(["Source", ref]));
      const uniqueRefs = unique(refs.filter((item) => item[1]).map((item) => `${item[0]}|${item[1]}`))
        .map((item) => item.split("|"));
      target.innerHTML = uniqueRefs.length
        ? `<section class="report-source-group">
            <h3>Process sources <span>${escapeHtml(String(uniqueRefs.length))}</span></h3>
            <div class="report-source-group-list">
              ${uniqueRefs.map(([title, ref]) => `
                <div class="report-source-row readonly">
                  <span class="report-source-row-main">
                    <span class="report-source-row-title">${escapeHtml(title)}</span>
                    <span class="report-source-row-path">${escapeHtml(ref)}</span>
                  </span>
                </div>`).join("")}
            </div>
          </section>`
        : `<div class="message">Process artifacts will appear as soon as the run writes them.</div>`;
    }

    function renderReportProgress(job, detail) {
      const target = document.querySelector("#report-reader");
      if (!target) return;
      const status = String(job?.status || detail?.fields?.status || "queued").toLowerCase();
      const stages = Array.isArray(detail?.stages) ? detail.stages : [];
      const percent = reportProgressPercent(status, stages);
      const milestones = reportMilestones(stages, status);
      const logs = reportProgressLogs(job, detail);
      target.innerHTML = `
        <section class="report-progress">
          <div class="report-progress-head">
            <div>
              <span class="eyebrow">Report process</span>
              <h2>${escapeHtml(label(status || "queued"))}</h2>
            </div>
            ${statusPill(status || "queued")}
          </div>
          <div class="report-progress-meter" aria-label="Report generation progress">
            <span style="width: ${Math.max(0, Math.min(100, percent))}%"></span>
          </div>
          <div class="report-progress-meta">${escapeHtml(String(Math.round(percent)))}% complete</div>
          <div class="report-milestone-list">
            ${milestones.map((item) => `
              <div class="report-milestone ${escapeHtml(statusClass(item.status))}">
                <span class="report-milestone-dot"></span>
                <span class="report-milestone-main">
                  <span class="report-milestone-title">${escapeHtml(item.label)}</span>
                  <span class="report-milestone-detail">${escapeHtml(item.detail)}</span>
                </span>
              </div>`).join("")}
          </div>
          <section class="report-log-panel">
            <h3>Live log</h3>
            <div class="report-log-stream">
              ${logs.length ? logs.slice(-80).map((line) => `<div>${escapeHtml(line)}</div>`).join("") : `<div>Waiting for the run manifest.</div>`}
            </div>
          </section>
        </section>
      `;
      renderOutline([]);
    }

    function reportProgressPercent(status, stages) {
      if (status === "succeeded") return 100;
      if (status === "failed" || status === "cancelled" || status === "blocked") {
        return stages.length ? 100 : 0;
      }
      if (!stages.length) return 5;
      const total = reportStageLabels().length;
      let score = 0;
      stages.forEach((stage) => {
        const stageStatus = String(stage.status || "").toLowerCase();
        if (stageStatus === "succeeded" || stageStatus === "skipped" || stageStatus === "not_run") score += 1;
        else if (stageStatus === "running") score += 0.5;
        else if (stageStatus === "failed") score += 1;
      });
      return Math.min(95, (score / total) * 100);
    }

    function reportMilestones(stages, jobStatus) {
      const byName = new Map((Array.isArray(stages) ? stages : []).map((stage) => [stage.name, stage]));
      return reportStageLabels().map((item) => {
        const stage = byName.get(item.name);
        const status = String(stage?.status || (reportJobIsActive({status: jobStatus}) ? "queued" : jobStatus || "queued")).toLowerCase();
        const activeTask = (stage?.tasks || []).find((task) => String(task.status || "").toLowerCase() === "running");
        const failedTask = (stage?.tasks || []).find((task) => String(task.status || "").toLowerCase() === "failed");
        const task = activeTask || failedTask;
        const detail = task
          ? `${label(task.status || status)}: ${task.name}`
          : stage?.reason
          ? stage.reason
          : stage?.finished_at
          ? formatTimestamp(stage.finished_at)
          : stage?.started_at
          ? formatTimestamp(stage.started_at)
          : "Waiting";
        return {label: item.label, status, detail};
      });
    }

    function reportStageLabels() {
      return [
        {name: "refresh_data", label: "Latest data"},
        {name: "build_source_evidence", label: "Source evidence"},
        {name: "run_strategy_research", label: "Quant strategy run"},
        {name: "synthesize_intelligence", label: "Intelligence synthesis"},
        {name: "build_materials", label: "Report materials"},
        {name: "generate_report", label: "Codex report"},
        {name: "finalize_run", label: "Finalize"},
      ];
    }

    function reportProgressLogs(job, detail) {
      const lines = [];
      if (job?.created_at) lines.push(`${formatTimestamp(job.created_at)} job ${job.job_id || "pending"} created`);
      if (job?.started_at) lines.push(`${formatTimestamp(job.started_at)} job started`);
      (detail?.stages || []).forEach((stage) => {
        if (stage.started_at) lines.push(`${formatTimestamp(stage.started_at)} stage ${stage.name} ${stage.status || "started"}`);
        (stage.tasks || []).forEach((task) => {
          if (task.started_at) lines.push(`${formatTimestamp(task.started_at)} task ${task.name} ${task.status || "started"}`);
          if (task.error?.message) lines.push(`${formatTimestamp(task.finished_at || stage.finished_at)} error ${task.name}: ${task.error.message}`);
          if (task.reason) lines.push(`${formatTimestamp(task.finished_at || stage.finished_at)} ${task.name}: ${task.reason}`);
        });
        if (stage.error?.message) lines.push(`${formatTimestamp(stage.finished_at)} error ${stage.name}: ${stage.error.message}`);
      });
      (job?.warnings || []).forEach((warning) => lines.push(`warning: ${warning}`));
      (job?.errors || []).forEach((error) => lines.push(`error: ${error}`));
      if (job?.finished_at) lines.push(`${formatTimestamp(job.finished_at)} job ${job.status || "finished"}`);
      return lines.filter(Boolean);
    }

    function reportSourceButton(file, selectedRef, options = {}) {
      const active = file.ref === selectedRef;
      const size = file.size_bytes ? formatFileSize(file.size_bytes) : file.preview_kind;
      return `
        <button class="report-source-row ${active ? "active" : ""} ${options.pinned ? "pinned" : ""}" type="button" data-report-artifact-ref="${escapeHtml(file.ref)}">
          <span class="report-source-row-main">
            <span class="report-source-row-title">${escapeHtml(file.title || file.name)}</span>
            <span class="report-source-row-path">${escapeHtml(file.path || file.ref)}</span>
          </span>
          <span class="report-source-row-meta">${escapeHtml(size || "file")}</span>
        </button>`;
    }

    function formatFileSize(bytes) {
      const value = Number(bytes || 0);
      if (!Number.isFinite(value) || value <= 0) return "";
      if (value < 1024) return `${value} B`;
      if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
      return `${(value / 1024 / 1024).toFixed(1)} MB`;
    }

    async function selectReportArtifact(artifact) {
      if (!artifact?.ref) return;
      state.selectedReportArtifact = artifact;
      renderReportSourceFiles();
      document.querySelector("#report-reader").innerHTML = `<div class="empty-state">Loading ${escapeHtml(artifact.title || artifact.name || "report source")}.</div>`;
      try {
        const preview = await fetchJson(`${endpoints.preview}?path=${encodeURIComponent(artifact.ref)}`);
        state.selectedReportArtifactPreview = preview;
        if (artifact.pinned || artifact.category === "report") {
          state.selectedReportPreview = preview;
          renderReportPreview(preview, state.selectedReport);
        } else {
          renderReportArtifactPreview(preview, artifact);
        }
      } catch (error) {
        document.querySelector("#report-reader").innerHTML = `<div class="empty-state">Report source preview is unavailable. ${escapeHtml(error.message)}</div>`;
        renderOutline([]);
      }
    }

    function renderReportDetails(run, detail) {
      const title = document.querySelector("#report-details-drawer-title");
      if (title) title.textContent = run?.title || "Report details";
      if (!run) {
        setHtml("#report-details-drawer-body", `<div class="empty-state">Select a report to inspect its details.</div>`);
        return;
      }
      const refs = reportSourceRefs(run, detail);
      const details = [
        detailRow("Type", run.type),
        detailRow("Run", run.run_id),
        detailRow("Run role", runRole(run)),
        detailRow("Status", run.status),
        detailRow("Duration", durationBetween(run.started_at, run.finished_at)),
        detailRow("Generated", formatTimestamp(run.finished_at || run.started_at)),
        detailRow("Origin", run.codex_status === "skipped" ? "Local pipeline" : "Codex report"),
      ].join("");
      setHtml("#report-details-drawer-body", `
        <div class="artifact-summary">
          <span class="report-source-chip">${escapeHtml(run.type || "Report")}</span>
          ${statusPill(run.status || "unknown")}
        </div>
        <div class="report-detail-stack">${details}</div>
        <section class="drawer-section">
          <h3>Sources</h3>
          <ul class="compact-list report-source-list">
            ${refs.length ? refs.slice(0, 12).map((source) => `<li class="compact-row">${escapeHtml(source)}</li>`).join("") : `<li class="message">No source refs recorded for this report.</li>`}
          </ul>
        </section>
      `);
    }

    function openReportDetailsDrawer() {
      if (!state.selectedReport) {
        showToast("Select a report first.");
        return;
      }
      state.reportDetailsDrawerOpen = true;
      renderReportDetails(state.selectedReport, state.selectedReportDetail);
      document.querySelector("#report-details-drawer")?.classList.remove("hidden");
      const backdrop = document.querySelector("#report-details-drawer-backdrop");
      backdrop?.classList.remove("hidden");
      backdrop?.setAttribute("aria-hidden", "false");
      document.querySelector("#report-details-drawer-close")?.focus({preventScroll: true});
    }

    function closeReportDetailsDrawer(returnFocus = true) {
      state.reportDetailsDrawerOpen = false;
      document.querySelector("#report-details-drawer")?.classList.add("hidden");
      const backdrop = document.querySelector("#report-details-drawer-backdrop");
      backdrop?.classList.add("hidden");
      backdrop?.setAttribute("aria-hidden", "true");
      if (returnFocus) document.querySelector("#report-details-button")?.focus({preventScroll: true});
    }

    function runRole(run) {
      const latest = run?.latest_state || {};
      if (latest.is_latest_run && latest.is_latest_successful_run) return "Latest run and latest successful run";
      if (latest.is_latest_run) return "Latest run";
      if (latest.is_latest_successful_run) return "Latest successful run";
      return "Historical run";
    }

    function renderReportPreview(preview, run) {
      const content = typeof preview.preview === "string" ? preview.preview : "";
      if (!content) {
        const messages = [...(preview.warnings || []), ...(preview.errors || [])];
        document.querySelector("#report-reader").innerHTML = `<div class="empty-state">${escapeHtml(messages.join(" ") || "No readable report content is recorded for this run.")}</div>`;
        renderOutline([]);
        return;
      }
      const markdown = typeof content === "string" ? content : JSON.stringify(content, null, 2);
      document.querySelector("#report-reader").innerHTML = `<article class="markdown-reader">${markdownToHtml(markdown, state.reportSearchTerm)}</article>`;
      renderOutline(annotateReportHeadings());
    }

    function renderReportArtifactPreview(preview, artifact) {
      const messages = [...(preview?.warnings || []), ...(preview?.errors || [])];
      if (!preview || preview.status !== "available") {
        document.querySelector("#report-reader").innerHTML = `
          <article class="artifact-document">
            ${artifactDocumentHeader(artifact)}
            <div class="empty-state">${escapeHtml(messages.join(" ") || "This report source cannot be rendered.")}</div>
          </article>`;
        renderOutline(annotateReportHeadings());
        return;
      }
      const kind = preview.kind === "text" && artifact.preview_kind ? artifact.preview_kind : preview.kind;
      const body = kind === "markdown"
        ? `<div class="markdown-reader">${markdownToHtml(String(preview.preview || ""), state.reportSearchTerm)}</div>`
        : kind === "json" || kind === "jsonl"
          ? renderJsonArtifact(preview.preview)
          : kind === "csv"
            ? renderCsvArtifact(String(preview.preview || ""))
            : renderTextArtifact(String(preview.preview || ""));
      document.querySelector("#report-reader").innerHTML = `
        <article class="artifact-document">
          ${artifactDocumentHeader(artifact, preview)}
          ${body}
          ${preview.truncated ? `<div class="message">Preview is bounded and does not include the full file.</div>` : ""}
        </article>`;
      renderOutline(annotateReportHeadings());
    }

    function artifactDocumentHeader(artifact, preview = null) {
      const size = artifact?.size_bytes ? formatFileSize(artifact.size_bytes) : "";
      const meta = unique([artifact?.path || artifact?.ref, preview?.kind || artifact?.preview_kind, size]).join(" - ");
      return `
        <header class="artifact-document-header">
          <div>
            <span class="report-source-chip">${escapeHtml(artifact?.category_label || "Source")}</span>
            <h1>${escapeHtml(artifact?.title || artifact?.name || "Report source")}</h1>
            <p>${escapeHtml(meta)}</p>
          </div>
        </header>`;
    }

    function renderJsonArtifact(value) {
      if (typeof value === "string") {
        try {
          return `<div class="artifact-structured">${renderJsonValue(JSON.parse(value), "Document")}</div>`;
        } catch (_error) {
          return `
            <section class="artifact-section">
              <h2>JSON preview</h2>
              <div class="artifact-list-block">
                <p>This JSON source is larger than the bounded preview and cannot be safely rendered as structured fields from the truncated sample.</p>
              </div>
            </section>`;
        }
      }
      return `<div class="artifact-structured">${renderJsonValue(value, "Document")}</div>`;
    }

    function renderJsonValue(value, label) {
      if (Array.isArray(value)) {
        return renderArrayArtifact(value, label);
      }
      if (value && typeof value === "object") {
        const entries = Object.entries(value);
        const scalarRows = entries.filter(([, item]) => !item || typeof item !== "object");
        const nested = entries.filter(([, item]) => item && typeof item === "object");
        return `
          <section class="artifact-section">
            <h2>${escapeHtml(label)}</h2>
            ${scalarRows.length ? `<div class="artifact-field-grid">${scalarRows.map(([key, item]) => artifactField(key, item)).join("")}</div>` : ""}
            ${nested.map(([key, item]) => renderJsonValue(item, key)).join("")}
          </section>`;
      }
      return `
        <section class="artifact-section">
          <h2>${escapeHtml(label)}</h2>
          <p>${escapeHtml(text(value))}</p>
        </section>`;
    }

    function renderArrayArtifact(values, label) {
      const rows = values.slice(0, 40);
      const objectRows = rows.filter((item) => item && typeof item === "object" && !Array.isArray(item));
      if (objectRows.length && objectRows.length === rows.length) {
        const headers = unique(objectRows.flatMap((item) => Object.keys(item))).slice(0, 8);
        return `
          <section class="artifact-section">
            <h2>${escapeHtml(label)} <span>${escapeHtml(String(values.length))}</span></h2>
            ${artifactTable(headers, objectRows.map((row) => headers.map((header) => formatArtifactCell(row[header]))))}
          </section>`;
      }
      return `
        <section class="artifact-section">
          <h2>${escapeHtml(label)} <span>${escapeHtml(String(values.length))}</span></h2>
          <div class="artifact-list-block">${rows.map((item) => `<p>${escapeHtml(text(item))}</p>`).join("")}</div>
        </section>`;
    }

    function artifactField(key, value) {
      return `
        <div class="artifact-field-card">
          <span>${escapeHtml(key)}</span>
          <strong>${escapeHtml(formatArtifactCell(value))}</strong>
        </div>`;
    }

    function renderCsvArtifact(content) {
      const rows = parseCsvRows(content).slice(0, 60);
      if (!rows.length) {
        return `<div class="empty-state">No rows were available in this CSV preview.</div>`;
      }
      const headers = rows[0].map((header, index) => header || `Column ${index + 1}`);
      return `
        <section class="artifact-section">
          <h2>CSV rows</h2>
          ${artifactTable(headers, rows.slice(1).map((row) => headers.map((_, index) => row[index] || "")))}
        </section>`;
    }

    function parseCsvRows(content) {
      return String(content || "").split(/\r?\n/).filter((line) => line.trim()).map((line) => {
        const cells = [];
        let current = "";
        let quoted = false;
        for (let index = 0; index < line.length; index += 1) {
          const char = line[index];
          const next = line[index + 1];
          if (char === '"' && quoted && next === '"') {
            current += '"';
            index += 1;
          } else if (char === '"') {
            quoted = !quoted;
          } else if (char === "," && !quoted) {
            cells.push(current.trim());
            current = "";
          } else {
            current += char;
          }
        }
        cells.push(current.trim());
        return cells;
      });
    }

    function renderTextArtifact(content) {
      const blocks = String(content || "").split(/\n{2,}/).map((block) => block.trim()).filter(Boolean).slice(0, 80);
      if (!blocks.length) {
        return `<div class="empty-state">No text content was available in this preview.</div>`;
      }
      return `
        <section class="artifact-section">
          <h2>Text preview</h2>
          <div class="artifact-text-blocks">
            ${blocks.map((block) => `<p>${escapeHtml(block).replace(/\n/g, "<br>")}</p>`).join("")}
          </div>
        </section>`;
    }

    function artifactTable(headers, rows) {
      return `
        <div class="markdown-table-wrap artifact-table-wrap">
          <table>
            <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
            <tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}</tbody>
          </table>
        </div>`;
    }

    function formatArtifactCell(value) {
      if (value === null || value === undefined) return "n/a";
      if (typeof value === "object") return Array.isArray(value) ? `${value.length} items` : `${Object.keys(value).length} fields`;
      return text(value);
    }

    function annotateReportHeadings() {
      const headings = Array.from(document.querySelectorAll("#report-reader .markdown-reader h1, #report-reader .markdown-reader h2, #report-reader .markdown-reader h3")).slice(0, 12);
      headings.forEach((heading, index) => {
        heading.dataset.reportHeadingIndex = String(index);
      });
      return headings.map((heading, index) => ({
        index,
        title: heading.textContent.trim() || `Section ${index + 1}`,
      }));
    }

    function renderOutline(headings) {
      document.querySelector("#report-outline").innerHTML = headings.length ? headings.map((heading) => {
        return `<li><a href="#" data-outline-index="${heading.index}">${escapeHtml(heading.title)}</a></li>`;
      }).join("") : `<li class="message">No outline extracted.</li>`;
      wireReportOutline();
    }

    function wireReportOutline() {
      document.querySelectorAll("[data-outline-index]").forEach((link) => {
        link.addEventListener("click", (event) => {
          event.preventDefault();
          const index = link.dataset.outlineIndex || "0";
          const reader = document.querySelector("#report-reader");
          const heading = document.querySelector(`#report-reader [data-report-heading-index="${CSS.escape(index)}"]`);
          if (!reader || !heading) return;
          const offset = heading.getBoundingClientRect().top - reader.getBoundingClientRect().top + reader.scrollTop - 14;
          if (reader.scrollHeight > reader.clientHeight + 2) {
            reader.scrollTo({top: Math.max(0, offset), behavior: "smooth"});
          } else {
            heading.scrollIntoView({block: "start", behavior: "smooth"});
          }
          document.querySelectorAll("[data-outline-index]").forEach((item) => item.classList.toggle("active", item === link));
        });
      });
    }

    async function deleteSelectedReport() {
      if (!state.selectedReport?.run_id) {
        showToast("Select a report first.");
        return;
      }
      const ok = await dialogs.confirmAction({
        title: "Delete report artifacts",
        message: "Delete this report's single-run artifacts? Shared data is not deleted.",
        confirmLabel: "Delete report",
        danger: true,
      });
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

    async function refreshStrategies() {
      try {
        const [strategies] = await Promise.all([
          fetchJson(endpoints.strategies),
          dataViewerWorkflow.loadDataViewerSummary(),
        ]);
        state.strategies = strategies;
      } catch (error) {
        state.strategies = {status: "failed", errors: [error.message], standalone: {backtests: [], experiments: []}, commands: {options: {}}};
        await dataViewerWorkflow.loadDataViewerSummary();
      }
      renderStrategyControls();
      renderStrategies();
      dataViewerWorkflow.renderStrategyViewer();
    }

    function strategyOutputs() {
      const standalone = state.strategies?.standalone || {};
      const shared = state.strategies?.shared_history || {};
      const sharedBacktests = Array.isArray(shared.backtests) ? shared.backtests : [];
      const standaloneBacktests = Array.isArray(standalone.backtests) ? standalone.backtests : [];
      const sharedBacktestRefs = new Set(sharedBacktests.map((item) => item?.output_dir || item?.fields?.execution_source?.output_dir || ""));
      const backtests = [
        ...sharedBacktests,
        ...standaloneBacktests.filter((item) => !sharedBacktestRefs.has(item?.output_dir || "")),
      ];
      return backtests.filter(isDisplayableBacktestOutput);
    }

    function isDisplayableBacktestOutput(item) {
      if (!item || item.type !== "strategy_backtest") return false;
      const identity = strategyIdentity(item);
      return Boolean(identity.name && identity.symbol && identity.timeframe);
    }

    function strategyProfiles() {
      const configured = state.strategies?.commands?.options?.strategy_profiles;
      if (Array.isArray(configured) && configured.length) {
        return configured.filter((profile) => profile && profile.strategy_name);
      }
      const symbols = state.strategies?.commands?.options?.symbols || [];
      const timeframes = state.strategies?.commands?.options?.timeframes || [];
      const source = defaultStrategySource();
      const fallbackSymbol = symbols[0] || "";
      const fallbackTimeframe = timeframes[0] || "";
      return strategySpecs().flatMap((spec) => {
        const targeted = Array.isArray(spec.targeted_params) ? spec.targeted_params : [];
        const profiles = targeted.length ? targeted : [{source, symbol: fallbackSymbol, timeframe: fallbackTimeframe, params: spec.configured_params || spec.default_params || {}}];
        return profiles.map((profile, index) => {
          const profileSource = profile.source || source;
          const symbol = profile.symbol || fallbackSymbol;
          const timeframe = profile.timeframe || fallbackTimeframe;
          return {
            profile_id: `${spec.name}:${profileSource}:${symbol}:${timeframe}:${index}`,
            display_name: `${symbol || "symbol"} ${timeframe || "timeframe"} - ${spec.name}`,
            strategy_name: spec.name,
            family: spec.family,
            description: spec.description,
            source: profileSource,
            symbol,
            timeframe,
            params: {...(spec.configured_params || {}), ...(profile.params || {})},
            tuned: targeted.length > 0,
            supported_market_types: spec.supported_market_types || [],
            minimum_rows_policy: spec.minimum_rows_policy || {},
          };
        });
      });
    }

    function strategyProfileId(profile) {
      return profile?.profile_id || [profile?.strategy_name, profile?.source, profile?.symbol, profile?.timeframe].filter(Boolean).join(":");
    }

    function strategyProfileLabels(profiles) {
      return Object.fromEntries(profiles.map((profile) => [strategyProfileId(profile), profile.display_name || `${profile.symbol} ${profile.timeframe} - ${profile.strategy_name}`]));
    }

    function selectedStrategyProfile(selector = "#strategy-profile") {
      const profiles = strategyProfiles();
      const selectedId = document.querySelector(selector)?.value || "";
      return profiles.find((profile) => strategyProfileId(profile) === selectedId) || profiles[0] || null;
    }

    function renderProfileSummary(selector, profile) {
      const node = document.querySelector(selector);
      if (!node) return;
      if (!profile) {
        node.innerHTML = `<div class="message">No configured strategy profile is available.</div>`;
        return;
      }
      const policy = profile.minimum_rows_policy || {};
      const params = Object.entries(profile.params || {}).slice(0, 4).map(([name, value]) => `${name}: ${value}`).join(" / ");
      node.innerHTML = `
        <div>
          <strong>${escapeHtml(profile.display_name || profile.strategy_name || "Strategy profile")}</strong>
          <p>${escapeHtml(profile.description || "Configured strategy profile ready for evaluation.")}</p>
        </div>
        <div class="strategy-profile-facts">
          <span class="chip">${escapeHtml(profile.tuned ? "configured target" : "base profile")}</span>
          <span class="chip">${escapeHtml(profile.source || "source n/a")}</span>
          <span class="chip">${escapeHtml(profile.symbol || "symbol n/a")}</span>
          <span class="chip">${escapeHtml(profile.timeframe || "timeframe n/a")}</span>
          <span class="chip">${escapeHtml(`${policy.minimum_rows_with_default_params || "n/a"} rows`)}</span>
        </div>
        ${params ? `<p class="strategy-profile-params">${escapeHtml(params)}</p>` : ""}`;
    }

    function renderStrategyProfileOverview() {
      const node = document.querySelector("#strategy-profile-overview");
      if (!node) return;
      const profiles = strategyProfiles();
      const outputs = strategyOutputs();
      if (!profiles.length) {
        node.innerHTML = `<div class="empty-state">
          <strong>No strategy profiles are configured.</strong>
          <span>Dashboard backtests require a strategy profile created by the strategy configuration pipeline.</span>
        </div>`;
        return;
      }
      if (!outputs.length) {
        const tunedCount = profiles.filter((profile) => profile.tuned).length;
        node.innerHTML = `<section class="strategy-backtest-focus">
          ${strategyFocusCell("Ready profiles", formatNumber(profiles.length), `${tunedCount} tuned target${tunedCount === 1 ? "" : "s"}`)}
          ${strategyFocusCell("Latest run", "n/a", "No stored backtest yet")}
        </section>`;
        return;
      }
      node.innerHTML = `<section class="strategy-backtest-focus">
        ${strategyBacktestFocusCells(outputs)}
      </section>`;
    }

    function strategyBacktestFocusCells(outputs) {
      const summaries = outputs.map((item) => {
        const identity = strategyIdentity(item);
        const numbers = strategyMetricNumbers(item);
        return {item, identity, numbers};
      });
      const bestReturn = bestByMetric(summaries, (item) => item.numbers.totalReturn, "max");
      const bestSharpe = bestByMetric(summaries, (item) => item.numbers.sharpe, "max");
      const lowestDrawdown = bestByMetric(
        summaries,
        (item) => Number.isFinite(item.numbers.drawdown) ? Math.abs(item.numbers.drawdown) : null,
        "min",
      );
      const latest = summaries
        .map((item) => ({...item, createdMs: createdTimeMs(item.item)}))
        .filter((item) => Number.isFinite(item.createdMs))
        .sort((a, b) => b.createdMs - a.createdMs)[0] || summaries[0];
      return [
        strategyFocusCell("Best return", bestReturn ? metricPercent(bestReturn.numbers.totalReturn) : "n/a", strategyFocusNote(bestReturn), bestReturn ? pnlClass(bestReturn.numbers.totalReturn) : ""),
        strategyFocusCell("Best Sharpe", bestSharpe ? text(bestSharpe.numbers.sharpe) : "n/a", strategyFocusNote(bestSharpe), bestSharpe ? pnlClass(bestSharpe.numbers.sharpe) : ""),
        strategyFocusCell("Lowest drawdown", lowestDrawdown ? metricPercent(lowestDrawdown.numbers.drawdown) : "n/a", strategyFocusNote(lowestDrawdown), lowestDrawdown ? pnlClass(lowestDrawdown.numbers.drawdown) : ""),
        strategyFocusCell("Latest run", latest ? formatTimestamp(createdTimeValue(latest.item)) : "n/a", strategyFocusNote(latest)),
      ].join("");
    }

    function strategyFocusCell(labelText, value, note = "", valueClass = "") {
      return `<div class="strategy-focus-cell">
        <span class="strategy-focus-label">${escapeHtml(labelText)}</span>
        <strong class="${escapeHtml(valueClass)}">${escapeHtml(value)}</strong>
        ${note ? `<span class="strategy-focus-note">${escapeHtml(note)}</span>` : ""}
      </div>`;
    }

    function strategyFocusNote(summary) {
      if (!summary) return "";
      return [summary.identity.symbol, summary.identity.timeframe, summary.identity.name].filter(Boolean).join(" / ");
    }

    function bestByMetric(items, getValue, direction) {
      const rows = items
        .map((item) => ({item, value: getValue(item)}))
        .filter((row) => Number.isFinite(row.value));
      if (!rows.length) return null;
      rows.sort((a, b) => direction === "min" ? a.value - b.value : b.value - a.value);
      return rows[0].item;
    }

    function createdTimeValue(item) {
      return item?.fields?.created_at || item?.created_at || item?.status || "";
    }

    function createdTimeMs(item) {
      const value = createdTimeValue(item);
      return value ? new Date(value).getTime() : NaN;
    }

    function syncBacktestProfileControls(force = false) {
      const profile = selectedStrategyProfile("#strategy-profile");
      if (!profile) {
        renderProfileSummary("#strategy-profile-summary", null);
        return;
      }
      const profileId = strategyProfileId(profile);
      setSelectIfPresent("#strategy-profile", profileId);
      const spec = strategySpecByName(profile.strategy_name);
      if (spec?.family) {
        setSelectIfPresent("#strategy-family", spec.family);
        fillSelect("#strategy-name", strategiesForFamily(spec.family).map((itemSpec) => itemSpec.name));
      }
      setSelectIfPresent("#strategy-name", profile.strategy_name);
      setSelectIfPresent("#strategy-symbol", profile.symbol);
      setSelectIfPresent("#strategy-timeframe", profile.timeframe);
      setInputValue("#strategy-source", profile.source || defaultStrategySource(), true);
      setInputValue("#strategy-evaluation-window", strategyActionScopeLabel("backtest"), true);
      renderProfileSummary("#strategy-profile-summary", profile);
      renderStrategySpecControls();
      if (force) {
        state.selectedStrategyOutput = null;
        queueStrategyChartRefresh({clearBacktest: true});
      }
    }

    function renderStrategyControls() {
      const options = state.strategies?.commands?.options || {};
      const sources = options.sources || ["binance"];
      const symbols = options.symbols || [];
      const timeframes = options.timeframes || [];
      const specs = strategySpecs();
      const families = strategyFamilies(specs);
      const marketTypes = options.market_types || [];
      const profiles = strategyProfiles();
      const profileIds = profiles.map(strategyProfileId);
      const profileLabels = strategyProfileLabels(profiles);
      fillDatalist("#strategy-ohlcv-source-options", sources);
      setInputValue("#strategy-source", defaultStrategySource(), true);
      setInputValue("#strategy-evaluation-window", strategyActionScopeLabel("backtest"), true);
      setText("#strategy-experiment-window", strategyActionScopeLabel("experiment"));
      fillSelect("#strategy-profile", profileIds, profileLabels);
      fillSelect("#strategy-market-type", marketTypes);
      fillSelect("#strategy-symbol", symbols);
      fillSelect("#strategy-timeframe", timeframes);
      fillSelect("#strategy-family", ["all", ...families], {"all": "All families"});
      fillSelect("#strategy-name", strategiesForFamily(document.querySelector("#strategy-family")?.value || "all").map((spec) => spec.name));
      fillSelect("#strategy-experiment-family", ["all", ...families], {"all": "All families"});
      fillSelect("#strategy-experiment-symbol", ["all", ...symbols], {"all": "All symbols"});
      fillSelect("#strategy-experiment-timeframe", ["all", ...timeframes], {"all": "All timeframes"});
      setSelectIfPresent("#strategy-experiment-family", state.strategyExperimentFilters.family || "all");
      setSelectIfPresent("#strategy-experiment-symbol", state.strategyExperimentFilters.symbol || "all");
      setSelectIfPresent("#strategy-experiment-timeframe", state.strategyExperimentFilters.timeframe || "all");
      fillSelect("#strategy-chart-symbol", symbols);
      fillSelect("#strategy-chart-timeframe", timeframes);
      syncBacktestProfileControls(false);
      renderStrategySpecControls();
      renderStrategyExperimentStrategies();
      syncStrategyOperationTabs();
      syncStrategyDataInputs(false);
      syncStrategyRangePresets(false);
      document.querySelector("#strategy-profile").onchange = () => syncBacktestProfileControls(true);
      ["#strategy-symbol", "#strategy-timeframe", "#strategy-name", "#strategy-family", "#strategy-market-type"].forEach((selector) => {
        document.querySelector(selector).onchange = () => {
          state.selectedStrategyOutput = null;
          state.strategyBacktestDetailOpen = false;
          if (selector === "#strategy-family") {
            fillSelect("#strategy-name", strategiesForFamily(document.querySelector("#strategy-family")?.value || "all").map((spec) => spec.name));
          }
          renderStrategySpecControls();
          renderStrategies();
        };
      });
      ["#strategy-experiment-family", "#strategy-experiment-symbol", "#strategy-experiment-timeframe"].forEach((selector) => {
        document.querySelector(selector).onchange = () => {
          state.strategyExperimentFilters = {
            family: document.querySelector("#strategy-experiment-family")?.value || "all",
            symbol: document.querySelector("#strategy-experiment-symbol")?.value || "all",
            timeframe: document.querySelector("#strategy-experiment-timeframe")?.value || "all",
          };
          renderStrategyExperimentStrategies();
        };
      });
      document.querySelector("#strategy-experiment-select-all").onclick = () => {
        const names = filteredExperimentChoices(experimentChoices()).map((choice) => choice.name);
        state.strategyExperimentSelection = unique([...state.strategyExperimentSelection, ...names]);
        state.strategyExperimentSelectionInitialized = true;
        renderStrategyExperimentStrategies();
      };
      document.querySelector("#strategy-experiment-clear").onclick = () => {
        const visible = new Set(filteredExperimentChoices(experimentChoices()).map((choice) => choice.name));
        state.strategyExperimentSelection = state.strategyExperimentSelection.filter((name) => !visible.has(name));
        state.strategyExperimentSelectionInitialized = true;
        renderStrategyExperimentStrategies();
      };
      queueStrategyChartRefresh();
    }

    function syncStrategyDataInputs(force = false) {
      const profile = selectedStrategyProfile("#strategy-profile");
      const symbol = document.querySelector("#strategy-symbol")?.value || profile?.symbol || "";
      const timeframe = document.querySelector("#strategy-timeframe")?.value || profile?.timeframe || "";
      const source = profile?.source || defaultStrategySource();
      setInputValue("#strategy-chart-source", source, false);
      setInputValue("#strategy-chart-symbol", symbol, force);
      setInputValue("#strategy-chart-timeframe", timeframe, force);
      setInputValue("#strategy-collect-source", source, false);
    }

    function setInputValue(selector, value, force) {
      const node = document.querySelector(selector);
      if (!node || !value) return;
      if (force || !node.value) node.value = value;
    }

    function fillSelect(selector, values, labels = {}) {
      const node = document.querySelector(selector);
      if (!node) return;
      const current = node.value;
      node.innerHTML = values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(labels[value] || value)}</option>`).join("");
      if (values.includes(current)) node.value = current;
    }

    function fillDatalist(selector, values) {
      const node = document.querySelector(selector);
      if (!node) return;
      node.innerHTML = values.map((value) => `<option value="${escapeHtml(value)}"></option>`).join("");
    }

    function defaultStrategySource() {
      const sources = state.strategies?.commands?.options?.sources || [];
      return sources[0] || "binance";
    }

    function strategyActionScopeLabel(action) {
      const scopes = state.strategies?.commands?.options?.action_scopes || {};
      const scope = scopes[action] || {};
      return scope.label || scope.window_policy || "Configured window";
    }

    function strategySpecs() {
      const specs = state.strategies?.commands?.options?.strategy_specs;
      return Array.isArray(specs) ? specs : [];
    }

    function strategyFamilies(specs = strategySpecs()) {
      return unique(specs.map((spec) => spec.family).filter(Boolean)).sort();
    }

    function strategiesForFamily(family) {
      const normalized = family || "all";
      return strategySpecs().filter((spec) => normalized === "all" || spec.family === normalized);
    }

    function strategySpecByName(name) {
      return strategySpecs().find((spec) => spec.name === name) || null;
    }

    function selectedStrategySpec() {
      return strategySpecByName(document.querySelector("#strategy-name")?.value || "");
    }

    function renderStrategySpecControls() {
      const spec = selectedStrategySpec();
      const summary = document.querySelector("#strategy-spec-summary");
      const panel = document.querySelector("#strategy-parameter-controls");
      if (!summary || !panel) return;
      if (!spec) {
        summary.innerHTML = `<div><strong>No configured strategy selected</strong>Select a strategy to inspect its family, market support, row policy, and parameter metadata.</div>`;
        panel.innerHTML = "";
        return;
      }
      const marketTypes = (spec.supported_market_types || []).join(", ") || "n/a";
      const rowPolicy = spec.minimum_rows_policy || {};
      summary.innerHTML = `
        <div><strong>${escapeHtml(spec.name)}</strong>${escapeHtml(spec.description || "No description recorded.")}</div>
        <div><strong>Family</strong>${escapeHtml(label(spec.family || "n/a"))}</div>
        <div><strong>Market support</strong>${escapeHtml(marketTypes)}</div>
        <div><strong>Rows</strong>${escapeHtml(rowPolicy.minimum_rows_with_default_params || "n/a")} minimum</div>`;
      const schema = spec.parameter_schema || {};
      const defaults = Object.keys(spec.configured_params || {}).length ? spec.configured_params : spec.default_params || {};
      panel.innerHTML = Object.entries(schema).map(([name, field]) => {
        const value = defaults[name] ?? field.default ?? "";
        const inputType = String(field.type || "").includes("integer") || String(field.type || "").includes("number") ? "number" : "text";
        const minimum = field.minimum ?? field.exclusive_minimum;
        const maximum = field.maximum;
        const constraints = Array.isArray(field.constraints) ? field.constraints.join("; ") : "";
        return `
          <div class="strategy-param-card">
            <label for="strategy-param-${escapeHtml(name)}">${escapeHtml(name)}</label>
            <input id="strategy-param-${escapeHtml(name)}" class="text-input" type="${inputType}" value="${escapeHtml(value)}" data-strategy-param="${escapeHtml(name)}" ${minimum !== undefined ? `min="${escapeHtml(minimum)}"` : ""} ${maximum !== undefined ? `max="${escapeHtml(maximum)}"` : ""} readonly>
            <p>${escapeHtml(field.description || "No parameter description recorded.")}</p>
            ${constraints ? `<p>${escapeHtml(constraints)}</p>` : ""}
          </div>`;
      }).join("");
    }

    function renderStrategyExperimentStrategies() {
      const panel = document.querySelector("#strategy-experiment-strategies");
      if (!panel) return;
      const choices = experimentChoices();
      ensureExperimentSelection(choices);
      const visibleChoices = filteredExperimentChoices(choices);
      const selectedSet = new Set(state.strategyExperimentSelection);
      if (!choices.length) {
        panel.innerHTML = `<div class="message">No configured strategy profiles are available for the benchmark suite.</div>`;
        return;
      }
      if (!visibleChoices.length) {
        panel.innerHTML = `
          <div class="strategy-lab-selection-summary">
            ${metricCell("Configured", choices.length, "strategies")}
            ${metricCell("Selected", state.strategyExperimentSelection.length, "for next validation")}
            ${metricCell("Visible", 0, "after filters")}
          </div>
          <div class="message">No strategy candidates match the current filters.</div>`;
        return;
      }
      panel.innerHTML = `
        <div class="strategy-lab-selection-summary">
          ${metricCell("Configured", choices.length, "strategies")}
          ${metricCell("Selected", state.strategyExperimentSelection.length, "for next validation")}
          ${metricCell("Visible", visibleChoices.length, "after filters")}
        </div>
        <div class="strategy-choice-list strategy-lab-choice-list">
          ${visibleChoices.map((choice) => {
        const checked = selectedSet.has(choice.name);
        return `
          <label class="strategy-choice-card strategy-lab-choice ${checked ? "selected" : ""}">
            <input type="checkbox" data-strategy-experiment-name="${escapeHtml(choice.name)}" ${checked ? "checked" : ""}>
            <span>
              <span class="strategy-profile-card-top">
                <strong>${escapeHtml(choice.displayName || choice.name)}</strong>
                <span class="chip">${escapeHtml(label(choice.family || "family n/a"))}</span>
              </span>
              <p>${escapeHtml(experimentTargetSummary(choice))}</p>
              ${choice.paramsSummary ? `<p class="strategy-profile-params">${escapeHtml(choice.paramsSummary)}</p>` : ""}
              <small>${escapeHtml(`${choice.targets.length} configured target${choice.targets.length === 1 ? "" : "s"}`)}</small>
            </span>
          </label>`;
      }).join("")}
        </div>`;
      panel.querySelectorAll("[data-strategy-experiment-name]").forEach((input) => {
        input.onchange = () => {
          const name = input.dataset.strategyExperimentName;
          state.strategyExperimentSelectionInitialized = true;
          if (input.checked && name && !state.strategyExperimentSelection.includes(name)) {
            state.strategyExperimentSelection = unique([...state.strategyExperimentSelection, name]);
          }
          if (!input.checked) {
            state.strategyExperimentSelection = state.strategyExperimentSelection.filter((item) => item !== name);
          }
          renderStrategyExperimentStrategies();
        };
      });
    }

    function experimentChoices() {
      const byName = new Map();
      strategyProfiles().forEach((profile) => {
        const name = profile.strategy_name || profile.display_name || "";
        if (!name) return;
        const spec = strategySpecByName(name);
        const current = byName.get(name) || {
          name,
          displayName: profile.display_name || name,
          family: profile.family || spec?.family || "",
          targets: [],
          paramsSummary: "",
        };
        current.targets.push(profile);
        current.family = current.family || profile.family || spec?.family || "";
        if (!current.paramsSummary) {
          current.paramsSummary = experimentParamSummary(profile.params || spec?.configured_params || spec?.default_params || {});
        }
        byName.set(name, current);
      });
      return Array.from(byName.values()).sort((left, right) => left.name.localeCompare(right.name));
    }

    function filteredExperimentChoices(choices) {
      const filters = state.strategyExperimentFilters || {};
      return choices.filter((choice) => {
        const targets = choice.targets || [];
        const family = filters.family || "all";
        const symbol = filters.symbol || "all";
        const timeframe = filters.timeframe || "all";
        return (family === "all" || choice.family === family)
          && (symbol === "all" || targets.some((profile) => profile.symbol === symbol))
          && (timeframe === "all" || targets.some((profile) => profile.timeframe === timeframe));
      });
    }

    function ensureExperimentSelection(choices) {
      const names = choices.map((choice) => choice.name);
      if (!state.strategyExperimentSelectionInitialized) {
        state.strategyExperimentSelection = names;
        state.strategyExperimentSelectionInitialized = true;
        return;
      }
      state.strategyExperimentSelection = state.strategyExperimentSelection.filter((name) => names.includes(name));
    }

    function experimentTargetSummary(choice) {
      const targets = unique((choice.targets || []).map((profile) => [
        profile.source || "source n/a",
        profile.symbol || "symbol n/a",
        profile.timeframe || "timeframe n/a",
      ].join(" / ")));
      if (!targets.length) return "No configured targets recorded.";
      if (targets.length <= 3) return targets.join(" | ");
      return `${targets.slice(0, 3).join(" | ")} | +${targets.length - 3} more`;
    }

    function experimentParamSummary(params) {
      return Object.entries(params || {})
        .slice(0, 4)
        .map(([name, value]) => `${name}: ${value}`)
        .join(" / ");
    }

    function ensureStrategyCollectTargets(symbols, timeframes) {
      if (state.strategyCollectTargets.length) return;
      const symbol = document.querySelector("#strategy-symbol")?.value || symbols[0] || "";
      const timeframe = document.querySelector("#strategy-timeframe")?.value || timeframes[0] || "";
      if (!symbol || !timeframe) return;
      state.strategyCollectTargets = [{id: nextCollectTargetId(), symbol, timeframe}];
    }

    function nextCollectTargetId() {
      return `target-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
    }

    function renderStrategyCollectTargets() {
      const target = document.querySelector("#strategy-collect-targets");
      if (!target) return;
      target.innerHTML = state.strategyCollectTargets.length
        ? state.strategyCollectTargets.map((item) => `
          <div class="collect-target-row" data-collect-target-id="${escapeHtml(item.id)}">
            <span class="collect-target-symbol">${escapeHtml(item.symbol)}</span>
            <span class="collect-target-timeframe">${escapeHtml(item.timeframe)}</span>
            <button class="icon-button" type="button" data-collect-target-remove="${escapeHtml(item.id)}" title="Remove target" aria-label="Remove ${escapeHtml(item.symbol)} ${escapeHtml(item.timeframe)}">x</button>
          </div>`).join("")
        : `<div class="message">Add at least one symbol and timeframe to collect OHLCV data.</div>`;
      document.querySelectorAll("[data-collect-target-remove]").forEach((button) => {
        button.onclick = () => {
          const id = button.dataset.collectTargetRemove;
          state.strategyCollectTargets = state.strategyCollectTargets.filter((item) => item.id !== id);
          renderStrategyCollectTargets();
          queueStrategyCollectTimelineRefresh();
        };
      });
      queueStrategyCollectTimelineRefresh();
    }

    function addStrategyCollectTarget() {
      const symbol = document.querySelector("#strategy-collect-symbol")?.value || "";
      const timeframe = document.querySelector("#strategy-collect-timeframe")?.value || "";
      if (!symbol || !timeframe) {
        showToast("Select a symbol and timeframe first.");
        return;
      }
      const duplicate = state.strategyCollectTargets.some((item) => item.symbol === symbol && item.timeframe === timeframe);
      if (duplicate) {
        showToast(`${symbol} ${timeframe} is already selected.`);
        return;
      }
      state.strategyCollectTargets.push({id: nextCollectTargetId(), symbol, timeframe});
      renderStrategyCollectTargets();
    }

    function strategyOhlcvCoverage() {
      const stores = Array.isArray(state.dataViewerSummary?.stores) ? state.dataViewerSummary.stores : [];
      return stores.find((store) => store.data_type === "ohlcv")?.coverage || {};
    }

    function syncStrategyRangePresets(force = false) {
      applyRangePreset("#strategy-backtest-range", "#strategy-backtest-start", "#strategy-backtest-end", force);
      applyRangePreset("#strategy-collect-range", "#strategy-collect-start", "#strategy-collect-end", force);
    }

    function presetDateRange(value) {
      const coverage = strategyOhlcvCoverage();
      const anchor = parseIsoDate(coverage.range_end) || new Date();
      if (value === "custom") return null;
      if (value === "all") {
        if (coverage.range_start && coverage.range_end) {
          return {start: coverage.range_start, end: coverage.range_end};
        }
        return {
          start: toIsoSecond(new Date(anchor.getTime() - 7 * 24 * 3600 * 1000)),
          end: toIsoSecond(anchor),
        };
      }
      const days = value === "1d" ? 1 : value === "7d" ? 7 : value === "30d" ? 30 : value === "90d" ? 90 : value === "180d" ? 180 : 7;
      return {
        start: toIsoSecond(new Date(anchor.getTime() - days * 24 * 3600 * 1000)),
        end: toIsoSecond(anchor),
      };
    }

    function applyRangePreset(rangeSelector, startSelector, endSelector, force = false) {
      const range = document.querySelector(rangeSelector);
      const start = document.querySelector(startSelector);
      const end = document.querySelector(endSelector);
      if (!range || !start || !end) return;
      if (!force && start.value && end.value) {
        syncDateRangePickerByInputs(startSelector, endSelector);
        return;
      }
      const value = range.value || "all";
      const nextRange = presetDateRange(value);
      if (!nextRange) {
        syncDateRangePickerByInputs(startSelector, endSelector);
        return;
      }
      start.value = nextRange.start;
      end.value = nextRange.end;
      syncDateRangePickerByInputs(startSelector, endSelector);
    }

    function wireDateRangePickers() {
      document.querySelectorAll("[data-date-range-picker]").forEach((field) => {
        if (field.dataset.rangePickerWired === "true") {
          syncDateRangePickerLabel(field);
          return;
        }
        field.dataset.rangePickerWired = "true";
        const controls = dateRangePickerControls(field);
        controls.trigger?.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          const isOpening = controls.popover?.classList.contains("hidden");
          closeDateRangePickers();
          if (isOpening) {
            initializeDateRangePickerState(field);
            renderDateRangePicker(field);
            controls.popover?.classList.remove("hidden");
            controls.trigger?.setAttribute("aria-expanded", "true");
          }
        });
        controls.popover?.addEventListener("click", (event) => {
          event.stopPropagation();
          handleDateRangePickerClick(event, field);
        });
        controls.popover?.addEventListener("input", (event) => handleDateRangePickerInput(event, field));
        syncDateRangePickerLabel(field);
      });
      if (!state.dateRangePickerGlobalWired) {
        state.dateRangePickerGlobalWired = true;
        document.addEventListener("click", (event) => {
          if (!event.target.closest("[data-date-range-picker]")) {
            closeDateRangePickers();
          }
        });
        document.addEventListener("keydown", (event) => {
          if (event.key === "Escape") closeDateRangePickers();
        });
      }
    }

    function dateRangePickerControls(field) {
      return {
        start: document.getElementById(field.dataset.startInput || ""),
        end: document.getElementById(field.dataset.endInput || ""),
        preset: document.getElementById(field.dataset.presetInput || ""),
        trigger: field.querySelector(".range-picker-trigger"),
        label: field.querySelector("[data-range-picker-label]"),
        popover: field.querySelector(".range-picker-popover"),
      };
    }

    function syncDateRangePickerByInputs(startSelector, endSelector) {
      const startId = selectorToId(startSelector);
      const endId = selectorToId(endSelector);
      document.querySelectorAll("[data-date-range-picker]").forEach((field) => {
        if (field.dataset.startInput === startId && field.dataset.endInput === endId) {
          syncDateRangePickerLabel(field);
          if (!field.querySelector(".range-picker-popover")?.classList.contains("hidden")) {
            renderDateRangePicker(field);
          }
        }
      });
    }

    function selectorToId(selector) {
      return String(selector || "").replace(/^#/, "");
    }

    function syncDateRangePickerLabel(field) {
      const controls = dateRangePickerControls(field);
      if (!controls.label) return;
      const startLabel = compactUtcDateTime(controls.start?.value);
      const endLabel = compactUtcDateTime(controls.end?.value);
      controls.label.textContent = startLabel && endLabel ? `${startLabel} -> ${endLabel}` : "Choose range";
      if (controls.trigger) {
        controls.trigger.title = startLabel && endLabel ? `${startLabel} UTC to ${endLabel} UTC` : "Choose start and end time";
        controls.trigger.setAttribute("aria-expanded", controls.popover?.classList.contains("hidden") ? "false" : "true");
      }
    }

    function initializeDateRangePickerState(field) {
      const controls = dateRangePickerControls(field);
      const startDate = parseIsoDate(controls.start?.value);
      const endDate = parseIsoDate(controls.end?.value);
      field.dataset.pendingStart = startDate ? utcDateKey(startDate) : "";
      field.dataset.pendingEnd = endDate ? utcDateKey(endDate) : "";
      field.dataset.pendingStartTime = startDate ? utcTimeKey(startDate) : "00:00:00";
      field.dataset.pendingEndTime = endDate ? utcTimeKey(endDate) : "23:59:59";
      field.dataset.pendingPreset = "";
      const monthKey = (field.dataset.pendingStart || field.dataset.pendingEnd || utcDateKey(new Date())).slice(0, 7);
      field.dataset.visibleMonth = monthKey;
    }

    function renderDateRangePicker(field) {
      const controls = dateRangePickerControls(field);
      const popover = controls.popover;
      if (!popover) return;
      const monthKey = field.dataset.visibleMonth || utcDateKey(new Date()).slice(0, 7);
      const [year, month] = monthKey.split("-").map((part) => Number(part));
      const firstDay = new Date(Date.UTC(year, month - 1, 1));
      const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
      const leading = firstDay.getUTCDay();
      const cells = [];
      for (let index = 0; index < leading; index += 1) {
        cells.push(`<span class="range-picker-day empty"></span>`);
      }
      for (let day = 1; day <= daysInMonth; day += 1) {
        const dateKey = `${monthKey}-${String(day).padStart(2, "0")}`;
        const classes = ["range-picker-day", dateRangeDayClass(field, dateKey)].filter(Boolean).join(" ");
        cells.push(`<button class="${classes}" type="button" data-range-day="${escapeHtml(dateKey)}">${day}</button>`);
      }
      popover.innerHTML = `
        <div class="range-picker-head">
          <button class="ghost-button compact-button" type="button" data-range-month-shift="-1">Prev</button>
          <strong>${escapeHtml(monthLabel(monthKey))}</strong>
          <button class="ghost-button compact-button" type="button" data-range-month-shift="1">Next</button>
        </div>
        <div class="range-picker-presets">
          ${rangeQuickButtons()}
        </div>
        <div class="range-picker-weekdays">${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => `<span>${day}</span>`).join("")}</div>
        <div class="range-picker-grid">${cells.join("")}</div>
        <div class="range-picker-times">
          <label>Start time<input class="text-input" type="time" step="1" data-range-start-time value="${escapeHtml(normalizeTime(field.dataset.pendingStartTime, "00:00:00"))}"></label>
          <label>End time<input class="text-input" type="time" step="1" data-range-end-time value="${escapeHtml(normalizeTime(field.dataset.pendingEndTime, "23:59:59"))}"></label>
        </div>
        <div class="range-picker-actions">
          <button class="ghost-button compact-button" type="button" data-range-cancel>Cancel</button>
          <button class="primary-button compact-button" type="button" data-range-apply>Apply</button>
        </div>
      `;
    }

    function rangeQuickButtons() {
      return [
        ["1d", "1D"],
        ["7d", "7D"],
        ["30d", "30D"],
        ["180d", "180D"],
      ].map(([value, labelText]) => `<button class="ghost-button compact-button" type="button" data-range-quick="${value}">${labelText}</button>`).join("");
    }

    function dateRangeDayClass(field, dateKey) {
      const start = field.dataset.pendingStart || "";
      const end = field.dataset.pendingEnd || "";
      if (!start && !end) return "";
      const normalizedEnd = end || start;
      const classes = [];
      if (dateKey === start) classes.push("range-start");
      if (dateKey === normalizedEnd) classes.push("range-end");
      if (dateKey > start && dateKey < normalizedEnd) classes.push("in-range");
      if (dateKey === start || dateKey === normalizedEnd || (dateKey > start && dateKey < normalizedEnd)) {
        classes.push("selected");
      }
      return classes.join(" ");
    }

    function handleDateRangePickerClick(event, field) {
      const monthButton = event.target.closest("[data-range-month-shift]");
      if (monthButton) {
        field.dataset.visibleMonth = shiftMonthKey(field.dataset.visibleMonth, Number(monthButton.dataset.rangeMonthShift) || 0);
        renderDateRangePicker(field);
        return;
      }
      const quickButton = event.target.closest("[data-range-quick]");
      if (quickButton) {
        applyDateRangeQuick(field, quickButton.dataset.rangeQuick);
        renderDateRangePicker(field);
        return;
      }
      const dayButton = event.target.closest("[data-range-day]");
      if (dayButton) {
        applyDateRangeDay(field, dayButton.dataset.rangeDay);
        renderDateRangePicker(field);
        return;
      }
      if (event.target.closest("[data-range-cancel]")) {
        closeDateRangePickers();
        return;
      }
      if (event.target.closest("[data-range-apply]")) {
        applyDateRangePickerSelection(field);
      }
    }

    function handleDateRangePickerInput(event, field) {
      if (event.target.matches("[data-range-start-time]")) {
        field.dataset.pendingStartTime = normalizeTime(event.target.value, "00:00:00");
      }
      if (event.target.matches("[data-range-end-time]")) {
        field.dataset.pendingEndTime = normalizeTime(event.target.value, "23:59:59");
      }
    }

    function applyDateRangeDay(field, dateKey) {
      field.dataset.pendingPreset = "custom";
      const start = field.dataset.pendingStart || "";
      const end = field.dataset.pendingEnd || "";
      if (!start || end) {
        field.dataset.pendingStart = dateKey;
        field.dataset.pendingEnd = "";
        return;
      }
      if (dateKey < start) {
        field.dataset.pendingStart = dateKey;
        field.dataset.pendingEnd = start;
        return;
      }
      field.dataset.pendingEnd = dateKey;
    }

    function applyDateRangeQuick(field, value) {
      const days = value === "1d" ? 1 : value === "7d" ? 7 : value === "30d" ? 30 : value === "180d" ? 180 : 7;
      const controls = dateRangePickerControls(field);
      const anchor = parseIsoDate(controls.end?.value) || new Date();
      const start = new Date(anchor.getTime() - days * 24 * 3600 * 1000);
      field.dataset.pendingStart = utcDateKey(start);
      field.dataset.pendingEnd = utcDateKey(anchor);
      field.dataset.pendingStartTime = utcTimeKey(start);
      field.dataset.pendingEndTime = utcTimeKey(anchor);
      field.dataset.visibleMonth = field.dataset.pendingStart.slice(0, 7);
      field.dataset.pendingPreset = value;
    }

    function applyDateRangePickerSelection(field) {
      const controls = dateRangePickerControls(field);
      if (!controls.start || !controls.end) return;
      const startDate = field.dataset.pendingStart || field.dataset.pendingEnd;
      const endDate = field.dataset.pendingEnd || field.dataset.pendingStart;
      if (!startDate || !endDate) {
        showToast("Choose at least one date for the time window.");
        return;
      }
      const startValue = `${startDate}T${normalizeTime(field.dataset.pendingStartTime, "00:00:00")}Z`;
      const endValue = `${endDate}T${normalizeTime(field.dataset.pendingEndTime, "23:59:59")}Z`;
      if (Date.parse(startValue) > Date.parse(endValue)) {
        showToast("Start time must be before end time.");
        return;
      }
      controls.start.value = startValue;
      controls.end.value = endValue;
      if (controls.preset) {
        controls.preset.value = field.dataset.pendingPreset && field.dataset.pendingPreset !== "custom"
          ? field.dataset.pendingPreset
          : "custom";
      }
      syncDateRangePickerLabel(field);
      closeDateRangePickers();
      dispatchInputChange(controls.start);
      dispatchInputChange(controls.end);
    }

    function dispatchInputChange(input) {
      input.dispatchEvent(new Event("change", {bubbles: true}));
    }

    function closeDateRangePickers() {
      document.querySelectorAll("[data-date-range-picker]").forEach((field) => {
        const controls = dateRangePickerControls(field);
        controls.popover?.classList.add("hidden");
        controls.trigger?.setAttribute("aria-expanded", "false");
      });
    }

    function utcDateKey(date) {
      return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-${String(date.getUTCDate()).padStart(2, "0")}`;
    }

    function utcTimeKey(date) {
      return `${String(date.getUTCHours()).padStart(2, "0")}:${String(date.getUTCMinutes()).padStart(2, "0")}:${String(date.getUTCSeconds()).padStart(2, "0")}`;
    }

    function compactUtcDateTime(value) {
      const date = parseIsoDate(value);
      if (!date) return value ? String(value) : "";
      return `${utcDateKey(date)} ${utcTimeKey(date)}`;
    }

    function normalizeTime(value, fallback) {
      const raw = String(value || "").trim();
      if (/^\d{2}:\d{2}:\d{2}$/.test(raw)) return raw;
      if (/^\d{2}:\d{2}$/.test(raw)) return `${raw}:00`;
      return fallback;
    }

    function monthLabel(monthKey) {
      const [year, month] = String(monthKey || "").split("-").map((part) => Number(part));
      if (!year || !month) return "Select range";
      const monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
      return `${monthNames[month - 1]} ${year}`;
    }

    function shiftMonthKey(monthKey, delta) {
      const [year, month] = String(monthKey || utcDateKey(new Date()).slice(0, 7)).split("-").map((part) => Number(part));
      const shifted = new Date(Date.UTC(year || new Date().getUTCFullYear(), (month || 1) - 1 + delta, 1));
      return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, "0")}`;
    }

    function parseIsoDate(value) {
      const time = value ? new Date(value) : null;
      return time && Number.isFinite(time.getTime()) ? time : null;
    }

    function toIsoSecond(date) {
      return date.toISOString().replace(/\.\d{3}Z$/, "Z");
    }

    function renderStrategies() {
      const outputs = strategyOutputs();
      const selected = state.strategyOperationTab === "backtest" ? selectedStrategyOutput(outputs) : null;
      if (state.strategyOperationTab === "backtest") {
        state.selectedStrategyOutput = selected;
        if (!selected) state.strategyBacktestDetailOpen = false;
      } else {
        state.strategyBacktestDetailOpen = false;
      }
      renderStrategyProfileOverview();
      syncStrategyControls(selected);
      syncStrategyDataInputs(false);
      syncStrategyOperationTabs();
      renderBacktestRuns(outputs);
      if (state.strategyOperationTab === "backtest" && state.strategyBacktestDetailOpen && selected) {
        renderBacktestDetail(selected);
      }
      renderStrategyExperimentResults();
    }

    function renderBacktestDetail(selected) {
      renderStrategyDetailHeader(selected);
      const vis = visibleStrategyVisualization(selected);
      setText("#strategy-window-label", strategyChart.strategyWindowLabel(
        vis,
        displayTimezone,
      ));
      setText("#strategy-chart-clock", displayTimezone);
      syncStrategyWindowControls();
      strategyChart.renderCandlestickSvg("#backtest-chart", vis, {displayTimezone, pnlColorScheme});
      if (state.strategyParamsDrawerOpen) renderStrategyParamsDrawer(selected, vis);
      renderStrategyOperationTree(fullBacktestVisualization(selected));
      renderStrategyTab(currentStrategyTab());
    }

    function renderStrategyDetailHeader(selected) {
      const title = document.querySelector("#strategy-detail-title");
      const kicker = document.querySelector("#strategy-detail-kicker");
      if (!title || !kicker) return;
      if (!selected) {
        kicker.textContent = "Backtest detail";
        title.textContent = "Select a backtest run";
        return;
      }
      const identity = strategyIdentity(selected);
      const vis = backtestVisualization(selected);
      const created = selected?.fields?.created_at || selected?.created_at || "";
      const source = selected?.fields?.source || selected?.source || vis.source || document.querySelector("#strategy-chart-source")?.value || "";
      const status = vis.status || selected?.status || "";
      kicker.textContent = [
        source,
        identity.symbol,
        identity.timeframe,
        formatTimestamp(created),
        status ? label(status) : "",
      ].filter(Boolean).join(" / ") || "Backtest detail";
      title.textContent = identity.name || "Strategy backtest";
    }

    function closeStrategyDetailActionMenu() {
      document.querySelector(".strategy-detail-action-shell")?.classList.remove("open");
      document.querySelector("#strategy-detail-action-menu")?.setAttribute("aria-expanded", "false");
    }

    function toggleStrategyDetailActionMenu() {
      const shell = document.querySelector(".strategy-detail-action-shell");
      const button = document.querySelector("#strategy-detail-action-menu");
      if (!shell || !button) return;
      const isOpen = !shell.classList.contains("open");
      shell.classList.toggle("open", isOpen);
      button.setAttribute("aria-expanded", isOpen ? "true" : "false");
    }

    function setStrategyOperationTab(tab) {
      state.strategyOperationTab = ["backtest", "experiment"].includes(tab) ? tab : "backtest";
      if (state.strategyOperationTab !== "backtest") state.strategyBacktestDetailOpen = false;
      syncStrategyOperationTabs();
      renderStrategies();
    }

    function syncStrategyOperationTabs() {
      const detailOpen = state.strategyOperationTab === "backtest" && state.strategyBacktestDetailOpen && Boolean(state.selectedStrategyOutput);
      document.querySelector("#strategy-workbench")?.classList.toggle("hidden", detailOpen);
      document.querySelector("#strategy-backtest-detail")?.classList.toggle("hidden", !detailOpen);
      document.querySelectorAll("[data-strategy-operation-tab]").forEach((button) => {
        button.classList.toggle("active", button.dataset.strategyOperationTab === state.strategyOperationTab);
      });
      document.querySelectorAll("[data-strategy-operation-panel]").forEach((panel) => {
        panel.classList.toggle("hidden", detailOpen || panel.dataset.strategyOperationPanel !== state.strategyOperationTab);
      });
      document.querySelectorAll("[data-backtest-only]").forEach((panel) => {
        panel.classList.toggle("hidden", !detailOpen);
      });
    }

    function selectedStrategyOutput(outputs) {
      const selectedName = document.querySelector("#strategy-name")?.value || "";
      const selectedSymbol = document.querySelector("#strategy-symbol")?.value || "";
      const selectedTimeframe = document.querySelector("#strategy-timeframe")?.value || "";
      if (!state.selectedStrategyOutput || !outputs.includes(state.selectedStrategyOutput)) {
        return null;
      }
      const identity = strategyIdentity(state.selectedStrategyOutput);
      const matchesControls = (!selectedName || identity.name === selectedName)
        && (!selectedSymbol || identity.symbol === selectedSymbol)
        && (!selectedTimeframe || identity.timeframe === selectedTimeframe);
      if (matchesControls) return state.selectedStrategyOutput;
      return null;
    }

    function filteredStrategyOutputs(outputs) {
      const selectedName = document.querySelector("#strategy-name")?.value || "";
      const selectedSymbol = document.querySelector("#strategy-symbol")?.value || "";
      const selectedTimeframe = document.querySelector("#strategy-timeframe")?.value || "";
      return outputs.filter((item) => {
        const identity = strategyIdentity(item);
        return (!selectedName || identity.name === selectedName)
          && (!selectedSymbol || identity.symbol === selectedSymbol)
          && (!selectedTimeframe || identity.timeframe === selectedTimeframe);
      });
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
      if (!item) {
        return;
      }
      const spec = strategySpecByName(identity.name);
      if (spec?.family) {
        setSelectIfPresent("#strategy-family", spec.family);
        fillSelect("#strategy-name", strategiesForFamily(spec.family).map((itemSpec) => itemSpec.name));
      }
      setSelectIfPresent("#strategy-name", identity.name);
      setSelectIfPresent("#strategy-symbol", identity.symbol);
      setSelectIfPresent("#strategy-timeframe", identity.timeframe);
      renderStrategySpecControls();
    }

    function setSelectIfPresent(selector, value) {
      const node = document.querySelector(selector);
      if (!node || value === null || value === undefined) return;
      const raw = String(value);
      if (Array.from(node.options).some((option) => option.value === raw)) {
        node.value = raw;
      }
    }

    function strategyMetrics(item) {
      const fields = item?.fields || {};
      const metrics = fields.metrics || {};
      const strategy = metrics.strategy_metrics || fields.strategy_metrics || {};
      const trade = strategyTradeSummary(item);
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

    function strategyMetricNumbers(item) {
      const fields = item?.fields || {};
      const metrics = fields.metrics || {};
      const strategy = metrics.strategy_metrics || fields.strategy_metrics || {};
      const trade = strategyTradeSummary(item);
      return {
        totalReturn: numberFromMetric(strategy.net_return_pct ?? strategy.total_return_pct ?? item?.records?.summary?.net_return_pct),
        drawdown: numberFromMetric(strategy.max_drawdown_pct),
        sharpe: numberFromMetric(strategy.sharpe_ratio ?? strategy.sharpe),
        trades: numberFromMetric(trade.trade_count ?? fields.metrics?.trade_summary?.trade_count),
      };
    }

    function numberFromMetric(value) {
      if (typeof value === "number" && Number.isFinite(value)) return value;
      if (typeof value !== "string") return null;
      const cleaned = value.replace(/[%,\s$]/g, "");
      const number = Number(cleaned);
      return Number.isFinite(number) ? number : null;
    }

    function strategyTradeSummary(item) {
      const fields = item?.fields || {};
      const metrics = fields.metrics || {};
      return metrics.trade_summary || fields.trade_summary || {};
    }

    function numericOrNull(value) {
      const number = Number(value);
      return Number.isFinite(number) ? number : null;
    }

    function omittedVisualizationMarkers(vis) {
      return Math.max(0, numericOrNull(vis?.omitted?.markers) || 0);
    }

    function metricPercent(value) {
      const number = Number(value);
      if (!Number.isFinite(number)) return "n/a";
      const sign = number > 0 ? "+" : "";
      return `${sign}${number.toFixed(2)}%`;
    }

    function backtestVisualization(item) {
      const vis = item?.visualization || {};
      if ((Array.isArray(vis.bars) && vis.bars.length)
        || (Array.isArray(vis.markers) && vis.markers.length)
        || (Array.isArray(vis.equity_curve) && vis.equity_curve.length)
        || (Array.isArray(vis.equity_sparkline) && vis.equity_sparkline.length)) {
        return vis;
      }
      const identity = strategyIdentity(item);
      return {
        status: item?.status || "missing",
        strategy_name: identity.name,
        symbol: identity.symbol,
        timeframe: identity.timeframe,
        bars: [],
        markers: [],
        equity_curve: [],
        equity_sparkline: [],
      };
    }

    function visibleStrategyVisualization(item) {
      return applyStrategyWindow(strategyVisualization(item), state.strategyWindow, state.strategyFocusedMarkerTime);
    }

    function strategyVisualization(item) {
      const dataVis = state.strategyDataVisualization;
      if (!item) {
        return dataVis || emptyStrategyVisualization();
      }
      const backtestVis = backtestVisualization(item);
      const sampleWindow = backtestSampleWindow(item);
      if (sampleWindow && !dataVisualizationMatchesBacktestWindow(dataVis, sampleWindow)) {
        return backtestVis;
      }
      if (Array.isArray(backtestVis.bars) && backtestVis.bars.length && !canOverlayBacktest(dataVis, backtestVis)) {
        return backtestVis;
      }
      if (canOverlayBacktest(dataVis, backtestVis)) {
        return {
          ...dataVis,
          chart_type: "candlestick_backtest",
          status: backtestVis.status || item.status || dataVis.status,
          strategy_name: backtestVis.strategy_name,
          markers: Array.isArray(backtestVis.markers) ? backtestVis.markers : [],
          equity_curve: Array.isArray(backtestVis.equity_curve) ? backtestVis.equity_curve : [],
          warnings: [...(dataVis.warnings || []), ...(backtestVis.warnings || [])],
        };
      }
      return backtestVis;
    }

    function emptyStrategyVisualization() {
      return {
        chart_type: "candlestick_data_viewer",
        status: "missing",
        strategy_name: "",
        source: document.querySelector("#strategy-chart-source")?.value || defaultStrategySource(),
        symbol: document.querySelector("#strategy-chart-symbol")?.value || document.querySelector("#strategy-symbol")?.value || "",
        timeframe: document.querySelector("#strategy-chart-timeframe")?.value || document.querySelector("#strategy-timeframe")?.value || "",
        bars: [],
        markers: [],
        equity_curve: [],
      };
    }

    function canOverlayBacktest(dataVis, backtestVis) {
      if (!dataVis || !Array.isArray(dataVis.bars) || !dataVis.bars.length) return false;
      if (!backtestVis || !Array.isArray(backtestVis.markers)) return false;
      return String(dataVis.symbol || "") === String(backtestVis.symbol || "")
        && String(dataVis.timeframe || "") === String(backtestVis.timeframe || "");
    }

    function renderStrategyOhlcvPreview(payload, request, options = {}) {
      state.strategyDataVisualization = ohlcvPreviewVisualization(payload, request);
      if (options.clearBacktest !== false) {
        state.selectedStrategyOutput = null;
        state.strategyBacktestDetailOpen = false;
        setSelectIfPresent("#strategy-name", "");
      }
      strategyChart.resetCandlestickView("#backtest-chart");
      renderStrategies();
    }

    function ohlcvPreviewVisualization(payload, request) {
      const records = Array.isArray(payload?.records) ? payload.records : [];
      return {
        chart_type: "candlestick_data_viewer",
        status: payload?.status || "ok",
        strategy_name: "",
        source: payload?.source || request?.source || defaultStrategySource(),
        symbol: request?.symbol || payload?.identity?.symbol || "",
        timeframe: request?.timeframe || payload?.identity?.timeframe || "",
        bars: records.map((record) => ({
          time: record.open_time,
          open: record.open,
          high: record.high,
          low: record.low,
          close: record.close,
          volume: record.volume,
        })).filter((bar) => bar.time),
        markers: [],
        equity_curve: [],
        warnings: payload?.warnings || [],
        query: payload?.query || {},
        backtest_window: Boolean(request?.backtest_window),
        request_start: request?.start || "",
        request_end: request?.end || "",
      };
    }

    function visibleBacktestVisualization(item) {
      return applyStrategyWindow(backtestVisualization(item), state.strategyWindow, state.strategyFocusedMarkerTime);
    }

    function fullBacktestVisualization(item) {
      return backtestVisualization(item);
    }

    function strategyChartWindowValue(value) {
      const normalized = String(value || "30");
      return ["30", "90", "180", "360"].includes(normalized) ? normalized : "30";
    }

    function applyStrategyWindow(vis, windowValue, focusTime = "") {
      const bars = Array.isArray(vis.bars) ? vis.bars : [];
      const limit = Number(strategyChartWindowValue(windowValue));
      if (!Number.isInteger(limit) || limit <= 0 || bars.length <= limit) {
        return vis;
      }
      const focusIndex = focusTime ? bars.findIndex((bar) => String(bar.time || bar.open_time || "") === String(focusTime)) : -1;
      const start = focusIndex >= 0
        ? Math.min(Math.max(0, focusIndex - Math.floor(limit / 2)), Math.max(0, bars.length - limit))
        : Math.max(0, bars.length - limit);
      const visibleBars = bars.slice(start, start + limit);
      const visibleTimes = new Set(visibleBars.map((bar) => bar.time));
      const markers = Array.isArray(vis.markers)
        ? vis.markers.filter((marker) => visibleTimes.has(marker.time))
        : [];
      const curve = Array.isArray(vis.equity_curve)
        ? vis.equity_curve.filter((point) => visibleTimes.has(point.time))
        : [];
      return {...vis, bars: visibleBars, markers, equity_curve: curve, focused_marker_time: focusIndex >= 0 ? focusTime : ""};
    }

    function setStrategyWindow(value, options = {}) {
      state.strategyWindow = strategyChartWindowValue(value);
      state.strategyFocusedMarkerTime = "";
      const range = document.querySelector("#strategy-chart-range");
      if (range) range.value = state.strategyWindow;
      syncStrategyWindowControls();
      strategyChart.resetCandlestickView("#backtest-chart");
      renderStrategies();
      if (options.reload) {
        queueStrategyChartRefresh({clearBacktest: options.clearBacktest});
      }
    }

    function syncStrategyWindowControls() {
      const range = document.querySelector("#strategy-chart-range");
      if (range) range.value = state.strategyWindow;
    }

    function strategyName(item) {
      return strategyIdentity(item).name || "No strategy selected";
    }

    function renderStrategyParamsDrawer(item, vis = null) {
      const body = document.querySelector("#strategy-params-drawer-body");
      const title = document.querySelector("#strategy-params-drawer-title");
      if (!body) return;
      if (!item) {
        if (title) title.textContent = "Strategy parameters";
        body.innerHTML = `<div class="empty-state">Select a backtest run to inspect parameters.</div>`;
        return;
      }
      const visual = vis || visibleStrategyVisualization(item);
      const identity = strategyIdentity(item);
      if (title) title.textContent = identity.name || "Strategy parameters";
      const sections = strategyParameterSections(item, visual);
      body.innerHTML = `
        <div class="artifact-summary">
          ${statusPill(item.status || item.fields?.status || visual.status || "unknown")}
          <span class="tag">${escapeHtml(identity.symbol || "symbol n/a")}</span>
          <span class="tag">${escapeHtml(identity.timeframe || "timeframe n/a")}</span>
          <span class="tag">${escapeHtml(visual.source || item.fields?.source || "source n/a")}</span>
        </div>
        ${sections.map((section) => `
          <section class="drawer-section">
            <h3>${escapeHtml(section.title)}</h3>
            ${section.rows.length ? kvRows(section.rows) : `<div class="message">${escapeHtml(section.empty || "No values recorded.")}</div>`}
          </section>`).join("")}`;
    }

    function strategyParameterSections(item, vis) {
      const fields = item?.fields || {};
      const inputs = objectValue(fields.inputs);
      const metrics = objectValue(fields.metrics);
      const identity = strategyIdentity(item);
      const window = backtestRunWindow(item);
      const runParams = {...objectValue(inputs.params), ...objectValue(fields.params)};
      const spec = strategySpecByName(identity.name);
      const configuredParams = objectValue(spec?.configured_params && Object.keys(spec.configured_params).length ? spec.configured_params : spec?.default_params);
      const strategyParams = {...configuredParams, ...runParams};
      const inputRows = objectRows(inputs, new Set(["params"]));
      const executionRows = [
        ...objectRows(metrics.execution_model),
        ...objectRows(metrics.cost_assumptions),
      ];
      return [
        {
          title: "Run",
          rows: [
            ["Strategy", identity.name],
            ["Created", formatTimestamp(fields.created_at || item?.created_at)],
            ["Status", item.status || fields.status || vis.status],
            ["Source", fields.source || inputs.source || vis.source],
            ["Symbol", identity.symbol || vis.symbol],
            ["Timeframe", identity.timeframe || vis.timeframe],
            ["Window start", window.start],
            ["Window end", window.end],
            ["Evaluation id", fields.evaluation_id],
            ["Output", item.output_dir],
          ].filter((row) => row[1] !== undefined && row[1] !== null && row[1] !== ""),
        },
        {
          title: "Strategy parameters",
          rows: objectRows(strategyParams),
          empty: "No strategy-specific parameters are recorded for this run.",
        },
        {
          title: "Backtest inputs",
          rows: inputRows,
          empty: "No additional backtest inputs are recorded.",
        },
        {
          title: "Execution and cost",
          rows: executionRows,
          empty: "No execution model or cost assumptions are recorded.",
        },
        {
          title: "Sample",
          rows: objectRows(metrics.sample),
          empty: "No sample window metrics are recorded.",
        },
      ];
    }

    function objectValue(value) {
      return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    }

    function objectRows(value, excluded = new Set()) {
      return Object.entries(objectValue(value))
        .filter(([key, item]) => !excluded.has(key) && item !== undefined && item !== null && item !== "")
        .map(([key, item]) => [label(key), parameterValueText(item)]);
    }

    function parameterValueText(value) {
      if (value && typeof value === "object") {
        try {
          return JSON.stringify(value);
        } catch {
          return text(value);
        }
      }
      return text(value);
    }

    function kvRows(rows) {
      return `<table class="kv-table"><tbody>${rows.map(([key, value]) => `
        <tr><td>${escapeHtml(key)}</td><td>${escapeHtml(parameterValueText(value))}</td></tr>`).join("")}</tbody></table>`;
    }

    function renderStrategyOperationTree(vis) {
      const node = document.querySelector("#strategy-operation-tree");
      if (!node) return;
      const markers = strategyOperationMarkers(vis);
      const omittedMarkers = omittedVisualizationMarkers(vis);
      if (!markers.length) {
        node.innerHTML = `<div class="message">No operation markers are stored for this backtest.</div>`;
        return;
      }
      const groups = new Map();
      markers.forEach((marker) => {
        const day = formatTimestamp(marker.time).split(" ")[0] || "Unknown";
        if (!groups.has(day)) groups.set(day, []);
        groups.get(day).push(marker);
      });
      const omittedNotice = omittedMarkers > 0
        ? `<div class="message compact-message">${escapeHtml(formatNumber(omittedMarkers))} older operation marker${omittedMarkers === 1 ? "" : "s"} are omitted by the bounded artifact.</div>`
        : "";
      node.innerHTML = `${omittedNotice}<div class="strategy-operation-tree">
        ${Array.from(groups.entries()).map(([day, dayMarkers]) => `
          <section class="strategy-operation-day">
            <h3>${escapeHtml(day)}</h3>
            <div class="strategy-operation-nodes">
              ${dayMarkers.map((marker) => strategyOperationNode(marker)).join("")}
            </div>
          </section>`).join("")}
        </div>`;
      wireStrategyMarkerJumps();
    }

    function strategyOperationMarkers(vis) {
      return (Array.isArray(vis?.markers) ? vis.markers : [])
        .filter((marker) => marker && marker.time)
        .slice()
        .sort((left, right) => timestampMs(right.time) - timestampMs(left.time));
    }

    function strategyOperationNode(marker) {
      const price = marker.price === undefined || marker.price === null || marker.price === "" ? "n/a" : formatNumber(marker.price);
      const exposure = marker.position ?? marker.exposure ?? "";
      const labelText = marker.label || marker.kind || marker.side || "operation";
      const isActive = String(marker.time || "") === String(state.strategyFocusedMarkerTime || "");
      return `
        <button class="strategy-operation-node ${isActive ? "active" : ""}" type="button" data-strategy-marker-time="${escapeHtml(marker.time || "")}">
          <span class="strategy-operation-rail" aria-hidden="true"></span>
          <span class="status-pill ${escapeHtml(strategyOperationStatusClass(marker))}">${escapeHtml(labelText)}</span>
          <span class="strategy-operation-node-main">
            <strong>${escapeHtml(formatTimestamp(marker.time))}</strong>
            <small>${escapeHtml([marker.side, price, exposure !== "" ? `exposure ${parameterValueText(exposure)}` : ""].filter(Boolean).join(" / "))}</small>
          </span>
        </button>`;
    }

    function strategyOperationStatusClass(marker) {
      const textValue = String(marker?.kind || marker?.label || "").toLowerCase();
      if (textValue.includes("exit") || textValue.includes("close")) return "failed";
      if (textValue.includes("short")) return "warning";
      return "available";
    }

    function renderBacktestRuns(outputs) {
      const indexedRuns = outputs.map((item, index) => ({item, index, identity: strategyIdentity(item)}));
      const board = document.querySelector("#strategy-backtest-board");
      if (board) {
        if (!indexedRuns.length) {
          board.innerHTML = `
            <div class="empty-state">
              <strong>No backtest runs yet.</strong>
              <span>Run a configured strategy profile to create an inspectable evaluation record with a strategy, symbol, and timeframe.</span>
            </div>`;
        } else {
          const filteredRuns = sortedBacktestRuns(filteredBacktestRuns(indexedRuns));
          const pageSize = strategyRunPageSize();
          state.strategyRunVisibleCount = Math.max(pageSize, Number(state.strategyRunVisibleCount) || pageSize);
          const visibleRuns = filteredRuns.slice(0, state.strategyRunVisibleCount);
          const groups = new Map();
          visibleRuns.forEach((run) => {
            const key = run.identity.symbol;
            if (!key) return;
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(run);
          });
          const groupMarkup = Array.from(groups.entries()).map(([symbol, runs]) => `
            <section class="strategy-run-group">
              <div class="strategy-run-group-header">
                <div>
                  <h3>${escapeHtml(symbol)}</h3>
                  <p>${escapeHtml(`${runs.length} recorded run${runs.length === 1 ? "" : "s"}`)}</p>
                </div>
              </div>
              <div class="strategy-run-list" role="list">
                <div class="strategy-run-list-head" aria-hidden="true">
                  <span>Strategy</span>
                  <span>Timeframe</span>
                  <span>Window</span>
                  <span>Return</span>
                  <span>Drawdown</span>
                  <span>Sharpe</span>
                  <span>Trades</span>
                  <span>Equity</span>
                </div>
                ${runs.map((run) => renderBacktestRunRow(run)).join("")}
              </div>
          </section>`).join("");
          const remaining = Math.max(0, filteredRuns.length - visibleRuns.length);
          board.innerHTML = `
            ${renderBacktestRunControls(indexedRuns, filteredRuns.length, visibleRuns.length)}
            ${groupMarkup || `<div class="empty-state"><strong>No matching backtest runs.</strong><span>Adjust filters or date range to review stored evaluations.</span></div>`}
            ${remaining ? `<div class="strategy-run-load-row"><button class="secondary-button" type="button" id="strategy-run-load-more">Load ${escapeHtml(Math.min(pageSize, remaining))} more</button><span>${escapeHtml(`${remaining} remaining`)}</span></div>` : ""}`;
        }
      }
      wireBacktestRunControls(outputs);
      document.querySelectorAll("[data-backtest-index]").forEach((button) => {
        button.addEventListener("click", () => {
          selectBacktestRun(outputs, Number(button.dataset.backtestIndex));
        });
      });
    }

    function renderBacktestRunControls(runs, filteredCount, visibleCount) {
      const filters = strategyRunFilters();
      const strategies = uniqueSorted(runs.map((run) => run.identity.name).filter(Boolean));
      const timeframes = uniqueSorted(runs.map((run) => run.identity.timeframe).filter(Boolean));
      const summary = `${visibleCount} shown / ${filteredCount} matching / ${runs.length} total`;
      return `
        <section class="strategy-run-toolbar" aria-label="Backtest run filters">
          <div class="field strategy-run-search-field">
            <label for="strategy-run-search">Search</label>
            <input id="strategy-run-search" class="text-input" type="search" value="${escapeHtml(filters.query)}" placeholder="Strategy, symbol, timeframe">
          </div>
          <div class="field">
            <label for="strategy-run-strategy-filter">Strategy</label>
            <select id="strategy-run-strategy-filter" data-strategy-run-filter="strategy">
              <option value="all">All strategies</option>
              ${strategies.map((name) => `<option value="${escapeHtml(name)}" ${filters.strategy === name ? "selected" : ""}>${escapeHtml(name)}</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <label for="strategy-run-timeframe-filter">Timeframe</label>
            <select id="strategy-run-timeframe-filter" data-strategy-run-filter="timeframe">
              <option value="all">All timeframes</option>
              ${timeframes.map((timeframe) => `<option value="${escapeHtml(timeframe)}" ${filters.timeframe === timeframe ? "selected" : ""}>${escapeHtml(timeframe)}</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <label for="strategy-run-date-from">From</label>
            <input id="strategy-run-date-from" class="text-input" type="date" value="${escapeHtml(filters.start)}" data-strategy-run-filter="start">
          </div>
          <div class="field">
            <label for="strategy-run-date-to">To</label>
            <input id="strategy-run-date-to" class="text-input" type="date" value="${escapeHtml(filters.end)}" data-strategy-run-filter="end">
          </div>
          <div class="field">
            <label for="strategy-run-sort">Sort</label>
            <select id="strategy-run-sort">
              ${strategyRunSortOptions().map((option) => `<option value="${escapeHtml(option.value)}" ${state.strategyRunSort === option.value ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}
            </select>
          </div>
          <div class="field">
            <label for="strategy-run-page-size">Rows</label>
            <select id="strategy-run-page-size">
              ${[10, 25, 50, 100].map((size) => `<option value="${size}" ${strategyRunPageSize() === size ? "selected" : ""}>${size}</option>`).join("")}
            </select>
          </div>
          <button class="secondary-button" type="button" id="strategy-run-clear-filters">Clear</button>
          <span class="strategy-run-toolbar-summary">${escapeHtml(summary)}</span>
        </section>`;
    }

    function wireBacktestRunControls(outputs) {
      const search = document.querySelector("#strategy-run-search");
      if (search) {
        search.addEventListener("input", () => {
          const selectionStart = search.selectionStart;
          state.strategyRunFilters = {...strategyRunFilters(), query: search.value};
          state.strategyRunVisibleCount = strategyRunPageSize();
          renderBacktestRuns(outputs);
          const replacement = document.querySelector("#strategy-run-search");
          if (replacement) {
            replacement.focus({preventScroll: true});
            const caret = Math.min(selectionStart ?? replacement.value.length, replacement.value.length);
            replacement.setSelectionRange(caret, caret);
          }
        });
      }
      document.querySelectorAll("[data-strategy-run-filter]").forEach((control) => {
        control.addEventListener("change", () => {
          const key = control.dataset.strategyRunFilter;
          state.strategyRunFilters = {...strategyRunFilters(), [key]: control.value};
          state.strategyRunVisibleCount = strategyRunPageSize();
          renderBacktestRuns(outputs);
        });
      });
      document.querySelector("#strategy-run-sort")?.addEventListener("change", (event) => {
        state.strategyRunSort = event.target.value || "time_desc";
        state.strategyRunVisibleCount = strategyRunPageSize();
        renderBacktestRuns(outputs);
      });
      document.querySelector("#strategy-run-page-size")?.addEventListener("change", (event) => {
        state.strategyRunPageSize = Number(event.target.value) || 25;
        state.strategyRunVisibleCount = strategyRunPageSize();
        renderBacktestRuns(outputs);
      });
      document.querySelector("#strategy-run-clear-filters")?.addEventListener("click", () => {
        state.strategyRunFilters = {query: "", strategy: "all", timeframe: "all", start: "", end: ""};
        state.strategyRunVisibleCount = strategyRunPageSize();
        renderBacktestRuns(outputs);
      });
      document.querySelector("#strategy-run-load-more")?.addEventListener("click", () => {
        state.strategyRunVisibleCount += strategyRunPageSize();
        renderBacktestRuns(outputs);
      });
    }

    function filteredBacktestRuns(runs) {
      const filters = strategyRunFilters();
      const query = String(filters.query || "").trim().toLowerCase();
      return runs.filter((run) => {
        const dateKey = backtestRunCreatedDateKey(run.item);
        if (filters.strategy !== "all" && run.identity.name !== filters.strategy) return false;
        if (filters.timeframe !== "all" && run.identity.timeframe !== filters.timeframe) return false;
        if (filters.start && (!dateKey || dateKey < filters.start)) return false;
        if (filters.end && (!dateKey || dateKey > filters.end)) return false;
        if (!query) return true;
        const metrics = strategyMetrics(run.item);
        return [
          run.identity.name,
          run.identity.symbol,
          run.identity.timeframe,
          backtestRunCreatedAt(run.item),
          backtestRunDuration(run.item),
          metrics.totalReturn,
          metrics.drawdown,
          metrics.sharpe,
          metrics.trades,
        ].join(" ").toLowerCase().includes(query);
      });
    }

    function sortedBacktestRuns(runs) {
      const sort = state.strategyRunSort || "time_desc";
      return [...runs].sort((a, b) => {
        const metricA = strategyMetricNumbers(a.item);
        const metricB = strategyMetricNumbers(b.item);
        let result = 0;
        if (sort === "time_asc") result = compareNullableNumbers(backtestRunCreatedTime(a.item), backtestRunCreatedTime(b.item), "asc");
        else if (sort === "return_desc") result = compareNullableNumbers(metricA.totalReturn, metricB.totalReturn, "desc");
        else if (sort === "return_asc") result = compareNullableNumbers(metricA.totalReturn, metricB.totalReturn, "asc");
        else if (sort === "drawdown_best") result = compareNullableNumbers(metricA.drawdown, metricB.drawdown, "desc");
        else if (sort === "drawdown_worst") result = compareNullableNumbers(metricA.drawdown, metricB.drawdown, "asc");
        else if (sort === "sharpe_desc") result = compareNullableNumbers(metricA.sharpe, metricB.sharpe, "desc");
        else if (sort === "sharpe_asc") result = compareNullableNumbers(metricA.sharpe, metricB.sharpe, "asc");
        else if (sort === "trades_desc") result = compareNullableNumbers(metricA.trades, metricB.trades, "desc");
        else if (sort === "trades_asc") result = compareNullableNumbers(metricA.trades, metricB.trades, "asc");
        else if (sort === "name_asc") result = compareText(a.identity.name, b.identity.name, "asc");
        else if (sort === "name_desc") result = compareText(a.identity.name, b.identity.name, "desc");
        else if (sort === "timeframe_asc") result = compareText(a.identity.timeframe, b.identity.timeframe, "asc");
        else result = compareNullableNumbers(backtestRunCreatedTime(a.item), backtestRunCreatedTime(b.item), "desc");
        return result || compareNullableNumbers(backtestRunCreatedTime(a.item), backtestRunCreatedTime(b.item), "desc") || compareText(a.identity.name, b.identity.name, "asc") || (a.index - b.index);
      });
    }

    function strategyRunFilters() {
      return {
        query: "",
        strategy: "all",
        timeframe: "all",
        start: "",
        end: "",
        ...(state.strategyRunFilters || {}),
      };
    }

    function strategyRunSortOptions() {
      return [
        {value: "time_desc", label: "Newest first"},
        {value: "time_asc", label: "Oldest first"},
        {value: "return_desc", label: "Return high to low"},
        {value: "return_asc", label: "Return low to high"},
        {value: "drawdown_best", label: "Drawdown best first"},
        {value: "drawdown_worst", label: "Drawdown worst first"},
        {value: "sharpe_desc", label: "Sharpe high to low"},
        {value: "sharpe_asc", label: "Sharpe low to high"},
        {value: "trades_desc", label: "Trades high to low"},
        {value: "trades_asc", label: "Trades low to high"},
        {value: "name_asc", label: "Name A to Z"},
        {value: "name_desc", label: "Name Z to A"},
        {value: "timeframe_asc", label: "Timeframe A to Z"},
      ];
    }

    function strategyRunPageSize() {
      const value = Number(state.strategyRunPageSize);
      return [10, 25, 50, 100].includes(value) ? value : 25;
    }

    function uniqueSorted(values) {
      return Array.from(new Set(values)).sort((a, b) => String(a).localeCompare(String(b), undefined, {numeric: true}));
    }

    function compareNullableNumbers(a, b, direction) {
      const aOk = Number.isFinite(a);
      const bOk = Number.isFinite(b);
      if (!aOk && !bOk) return 0;
      if (!aOk) return 1;
      if (!bOk) return -1;
      return direction === "asc" ? a - b : b - a;
    }

    function compareText(a, b, direction) {
      const result = String(a || "").localeCompare(String(b || ""), undefined, {numeric: true});
      return direction === "desc" ? -result : result;
    }

    function backtestRunCreatedAt(item) {
      const fields = item?.fields || {};
      return fields.created_at || item?.created_at || fields.run_started_at || fields.generated_at || backtestRunWindow(item).end || "";
    }

    function backtestRunCreatedTime(item) {
      const parsed = Date.parse(backtestRunCreatedAt(item));
      return Number.isFinite(parsed) ? parsed : null;
    }

    function backtestRunCreatedDateKey(item) {
      const created = backtestRunCreatedAt(item);
      const parsed = Date.parse(created);
      if (Number.isFinite(parsed)) return new Date(parsed).toISOString().slice(0, 10);
      const match = String(created || "").match(/\d{4}-\d{2}-\d{2}/);
      return match ? match[0] : "";
    }

    function renderBacktestRunRow(run) {
      const metrics = strategyMetrics(run.item);
      const identity = run.identity;
      const created = backtestRunCreatedAt(run.item);
      const statusChip = backtestRunStatusChip(run.item);
      return `
        <button class="strategy-run-row ${run.item === state.selectedStrategyOutput ? "active" : ""}" type="button" data-backtest-index="${run.index}" role="listitem">
          <span class="strategy-run-cell strategy-run-main">
            <strong>${escapeHtml(identity.name || "Strategy")}</strong>
            <small>${escapeHtml(formatTimestamp(created))}</small>
            ${statusChip}
          </span>
          <span class="strategy-run-cell"><b>${escapeHtml(identity.timeframe || "n/a")}</b></span>
          <span class="strategy-run-cell"><b>${escapeHtml(backtestRunDuration(run.item))}</b></span>
          <span class="strategy-run-cell"><b class="${pnlClass(metrics.totalReturn)}">${escapeHtml(metrics.totalReturn)}</b></span>
          <span class="strategy-run-cell"><b class="${pnlClass(metrics.drawdown)}">${escapeHtml(metrics.drawdown)}</b></span>
          <span class="strategy-run-cell"><b class="${pnlClass(metrics.sharpe)}">${escapeHtml(metrics.sharpe)}</b></span>
          <span class="strategy-run-cell"><b>${escapeHtml(metrics.trades)}</b></span>
          <span class="strategy-run-cell strategy-run-sparkline-cell">
            ${renderBacktestSparkline(run.item)}
          </span>
        </button>`;
    }

    function backtestRunStatusChip(item) {
      const status = String(item?.status || item?.fields?.status || "stored").toLowerCase();
      if (["available", "ok", "stored", "succeeded", "success"].includes(status)) {
        return "";
      }
      return `<span class="status-pill ${escapeHtml(statusClass(status))}">${escapeHtml(label(status))}</span>`;
    }

    function backtestRunWindow(item) {
      const fields = item?.fields || {};
      const sample = fields.metrics?.sample || fields.sample || {};
      const vis = backtestVisualization(item);
      return {
        start: fields.input_window_start || sample.start || firstTime(vis?.equity_curve) || firstTime(vis?.bars),
        end: fields.input_window_end || sample.end || lastTime(vis?.equity_curve) || lastTime(vis?.bars),
      };
    }

    function firstTime(items) {
      return Array.isArray(items) && items.length ? items[0]?.time || items[0]?.open_time || "" : "";
    }

    function lastTime(items) {
      return Array.isArray(items) && items.length ? items[items.length - 1]?.time || items[items.length - 1]?.open_time || "" : "";
    }

    function backtestRunDuration(item) {
      const window = backtestRunWindow(item);
      return compactDurationBetween(window.start, window.end);
    }

    function compactDurationBetween(start, end) {
      const startMs = start ? new Date(start).getTime() : NaN;
      const endMs = end ? new Date(end).getTime() : NaN;
      if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs < startMs) {
        return "n/a";
      }
      return compactDurationMs(endMs - startMs);
    }

    function compactDurationMs(ms) {
      const totalMinutes = Math.max(0, Math.round(ms / 60000));
      const minutesPerHour = 60;
      const minutesPerDay = 24 * minutesPerHour;
      const minutesPerMonth = 30 * minutesPerDay;
      if (totalMinutes >= minutesPerMonth) {
        const months = Math.floor(totalMinutes / minutesPerMonth);
        const days = Math.floor((totalMinutes % minutesPerMonth) / minutesPerDay);
        return `${months}M${days ? `${days}d` : ""}`;
      }
      if (totalMinutes >= minutesPerDay) {
        const days = Math.floor(totalMinutes / minutesPerDay);
        const hours = Math.floor((totalMinutes % minutesPerDay) / minutesPerHour);
        return `${days}d${hours ? `${hours}h` : ""}`;
      }
      if (totalMinutes >= minutesPerHour) {
        const hours = Math.floor(totalMinutes / minutesPerHour);
        const minutes = totalMinutes % minutesPerHour;
        return `${hours}h${minutes ? `${minutes}m` : ""}`;
      }
      return `${totalMinutes}m`;
    }

    function renderBacktestSparkline(item) {
      const values = backtestSparklineReturns(item);
      if (values.length < 2) {
        return `<span class="strategy-run-sparkline-empty">n/a</span>`;
      }
      const width = 168;
      const height = 44;
      const padding = 4;
      const baseline = height / 2;
      const maxAbs = Math.max(...values.map((value) => Math.abs(value)), 0.000001);
      const points = values.map((value, index) => {
        const x = padding + (index / (values.length - 1)) * (width - padding * 2);
        const y = baseline - (value / maxAbs) * (baseline - padding);
        return {x: Number(x.toFixed(2)), y: Number(y.toFixed(2)), value};
      });
      const segments = splitSparklineSegments(points, baseline).map((segment) => (
        `<path class="strategy-run-sparkline-segment ${segment.tone}" d="M ${segment.x1} ${segment.y1} L ${segment.x2} ${segment.y2}" />`
      )).join("");
      return `<svg class="strategy-run-sparkline" viewBox="0 0 ${width} ${height}" role="img" aria-label="Backtest equity curve">
          <line class="strategy-run-sparkline-baseline" x1="${padding}" x2="${width - padding}" y1="${baseline}" y2="${baseline}" />
          ${segments}
        </svg>`;
    }

    function backtestSparklineReturns(item) {
      const vis = backtestVisualization(item);
      const curve = Array.isArray(vis.equity_sparkline) && vis.equity_sparkline.length
        ? vis.equity_sparkline
        : vis.equity_curve || [];
      const curveValues = equityCurveValues(curve);
      const returns = normalizedEquityReturns(curveValues);
      const metrics = strategyMetricNumbers(item);
      const range = returns.length ? Math.max(...returns) - Math.min(...returns) : 0;
      if (returns.length >= 2 && (range >= 0.05 || Math.abs(metrics.totalReturn || 0) < 0.05)) {
        return returns;
      }
      return fallbackSparklineReturns(metrics);
    }

    function normalizedEquityReturns(values) {
      if (!values.length) return [];
      const start = values[0];
      if (Number.isFinite(start) && start !== 0) {
        return values.map((value) => ((value / start) - 1) * 100).filter(Number.isFinite);
      }
      return values.filter(Number.isFinite);
    }

    function fallbackSparklineReturns(metrics) {
      const total = metrics.totalReturn;
      const drawdown = metrics.drawdown;
      if (!Number.isFinite(total) && !Number.isFinite(drawdown)) return [];
      const finalValue = Number.isFinite(total) ? total : 0;
      const drawdownValue = Number.isFinite(drawdown) ? Math.min(0, drawdown) : Math.min(0, finalValue);
      if (Math.abs(finalValue) < 0.05 && Math.abs(drawdownValue) < 0.05) {
        return [0, 0];
      }
      return [0, drawdownValue, finalValue];
    }

    function splitSparklineSegments(points, baseline) {
      const segments = [];
      points.slice(1).forEach((point, index) => {
        const previous = points[index];
        if (previous.value === point.value) {
          segments.push(sparklineSegment(previous, point, point.value >= 0 ? "profit" : "loss"));
          return;
        }
        if ((previous.value < 0 && point.value > 0) || (previous.value > 0 && point.value < 0)) {
          const ratio = (0 - previous.value) / (point.value - previous.value);
          const cross = {
            x: Number((previous.x + (point.x - previous.x) * ratio).toFixed(2)),
            y: Number(baseline.toFixed(2)),
            value: 0,
          };
          segments.push(sparklineSegment(previous, cross, previous.value >= 0 ? "profit" : "loss"));
          segments.push(sparklineSegment(cross, point, point.value >= 0 ? "profit" : "loss"));
          return;
        }
        segments.push(sparklineSegment(previous, point, point.value >= 0 ? "profit" : "loss"));
      });
      return segments;
    }

    function sparklineSegment(start, end, tone) {
      return {x1: start.x, y1: start.y, x2: end.x, y2: end.y, tone};
    }

    function selectBacktestRun(outputs, index) {
      const item = outputs[index];
      if (!item) return;
      state.selectedStrategyOutput = item;
      state.strategyBacktestDetailOpen = true;
      state.strategyFocusedMarkerTime = "";
      const identity = strategyIdentity(item);
      setSelectIfPresent("#strategy-name", identity.name);
      setSelectIfPresent("#strategy-symbol", identity.symbol);
      setSelectIfPresent("#strategy-timeframe", identity.timeframe);
      setSelectIfPresent("#strategy-chart-symbol", identity.symbol);
      setSelectIfPresent("#strategy-chart-timeframe", identity.timeframe);
      setInputValue("#strategy-chart-source", backtestVisualization(item).source || item?.fields?.source || defaultStrategySource(), true);
      strategyChart.resetCandlestickView("#backtest-chart");
      strategyChart.resetEquityCurveView("#strategy-equity-chart");
      strategyChart.resetDrawdownCurveView("#strategy-drawdown-chart");
      queueStrategyChartRefresh({clearBacktest: false});
      renderStrategies();
    }

    function showStrategyBacktestList() {
      state.strategyBacktestDetailOpen = false;
      closeStrategyParamsDrawer();
      syncStrategyOperationTabs();
      renderBacktestRuns(strategyOutputs());
    }

    function backtestRunMeta(item) {
      const identity = strategyIdentity(item);
      const created = item?.fields?.created_at || item?.created_at || item?.status || "latest";
      const market = [identity.symbol, identity.timeframe].filter(Boolean).join(" ");
      return [market, created].filter(Boolean).join(" / ");
    }

    function renderStrategyExperimentResults() {
      const node = document.querySelector("#strategy-experiment-results");
      if (!node) return;
      const experiments = standaloneExperiments();
      if (!experiments.length) {
        node.innerHTML = `<div class="message">No standalone experiment results yet.</div>`;
        return;
      }
      const latest = experiments[0];
      const fields = latest.fields || {};
      const coverage = fields.coverage || {};
      const counts = fields.counts || {};
      const candidates = latest.records?.candidates || [];
      const gates = latest.records?.gates || [];
      const benchmarks = latest.records?.benchmarks || [];
      const verdict = strategyExperimentVerdict(latest, fields, coverage, counts);
      const candidateRows = candidates.map((candidate) => {
        const gate = gates.find((item) => !candidate.strategy_name || item.strategy_name === candidate.strategy_name) || {};
        return [
          candidate.strategy_name || "n/a",
          candidate.status || "n/a",
          candidate.evaluation_count ?? "n/a",
          statusCountsText(candidate.evaluation_status_counts),
          gate.status || "n/a",
          (gate.reason_codes || []).join(", ") || "n/a",
        ];
      });
      const benchmarkRows = benchmarks.slice(0, 6).map((benchmark) => [
        benchmark.symbol || "n/a",
        benchmark.timeframe || "n/a",
        benchmark.status || "n/a",
        benchmark.row_count ?? "n/a",
      ]);
      node.innerHTML = `
        <div class="strategy-result-header">
          <div><strong>Latest validation</strong><span>${escapeHtml(fields.created_at || latest.output_dir || "latest stored result")}</span></div>
          <span class="status-pill ${escapeHtml(statusClass(latest.status))}">${escapeHtml(label(latest.status || "unknown"))}</span>
        </div>
        <div class="strategy-lab-verdict ${escapeHtml(verdict.className)}">
          <span class="status-pill ${escapeHtml(verdict.pillClass)}">${escapeHtml(verdict.pill)}</span>
          <div>
            <strong>${escapeHtml(verdict.title)}</strong>
            <p>${escapeHtml(verdict.body)}</p>
          </div>
        </div>
        <div class="summary-strip columns-4">
          ${metricCell("Candidates", coverage.strategy_candidates ?? counts.strategy_candidates, "strategies")}
          ${metricCell("Evaluations", coverage.evaluations ?? counts.evaluations, "benchmark runs")}
          ${metricCell("Succeeded", coverage.evaluations_succeeded ?? coverage.succeeded, "completed")}
          ${metricCell("Effective", fields.gate_coverage?.effective ?? counts.strategy_gate_effective, "gates")}
        </div>
        <div class="strategy-result-grid">
          <section>
            <h3 class="subsection-title">Candidates and gates</h3>
            ${candidateRows.length ? table(["Strategy", "Status", "Evaluations", "Counts", "Gate", "Reasons"], candidateRows) : `<div class="message">No candidate records are available.</div>`}
          </section>
          <section>
            <h3 class="subsection-title">Benchmark windows</h3>
            ${benchmarkRows.length ? table(["Symbol", "Timeframe", "Status", "Rows"], benchmarkRows) : `<div class="message">No benchmark records are available.</div>`}
          </section>
        </div>
        ${strategyResultMessages(latest)}`;
    }

    function strategyExperimentVerdict(latest, fields, coverage, counts) {
      const status = latest.status || fields.status || "unknown";
      const effective = Number(fields.gate_coverage?.effective ?? counts.strategy_gate_effective ?? 0) || 0;
      const candidateCount = Number(coverage.strategy_candidates ?? counts.strategy_candidates ?? 0) || 0;
      const succeeded = Number(coverage.evaluations_succeeded ?? coverage.succeeded ?? 0) || 0;
      const failed = Number(coverage.evaluations_failed ?? coverage.failed ?? 0) || 0;
      const warningCount = [
        ...(Array.isArray(latest.warnings) ? latest.warnings : []),
        ...(Array.isArray(latest.errors) ? latest.errors : []),
      ].length;
      if (status === "failed" || failed > 0) {
        return {
          className: "warning",
          pillClass: "warning",
          pill: "Needs review",
          title: "Validation completed with failed evidence paths.",
          body: `${failed} benchmark evaluation${failed === 1 ? "" : "s"} failed. Inspect warnings before treating any gate result as usable.`,
        };
      }
      if (effective > 0) {
        return {
          className: "ok",
          pillClass: "ok",
          pill: "Actionable",
          title: `${effective} configured strateg${effective === 1 ? "y has" : "ies have"} effective gate evidence.`,
          body: `${succeeded} benchmark evaluation${succeeded === 1 ? "" : "s"} succeeded across ${candidateCount || "configured"} candidate${candidateCount === 1 ? "" : "s"}. Review candidate rows before promoting conclusions.`,
        };
      }
      if (warningCount > 0) {
        return {
          className: "warning",
          pillClass: "warning",
          pill: "Insufficient",
          title: "No strategy has effective gate evidence yet.",
          body: `${warningCount} warning/error note${warningCount === 1 ? "" : "s"} were recorded. Treat this as an evidence gap, not a negative strategy conclusion.`,
        };
      }
      return {
        className: "pending",
        pillClass: "pending",
        pill: "Review",
        title: "Validation evidence is recorded but not yet effective.",
        body: "The benchmark suite ran without an effective gate result. Check coverage, sample size, and gate reasons before changing strategy configuration.",
      };
    }

    function standaloneExperiments() {
      const experiments = state.strategies?.standalone?.experiments;
      return Array.isArray(experiments) ? experiments : [];
    }

    function statusCountsText(counts) {
      if (!counts || typeof counts !== "object") return "n/a";
      const parts = Object.entries(counts)
        .filter(([, value]) => Number(value) > 0)
        .map(([name, value]) => `${label(name)} ${formatNumber(value)}`);
      return parts.join(", ") || "n/a";
    }

    function strategyResultMessages(item) {
      const warnings = Array.isArray(item?.warnings) ? item.warnings : [];
      const errors = Array.isArray(item?.errors) ? item.errors : [];
      if (!warnings.length && !errors.length) return "";
      const rows = [
        ...errors.slice(0, 6).map((message) => ["Error", message]),
        ...warnings.slice(0, 6).map((message) => ["Warning", message]),
      ];
      return `<section class="strategy-result-messages">
        <h3 class="subsection-title">Warnings and errors</h3>
        ${table(["Type", "Message"], rows)}
      </section>`;
    }

    function currentStrategyTab() {
      const active = document.querySelector("[data-strategy-tab].active")?.dataset.strategyTab || "equity";
      return ["equity", "drawdown", "summary"].includes(active) ? active : "equity";
    }

    function renderStrategyTab(tab) {
      const selectedTab = ["equity", "drawdown", "summary"].includes(tab) ? tab : "equity";
      document.querySelectorAll("[data-strategy-tab]").forEach((button) => button.classList.toggle("active", button.dataset.strategyTab === selectedTab));
      const vis = visibleBacktestVisualization(state.selectedStrategyOutput);
      const fullVis = fullBacktestVisualization(state.selectedStrategyOutput);
      let content = "";
      if (selectedTab === "equity") {
        content = renderStrategyEquityPanel(vis);
      } else if (selectedTab === "drawdown") {
        content = renderStrategyDrawdownPanel(fullVis);
      } else if (selectedTab === "summary") {
        content = renderStrategyEvaluationPanels(state.selectedStrategyOutput, vis);
      } else {
        content = renderStrategyDiagnostics();
      }
      document.querySelector("#strategy-tab-content").innerHTML = content;
      if (selectedTab === "equity") {
        strategyChart.renderEquityCurveSvg("#strategy-equity-chart", Array.isArray(vis.equity_curve) ? vis.equity_curve : [], {
          displayTimezone,
          pnlColorScheme,
        });
      }
      if (selectedTab === "drawdown") {
        strategyChart.renderDrawdownCurveSvg("#strategy-drawdown-chart", Array.isArray(fullVis.equity_curve) ? fullVis.equity_curve : [], {
          displayTimezone,
          pnlColorScheme,
        });
      }
    }

    function wireStrategyMarkerJumps() {
      document.querySelectorAll("[data-strategy-marker-time]").forEach((button) => {
        button.addEventListener("click", () => focusStrategyMarker(button.dataset.strategyMarkerTime));
      });
    }

    function focusStrategyMarker(time) {
      if (!time || !state.selectedStrategyOutput) return;
      state.strategyFocusedMarkerTime = String(time);
      strategyChart.resetCandlestickView("#backtest-chart");
      renderBacktestDetail(state.selectedStrategyOutput);
      document.querySelector("#backtest-chart")?.scrollIntoView({block: "center", behavior: "smooth"});
    }

    function renderStrategyEquityPanel(vis) {
      const curve = Array.isArray(vis.equity_curve) ? vis.equity_curve : [];
      const values = equityCurveValues(curve);
      if (!values.length) {
        return `<div class="message">No equity curve is available for the selected backtest.</div>`;
      }
      return `
        <div class="strategy-eval-chart strategy-equity-chart">
          <svg id="strategy-equity-chart" viewBox="0 0 900 240" role="img" aria-label="Equity curve"></svg>
        </div>`;
    }

    function renderStrategyDrawdownPanel(vis) {
      const values = equityCurveValues(Array.isArray(vis.equity_curve) ? vis.equity_curve : []);
      const drawdowns = drawdownValues(values);
      if (!drawdowns.length) {
        return `<div class="message">No drawdown data can be derived for the selected backtest.</div>`;
      }
      return `
        <div class="strategy-eval-chart strategy-drawdown-chart">
          <svg id="strategy-drawdown-chart" viewBox="0 0 900 240" role="img" aria-label="Drawdown curve"></svg>
        </div>`;
    }

    function renderStrategyEvaluationPanels(item, vis) {
      const context = strategyEvaluationContext(item, vis);
      if (!item && !context.hasEvidence) {
        return `<div class="message">Select a backtest or run Strategy Lab validation to inspect strategy evaluation evidence.</div>`;
      }
      return `
        <div class="strategy-eval-grid">
          ${strategyEvalPanel("Performance", renderPerformanceEvidence(item, context))}
          ${strategyEvalPanel("Cost and Funding", renderCostFundingEvidence(item, vis))}
          ${strategyEvalPanel("Gates", renderGateEvidence(context.gate))}
          ${strategyEvalPanel("Lifecycle", renderLifecycleEvidence(context.lifecycle))}
          ${strategyEvalPanel("Robustness evidence", renderOptimizationEvidence(context.optimization))}
          ${strategyEvalPanel("Walk-forward", renderWalkForwardEvidence(context))}
          ${strategyEvalPanel("Warnings", renderWarningEvidence(item, context))}
          ${strategyEvalPanel("Source refs", renderSourceEvidence(item, context))}
        </div>`;
    }

    function strategyEvalPanel(title, body) {
      return `<section class="strategy-eval-panel"><h3>${escapeHtml(title)}</h3>${body}</section>`;
    }

    function renderPerformanceEvidence(item, context) {
      const evaluation = context.evaluation || {};
      const strategy = evaluation.strategy_metrics || item?.fields?.metrics?.strategy_metrics || {};
      const trade = evaluation.trade_summary || item?.fields?.metrics?.trade_summary || {};
      const fallback = strategyMetrics(item);
      const baseline = evaluation.baseline_metrics || item?.fields?.metrics?.baseline_metrics || {};
      const relative = evaluation.relative_metrics || item?.fields?.metrics?.relative_metrics || {};
      const totalReturn = strategyMetricPercent(strategy.net_return_pct ?? strategy.total_return_pct, fallback.totalReturn);
      const drawdown = strategyMetricPercent(strategy.max_drawdown_pct, fallback.drawdown);
      return `<div class="strategy-eval-kv">
        ${detailRow("Status", item?.status || evaluation.status || "n/a")}
        ${detailRow("Total return", totalReturn)}
        ${detailRow("Max drawdown", drawdown)}
        ${detailRow("Sharpe", text(strategy.sharpe_ratio ?? strategy.sharpe, fallback.sharpe))}
        ${detailRow("Trades", trade.trade_count ?? fallback.trades)}
        ${detailRow("Buy and hold", metricPercent(baseline.buy_and_hold_return_pct))}
        ${detailRow("Excess return", metricPercent(relative.excess_return_vs_buy_and_hold_pct))}
      </div>`;
    }

    function strategyMetricPercent(value, fallback) {
      return Number.isFinite(Number(value)) ? metricPercent(value) : fallback;
    }

    function renderCostFundingEvidence(item, vis) {
      const cost = item?.fields?.metrics?.cost_assumptions || {};
      const fundingMarkers = (vis.markers || []).filter((marker) => marker.funding !== undefined || String(marker.kind || "").toLowerCase().includes("funding"));
      return `<div class="strategy-eval-kv">
        ${detailRow("Fees bps", cost.fees_bps)}
        ${detailRow("Slippage bps", cost.slippage_bps)}
        ${detailRow("Cost model", cost.cost_model_id || cost.model_id)}
        ${detailRow("Funding markers", fundingMarkers.length)}
        ${detailRow("Funding sample", fundingMarkers[0]?.funding ?? "n/a")}
      </div>`;
    }

    function renderGateEvidence(gate) {
      if (!gate) return `<div class="message">No gate outcome is available for the selected strategy context.</div>`;
      return `<div class="strategy-eval-kv">
        ${detailRow("Status", gate.status)}
        ${detailRow("Strategy", gate.strategy_name)}
        ${detailRow("Market", [gate.symbol, gate.timeframe].filter(Boolean).join(" "))}
        ${detailRow("Reasons", (gate.reason_codes || []).join(", ") || "n/a")}
      </div>`;
    }

    function renderLifecycleEvidence(lifecycle) {
      if (!lifecycle) return `<div class="message">No lifecycle state is available for the selected strategy context.</div>`;
      return `<div class="strategy-eval-kv">
        ${detailRow("Lifecycle", lifecycle.lifecycle_status)}
        ${detailRow("Degradation", lifecycle.degradation_state)}
        ${detailRow("Health", lifecycle.health_state)}
        ${detailRow("Retirement", lifecycle.retirement_state)}
        ${detailRow("Parameter version", lifecycle.parameter_version)}
      </div>`;
    }

    function renderOptimizationEvidence(optimization) {
      if (!optimization) return `<div class="message">No development-time robustness artifact is available for the selected strategy context.</div>`;
      const fields = optimization.fields || {};
      const candidate = fields.selected_candidate || {};
      const params = candidate.params || {};
      const rows = Object.entries(params).map(([name, value]) => [name, value]);
      return `<div class="strategy-eval-kv">
        ${detailRow("Status", optimization.status || fields.status)}
        ${detailRow("Candidate", candidate.candidate_id)}
        ${detailRow("Robustness", fields.robustness?.status)}
        ${detailRow("Combinations", fields.search_space?.combination_count)}
        ${detailRow("Succeeded", fields.coverage?.succeeded)}
      </div>
      ${rows.length ? table(["Parameter", "Selected value"], rows) : `<div class="message">No selected candidate params are recorded.</div>`}`;
    }

    function renderWalkForwardEvidence(context) {
      const wf = context.optimization?.fields?.walk_forward || context.evaluation?.walk_forward || {};
      if (!wf || !Object.keys(wf).length) return `<div class="message">No walk-forward evidence is available.</div>`;
      const summary = wf.summary || {};
      return `<div class="strategy-walkforward-card ${escapeHtml(statusClass(wf.status))}">
        <strong>${escapeHtml(label(wf.status || "unknown"))}</strong>
        <span>${escapeHtml(formatNumber(wf.window_count || summary.window_count || summary.succeeded_windows || 0))} windows</span>
        <span>${escapeHtml(summary.result_stability || summary.stability || "stability n/a")}</span>
      </div>`;
    }

    function renderWarningEvidence(item, context) {
      const warnings = [
        ...(item?.warnings || []),
        ...(item?.visualization?.warnings || []),
        ...(context.experiment?.warnings || []),
        ...(context.optimization?.warnings || []),
        ...(context.pipelineWarnings || []),
      ].filter(Boolean);
      if (!warnings.length) return `<div class="message">No warnings are recorded for the selected strategy context.</div>`;
      return `<ul class="compact-list">${warnings.slice(0, 8).map((warning) => `<li class="compact-row">${escapeHtml(warning)}</li>`).join("")}</ul>`;
    }

    function renderSourceEvidence(item, context) {
      const refs = unique([...(item?.source_artifacts || []), ...(context.sourceArtifacts || [])]);
      if (!refs.length) return `<div class="message">No source refs are recorded for this strategy context.</div>`;
      return `<ul class="compact-list">${refs.slice(0, 8).map((ref) => `<li class="compact-row">${escapeHtml(ref)}</li>`).join("")}</ul>`;
    }

    function equityCurveValues(curve) {
      return curve.map((point) => Number(point.net_equity ?? point.equity ?? point.value)).filter(Number.isFinite);
    }

    function drawdownValues(values) {
      let peak = -Infinity;
      return values.map((value) => {
        peak = Math.max(peak, value);
        if (!Number.isFinite(peak) || peak === 0) return 0;
        return (value - peak) / peak * 100;
      });
    }

    function strategyEvaluationContext(item, vis) {
      const identity = item ? strategyIdentity(item) : {
        name: document.querySelector("#strategy-name")?.value || vis.strategy_name || "",
        symbol: vis.symbol || document.querySelector("#strategy-symbol")?.value || "",
        timeframe: vis.timeframe || document.querySelector("#strategy-timeframe")?.value || "",
      };
      const evaluationArtifact = pipelineArtifact("strategy_evaluation_summary");
      const gateArtifact = pipelineArtifact("strategy_effectiveness_gates");
      const lifecycleArtifact = pipelineArtifact("strategy_lifecycle_state");
      const evaluation = matchingRecord(evaluationArtifact?.records?.records || [], identity);
      const gate = matchingRecord(gateArtifact?.records?.gates || [], identity);
      const lifecycle = matchingRecord(lifecycleArtifact?.records?.lifecycle || [], identity);
      const experiment = matchingStandaloneExperiment(identity);
      const optimization = matchingStandaloneOptimization(identity);
      return {
        identity,
        evaluation,
        gate,
        lifecycle,
        experiment,
        optimization,
        hasEvidence: Boolean(evaluation || gate || lifecycle || experiment || optimization),
        pipelineWarnings: [
          ...(evaluationArtifact?.warnings || []),
          ...(gateArtifact?.warnings || []),
          ...(lifecycleArtifact?.warnings || []),
        ],
        sourceArtifacts: [
          ...(evaluationArtifact?.source_artifacts || []),
          ...(gateArtifact?.source_artifacts || []),
          ...(lifecycleArtifact?.source_artifacts || []),
          ...(experiment?.source_artifacts || []),
          ...(optimization?.source_artifacts || []),
        ],
      };
    }

    function pipelineArtifact(name) {
      const artifacts = Array.isArray(state.strategies?.pipeline?.artifacts) ? state.strategies.pipeline.artifacts : [];
      return artifacts.find((artifact) => artifact.name === name) || null;
    }

    function matchingRecord(records, identity) {
      return records.find((record) => matchesStrategyIdentity(record, identity)) || null;
    }

    function matchingStandaloneExperiment(identity) {
      const experiments = Array.isArray(state.strategies?.standalone?.experiments) ? state.strategies.standalone.experiments : [];
      return experiments.find((experiment) => {
        const candidates = experiment.records?.candidates || [];
        return candidates.some((candidate) => !identity.name || candidate.strategy_name === identity.name);
      }) || null;
    }

    function matchingStandaloneOptimization(identity) {
      const optimizations = Array.isArray(state.strategies?.standalone?.optimizations) ? state.strategies.standalone.optimizations : [];
      return optimizations.find((optimization) => !identity.name || optimization.fields?.strategy_name === identity.name) || null;
    }

    function matchesStrategyIdentity(record, identity) {
      if (!record) return false;
      return (!identity.name || !record.strategy_name || record.strategy_name === identity.name)
        && (!identity.symbol || !record.symbol || record.symbol === identity.symbol)
        && (!identity.timeframe || !record.timeframe || record.timeframe === identity.timeframe);
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

    function openStrategyBacktestDialog(options = {}) {
      state.strategyBacktestDialogOpen = true;
      syncBacktestProfileControls(false);
      syncStrategyRangePresets(false);
      if (options.prefillBacktest) {
        prefillBacktestDialogFromRun(options.prefillBacktest);
      }
      document.querySelector("#strategy-backtest-dialog")?.classList.remove("hidden");
      document.querySelector("#strategy-backtest-dialog-backdrop")?.classList.remove("hidden");
      document.querySelector("#strategy-profile")?.focus();
    }

    function closeStrategyBacktestDialog() {
      state.strategyBacktestDialogOpen = false;
      document.querySelector("#strategy-backtest-dialog")?.classList.add("hidden");
      document.querySelector("#strategy-backtest-dialog-backdrop")?.classList.add("hidden");
    }

    function openStrategyParamsDrawer() {
      const selected = state.selectedStrategyOutput;
      if (!selected) {
        showToast("Select a backtest run first.");
        return;
      }
      state.strategyParamsDrawerOpen = true;
      renderStrategyParamsDrawer(selected, visibleStrategyVisualization(selected));
      document.querySelector("#strategy-params-drawer")?.classList.remove("hidden");
      const backdrop = document.querySelector("#strategy-params-drawer-backdrop");
      backdrop?.classList.remove("hidden");
      backdrop?.setAttribute("aria-hidden", "false");
      document.querySelector("#strategy-params-drawer-close")?.focus({preventScroll: true});
    }

    function closeStrategyParamsDrawer() {
      state.strategyParamsDrawerOpen = false;
      document.querySelector("#strategy-params-drawer")?.classList.add("hidden");
      const backdrop = document.querySelector("#strategy-params-drawer-backdrop");
      backdrop?.classList.add("hidden");
      backdrop?.setAttribute("aria-hidden", "true");
    }

    function rerunSelectedBacktest() {
      const selected = state.selectedStrategyOutput;
      if (!selected) {
        showToast("Select a backtest run first.");
        return;
      }
      openStrategyBacktestDialog({prefillBacktest: selected});
    }

    function prefillBacktestDialogFromRun(item) {
      const params = strategyBacktestActionParams(item);
      const profile = strategyProfiles().find((candidate) => (
        (!params.strategy_name || candidate.strategy_name === params.strategy_name)
        && (!params.source || candidate.source === params.source)
        && (!params.symbol || candidate.symbol === params.symbol)
        && (!params.timeframe || candidate.timeframe === params.timeframe)
      ));
      if (profile) {
        setSelectIfPresent("#strategy-profile", strategyProfileId(profile));
        syncBacktestProfileControls(false);
      }
      const spec = strategySpecByName(params.strategy_name);
      if (spec?.family) {
        setSelectIfPresent("#strategy-family", spec.family);
        fillSelect("#strategy-name", strategiesForFamily(spec.family).map((itemSpec) => itemSpec.name));
      }
      setSelectIfPresent("#strategy-name", params.strategy_name);
      setSelectIfPresent("#strategy-symbol", params.symbol);
      setSelectIfPresent("#strategy-timeframe", params.timeframe);
      setInputValue("#strategy-source", params.source || defaultStrategySource(), true);
      document.querySelector("#strategy-backtest-range").value = "custom";
      document.querySelector("#strategy-backtest-start").value = params.start || "";
      document.querySelector("#strategy-backtest-end").value = params.end || "";
      syncDateRangePickerByInputs("#strategy-backtest-start", "#strategy-backtest-end");
      renderStrategySpecControls();
    }

    function strategyBacktestActionParams(item) {
      const fields = item?.fields || {};
      const inputs = objectValue(fields.inputs);
      const identity = strategyIdentity(item);
      const window = backtestRunWindow(item);
      return {
        strategy_name: identity.name || inputs.strategy_name || fields.strategy_name || "",
        source: inputs.source || fields.source || item?.visualization?.source || defaultStrategySource(),
        symbol: identity.symbol || inputs.symbol || fields.symbol || "",
        timeframe: identity.timeframe || inputs.timeframe || fields.timeframe || "",
        start: fields.input_window_start || inputs.start || window.start || "",
        end: fields.input_window_end || inputs.end || window.end || "",
      };
    }

    async function deleteSelectedBacktest() {
      const selected = state.selectedStrategyOutput;
      if (!selected) {
        showToast("Select a backtest run first.");
        return;
      }
      const identity = strategyIdentity(selected);
      const ok = await dialogs.confirmAction({
        title: "Delete backtest run",
        message: `Delete ${identity.name || "this strategy"} ${identity.symbol || ""} ${identity.timeframe || ""}? Standalone backtest artifacts are removed when this run owns them; report artifacts are preserved.`,
        confirmLabel: "Delete backtest",
        danger: true,
      });
      if (!ok) return;
      try {
        const result = await postStrategyBacktestDelete(selected);
        state.selectedStrategyOutput = null;
        state.strategyBacktestDetailOpen = false;
        closeStrategyParamsDrawer();
        strategyChart.resetCandlestickView("#backtest-chart");
        await refreshStrategies();
        showToast(`Backtest delete ${result.status || "completed"}.`);
      } catch (error) {
        showToast(`Delete failed: ${error.message}`, "error");
      }
    }

    async function startBacktest() {
      const params = {
        strategy_name: document.querySelector("#strategy-name")?.value,
        source: document.querySelector("#strategy-source")?.value || defaultStrategySource(),
        symbol: document.querySelector("#strategy-symbol")?.value,
        timeframe: document.querySelector("#strategy-timeframe")?.value,
      };
      const start = String(document.querySelector("#strategy-backtest-start")?.value || "").trim();
      const end = String(document.querySelector("#strategy-backtest-end")?.value || "").trim();
      if (start) params.start = start;
      if (end) params.end = end;
      if (!params.strategy_name || !params.symbol || !params.timeframe) {
        showToast("Select a configured strategy, symbol, and timeframe first.");
        return;
      }
      closeStrategyBacktestDialog();
      await runStrategyAction("backtest", params, {
        headline: `Backtest ${params.symbol} ${params.timeframe}`,
        submitLog: `Submitting ${params.strategy_name} on ${params.symbol} ${params.timeframe}${start || end ? ` from ${start || "start"} to ${end || "end"}` : ""}.`,
      });
    }

    async function startStrategyExperiment() {
      const strategyNames = selectedExperimentStrategyNames();
      if (!strategyNames.length) {
        showToast("Select at least one configured strategy for the experiment.");
        return;
      }
      await runStrategyAction("experiment", {strategy_names: strategyNames}, {
        headline: `Experiment ${strategyNames.length} strateg${strategyNames.length === 1 ? "y" : "ies"}`,
        submitLog: `Submitting experiment for ${strategyNames.join(", ")}.`,
      });
    }

    async function runStrategyAction(kind, params, copy) {
      state[strategyOperationLogKey(kind)] = [];
      appendOperationLog(kind, copy.submitLog);
      renderOperationProgress(kind, {
        status: "running",
        percent: 6,
        headline: copy.headline,
        logs: state[strategyOperationLogKey(kind)],
      });
      try {
        const job = await postStrategyAction(kind, params);
        appendOperationLog(kind, `Job ${job.job_id || "pending"} ${job.status || "created"}.`);
        renderOperationProgress(kind, {
          status: job.status || "queued",
          percent: jobStatusPercent(job.status),
          headline: copy.headline,
          logs: operationLogsWithJob(kind, job),
        });
        if (job.job_id) {
          const completed = await pollStrategyActionJob(kind, job.job_id, copy.headline);
          if (terminalJobStatus(completed.status)) {
            await refreshStrategies();
            if (kind === "backtest") {
              openLatestBacktestForParams(params);
            }
          }
        }
      } catch (error) {
        appendOperationLog(kind, `Failed: ${error.message}`);
        renderOperationProgress(kind, {
          status: "failed",
          percent: 100,
          headline: `${label(kind)} failed`,
          logs: state[strategyOperationLogKey(kind)],
        });
      }
    }

    async function pollStrategyActionJob(kind, jobId, headline) {
      let latest = {job_id: jobId, status: "queued"};
      let lastStatus = "";
      for (let attempt = 0; attempt < 600; attempt += 1) {
        await wait(3000);
        latest = await fetchJob(jobId);
        const status = latest.status || "unknown";
        if (status !== lastStatus) {
          appendOperationLog(kind, `Job ${jobId} ${status}.`);
          lastStatus = status;
        }
        renderOperationProgress(kind, {
          status,
          percent: jobStatusPercent(status),
          headline,
          logs: operationLogsWithJob(kind, latest),
        });
        if (terminalJobStatus(status)) {
          showToast(`${label(kind)} job ${status}.`);
          return latest;
        }
      }
      appendOperationLog(kind, `${label(kind)} is still running. Refresh jobs to inspect it later.`);
      renderOperationProgress(kind, {
        status: "running",
        percent: 88,
        headline,
        logs: state[strategyOperationLogKey(kind)],
      });
      return latest;
    }

    function openLatestBacktestForParams(params) {
      const outputs = strategyOutputs();
      const match = outputs.find((item) => {
        const identity = strategyIdentity(item);
        return (!params.strategy_name || identity.name === params.strategy_name)
          && (!params.symbol || identity.symbol === params.symbol)
          && (!params.timeframe || identity.timeframe === params.timeframe);
      });
      if (!match) return;
      state.strategyOperationTab = "backtest";
      state.selectedStrategyOutput = match;
      state.strategyBacktestDetailOpen = true;
      const identity = strategyIdentity(match);
      setSelectIfPresent("#strategy-name", identity.name);
      setSelectIfPresent("#strategy-symbol", identity.symbol);
      setSelectIfPresent("#strategy-timeframe", identity.timeframe);
      setSelectIfPresent("#strategy-chart-symbol", identity.symbol);
      setSelectIfPresent("#strategy-chart-timeframe", identity.timeframe);
      strategyChart.resetCandlestickView("#backtest-chart");
      queueStrategyChartRefresh({clearBacktest: false});
      renderStrategies();
    }

    function selectedExperimentStrategyNames() {
      const choices = experimentChoices();
      ensureExperimentSelection(choices);
      const validNames = new Set(choices.map((choice) => choice.name));
      return unique(state.strategyExperimentSelection.filter((name) => validNames.has(name)));
    }

    function queueStrategyChartRefresh(options = {}) {
      window.clearTimeout(state.strategyChartPreviewTimer);
      state.strategyChartPreviewTimer = window.setTimeout(() => loadStrategyChartPreview({silent: true, ...options}), 220);
    }

    function strategyChartRequest({silent = false} = {}) {
      const source = String(document.querySelector("#strategy-chart-source")?.value || "").trim();
      const symbol = String(document.querySelector("#strategy-chart-symbol")?.value || "").trim();
      const timeframe = String(document.querySelector("#strategy-chart-timeframe")?.value || "").trim();
      const windowValue = strategyChartWindowValue(document.querySelector("#strategy-chart-range")?.value || state.strategyWindow);
      if (!source || !symbol || !timeframe) {
        if (!silent) showToast("Chart requires source, symbol, and timeframe.");
        return null;
      }
      const selected = state.strategyOperationTab === "backtest" ? state.selectedStrategyOutput : null;
      const sampleWindow = backtestSampleWindow(selected);
      if (sampleWindow) {
        return {
          data_type: "ohlcv",
          source,
          symbol,
          timeframe,
          start: sampleWindow.start,
          end: sampleWindow.end,
          end_inclusive: true,
          limit: sampleWindow.limit,
          backtest_window: true,
        };
      }
      return {
        data_type: "ohlcv",
        source,
        symbol,
        timeframe,
        lookback: Number(windowValue),
      };
    }

    function backtestSampleWindow(item) {
      const sample = item?.fields?.metrics?.sample || {};
      const start = String(sample.start || sample.input_window_start || "").trim();
      const end = String(sample.end || sample.input_window_end || "").trim();
      if (!start || !end) return null;
      const rows = Number(sample.rows || sample.record_count || 0);
      return {
        start,
        end,
        limit: Math.min(BACKTEST_CHART_MAX_CANDLES, Number.isFinite(rows) && rows > 0 ? Math.ceil(rows) : BACKTEST_CHART_MAX_CANDLES),
      };
    }

    function dataVisualizationMatchesBacktestWindow(dataVis, sampleWindow) {
      if (!dataVis || !sampleWindow) return false;
      return Boolean(dataVis.backtest_window)
        && String(dataVis.request_start || "") === String(sampleWindow.start)
        && String(dataVis.request_end || "") === String(sampleWindow.end);
    }

    async function loadStrategyChartPreview(options = {}) {
      const request = strategyChartRequest(options);
      if (!request) return;
      const requestId = state.strategyChartPreviewRequest + 1;
      state.strategyChartPreviewRequest = requestId;
      try {
        const payload = await postJson(endpoints.dataViewerPreview, {
          ...request,
          limit: request.limit || request.lookback,
          sort_order: "asc",
        });
        if (requestId !== state.strategyChartPreviewRequest) return;
        state.dataViewerStrategyPreview = payload;
        const clearBacktest = options.clearBacktest ?? state.strategyOperationTab !== "backtest";
        renderStrategyOhlcvPreview(payload, request, {clearBacktest});
      } catch (error) {
        if (requestId !== state.strategyChartPreviewRequest) return;
        if (!options.silent) showToast(`Chart load failed: ${error.message}`);
      }
    }

    function strategyCollectTargets() {
      return state.strategyCollectTargets.filter((target) => target.symbol && target.timeframe);
    }

    function strategyCollectBaseRequest({silent = false} = {}) {
      const source = String(document.querySelector("#strategy-collect-source")?.value || "").trim();
      const start = String(document.querySelector("#strategy-collect-start")?.value || "").trim();
      const end = String(document.querySelector("#strategy-collect-end")?.value || "").trim();
      if (!source || !start || !end) {
        if (!silent) showToast("Collect requires source, start, and end.");
        return null;
      }
      return {
        data_type: "ohlcv",
        source,
        start,
        end,
        max_exact_windows: 3,
        merge_gap_threshold_seconds: 0,
        min_fetch_window_seconds: 0,
      };
    }

    function strategyCollectRequest(target, options = {}) {
      const base = strategyCollectBaseRequest(options);
      if (!base) return null;
      return {...base, symbol: target.symbol, timeframe: target.timeframe};
    }

    function queueStrategyCollectTimelineRefresh() {
      window.clearTimeout(state.strategyCollectTimelineTimer);
      state.strategyCollectTimelineTimer = window.setTimeout(refreshStrategyCollectTimeline, 220);
    }

    async function refreshStrategyCollectTimeline() {
      const panel = document.querySelector("#strategy-collect-timeline");
      if (!panel || state.strategyOperationTab !== "collect") return;
      const targets = strategyCollectTargets();
      const base = strategyCollectBaseRequest({silent: true});
      if (!targets.length) {
        panel.innerHTML = `<div class="message">Add at least one target to view collection coverage.</div>`;
        return;
      }
      if (!base) {
        panel.innerHTML = `<div class="message">Choose a source and time range to view collection coverage.</div>`;
        return;
      }
      const requestId = state.strategyCollectTimelineRequest + 1;
      state.strategyCollectTimelineRequest = requestId;
      panel.innerHTML = `<div class="message">Loading ${escapeHtml(formatNumber(targets.length))} coverage timeline${targets.length === 1 ? "" : "s"}.</div>`;
      const results = await Promise.all(targets.map(async (target) => {
        const request = {...base, symbol: target.symbol, timeframe: target.timeframe};
        try {
          const payload = await postJson(endpoints.dataViewerTimeline, request);
          return {target, request, payload};
        } catch (error) {
          return {target, request, payload: {status: "failed", intervals: [], errors: [error.message]}};
        }
      }));
      if (requestId !== state.strategyCollectTimelineRequest) return;
      panel.innerHTML = renderCollectTimelineResults(results, base);
    }

    function renderCollectTimelineResults(results, base) {
      return results.map((item) => {
        const intervals = Array.isArray(item.payload?.intervals) ? item.payload.intervals : [];
        const errors = Array.isArray(item.payload?.errors) ? item.payload.errors : [];
        const segments = intervals.length && !errors.length
          ? intervals.map((interval) => collectTimelineSegment(interval, base)).join("")
          : collectTimelineSegment({range_start: base.start, range_end: base.end, status: errors.length ? "failed" : "unknown"}, base);
        const meta = errors.length
          ? errors.slice(0, 2).join("; ")
          : intervals.length
          ? `${intervals.length} coverage interval${intervals.length === 1 ? "" : "s"}`
          : "coverage is unknown for this range";
        return `
          <div class="collect-timeline-row">
            <div class="collect-timeline-label"><strong>${escapeHtml(item.target.symbol)}</strong><span>${escapeHtml(item.target.timeframe)}</span></div>
            <div class="collect-timeline-track" aria-label="${escapeHtml(item.target.symbol)} ${escapeHtml(item.target.timeframe)} coverage">${segments}</div>
            <div class="collect-timeline-meta">${escapeHtml(meta)}</div>
          </div>`;
      }).join("");
    }

    function collectTimelineSegment(interval, base) {
      const startMs = Date.parse(base.start);
      const endMs = Date.parse(base.end);
      if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) {
        const status = String(interval.status || "unknown").toLowerCase();
        return `<span class="collect-timeline-segment ${escapeHtml(statusClass(status))} ${escapeHtml(status)}" style="left:0%;width:100%;" title="${escapeHtml(status)}"></span>`;
      }
      const rawIntervalStart = Date.parse(interval.range_start || base.start);
      const rawIntervalEnd = Date.parse(interval.range_end || base.end);
      const intervalStart = Math.max(startMs, Number.isFinite(rawIntervalStart) ? rawIntervalStart : startMs);
      const intervalEnd = Math.min(endMs, Number.isFinite(rawIntervalEnd) ? rawIntervalEnd : endMs);
      const total = Math.max(1, endMs - startMs);
      const left = Math.max(0, Math.min(100, (intervalStart - startMs) / total * 100));
      const width = Math.max(1, Math.min(100 - left, (intervalEnd - intervalStart) / total * 100));
      const status = String(interval.status || "unknown").toLowerCase();
      const title = `${status}: ${formatTimestamp(interval.range_start || base.start)} to ${formatTimestamp(interval.range_end || base.end)}`;
      return `<span class="collect-timeline-segment ${escapeHtml(statusClass(status))} ${escapeHtml(status)}" style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%;" title="${escapeHtml(title)}"></span>`;
    }

    async function runStrategyCollectBatch() {
      const targets = strategyCollectTargets();
      if (!targets.length) {
        showToast("Add at least one collection target first.");
        return;
      }
      state.strategyCollectLogs = [];
      appendOperationLog("collect", `Starting collection for ${targets.length} target${targets.length === 1 ? "" : "s"}.`);
      let failed = false;
      for (let index = 0; index < targets.length; index += 1) {
        const target = targets[index];
        const request = strategyCollectRequest(target);
        if (!request) return;
        appendOperationLog("collect", `Submitting ${target.symbol} ${target.timeframe}.`);
        renderOperationProgress("collect", {
          status: "running",
          percent: Math.round(index / targets.length * 100),
          headline: `Collecting ${target.symbol} ${target.timeframe}`,
          logs: state.strategyCollectLogs,
        });
        try {
          const payload = await postJson(endpoints.dataViewerCollectJobs, request);
          const job = payload.job || payload;
          appendOperationLog("collect", `${target.symbol} ${target.timeframe} job ${job.job_id || "pending"} ${job.status || "created"}.`);
          if (job.job_id) {
            const completed = await pollCollectJob(job.job_id, target, index, targets.length);
            failed = failed || statusClass(completed.status) === "failed";
          } else {
            failed = true;
          }
        } catch (error) {
          failed = true;
          appendOperationLog("collect", `${target.symbol} ${target.timeframe} failed: ${error.message}`);
          renderOperationProgress("collect", {
            status: "failed",
            percent: Math.round((index + 1) / targets.length * 100),
            headline: `Collection failed for ${target.symbol} ${target.timeframe}`,
            logs: state.strategyCollectLogs,
          });
        }
      }
      await dataViewerWorkflow.loadDataViewerSummary();
      dataViewerWorkflow.renderStrategyViewer();
      queueStrategyCollectTimelineRefresh();
      renderOperationProgress("collect", {
        status: failed ? "failed" : "succeeded",
        percent: 100,
        headline: failed ? "Collection finished with errors" : "Collection complete",
        logs: state.strategyCollectLogs,
      });
    }

    async function pollCollectJob(jobId, target, index, total) {
      let latest = {job_id: jobId, status: "queued"};
      let lastStatus = "";
      for (let attempt = 0; attempt < 600; attempt += 1) {
        await wait(3000);
        latest = await fetchJob(jobId);
        const status = latest.status || "unknown";
        if (status !== lastStatus) {
          appendOperationLog("collect", `${target.symbol} ${target.timeframe} ${status}.`);
          lastStatus = status;
        }
        const percent = Math.round(((index + jobStatusFraction(status)) / total) * 100);
        renderOperationProgress("collect", {
          status,
          percent,
          headline: `Collecting ${target.symbol} ${target.timeframe}`,
          logs: operationLogsWithJob("collect", latest),
        });
        if (terminalJobStatus(status)) return latest;
      }
      appendOperationLog("collect", `${target.symbol} ${target.timeframe} is still running.`);
      return latest;
    }

    function appendOperationLog(kind, message) {
      const key = strategyOperationLogKey(kind);
      const timeText = new Date().toLocaleTimeString(undefined, {hour12: false});
      state[key].push(`${timeText} ${message}`);
    }

    function operationLogsWithJob(kind, job) {
      const key = strategyOperationLogKey(kind);
      const logs = [...state[key]];
      const warnings = Array.isArray(job?.warnings) ? job.warnings : [];
      const errors = Array.isArray(job?.errors) ? job.errors : [];
      Object.entries(job?.result_refs || {}).forEach(([name, ref]) => logs.push(`${name}: ${ref}`));
      warnings.slice(0, 3).forEach((warning) => logs.push(`warning: ${warning}`));
      errors.slice(0, 3).forEach((error) => logs.push(`error: ${error}`));
      return logs;
    }

    function strategyOperationLogKey(kind) {
      if (kind === "backtest") return "strategyBacktestLogs";
      if (kind === "experiment") return "strategyExperimentLogs";
      return "strategyCollectLogs";
    }

    function renderOperationProgress(kind, payload) {
      const node = document.querySelector(`#strategy-${kind}-progress`);
      if (!node) return;
      const status = payload.status || "running";
      const percent = Math.max(0, Math.min(100, Number(payload.percent) || 0));
      const logs = Array.isArray(payload.logs) ? payload.logs : [];
      const expanded = node.dataset.expanded === "true";
      const visibleLogs = logs.slice().reverse();
      const latestLog = visibleLogs[0] || "No log lines yet.";
      node.className = `operation-progress ${expanded ? "expanded" : ""}`.trim();
      node.innerHTML = `
        <div class="operation-progress-top">
          <div><strong>${escapeHtml(payload.headline || label(status))}</strong><span>${escapeHtml(label(status))}</span></div>
          <span>${escapeHtml(`${Math.round(percent)}%`)}</span>
        </div>
        <div class="operation-progress-track"><span class="${escapeHtml(statusClass(status))}" style="width:${percent}%;"></span></div>
        <div class="operation-log-header">
          <span class="operation-log-latest" title="${escapeHtml(latestLog)}">${escapeHtml(latestLog)}</span>
          <button class="ghost-button compact-button" type="button" data-operation-log-toggle="${escapeHtml(kind)}" aria-expanded="${expanded ? "true" : "false"}">${expanded ? "Collapse" : "Expand logs"}</button>
        </div>
        <pre class="operation-log ${expanded ? "expanded" : ""}">${escapeHtml(visibleLogs.join("\n") || "No log lines yet.")}</pre>`;
      node.querySelector("[data-operation-log-toggle]")?.addEventListener("click", () => {
        node.dataset.expanded = expanded ? "false" : "true";
        renderOperationProgress(kind, payload);
      });
    }

    function jobStatusFraction(status) {
      const normalized = String(status || "").toLowerCase();
      if (terminalJobStatus(normalized)) return 1;
      if (normalized === "running") return 0.66;
      if (normalized === "queued" || normalized === "created" || normalized === "creating") return 0.18;
      if (normalized === "cancel_requested") return 0.85;
      return 0.35;
    }

    function jobStatusPercent(status) {
      return Math.round(jobStatusFraction(status) * 100);
    }

    function removeEmpty(value) {
      return Object.fromEntries(Object.entries(value).filter((entry) => entry[1] !== null && entry[1] !== undefined && entry[1] !== ""));
    }

    async function refreshIntelligence() {
      try {
        const [textIntel] = await Promise.all([
          fetchJson(endpoints.textIntel),
          loadStores().catch(() => null),
          dataViewerWorkflow.loadDataViewerSummary().catch(() => null),
        ]);
        state.intelligence = textIntel;
        state.intelligenceOverviewPreviews = null;
        state.intelligenceOverviewErrors = {};
      } catch (error) {
        state.intelligence = {status: "failed", warnings: [error.message], artifacts: []};
        state.intelligenceOverviewPreviews = null;
        state.intelligenceOverviewErrors = {};
        await dataViewerWorkflow.loadDataViewerSummary();
      }
      renderIntelligence();
    }

    function renderIntelligence() {
      syncIntelTabs();
      const overview = state.selectedIntelTab === "overview";
      document.querySelector("#intel-overview-panel")?.classList.toggle("hidden", !overview);
      document.querySelector("#intel-data-viewer")?.classList.toggle("hidden", overview);
      if (overview) {
        renderIntelligenceOverview();
        return;
      }
      setSelectIfPresent("#intel-data-type", state.selectedIntelTab);
      state.selectedIntelPreviewIndex = 0;
      dataViewerWorkflow.renderIntelligenceViewer();
    }

    function syncIntelTabs() {
      const supportedTabs = ["overview", ...INTELLIGENCE_DATA_TYPES];
      if (!supportedTabs.includes(state.selectedIntelTab)) {
        state.selectedIntelTab = "overview";
      }
      document.querySelectorAll("[data-intel-tab]").forEach((button) => {
        button.classList.toggle("active", button.dataset.intelTab === state.selectedIntelTab);
      });
    }

    function renderIntelligenceOverviewLoading() {
      setHtml("#intel-overview-kpis", `
        <div class="intel-overview-pulse">
          ${Array.from({length: 4}, () => `<div class="intel-overview-pulse-card loading-surface">${skeletonLine("48%")}${skeletonLine("72%")}</div>`).join("")}
        </div>`);
    }

    function renderIntelligenceOverview() {
      const hasPreviews = state.intelligenceOverviewPreviews && Object.keys(state.intelligenceOverviewPreviews).length;
      if (!hasPreviews) {
        renderIntelligenceOverviewLoading();
        setHtml("#intel-overview-content", `
          <div class="intel-overview-dashboard">
            <section class="panel panel-pad intel-overview-section wide">${skeletonList(4)}</section>
            <section class="panel panel-pad intel-overview-section side">${skeletonList(4)}</section>
            <section class="panel panel-pad intel-overview-section chart">${skeletonMessage(3)}</section>
            <section class="panel panel-pad intel-overview-section chart">${skeletonMessage(3)}</section>
          </div>`);
        loadIntelligenceOverviewPreviews();
        return;
      }
      const model = buildIntelligenceOverviewModel();
      document.querySelector("#intel-overview-kpis").innerHTML = renderIntelligenceOverviewPulse(model);
      document.querySelector("#intel-overview-content").innerHTML = renderIntelligenceOverviewDashboard(model);
      wireIntelligenceOverview();
    }

    async function loadIntelligenceOverviewPreviews() {
      if (state.intelligenceOverviewLoading) return;
      const requestId = state.intelligenceOverviewRequestId + 1;
      state.intelligenceOverviewRequestId = requestId;
      state.intelligenceOverviewLoading = true;
      const results = {};
      const errors = {};
      await Promise.all(INTELLIGENCE_DATA_TYPES.map(async (dataType) => {
        const request = intelligenceOverviewPreviewRequest(dataType);
        if (!request || !endpoints.dataViewerPreview) {
          results[dataType] = {data_type: dataType, status: "unavailable", records: [], query: {}, overview_request: request};
          return;
        }
        try {
          const payload = await postJson(endpoints.dataViewerPreview, request);
          results[dataType] = {...payload, overview_request: request};
        } catch (error) {
          errors[dataType] = error.message || "Preview failed.";
          results[dataType] = {data_type: dataType, status: "failed", records: [], errors: [errors[dataType]], query: {}, overview_request: request};
        }
      }));
      if (state.intelligenceOverviewRequestId !== requestId) return;
      state.intelligenceOverviewPreviews = results;
      state.intelligenceOverviewErrors = errors;
      state.intelligenceOverviewLoading = false;
      if (state.selectedIntelTab === "overview") {
        renderIntelligenceOverview();
      }
    }

    function intelligenceOverviewPreviewRequest(dataType) {
      const summary = intelligenceStoreSummary(dataType);
      const coverage = summary?.coverage || {};
      const coverageStart = parseDateSafe(coverage.range_start);
      const coverageEnd = parseDateSafe(coverage.range_end);
      const now = new Date();
      let start;
      let end;
      if (coverageStart && coverageEnd) {
        if (dataType === "macro_calendar") {
          start = maxDate(coverageStart, new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000));
          end = minDate(coverageEnd, new Date(now.getTime() + 180 * 24 * 60 * 60 * 1000));
          if (start.getTime() > end.getTime()) {
            start = coverageStart;
            end = coverageEnd;
          }
        } else {
          end = coverageEnd;
          start = maxDate(coverageStart, new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000));
        }
      } else {
        end = dataType === "macro_calendar" ? new Date(now.getTime() + 180 * 24 * 60 * 60 * 1000) : now;
        start = dataType === "macro_calendar" ? new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000) : new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000);
      }
      if (!start || !end || start.getTime() > end.getTime()) return null;
      return {
        data_type: dataType,
        start: toIsoSeconds(start),
        end: toIsoSeconds(end),
        limit: INTELLIGENCE_OVERVIEW_LIMITS[dataType] || 80,
        sort_order: dataType === "macro_calendar" ? "asc" : "desc",
      };
    }

    function buildIntelligenceOverviewModel() {
      const previews = state.intelligenceOverviewPreviews || {};
      const stores = intelligenceStoreSummaries();
      const recordsByType = Object.fromEntries(INTELLIGENCE_DATA_TYPES.map((dataType) => [
        dataType,
        (Array.isArray(previews[dataType]?.records) ? previews[dataType].records : []).slice(),
      ]));
      const latestRecords = INTELLIGENCE_DATA_TYPES.flatMap((dataType) => recordsByType[dataType].map((record) => ({dataType, record})))
        .sort((left, right) => timestampMs(intelligenceRecordTime(right.record, right.dataType)) - timestampMs(intelligenceRecordTime(left.record, left.dataType)));
      const issueCount = stores.reduce((sum, store) => sum + (store.warnings || []).length + (store.errors || []).length, 0)
        + Object.values(previews).reduce((sum, payload) => sum + (payload?.warnings || []).length + (payload?.errors || []).length, 0);
      return {
        previews,
        stores,
        recordsByType,
        latestRecords,
        issueCount,
        textEvents: recordsByType.text_event || [],
        macroEvents: intelligenceOverviewMacroEvents(recordsByType.macro_calendar || []),
        anomalies: intelligenceOverviewAnomalies(recordsByType.market_anomaly || []),
        onchainChart: intelligenceOverviewMetricModel("onchain_flow", recordsByType.onchain_flow || []),
        derivativesChart: intelligenceOverviewMetricModel("derivatives_market", recordsByType.derivatives_market || []),
      };
    }

    function renderIntelligenceOverviewPulse(model) {
      const sourceCount = unique(model.latestRecords.map(({record}) => intelligenceRecordSource(record)).filter(Boolean)).length;
      const newest = model.latestRecords[0];
      const upcoming = model.macroEvents.filter((event) => timestampMs(intelligenceRecordTime(event, "macro_calendar")) >= Date.now()).length;
      const highAnomalies = model.anomalies.filter((record) => ["critical", "high"].includes(String(record?.severity || "").toLowerCase())).length;
      return `
        <div class="intel-overview-pulse">
          ${renderIntelOverviewPulseCard("Latest intelligence", model.latestRecords.length, newest ? `${intelligenceTypeLabel(newest.dataType)} / ${formatTimestamp(intelligenceRecordTime(newest.record, newest.dataType))}` : "No recent records")}
          ${renderIntelOverviewPulseCard("Market anomalies", model.anomalies.length, `${formatNumber(highAnomalies)} high severity`)}
          ${renderIntelOverviewPulseCard("Macro agenda", upcoming, "upcoming scheduled events")}
          ${renderIntelOverviewPulseCard("Sources", sourceCount, model.issueCount ? `${formatNumber(model.issueCount)} warnings or errors` : "no overview issues")}
        </div>`;
    }

    function renderIntelOverviewPulseCard(title, value, note) {
      return `
        <article class="intel-overview-pulse-card">
          <span>${escapeHtml(title)}</span>
          <strong>${escapeHtml(formatNumber(value))}</strong>
          <small>${escapeHtml(note || "")}</small>
        </article>`;
    }

    function renderIntelligenceOverviewDashboard(model) {
      return `
        <div class="intel-overview-dashboard">
          ${renderIntelOverviewTextEvents(model.textEvents)}
          ${renderIntelOverviewMacroAgenda(model.macroEvents)}
          ${renderIntelOverviewAnomalyRadar(model.anomalies)}
          ${renderIntelOverviewChartSection("On-chain flow", "onchain_flow", model.onchainChart)}
          ${renderIntelOverviewChartSection("Derivatives market", "derivatives_market", model.derivativesChart)}
          ${renderIntelOverviewHealth(model)}
        </div>`;
    }

    function renderIntelOverviewTextEvents(records) {
      const rows = records
        .slice()
        .sort((left, right) => timestampMs(intelligenceRecordTime(right, "text_event")) - timestampMs(intelligenceRecordTime(left, "text_event")))
        .slice(0, 6);
      return `
        <section class="panel panel-pad intel-overview-section wide">
          ${renderIntelOverviewSectionHead("Recent text intelligence", "Headlines, source refs, and warning text from text-event stores.", "text_event")}
          <div class="intel-overview-headline-list">
            ${rows.map((record) => renderIntelOverviewHeadlineRow(record, "text_event")).join("") || `<div class="empty-state">No recent text events are available for the overview window.</div>`}
          </div>
        </section>`;
    }

    function renderIntelOverviewMacroAgenda(records) {
      const rows = records.slice(0, 7);
      return `
        <section class="panel panel-pad intel-overview-section side">
          ${renderIntelOverviewSectionHead("Macro agenda", "Upcoming and recent scheduled events.", "macro_calendar")}
          <div class="intel-overview-agenda">
            ${rows.map((record) => renderIntelOverviewAgendaRow(record)).join("") || `<div class="empty-state">No macro calendar events are available for the overview window.</div>`}
          </div>
        </section>`;
    }

    function renderIntelOverviewAnomalyRadar(records) {
      const rows = records.slice(0, 6);
      const severityCounts = countBySimple(records, (record) => String(record?.severity || "unknown").toLowerCase());
      return `
        <section class="panel panel-pad intel-overview-section side">
          ${renderIntelOverviewSectionHead("Anomaly radar", "Deduped market anomalies ranked by severity and magnitude.", "market_anomaly")}
          <div class="intel-overview-anomaly-strip">
            ${["critical", "high", "medium", "low"].map((severity) => `
              <span class="intel-overview-anomaly-count severity-${escapeHtml(severity)}"><strong>${escapeHtml(formatNumber(severityCounts.get(severity) || 0))}</strong>${escapeHtml(label(severity))}</span>
            `).join("")}
          </div>
          <div class="intel-overview-mini-list">
            ${rows.map((record) => renderIntelOverviewHeadlineRow(record, "market_anomaly")).join("") || `<div class="empty-state">No anomaly records are available for the overview window.</div>`}
          </div>
        </section>`;
    }

    function renderIntelOverviewChartSection(title, dataType, model) {
      return `
        <section class="panel panel-pad intel-overview-section chart">
          ${renderIntelOverviewSectionHead(title, model ? `${model.label} / ${overviewMetricLabel(model.metricKey)}` : "No numeric series available.", dataType)}
          ${model ? `
            <div class="intel-overview-chart-summary">
              <div>
                <span>Latest</span>
                <strong>${escapeHtml(formatOverviewMetricValue(model.latest?.value, model.metricKey, model.unit))}</strong>
              </div>
              <div>
                <span>Range</span>
                <strong>${escapeHtml(formatTimestamp(model.first?.time))} - ${escapeHtml(formatTimestamp(model.latest?.time))}</strong>
              </div>
            </div>
            ${renderIntelOverviewSparkline(model)}
          ` : `<div class="empty-state">No chartable ${escapeHtml(intelligenceTypeLabel(dataType))} observations are available for the overview window.</div>`}
        </section>`;
    }

    function renderIntelOverviewHealth(model) {
      return `
        <section class="panel panel-pad intel-overview-section health">
          <div class="intel-overview-section-head">
            <div>
              <h2 class="panel-title">Data health</h2>
              <p>Compact status only; use each tab for full coverage timelines and properties.</p>
            </div>
            ${model.issueCount ? statusPill("warning", `${formatNumber(model.issueCount)} issues`) : statusPill("available", "No issues")}
          </div>
          <div class="intel-overview-health-list">
            ${INTELLIGENCE_DATA_TYPES.map((dataType) => renderIntelOverviewHealthRow(dataType, model)).join("")}
          </div>
        </section>`;
    }

    function renderIntelOverviewSectionHead(title, note, dataType) {
      return `
        <div class="intel-overview-section-head">
          <div>
            <h2 class="panel-title">${escapeHtml(title)}</h2>
            <p>${escapeHtml(note || "")}</p>
          </div>
          <button class="ghost-button compact-button" type="button" data-intel-overview-open="${escapeHtml(dataType)}">Open</button>
        </div>`;
    }

    function renderIntelOverviewHeadlineRow(record, dataType) {
      const time = intelligenceRecordTime(record, dataType);
      const category = intelligenceRecordCategory(record, dataType);
      const source = intelligenceRecordSource(record);
      return `
        <button class="intel-overview-record-row" type="button" data-intel-overview-open="${escapeHtml(dataType)}">
          <span class="intel-overview-record-main">
            <strong>${escapeHtml(intelligenceRecordTitle(record, dataType))}</strong>
            <small>${escapeHtml(formatTimestamp(time))}${source ? ` / ${escapeHtml(source)}` : ""}</small>
          </span>
          <span class="tag-row">
            ${record?.severity ? `<span class="status-pill ${escapeHtml(anomalyOverviewStatus(record.severity))}">${escapeHtml(label(record.severity))}</span>` : ""}
            <span class="tag">${escapeHtml(category)}</span>
          </span>
        </button>`;
    }

    function renderIntelOverviewAgendaRow(record) {
      const time = intelligenceRecordTime(record, "macro_calendar");
      const future = timestampMs(time) >= Date.now();
      const importance = record?.importance || record?.impact || "unknown";
      const region = record?.region || record?.country || record?.currency || "global";
      return `
        <button class="intel-overview-agenda-row ${future ? "future" : "past"}" type="button" data-intel-overview-open="macro_calendar">
          <span class="intel-overview-agenda-date">${escapeHtml(formatTimestamp(time))}</span>
          <span class="intel-overview-record-main">
            <strong>${escapeHtml(intelligenceRecordTitle(record, "macro_calendar"))}</strong>
            <small>${escapeHtml(intelligenceRecordSummary(record, "macro_calendar"))}</small>
          </span>
          <span class="tag-row">
            <span class="status-pill ${future ? "available" : "skipped"}">${future ? "Future" : "Past"}</span>
            <span class="tag">${escapeHtml(label(importance))}</span>
            <span class="tag">${escapeHtml(label(region))}</span>
          </span>
        </button>`;
    }

    function renderIntelOverviewHealthRow(dataType, model) {
      const store = intelligenceStoreSummary(dataType);
      const preview = model.previews[dataType] || {};
      const coverage = store?.coverage || {};
      const records = Array.isArray(preview.records) ? preview.records.length : 0;
      const status = preview.status || store?.status || coverage.state_status || "unknown";
      const range = coverage.range_start && coverage.range_end
        ? `${formatTimestamp(coverage.range_start)} - ${formatTimestamp(coverage.range_end)}`
        : "No coverage range";
      return `
        <button class="intel-overview-health-row" type="button" data-intel-overview-open="${escapeHtml(dataType)}">
          <span>
            <strong>${escapeHtml(intelligenceTypeLabel(dataType))}</strong>
            <small>${escapeHtml(range)}</small>
          </span>
          <span>${escapeHtml(formatNumber(records))} loaded</span>
          ${statusPill(status)}
        </button>`;
    }

    function renderIntelOverviewSparkline(model) {
      const series = model.series || [];
      if (series.length < 2) {
        return `<div class="empty-state">At least two numeric observations are needed for a trend chart.</div>`;
      }
      const values = series.map((point) => point.value);
      let min = Math.min(...values);
      let max = Math.max(...values);
      if (min === max) {
        const padding = Math.abs(max || 1) * 0.05;
        min -= padding;
        max += padding;
      } else {
        const padding = (max - min) * 0.08;
        min -= padding;
        max += padding;
      }
      const width = 620;
      const height = 190;
      const left = 58;
      const right = 24;
      const top = 18;
      const bottom = 40;
      const plotWidth = width - left - right;
      const plotHeight = height - top - bottom;
      const xFor = (index) => left + (index / Math.max(1, series.length - 1)) * plotWidth;
      const yFor = (value) => top + ((max - value) / Math.max(1, max - min)) * plotHeight;
      const path = series.map((point, index) => `${index === 0 ? "M" : "L"}${xFor(index).toFixed(2)},${yFor(point.value).toFixed(2)}`).join(" ");
      const yTicks = [max, (max + min) / 2, min];
      const visibleEvery = Math.max(1, Math.ceil(series.length / 48));
      return `
        <div class="intel-overview-sparkline" aria-label="${escapeHtml(model.label)} ${escapeHtml(overviewMetricLabel(model.metricKey))} trend">
          <svg class="intel-overview-sparkline-svg" viewBox="0 0 ${width} ${height}" role="img">
            <rect x="0" y="0" width="${width}" height="${height}" fill="transparent"></rect>
            ${yTicks.map((tick) => {
              const y = yFor(tick);
              return `<g class="intel-overview-spark-grid"><line x1="${left}" x2="${width - right}" y1="${y.toFixed(2)}" y2="${y.toFixed(2)}"></line><text x="${left - 8}" y="${(y + 4).toFixed(2)}">${escapeHtml(formatOverviewMetricValue(tick, model.metricKey, model.unit))}</text></g>`;
            }).join("")}
            <path class="intel-overview-sparkline-path" d="${path}"></path>
            ${series.map((point, index) => {
              const x = xFor(index);
              const y = yFor(point.value);
              const valueLabel = formatOverviewMetricValue(point.value, model.metricKey, model.unit);
              const lines = [
                formatTimestamp(point.time),
                `${overviewMetricLabel(model.metricKey)}: ${valueLabel}`,
                intelligenceRecordTitle(point.record, model.dataType),
              ];
              return `
                <g class="intel-overview-spark-point">
                  ${(index % visibleEvery === 0 || index === series.length - 1) ? `<circle class="intel-overview-spark-dot" cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="${index === series.length - 1 ? 3.8 : 2.2}"></circle>` : ""}
                  <circle class="intel-overview-spark-hit" tabindex="0" cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="10"><title>${escapeHtml(lines.join(" / "))}</title></circle>
                  ${renderIntelOverviewSparkHover(x, y, left, right, top, width, height, plotHeight, valueLabel, lines)}
                </g>`;
            }).join("")}
          </svg>
        </div>`;
    }

    function renderIntelOverviewSparkHover(x, y, left, right, top, width, height, plotHeight, valueLabel, lines) {
      const tooltipWidth = 220;
      const lineHeight = 15;
      const tooltipHeight = 18 + lines.length * lineHeight;
      const tooltipX = Math.max(left + 8, Math.min(width - right - tooltipWidth - 8, x < width - tooltipWidth - 28 ? x + 14 : x - tooltipWidth - 14));
      const tooltipY = Math.max(top + 8, Math.min(height - tooltipHeight - 10, y - tooltipHeight - 12));
      return `
        <g class="intel-overview-spark-hover">
          <line class="intel-overview-spark-cross vertical" x1="${x.toFixed(2)}" x2="${x.toFixed(2)}" y1="${top}" y2="${top + plotHeight}"></line>
          <line class="intel-overview-spark-cross horizontal" x1="${left}" x2="${width - right}" y1="${y.toFixed(2)}" y2="${y.toFixed(2)}"></line>
          <rect class="intel-overview-spark-axis-pill" x="4" y="${(y - 11).toFixed(2)}" width="${Math.max(48, left - 12)}" height="22" rx="6"></rect>
          <text class="intel-overview-spark-axis-label" x="${left - 12}" y="${(y + 4).toFixed(2)}">${escapeHtml(valueLabel)}</text>
          <rect class="intel-overview-spark-tooltip-box" x="${tooltipX.toFixed(2)}" y="${tooltipY.toFixed(2)}" width="${tooltipWidth}" height="${tooltipHeight}" rx="8"></rect>
          ${lines.map((line, index) => `<text class="intel-overview-spark-tooltip-text ${index === 0 ? "primary" : ""}" x="${(tooltipX + 10).toFixed(2)}" y="${(tooltipY + 18 + index * lineHeight).toFixed(2)}">${escapeHtml(line)}</text>`).join("")}
        </g>`;
    }

    function wireIntelligenceOverview() {
      document.querySelectorAll("[data-intel-overview-open]").forEach((button) => {
        button.addEventListener("click", () => {
          const target = button.dataset.intelOverviewOpen;
          if (!INTELLIGENCE_DATA_TYPES.includes(target)) return;
          state.selectedIntelTab = target;
          renderIntelligence();
        });
      });
      wireIntelligenceOverviewSparklineHover();
    }

    function wireIntelligenceOverviewSparklineHover() {
      document.querySelectorAll(".intel-overview-spark-hit").forEach((hit) => {
        const point = hit.closest(".intel-overview-spark-point");
        if (!point) return;
        const show = () => point.classList.add("hovered");
        const hide = () => point.classList.remove("hovered");
        hit.addEventListener("mouseenter", show);
        hit.addEventListener("focus", show);
        hit.addEventListener("mouseleave", hide);
        hit.addEventListener("blur", hide);
      });
    }

    function intelligenceStoreSummaries() {
      const stores = Array.isArray(state.dataViewerSummary?.stores) ? state.dataViewerSummary.stores : [];
      return stores.filter((store) => INTELLIGENCE_DATA_TYPES.includes(store.data_type));
    }

    function intelligenceStoreSummary(dataType) {
      return intelligenceStoreSummaries().find((store) => store.data_type === dataType) || null;
    }

    function renderIntelStoreCard(store) {
      const coverage = store.coverage || {};
      const summary = store.summary || {};
      const records = summary.records ?? summary.record_count ?? coverage.record_count ?? 0;
      const statusCounts = Object.entries(coverage.status_counts || {})
        .filter((entry) => Number(entry[1]) > 0)
        .map(([status, count]) => `${status}: ${formatNumber(count)}`)
        .join(" / ");
      return `
        <article class="intel-store-card">
          <div class="intel-store-card-head">
            <strong>${escapeHtml(intelligenceTypeLabel(store.data_type))}</strong>
            ${statusPill(store.status || coverage.state_status || "unknown")}
          </div>
          <div class="intel-store-card-metric">${escapeHtml(formatNumber(records))}</div>
          <div class="muted">${escapeHtml(coverage.range_start && coverage.range_end ? `${formatTimestamp(coverage.range_start)} to ${formatTimestamp(coverage.range_end)}` : "No collected range")}</div>
          <div class="tag-row">${statusCounts ? statusCounts.split(" / ").map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("") : `<span class="tag">coverage n/a</span>`}</div>
        </article>`;
    }

    function renderIntelOverviewItem(item) {
      return `
        <article class="intel-overview-row">
          <div>
            <strong>${escapeHtml(item.title)}</strong>
            <span>${escapeHtml(item.summary || "No summary recorded.")}</span>
          </div>
          <div class="tag-row"><span class="status-pill ${item.severity === "High" ? "failed" : item.severity === "Medium" ? "warning" : "available"}">${escapeHtml(item.severity)}</span><span class="tag">${escapeHtml(item.category)}</span></div>
        </article>`;
    }

    function intelligenceOverviewItems() {
      const artifacts = Array.isArray(state.intelligence?.artifacts) ? state.intelligence.artifacts : [];
      return artifacts.map((artifact) => ({
        title: artifact.fields?.title || artifact.name || "Intelligence artifact",
        severity: artifact.errors?.length ? "High" : artifact.warnings?.length ? "Medium" : "Low",
        category: artifact.name || "artifact",
        time: artifact.fields?.updated_at || artifact.fields?.created_at,
        summary: [...(artifact.warnings || []), ...(artifact.errors || [])].join(" ") || `${label(artifact.status)} source-aware intelligence artifact.`,
        sources: artifact.source_artifacts || [],
        assets: intelligenceAssets(artifact),
      })).sort((left, right) => timestampMs(right.time) - timestampMs(left.time));
    }

    function intelligenceTypeLabel(dataType) {
      return {
        text_event: "Text events",
        macro_calendar: "Macro calendar",
        onchain_flow: "On-chain flow",
        derivatives_market: "Derivatives market",
        market_anomaly: "Market anomalies",
      }[dataType] || label(dataType);
    }

    function intelligenceOverviewMacroEvents(records) {
      return (Array.isArray(records) ? records : [])
        .slice()
        .sort((left, right) => {
          const leftTime = timestampMs(intelligenceRecordTime(left, "macro_calendar"));
          const rightTime = timestampMs(intelligenceRecordTime(right, "macro_calendar"));
          const now = Date.now();
          const leftFuture = leftTime >= now;
          const rightFuture = rightTime >= now;
          if (leftFuture !== rightFuture) return leftFuture ? -1 : 1;
          return leftFuture ? leftTime - rightTime : rightTime - leftTime;
        });
    }

    function intelligenceOverviewAnomalies(records) {
      return (Array.isArray(records) ? records : [])
        .slice()
        .sort((left, right) => {
          const severityDelta = overviewSeverityScore(right?.severity) - overviewSeverityScore(left?.severity);
          if (severityDelta) return severityDelta;
          const magnitudeDelta = overviewRecordMagnitude(right) - overviewRecordMagnitude(left);
          if (magnitudeDelta) return magnitudeDelta;
          return timestampMs(intelligenceRecordTime(right, "market_anomaly")) - timestampMs(intelligenceRecordTime(left, "market_anomaly"));
        });
    }

    function intelligenceOverviewMetricModel(dataType, records) {
      const groups = new Map();
      (Array.isArray(records) ? records : []).forEach((record) => {
        const category = intelligenceRecordCategory(record, dataType);
        if (!groups.has(category)) groups.set(category, []);
        groups.get(category).push(record);
      });
      const candidates = [];
      groups.forEach((groupRecords, groupKey) => {
        const keys = unique(groupRecords.flatMap((record) => overviewMetricEntries(record).map(([key]) => key)));
        const metricKey = overviewPreferredMetric(dataType, keys);
        if (!metricKey) return;
        const series = groupRecords
          .map((record) => {
            const value = overviewMetricValue(record, metricKey);
            const time = intelligenceRecordTime(record, dataType);
            return {record, time, timestamp: timestampMs(time), value};
          })
          .filter((point) => Number.isFinite(point.timestamp) && Number.isFinite(point.value))
          .sort((left, right) => left.timestamp - right.timestamp);
        if (!series.length) return;
        candidates.push({
          dataType,
          key: groupKey,
          label: label(groupKey),
          metricKey,
          unit: series[series.length - 1]?.record?.units?.[metricKey] || "",
          series,
          first: series[0],
          latest: series[series.length - 1],
        });
      });
      return candidates.sort((left, right) => {
        if (right.series.length !== left.series.length) return right.series.length - left.series.length;
        return timestampMs(right.latest?.time) - timestampMs(left.latest?.time);
      })[0] || null;
    }

    function intelligenceRecordTime(record, dataType) {
      const fields = {
        text_event: ["event_time", "published_at", "timestamp", "time", "first_seen_at", "collected_at"],
        macro_calendar: ["event_time", "scheduled_at", "release_time", "timestamp", "date", "time"],
        onchain_flow: ["observed_at", "timestamp", "as_of", "time", "collected_at"],
        derivatives_market: ["observed_at", "timestamp", "as_of", "funding_time", "time", "collected_at"],
        market_anomaly: ["event_time", "detected_at", "observed_at", "timestamp", "time", "collected_at"],
      }[dataType] || ["timestamp", "time", "collected_at"];
      const value = fields.map((field) => record?.[field]).find(Boolean);
      return value || record?.as_of || record?.collected_at || "";
    }

    function intelligenceRecordTitle(record, dataType) {
      if (!record) return "No record";
      if (dataType === "macro_calendar") return text(record.title || record.event || record.name || record.event_name, "Macro calendar event");
      if (dataType === "onchain_flow") return text(record.title, `${label(record.data_class || record.endpoint || "On-chain flow")} ${record.asset || record.chain || ""}`.trim());
      if (dataType === "derivatives_market") return text(record.title, `${record.symbol || "Market"} ${label(record.data_class || record.endpoint || "derivatives")}`.trim());
      if (dataType === "market_anomaly") return text(record.title, `${record.symbol || "Market"} ${label(record.data_class || record.anomaly_type || "anomaly")}`.trim());
      return text(record.title || record.headline || record.name || record.url, "Text event");
    }

    function intelligenceRecordSummary(record, dataType) {
      if (!record) return "";
      if (record.summary || record.description) return String(record.summary || record.description);
      if (dataType === "macro_calendar") {
        const parts = [
          record.region || record.country || record.currency,
          record.importance || record.impact,
          record.source,
        ].filter(Boolean);
        return parts.length ? parts.map(label).join(" / ") : "Scheduled macro event.";
      }
      const metrics = overviewMetricEntries(record).slice(0, 3);
      if (metrics.length) {
        return metrics.map(([key, value, unit]) => `${overviewMetricLabel(key)} ${formatOverviewMetricValue(value, key, unit)}`).join(" / ");
      }
      return text(record.content || record.body || record.url, "No summary recorded.");
    }

    function intelligenceRecordCategory(record, dataType) {
      return String(record?.data_class || record?.category || record?.event_type || record?.source_type || record?.endpoint || dataType || "uncategorized");
    }

    function intelligenceRecordSource(record) {
      return text(record?.source || record?.source_name || record?.provider || record?.source_type, "");
    }

    function overviewMetricEntries(record) {
      const metrics = record?.metrics && typeof record.metrics === "object" ? record.metrics : {};
      const units = record?.units && typeof record.units === "object" ? record.units : {};
      const entries = Object.entries(metrics)
        .map(([key, value]) => [key, Number(value), units[key] || ""])
        .filter((entry) => Number.isFinite(entry[1]));
      Object.entries(record || {}).forEach(([key, value]) => {
        if (entries.some(([existing]) => existing === key)) return;
        if (!overviewTopLevelMetricKey(key)) return;
        const numeric = Number(value);
        if (Number.isFinite(numeric)) entries.push([key, numeric, units[key] || ""]);
      });
      return entries;
    }

    function overviewTopLevelMetricKey(key) {
      return !/(^id$|_id$|key$|time$|timestamp|date|source|symbol|asset|chain|title|summary|url|status|severity|direction|class|type|endpoint)/i.test(key);
    }

    function overviewMetricValue(record, metricKey) {
      const raw = record?.metrics && Object.prototype.hasOwnProperty.call(record.metrics, metricKey) ? record.metrics[metricKey] : record?.[metricKey];
      const value = Number(raw);
      return Number.isFinite(value) ? value : NaN;
    }

    function overviewPreferredMetric(dataType, keys) {
      const preferred = {
        onchain_flow: ["exchange_netflow", "netflow", "mempool_size_bytes", "mempool_transaction_count", "transaction_count", "active_addresses", "value"],
        derivatives_market: ["funding_rate", "last_funding_rate", "open_interest_value", "open_interest_contracts", "basis_rate", "premium_rate", "depth_imbalance", "bid_depth_notional", "ask_depth_notional", "mark_price"],
        market_anomaly: ["severity_score", "score", "z_score", "volume_spike_multiplier", "price_change_pct", "magnitude", "value"],
      }[dataType] || [];
      return preferred.find((key) => keys.includes(key)) || keys[0] || "";
    }

    function overviewMetricLabel(key) {
      return {
        exchange_netflow: "Exchange netflow",
        mempool_size_bytes: "Mempool size",
        mempool_transaction_count: "Mempool transactions",
        active_addresses: "Active addresses",
        transaction_count: "Transactions",
        funding_rate: "Funding rate",
        last_funding_rate: "Last funding rate",
        open_interest_value: "Open interest value",
        open_interest_contracts: "Open interest",
        basis_rate: "Basis rate",
        premium_rate: "Premium rate",
        depth_imbalance: "Depth imbalance",
        bid_depth_notional: "Bid depth",
        ask_depth_notional: "Ask depth",
        volume_spike_multiplier: "Volume spike",
        price_change_pct: "Price change",
      }[key] || label(key);
    }

    function formatOverviewMetricValue(value, key, unit = "") {
      const number = Number(value);
      if (!Number.isFinite(number)) return text(value);
      const normalizedUnit = String(unit || "").toLowerCase();
      if (normalizedUnit === "ratio" || /rate|ratio|pct|percent/.test(String(key || "").toLowerCase())) {
        const pctValue = Math.abs(number) <= 1 ? number * 100 : number;
        return `${pctValue.toFixed(Math.abs(pctValue) >= 10 ? 1 : 2)}%`;
      }
      if (Math.abs(number) >= 1000000) return new Intl.NumberFormat("en-US", {notation: "compact", maximumFractionDigits: 2}).format(number);
      if (Math.abs(number) >= 1000) return formatNumber(Math.round(number));
      return Number.isInteger(number) ? formatNumber(number) : number.toFixed(Math.abs(number) >= 10 ? 2 : 4).replace(/0+$/, "").replace(/\.$/, "");
    }

    function overviewSeverityScore(severity) {
      return {critical: 5, high: 4, medium: 3, warning: 2, low: 1}[String(severity || "").toLowerCase()] || 0;
    }

    function overviewRecordMagnitude(record) {
      const entries = overviewMetricEntries(record);
      return entries.reduce((max, [, value]) => Math.max(max, Math.abs(Number(value) || 0)), 0);
    }

    function anomalyOverviewStatus(severity) {
      const normalized = String(severity || "").toLowerCase();
      if (["critical", "high"].includes(normalized)) return "failed";
      if (["medium", "warning"].includes(normalized)) return "warning";
      if (normalized === "low") return "available";
      return "unknown";
    }

    function countBySimple(items, getter) {
      const counts = new Map();
      (Array.isArray(items) ? items : []).forEach((item) => {
        const key = getter(item);
        counts.set(key, (counts.get(key) || 0) + 1);
      });
      return counts;
    }

    function parseDateSafe(value) {
      const date = value ? new Date(value) : null;
      return date && Number.isFinite(date.getTime()) ? date : null;
    }

    function maxDate(left, right) {
      return left.getTime() >= right.getTime() ? left : right;
    }

    function minDate(left, right) {
      return left.getTime() <= right.getTime() ? left : right;
    }

    function toIsoSeconds(date) {
      return date.toISOString().replace(/\.\d{3}Z$/, "Z");
    }

    function timestampMs(value) {
      const time = value ? new Date(value).getTime() : NaN;
      return Number.isFinite(time) ? time : 0;
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

    async function refreshSettings() {
      await Promise.allSettled([loadHealth(), loadStores(), loadDeletionPlan(), loadConfigProfile()]);
      renderSettings();
    }

    async function loadConfigProfile() {
      state.settingsProfile = await fetchJson(endpoints.settings);
      applyTimestampDisplayOptionsFromProfile(state.settingsProfile);
      return state.settingsProfile;
    }

    function renderSettings() {
      const sections = Array.isArray(state.settingsProfile?.sections) && state.settingsProfile.sections.length
        ? state.settingsProfile.sections
        : ["General", "Market data", "Strategy", "Reports", "Monitor", "Intelligence sources", "Storage", "Dashboard"];
      if (!sections.includes(state.settingsSection)) {
        state.settingsSection = sections[0] || "General";
      }
      document.querySelector("#settings-nav").innerHTML = sections.map((section) => `
        <button type="button" class="${section === state.settingsSection ? "active" : ""}" data-settings-section="${escapeHtml(section)}">
          <span>${escapeHtml(settingsSectionLabel(section))}</span>
          <svg class="settings-nav-chevron" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 4l4 4-4 4"></path></svg>
        </button>`).join("");
      document.querySelectorAll("[data-settings-section]").forEach((button) => button.addEventListener("click", () => {
        state.settingsSection = button.dataset.settingsSection;
        renderSettings();
      }));
      const loaded = state.settingsProfile?.config?.loaded !== false && state.settingsProfile?.status !== "unconfigured";
      renderSettingsConfigSelector();
      document.querySelector("#settings-section-title").textContent = settingsSectionLabel(state.settingsSection);
      document.querySelector("#settings-form").innerHTML = settingsForm(state.settingsSection);
      const backupButton = document.querySelector("#settings-backup");
      if (backupButton) backupButton.disabled = !loaded;
      renderChangeSummary();
      renderStorageMaintenance();
      wireSettingsControls();
      wireCleanupControls();
    }

    function settingsSectionLabel(section) {
      return section === "Monitor" ? "System Monitor" : section;
    }

    function renderSettingsConfigSelector() {
      const select = document.querySelector("#settings-config-select");
      if (!select) return;
      const selection = state.settingsProfile?.config_selection || {};
      const candidates = Array.isArray(selection.candidates) ? selection.candidates : [];
      const activeId = selection.active_id || candidates.find((candidate) => candidate.active)?.id || "";
      select.innerHTML = candidates.length
        ? candidates.map((candidate) => `<option value="${escapeHtml(candidate.id)}" ${candidate.id === activeId ? "selected" : ""}>${escapeHtml(settingsConfigOptionLabel(candidate))}</option>`).join("")
        : `<option value="">No config files found</option>`;
      select.value = activeId || "";
      select.disabled = state.settingsLoadingConfig || !candidates.length;
      const errorNode = document.querySelector("#settings-config-error");
      if (errorNode) {
        errorNode.textContent = state.settingsConfigError || "";
        errorNode.classList.toggle("hidden", !state.settingsConfigError);
      }
      const browseButton = document.querySelector("#settings-config-browse");
      if (browseButton) {
        browseButton.disabled = state.settingsLoadingConfig || !selection.import_supported || !endpoints.configImport;
      }
    }

    function settingsConfigOptionLabel(candidate) {
      const source = String(candidate?.source || "");
      const suffix = source && source !== "current" ? ` / ${label(source)}` : "";
      return `${candidate?.label || candidate?.ref || "Config"}${suffix}`;
    }

    function settingsForm(section) {
      if (state.settingsProfile?.status === "unconfigured") {
        return `<div class="empty-state">No config is active. Load a config file to show editable settings.</div>`;
      }
      if (section === "Storage") {
        return storageMaintenanceMarkup();
      }
      const fields = settingsFields().filter((field) => field.section === section && settingFieldIsVisible(field));
      if (!fields.length) {
        return `<div class="message">No editable controls are available for this section yet.</div>`;
      }
      const groups = settingsGroups(section, fields);
      return `<div class="settings-group-list">${groups.map(settingGroupMarkup).join("")}</div>`;
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

    function settingPathValue(path) {
      if (Object.prototype.hasOwnProperty.call(state.settingsChanges, path)) {
        return state.settingsChanges[path];
      }
      const field = settingField(path);
      return field ? field.value : undefined;
    }

    function settingPathEnabled(path) {
      return settingPathValue(path) === true;
    }

    function settingsGroups(section, fields) {
      const groups = [];
      const byId = new Map();
      fields.forEach((field) => {
        const meta = settingGroupForField(section, field);
        if (!byId.has(meta.id)) {
          byId.set(meta.id, {...meta, fields: []});
          groups.push(byId.get(meta.id));
        }
        byId.get(meta.id).fields.push(field);
      });
      return groups;
    }

    function settingGroupMarkup(group) {
      const status = settingGroupStatus(group);
      return `
        <section class="settings-group" data-settings-group="${escapeHtml(group.id)}">
          <div class="settings-group-head">
            <div class="settings-group-title">
              <h3>${escapeHtml(group.title)}</h3>
              ${group.description ? `<p>${escapeHtml(group.description)}</p>` : ""}
            </div>
            ${status}
          </div>
          <div class="settings-group-body">
            ${group.fields.map(settingRow).join("")}
          </div>
        </section>`;
    }

    function settingGroupStatus(group) {
      if (!group.enabledPath) {
        return "";
      }
      const enabled = settingPathEnabled(group.enabledPath);
      return statusPill(enabled ? "available" : "skipped", enabled ? "Enabled" : "Disabled");
    }

    function settingGroupForField(section, field) {
      const path = String(field?.path || "");
      if (section === "Live") {
        return liveSettingGroup(path);
      }
      if (section === "Market data") {
        return marketSettingGroup(path);
      }
      if (section === "Intelligence sources") {
        return intelligenceSettingGroup(path);
      }
      if (path.startsWith("codex.")) {
        return {id: "report-codex", title: "Codex report writer", description: "Local report-generation integration.", enabledPath: "codex.enabled"};
      }
      if (path.startsWith("report.")) {
        return {id: "report-output", title: "Report output", description: "Report language and title defaults."};
      }
      if (path.startsWith("dashboard.")) {
        return {id: "dashboard-display", title: "Dashboard display", description: "Dashboard timestamp and market color preferences."};
      }
      if (path.startsWith("monitor.")) {
        return {id: "monitor-health", title: "Monitor health checks", description: "Resident Monitor cadence and retry behavior."};
      }
      if (path.startsWith("quant.")) {
        return {id: "strategy-research", title: "Strategy research", description: "Deterministic strategy evaluation switches.", enabledPath: "quant.enabled"};
      }
      return {id: `settings-${section.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`, title: settingsSectionLabel(section)};
    }

    function liveSettingGroup(path) {
      const collectionMatch = path.match(/^live\.collections\.([^.]+)\./);
      if (collectionMatch) {
        const dataType = collectionMatch[1];
        return {
          id: `live-collection-${dataType}`,
          title: `${label(dataType)} collection`,
          description: "Cadence and collection window for this data type.",
          enabledPath: `live.collections.${dataType}.enabled`,
        };
      }
      const triggerMatch = path.match(/^live\.reports\.triggers\.([^.]+)\./);
      if (triggerMatch) {
        const triggerId = triggerMatch[1];
        return {
          id: `live-trigger-${triggerId}`,
          title: `${label(triggerId)} trigger`,
          description: "Thresholds and job intent for this report trigger.",
          enabledPath: `live.reports.triggers.${triggerId}.enabled`,
        };
      }
      if (path.startsWith("live.reports.daily.")) {
        return {
          id: "live-daily-report",
          title: "Daily report",
          description: "Daily report availability in Live.",
          enabledPath: "live.reports.daily.enabled",
        };
      }
      return {
        id: "live-scheduler",
        title: "Live scheduler",
        description: "Master switch and Core scheduler cadence.",
        enabledPath: "live.enabled",
      };
    }

    function marketSettingGroup(path) {
      if (path.startsWith("market.derivatives.")) {
        return {
          id: "market-derivatives",
          title: "Derivatives market",
          description: "Derivatives source, instruments, classes, periods, and history depth.",
          enabledPath: "market.derivatives.enabled",
        };
      }
      if (path.startsWith("market.ohlcv.")) {
        return {
          id: "market-ohlcv",
          title: "OHLCV history",
          description: "Reusable candle sources, timeframes, and lookback depth.",
          enabledPath: "market.enabled",
        };
      }
      if (path.startsWith("market.proxy.")) {
        return {
          id: "market-network",
          title: "Network access",
          description: "Proxy switch without exposing local proxy values.",
          enabledPath: "market.enabled",
        };
      }
      if (path.startsWith("market.anomalies.")) {
        return {
          id: "market-anomalies",
          title: "Market anomalies",
          description: "External or Halpha rule-detected market anomaly records.",
          enabledPath: "market.anomalies.enabled",
        };
      }
      return {
        id: "market-source",
        title: "Market source",
        description: "Primary public market source and instruments.",
        enabledPath: "market.enabled",
      };
    }

    function intelligenceSettingGroup(path) {
      if (path.startsWith("text.intelligence.models.")) {
        return {
          id: "intel-text-models",
          title: "Text intelligence models",
          description: "Local model providers, names, revisions, and cache location.",
          enabledPath: "text.intelligence.enabled",
        };
      }
      if (path.startsWith("text.intelligence.thresholds.")) {
        return {
          id: "intel-text-thresholds",
          title: "Text intelligence thresholds",
          description: "Deterministic duplicate, topic, classifier, and entity cutoffs.",
          enabledPath: "text.intelligence.enabled",
        };
      }
      if (path.startsWith("text.intelligence.")) {
        return {
          id: "intel-text-engine",
          title: "Text intelligence",
          description: "Local text-intelligence evidence generation.",
          enabledPath: "text.intelligence.enabled",
        };
      }
      if (path.startsWith("text.")) {
        return {
          id: "intel-text-collection",
          title: "Text collection",
          description: "Configured public text source collection.",
          enabledPath: "text.enabled",
        };
      }
      if (path.startsWith("macro_calendar.")) {
        return {
          id: "intel-macro-calendar",
          title: "Macro calendar",
          description: "Scheduled-event sources, regions, classes, and windows.",
          enabledPath: "macro_calendar.enabled",
        };
      }
      if (path.startsWith("onchain_flow.")) {
        return {
          id: "intel-onchain-flow",
          title: "On-chain flow",
          description: "Aggregate on-chain and exchange-flow source coverage.",
          enabledPath: "onchain_flow.enabled",
        };
      }
      return {id: "intel-sources", title: "Intelligence sources"};
    }

    function settingFieldIsVisible(field) {
      const path = String(field?.path || "");
      if (path === "market.enabled" || path === "text.enabled" || path === "macro_calendar.enabled" || path === "onchain_flow.enabled") {
        return true;
      }
      if (path === "live.enabled") {
        return true;
      }
      if (path === "live.tick_seconds" || path === "live.reports.daily.enabled") {
        return settingPathEnabled("live.enabled");
      }
      if (path.startsWith("live.collections.")) {
        const parts = path.split(".");
        const dataType = parts[2];
        const suffix = parts.slice(3).join(".");
        if (suffix === "enabled") {
          return settingPathEnabled("live.enabled");
        }
        return settingPathEnabled("live.enabled") && settingPathEnabled(`live.collections.${dataType}.enabled`);
      }
      if (path.startsWith("live.reports.triggers.")) {
        const parts = path.split(".");
        const triggerId = parts[3];
        const suffix = parts.slice(4).join(".");
        if (suffix === "enabled") {
          return settingPathEnabled("live.enabled");
        }
        if (!settingPathEnabled("live.enabled") || !settingPathEnabled(`live.reports.triggers.${triggerId}.enabled`)) {
          return false;
        }
        if (suffix === "confirm_codex") {
          return settingPathValue(`live.reports.triggers.${triggerId}.job_intent`) === "run";
        }
        return true;
      }
      if (path.startsWith("market.derivatives.")) {
        return settingPathEnabled("market.enabled") && (path === "market.derivatives.enabled" || settingPathEnabled("market.derivatives.enabled"));
      }
      if (path.startsWith("market.")) {
        return settingPathEnabled("market.enabled");
      }
      if (path === "text.intelligence.enabled") {
        return settingPathEnabled("text.enabled");
      }
      if (path.startsWith("text.intelligence.")) {
        return settingPathEnabled("text.enabled") && settingPathEnabled("text.intelligence.enabled");
      }
      if (path.startsWith("text.")) {
        return settingPathEnabled("text.enabled");
      }
      if (path.startsWith("macro_calendar.")) {
        return path === "macro_calendar.enabled" || settingPathEnabled("macro_calendar.enabled");
      }
      if (path.startsWith("onchain_flow.")) {
        return path === "onchain_flow.enabled" || settingPathEnabled("onchain_flow.enabled");
      }
      return true;
    }

    function settingVisibilityChanges(path) {
      if (String(path || "").startsWith("live.collections.") && String(path || "").endsWith(".enabled")) {
        return true;
      }
      if (String(path || "").startsWith("live.reports.triggers.")) {
        return String(path || "").endsWith(".enabled") || String(path || "").endsWith(".job_intent");
      }
      return [
        "market.enabled",
        "market.derivatives.enabled",
        "text.enabled",
        "text.intelligence.enabled",
        "macro_calendar.enabled",
        "onchain_flow.enabled",
        "live.enabled",
      ].includes(path);
    }

    function pruneHiddenSettingChanges() {
      Object.keys(state.settingsChanges).forEach((path) => {
        const field = settingField(path);
        if (field && !settingFieldIsVisible(field)) {
          delete state.settingsChanges[path];
        }
      });
    }

    function settingRow(field) {
      const error = state.settingsFieldErrors[field.path];
      return `
        <div class="form-row">
          <div>
            <strong>${escapeHtml(field.label)}</strong>
            ${field.description ? `<small class="muted">${escapeHtml(field.description)}</small>` : ""}
          </div>
          <div class="setting-control-stack">
            ${settingControl(field)}
            <small class="field-error ${error ? "" : "hidden"}" data-setting-error="${escapeHtml(field.path)}">${error ? escapeHtml(error) : ""}</small>
          </div>
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
        const numberType = field.value_type === "unit_interval_number"
          ? "unit_interval_number"
          : field.value_type === "positive_number"
            ? "positive_number"
            : "positive_int";
        const attrs = numberType === "unit_interval_number"
          ? 'min="0" max="1" step="0.01"'
          : numberType === "positive_number"
            ? 'min="0" step="0.01"'
            : 'min="1" step="1"';
        return `<input class="text-input" type="number" ${attrs} value="${escapeHtml(value)}" data-setting-path="${path}" data-setting-type="${numberType}">`;
      }
      if (field.control === "multi_select") {
        const values = Array.isArray(value) ? value.map(String) : [];
        const options = Array.isArray(field.options) ? field.options : values;
        return `<div class="chip-row">${options.map((option) => `<label class="chip choice-chip"><input type="checkbox" ${values.includes(String(option)) ? "checked" : ""} data-setting-path="${path}" data-setting-type="multi_select" data-setting-option="${escapeHtml(option)}"><span class="choice-check" aria-hidden="true"></span><span>${escapeHtml(option)}</span></label>`).join("")}</div>`;
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
            if (settingVisibilityChanges(node.dataset.settingPath)) {
              pruneHiddenSettingChanges();
              renderSettings();
            }
          });
          return;
        }
        node.addEventListener("change", () => {
          const path = node.dataset.settingPath;
          if (node.dataset.settingType === "multi_select") {
            recordSettingChange(path, multiSelectValues(path));
          } else if (node.dataset.settingType === "positive_int") {
            recordSettingChange(path, Number(node.value));
          } else if (node.dataset.settingType === "positive_number") {
            recordSettingChange(path, Number(node.value));
          } else if (node.dataset.settingType === "unit_interval_number") {
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
      if (Object.prototype.hasOwnProperty.call(state.settingsFieldErrors, path)) {
        delete state.settingsFieldErrors[path];
        const errorNode = document.querySelector(`[data-setting-error="${cssEscape(path)}"]`);
        if (errorNode) {
          errorNode.textContent = "";
          errorNode.classList.add("hidden");
        }
      }
      if (field.virtual && String(path).endsWith(".confirm_codex") && value === true) {
        state.settingsChanges[path] = true;
        renderChangeSummary();
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

    function cssEscape(value) {
      if (window.CSS && typeof window.CSS.escape === "function") {
        return window.CSS.escape(String(value));
      }
      return String(value).replace(/["\\]/g, "\\$&");
    }

    function renderChangeSummary() {
      const paths = Object.keys(state.settingsChanges);
      const saveButton = document.querySelector("#settings-save");
      if (saveButton) {
        saveButton.disabled = !paths.length || state.settingsProfile?.status === "unconfigured";
        saveButton.textContent = paths.length ? `Save ${paths.length} change${paths.length === 1 ? "" : "s"}` : "Save changes";
      }
    }

    function renderValidationResults() {
      if (state.validationJob) {
        renderValidationJob(state.validationJob);
        return;
      }
    }

    function renderStorageMaintenance() {
      renderRunCleanupList();
      renderSharedCleanupList();
    }

    function storageMaintenanceMarkup() {
      return `
        <section class="storage-maintenance settings-storage-page">
          <div class="storage-maintenance-header">
            <h2 class="panel-title" style="margin-bottom: 4px;">Storage maintenance</h2>
            <div class="muted">Run artifacts affect one run. Shared stores may be reused by reports and future runs.</div>
          </div>
          <div class="cleanup-grid">
            <section class="cleanup-panel">
              <div class="cleanup-panel-head">
                <strong>Single-run artifacts</strong>
                <button class="danger-button" type="button" id="cleanup-run-artifacts">Delete selected</button>
              </div>
              <div id="run-cleanup-list" class="cleanup-list"></div>
            </section>
            <section class="cleanup-panel">
              <div class="cleanup-panel-head">
                <strong>Shared data stores</strong>
                <button class="danger-button" type="button" id="cleanup-shared-data">Delete selected</button>
              </div>
              <div id="shared-cleanup-list" class="cleanup-list"></div>
            </section>
          </div>
        </section>`;
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
          <span class="choice-check" aria-hidden="true"></span>
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
            <span class="choice-check" aria-hidden="true"></span>
            <span>
              <strong>${escapeHtml(item.title || item.name)}</strong>
              <small>${escapeHtml(item.group || "shared")} / ${formatNumber(item.records || 0)} records / ${refs} refs${item.blocked_reason ? ` / ${escapeHtml(item.blocked_reason)}` : ""}</small>
            </span>
            ${statusPill(item.status || "unknown")}
          </label>`;
      }).join("");
    }

    function wireCleanupControls() {
      const runCleanupButton = document.querySelector("#cleanup-run-artifacts");
      if (runCleanupButton) {
        runCleanupButton.addEventListener("click", () => cleanup("runs"));
      }
      const sharedCleanupButton = document.querySelector("#cleanup-shared-data");
      if (sharedCleanupButton) {
        sharedCleanupButton.addEventListener("click", () => cleanup("shared"));
      }
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

    function settingsResultMessage(result, fallback) {
      const errors = Array.isArray(result?.errors) ? result.errors.filter(Boolean).map(String) : [];
      const warnings = Array.isArray(result?.warnings) ? result.warnings.filter(Boolean).map(String) : [];
      return errors.join("; ") || warnings.join("; ") || fallback;
    }

    function fieldErrorsFromMessages(errors) {
      const fieldPaths = new Set(settingsFields().map((field) => field.path));
      const fieldErrors = {};
      const general = [];
      (Array.isArray(errors) ? errors : []).forEach((raw) => {
        const message = String(raw || "").trim();
        const splitIndex = message.indexOf(":");
        const path = splitIndex > 0 ? message.slice(0, splitIndex).trim() : "";
        if (path && fieldPaths.has(path)) {
          fieldErrors[path] = message.slice(splitIndex + 1).trim() || message;
        } else if (message) {
          general.push(message);
        }
      });
      return {fieldErrors, general};
    }

    async function confirmDiscardSettingsChanges() {
      const count = Object.keys(state.settingsChanges).length;
      if (!count) {
        return true;
      }
      const ok = await dialogs.confirmAction({
        title: "Discard unsaved settings",
        message: `Loading another config will discard ${count} unsaved setting change${count === 1 ? "" : "s"}.`,
        confirmLabel: "Discard changes",
      });
      if (!ok) {
        showToast("Config change cancelled.", "info");
      }
      return ok;
    }

    function setSettingsConfigError(message) {
      state.settingsConfigError = message || "";
      renderSettingsConfigSelector();
      if (state.settingsConfigError) {
        showToast(state.settingsConfigError, "error");
      }
    }

    async function applyLoadedSettingsProfile(result, successMessage) {
      state.settingsProfile = result.profile;
      applyTimestampDisplayOptionsFromProfile(state.settingsProfile);
      state.settingsChanges = {};
      state.settingsFieldErrors = {};
      state.settingsConfigError = "";
      await loadHealth().catch(() => {});
      renderSettings();
      showToast(successMessage, "success");
    }

    async function saveSettings() {
      if (state.settingsProfile?.status === "unconfigured") {
        showToast("Select a config file first.", "warning");
        return;
      }
      const paths = Object.keys(state.settingsChanges);
      if (!paths.length) {
        showToast("No settings changes to save.", "info");
        return;
      }
      const ok = await dialogs.confirmAction({
        title: "Save settings",
        message: `Save ${paths.length} setting change(s)? A backup will be created before the config is updated.`,
        confirmLabel: "Save settings",
      });
      if (!ok) {
        showToast("Settings save cancelled.", "info");
        return;
      }
      try {
        const result = await postJson(endpoints.settings, {confirm: true, changes: state.settingsChanges});
        if (result.status === "succeeded") {
          state.settingsProfile = result.profile;
          applyTimestampDisplayOptionsFromProfile(state.settingsProfile);
          state.settingsChanges = {};
          state.settingsFieldErrors = {};
          renderSettings();
          showToast("Settings saved.", "success");
          return;
        }
        const errors = Array.isArray(result.errors) ? result.errors : [];
        const parsed = fieldErrorsFromMessages(errors);
        state.settingsFieldErrors = parsed.fieldErrors;
        renderSettings();
        showToast(parsed.general.join("; ") || errors.join("; ") || `Settings save ${result.status}.`, result.status === "skipped" ? "warning" : "error");
      } catch (error) {
        showToast(`Settings save failed: ${error.message}`, "error");
      }
    }

    async function backupSettings() {
      if (state.settingsProfile?.status === "unconfigured") {
        showToast("Select a config file first.", "warning");
        return;
      }
      try {
        const result = await postJson(`${endpoints.settings}/backup`, {});
        const kind = result.status === "succeeded" ? "success" : "error";
        showToast(settingsResultMessage(result, `Config backup ${result.status}.`), kind);
      } catch (error) {
        showToast(`Config backup failed: ${error.message}`, "error");
      }
    }

    async function loadSelectedConfigCandidate(candidateId) {
      if (!candidateId || state.settingsLoadingConfig) {
        return;
      }
      const selection = state.settingsProfile?.config_selection || {};
      if (candidateId === selection.active_id && !state.settingsConfigError) {
        return;
      }
      if (!(await confirmDiscardSettingsChanges())) {
        renderSettingsConfigSelector();
        return;
      }
      state.settingsLoadingConfig = true;
      state.settingsConfigError = "";
      renderSettingsConfigSelector();
      try {
        const result = await postJson(endpoints.configSelect, {candidate_id: candidateId});
        if (result.status === "succeeded") {
          state.settingsLoadingConfig = false;
          await applyLoadedSettingsProfile(result, `Config loaded: ${result.config?.ref || "selected config"}.`);
        } else {
          state.settingsLoadingConfig = false;
          setSettingsConfigError(settingsResultMessage(result, "Config load failed."));
        }
      } catch (error) {
        state.settingsLoadingConfig = false;
        setSettingsConfigError(`Config load failed: ${error.message}`);
      }
    }

    async function importSelectedConfigFile(event) {
      const input = event.currentTarget;
      const file = input?.files?.[0];
      if (input) {
        input.value = "";
      }
      if (!file || state.settingsLoadingConfig) {
        return;
      }
      if (!endpoints.configImport) {
        showToast("Config import is unavailable.", "error");
        return;
      }
      if (!(await confirmDiscardSettingsChanges())) {
        return;
      }
      state.settingsLoadingConfig = true;
      state.settingsConfigError = "";
      renderSettingsConfigSelector();
      try {
        const content = await file.text();
        const result = await postJson(endpoints.configImport, {name: file.name, content});
        if (result.status === "succeeded") {
          state.settingsLoadingConfig = false;
          await applyLoadedSettingsProfile(result, `Config imported: ${result.config?.ref || file.name}.`);
        } else {
          state.settingsLoadingConfig = false;
          setSettingsConfigError(settingsResultMessage(result, "Config import failed."));
        }
      } catch (error) {
        state.settingsLoadingConfig = false;
        setSettingsConfigError(`Config import failed: ${error.message}`);
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

    async function postStrategyAction(action, params = {}) {
      const payload = await postJson(`${endpoints.strategyActions}/${encodeURIComponent(action)}`, {params});
      const job = payload?.job || payload;
      if (!job || typeof job !== "object") {
        throw new Error("Strategy action request failed.");
      }
      showToast(`${label(action)} job ${job.status || "created"}.`);
      if (job.status === "blocked" || job.status === "unsupported") {
        const reason = Array.isArray(job.errors) && job.errors.length ? job.errors[0] : `Strategy action ${job.status}.`;
        throw new Error(reason);
      }
      return job;
    }

    async function postStrategyBacktestDelete(item) {
      if (!endpoints.strategyBacktests) {
        throw new Error("Strategy backtest deletion is not configured.");
      }
      return postJson(`${endpoints.strategyBacktests}/delete`, {backtest: strategyBacktestDeleteRef(item)});
    }

    function strategyBacktestDeleteRef(item) {
      const fields = item?.fields || {};
      const execution = objectValue(fields.execution_source);
      return {
        history_id: fields.history_id || item?.history_id || "",
        evaluation_id: fields.evaluation_id || item?.evaluation_id || "",
        output_dir: item?.output_dir || execution.output_dir || execution.run_dir || "",
        strategy_name: fields.strategy_name || strategyIdentity(item).name || "",
        symbol: fields.symbol || strategyIdentity(item).symbol || "",
        timeframe: fields.timeframe || strategyIdentity(item).timeframe || "",
      };
    }

    async function fetchJob(jobId) {
      return fetchJson(`${endpoints.jobs}/${encodeURIComponent(jobId)}`);
    }

    function latestReportJob() {
      const jobs = Array.isArray(state.jobs) ? state.jobs : [];
      const reportJobs = jobs.filter((job) => job.intent === "run");
      return reportJobs.find((job) => reportJobIsActive(job)) || null;
    }

    function reportJobRecord(job) {
      if (!reportJobShouldRender(job)) return null;
      const refs = reportJobRefs(job);
      const status = String(job.status || "created").toLowerCase();
      const runId = refs.run_id || `job:${job.job_id || "pending"}`;
      const failed = terminalJobStatus(status) && status !== "succeeded";
      return {
        run_id: runId,
        job_id: job.job_id || "pending",
        is_job_record: true,
        job,
        type: failed ? "Failed" : "Running",
        title: failed ? "Report Exception Record" : "Generating Report",
        status,
        started_at: job.started_at || job.created_at,
        finished_at: job.finished_at,
        report_path: refs.report || "",
        manifest: refs.run_manifest || refs.manifest || "",
      };
    }

    function reportJobRefs(job) {
      return job?.result_refs && typeof job.result_refs === "object" ? job.result_refs : {};
    }

    function reportJobIsActive(job) {
      return ["created", "creating", "queued", "running"].includes(String(job?.status || "").toLowerCase());
    }

    function reportJobShouldRender(job) {
      if (!job) return false;
      const status = String(job.status || "").toLowerCase();
      const refs = reportJobRefs(job);
      if (reportJobIsActive(job)) return true;
      if (status === "succeeded" && refs.report) return false;
      return terminalJobStatus(status);
    }

    function renderReportJob(job) {
      const nodes = [
        document.querySelector("#overview-report-job-status"),
        document.querySelector("#reports-report-job-status"),
      ].filter(Boolean);
      if (!nodes.length) {
        return;
      }
      if (!reportJobShouldRender(job)) {
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
      const hint = terminalJobStatus(status)
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
      const ok = await dialogs.confirmAction({
        title: "Generate report",
        message: "Generate a full Codex report now? This can take a while and will create a new run.",
        confirmLabel: "Generate report",
      });
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
      if (state.view === "reports") {
        renderReportLibrary();
        await selectReportJob(reportJobRecord(pending));
      }
      try {
        const job = await postJob("run", {confirm_codex: true});
        state.reportJob = job;
        renderReportJob(job);
        if (state.view === "reports") {
          renderReportLibrary();
          await selectReportJob(reportJobRecord(job));
        }
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
        if (state.view === "reports") {
          renderReportLibrary();
          await selectReportJob(reportJobRecord(state.reportJob));
        }
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
          await refreshSelectedReportJob(job);
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
          await refreshSelectedReportJob(state.reportJob);
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
      const target = document.querySelector("#validation-results");
      if (!target) {
        const message = errors.join("; ") || warnings.join("; ") || `Validation job ${status}.`;
        showToast(message, errors.length ? "error" : "info");
        return;
      }
      target.innerHTML = `
        <div class="message">
          <strong>Validation job ${escapeHtml(status)}</strong><br>
          Job: ${escapeHtml(jobId)}
          ${warnings.length ? `<br>Warnings: ${escapeHtml(warnings.slice(0, 2).join("; "))}` : ""}
          ${errors.length ? `<br>Errors: ${escapeHtml(errors.slice(0, 2).join("; "))}` : ""}
        </div>`;
    }

    async function cleanup(kind) {
      await loadDeletionPlan();
      if (kind === "runs") {
        const selected = state.selectedRunArtifacts.slice();
        if (!selected.length) return showToast("Select at least one run artifact first.");
        const required = state.deletionPlan?.confirmations?.run_artifacts || "DELETE RUN DATA";
        const confirmed = await dialogs.typedConfirmation({
          title: "Delete single-run artifacts",
          message: `Delete ${selected.length} run artifact set(s). Shared stores are not deleted.`,
          requiredText: required,
          confirmLabel: "Delete selected",
          danger: true,
        });
        if (!confirmed) {
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
        const confirmed = await dialogs.typedConfirmation({
          title: "Delete shared data stores",
          message: `Delete ${selected.length} shared store(s). These stores may be reused by reports and future runs.`,
          requiredText: required,
          confirmLabel: "Delete shared data",
          danger: true,
        });
        if (!confirmed) {
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
      dialogs.wire();
      initializeSidebarCollapse();
      wireTopbarTabDragging();
      wireStrategyDetailHeaderDrag();
      wireDateRangePickers();
      initializeTooltips();
      document.querySelectorAll("[data-view-target]").forEach((node) => node.addEventListener("click", (event) => {
        event.preventDefault();
        setHashView(node.dataset.viewTarget);
      }));
      document.querySelectorAll("[data-report-inspector-tab]").forEach((button) => {
        button.addEventListener("click", () => selectReportInspectorTab(button.dataset.reportInspectorTab));
      });
      selectReportInspectorTab(state.reportInspectorTab);
      document.querySelector("#report-search").addEventListener("input", renderReportLibrary);
      document.querySelector("#report-reader-search").addEventListener("input", () => {
        state.reportSearchTerm = document.querySelector("#report-reader-search").value;
        if (state.selectedReportArtifactPreview && state.selectedReportArtifact && !(state.selectedReportArtifact.pinned || state.selectedReportArtifact.category === "report")) {
          renderReportArtifactPreview(state.selectedReportArtifactPreview, state.selectedReportArtifact);
        } else if (state.selectedReportPreview && state.selectedReport) {
          renderReportPreview(state.selectedReportPreview, state.selectedReport);
        }
      });
      document.querySelector("#delete-report-button").addEventListener("click", deleteSelectedReport);
      document.querySelector("#report-details-button").addEventListener("click", openReportDetailsDrawer);
      document.querySelector("#report-details-drawer-close").addEventListener("click", () => closeReportDetailsDrawer());
      document.querySelector("#report-details-drawer-backdrop").addEventListener("click", () => closeReportDetailsDrawer());
      document.querySelector("#run-backtest-button").addEventListener("click", openStrategyBacktestDialog);
      document.querySelector("#strategy-backtest-submit").addEventListener("click", startBacktest);
      document.querySelector("#strategy-backtest-cancel").addEventListener("click", closeStrategyBacktestDialog);
      document.querySelector("#strategy-backtest-dialog-close").addEventListener("click", closeStrategyBacktestDialog);
      document.querySelector("#strategy-backtest-dialog-backdrop").addEventListener("click", closeStrategyBacktestDialog);
      document.querySelector("#strategy-backtest-back").addEventListener("click", showStrategyBacktestList);
      document.querySelector("#strategy-detail-action-menu").addEventListener("click", (event) => {
        event.stopPropagation();
        toggleStrategyDetailActionMenu();
      });
      document.addEventListener("click", (event) => {
        if (!event.target.closest(".strategy-detail-action-shell")) {
          closeStrategyDetailActionMenu();
        }
      });
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeStrategyDetailActionMenu();
      });
      document.querySelector("#strategy-detail-params").addEventListener("click", () => {
        closeStrategyDetailActionMenu();
        openStrategyParamsDrawer();
      });
      document.querySelector("#strategy-detail-rerun").addEventListener("click", () => {
        closeStrategyDetailActionMenu();
        rerunSelectedBacktest();
      });
      document.querySelector("#strategy-detail-delete").addEventListener("click", () => {
        closeStrategyDetailActionMenu();
        deleteSelectedBacktest();
      });
      document.querySelector("#strategy-params-drawer-close").addEventListener("click", closeStrategyParamsDrawer);
      document.querySelector("#strategy-params-drawer-backdrop").addEventListener("click", closeStrategyParamsDrawer);
      document.querySelector("#run-experiment-button").addEventListener("click", startStrategyExperiment);
      document.querySelectorAll("[data-strategy-operation-tab]").forEach((button) => {
        button.addEventListener("click", () => setStrategyOperationTab(button.dataset.strategyOperationTab));
      });
      document.querySelector("#strategy-collect-add-target")?.addEventListener("click", addStrategyCollectTarget);
      document.querySelector("#strategy-collect-refresh-timeline")?.addEventListener("click", refreshStrategyCollectTimeline);
      document.querySelector("#strategy-collect-run")?.addEventListener("click", runStrategyCollectBatch);
      ["#strategy-chart-source", "#strategy-chart-symbol", "#strategy-chart-timeframe"].forEach((selector) => {
        document.querySelector(selector)?.addEventListener("change", () => {
          state.selectedStrategyOutput = null;
          state.strategyFocusedMarkerTime = "";
          setSelectIfPresent("#strategy-name", "");
          queueStrategyChartRefresh({clearBacktest: true});
        });
      });
      document.querySelector("#strategy-chart-range").addEventListener("change", () => {
        setStrategyWindow(document.querySelector("#strategy-chart-range")?.value, {reload: true});
      });
      document.querySelector("#strategy-collect-range")?.addEventListener("change", () => {
        applyRangePreset("#strategy-collect-range", "#strategy-collect-start", "#strategy-collect-end", true);
        queueStrategyCollectTimelineRefresh();
      });
      document.querySelector("#strategy-backtest-range").addEventListener("change", () => {
        applyRangePreset("#strategy-backtest-range", "#strategy-backtest-start", "#strategy-backtest-end", true);
      });
      ["#strategy-collect-source", "#strategy-collect-start", "#strategy-collect-end"].forEach((selector) => {
        document.querySelector(selector)?.addEventListener("change", queueStrategyCollectTimelineRefresh);
      });
      ["#strategy-collect-symbol", "#strategy-collect-timeframe"].forEach((selector) => {
        document.querySelector(selector)?.addEventListener("change", () => {
          if (!state.strategyCollectTargets.length) addStrategyCollectTarget();
        });
      });
      document.querySelectorAll("[data-strategy-tab]").forEach((button) => button.addEventListener("click", () => renderStrategyTab(button.dataset.strategyTab)));
      liveWorkflow.wire();
      dataViewerWorkflow.wire();
      document.querySelectorAll("[data-report-job]").forEach((button) => button.addEventListener("click", startReportJob));
      document.querySelectorAll("[data-job-intent]").forEach((button) => button.addEventListener("click", () => postJob(button.dataset.jobIntent, {})));
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && state.strategyBacktestDialogOpen) {
          closeStrategyBacktestDialog();
        }
        if (event.key === "Escape" && state.reportDetailsDrawerOpen) {
          closeReportDetailsDrawer();
        }
        if (event.key === "Escape" && state.strategyParamsDrawerOpen) {
          closeStrategyParamsDrawer();
        }
      });
      document.querySelectorAll("[data-intel-tab]").forEach((button) => button.addEventListener("click", () => {
        state.selectedIntelTab = button.dataset.intelTab;
        state.selectedIntelItem = null;
        state.selectedIntelPreviewIndex = 0;
        state.intelPreviewDisplayLimit = 30;
        state.intelPreviewFetchLimit = 100;
        state.intelPreviewLoadingMore = false;
        state.intelPreviewKeyword = "";
        state.intelPreviewCategory = "";
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
        renderIntelligence();
      }));
      document.querySelector("#settings-save").addEventListener("click", saveSettings);
      document.querySelector("#settings-backup").addEventListener("click", backupSettings);
      document.querySelector("#settings-config-select").addEventListener("change", (event) => loadSelectedConfigCandidate(event.currentTarget.value));
      document.querySelector("#settings-config-browse").addEventListener("click", () => {
        document.querySelector("#settings-config-file-input")?.click();
      });
      document.querySelector("#settings-config-file-input").addEventListener("change", importSelectedConfigFile);
      window.addEventListener("hashchange", () => setView(viewFromHash()));
      window.addEventListener("resize", refreshTopbarTabHints);
      wireShortcutButtons();
    }

    renderInitialLoadingPlaceholders();
    wireGlobalEvents();
    refreshHealthForView();
    loadLivePayload().catch(() => renderSidebarLiveStatus());
    setView(viewFromHash());
