import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Divider,
  Drawer,
  IconButton,
  LinearProgress,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Toolbar,
  Tooltip,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import AssignmentOutlined from "@mui/icons-material/AssignmentOutlined";
import ChevronLeftOutlined from "@mui/icons-material/ChevronLeftOutlined";
import ChevronRightOutlined from "@mui/icons-material/ChevronRightOutlined";
import DashboardOutlined from "@mui/icons-material/DashboardOutlined";
import MenuOutlined from "@mui/icons-material/MenuOutlined";
import OpenInNewOutlined from "@mui/icons-material/OpenInNewOutlined";
import ReviewsOutlined from "@mui/icons-material/ReviewsOutlined";
import SettingsOutlined from "@mui/icons-material/SettingsOutlined";
import ShieldOutlined from "@mui/icons-material/ShieldOutlined";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useOutletContext,
  useParams,
} from "react-router";

import {
  ApiFailure,
  createActivation,
  completeReview,
  deletePlan,
  fixPlan,
  getActivation,
  getActivations,
  getActivationTimeline,
  getActivationPreview,
  getMarketContext,
  getMarketWindow,
  getOverview,
  getPlans,
  getReview,
  getReviews,
  getSettingsStatus,
  getStrategies,
  previewControl,
  refreshReview,
  sendTestEmail,
  submitActivationControl,
  type ControlIntent,
  type PlanKeyParameterDefinition,
  type PlanSummary,
  type ReviewCompletionPayload,
  type SettingsStatus,
} from "./api/client";
import PageHeader from "./components/PageHeader";
import FactGrid from "./components/FactGrid";
import { closedBarBreakoutGapPercent, entryExtensionBoundary, estimateImmediateExit, formatUserVisibleTime, gapPercent, latestUtc, marketPrice, marketVolume, notSubmittedReasonText, observedOrderStateText, pendingBreakoutNote, planEventSummary, shortDigest, venueReasonText } from "./format";
import {
  applyMarketColorScheme,
  DEFAULT_MARKET_COLOR_SCHEME,
  MarketToneText,
  marketToneForDirection,
  marketToneForSignedValue,
  readMarketColorScheme,
  saveMarketColorScheme,
  type MarketColorScheme,
} from "./marketColors";
import { surfaceFrameSx } from "./theme";

const DRAWER_WIDTH = 236;
const COLLAPSED_DRAWER_WIDTH = 72;
const NAVIGATION_COLLAPSED_STORAGE_KEY = "halpha.navigation-collapsed.v1";
const STATUS_QUERY_KEY = ["settings-status"] as const;
const NewPlanPage = lazy(() => import("./pages/NewPlanPage"));
const ReviewPriceChart = lazy(() => import("./components/ReviewCharts").then((module) => ({ default: module.ReviewPriceChart })));
const CumulativePnlChart = lazy(() => import("./components/ReviewCharts").then((module) => ({ default: module.CumulativePnlChart })));
const visuallyHiddenSx = {
  position: "absolute",
  width: "1px",
  height: "1px",
  p: 0,
  m: "-1px",
  overflow: "hidden",
  clip: "rect(0 0 0 0)",
  whiteSpace: "nowrap",
  border: 0,
} as const;

function readNavigationCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(NAVIGATION_COLLAPSED_STORAGE_KEY) === "collapsed";
  } catch {
    return false;
  }
}

function saveNavigationCollapsed(collapsed: boolean): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(NAVIGATION_COLLAPSED_STORAGE_KEY, collapsed ? "collapsed" : "expanded");
  } catch {
    // A blocked preference store must not prevent navigation.
  }
}

function valueOf(record: Record<string, unknown> | undefined, key: string, fallback = "UNKNOWN"): string {
  const value = record?.[key];
  return value === null || value === undefined ? fallback : String(value);
}

function recordOf(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function finiteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function recordsOf(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.map(recordOf) : [];
}

function TradingViewAttribution() {
  return (
    <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontSize: 10 }}>
      TradingView Lightweight Charts™ · Copyright © 2025 TradingView, Inc. ·{" "}
      <Box component="a" href="https://www.tradingview.com/" target="_blank" rel="noreferrer" sx={{ color: "inherit" }}>TradingView</Box>
    </Typography>
  );
}

function ClampedTooltipText({ text, lines = 2 }: { text: string; lines?: number }) {
  const textRef = useRef<HTMLSpanElement | null>(null);
  const [truncated, setTruncated] = useState(false);
  const updateTruncation = useCallback(() => {
    const element = textRef.current;
    if (!element) return;
    setTruncated(element.scrollHeight > element.clientHeight + 1 || element.scrollWidth > element.clientWidth + 1);
  }, []);

  useLayoutEffect(() => {
    updateTruncation();
    const element = textRef.current;
    if (!element || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(updateTruncation);
    observer.observe(element);
    return () => observer.disconnect();
  }, [text, lines, updateTruncation]);

  return (
    <Tooltip
      title={text}
      placement="top"
      arrow
      disableHoverListener={!truncated}
      disableFocusListener={!truncated}
      disableTouchListener={!truncated}
      slotProps={{ tooltip: { sx: { maxWidth: 440, fontSize: 13, lineHeight: 1.55 } } }}
    >
      <Typography
        ref={textRef}
        component="span"
        tabIndex={truncated ? 0 : undefined}
        variant="caption"
        color="text.secondary"
        sx={{
          display: "-webkit-box",
          WebkitBoxOrient: "vertical",
          WebkitLineClamp: lines,
          maxHeight: `${lines * 1.45}em`,
          overflow: "hidden",
          lineHeight: 1.45,
          overflowWrap: "anywhere",
          cursor: truncated ? "help" : "inherit",
          outlineOffset: 2,
        }}
      >
        {text}
      </Typography>
    </Tooltip>
  );
}

function ExpandableList<T>({
  items,
  renderItem,
  initialCount = 8,
  step = 8,
  spacing = 1.5,
}: {
  items: T[];
  renderItem: (item: T, index: number) => ReactNode;
  initialCount?: number;
  step?: number;
  spacing?: number;
}) {
  const [visibleCount, setVisibleCount] = useState(initialCount);
  useEffect(() => { setVisibleCount(initialCount); }, [initialCount, items.length]);
  const remaining = Math.max(0, items.length - visibleCount);
  return (
    <>
      <Stack spacing={spacing}>{items.slice(0, visibleCount).map(renderItem)}</Stack>
      {remaining > 0 && (
        <Button variant="text" sx={{ mt: 1.5 }} onClick={() => setVisibleCount((count) => count + step)}>
          显示更多（剩余 {remaining} 条）
        </Button>
      )}
    </>
  );
}

function signedUsdt(value: unknown): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "未知";
  const normalized = Math.abs(amount) < 0.0000005 ? 0 : amount;
  return `${new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
    signDisplay: "exceptZero",
  }).format(normalized)} USDT`;
}

function usdt(value: unknown): string {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "未知";
  return `${new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(amount)} USDT`;
}

function planDurationMinutes(validFrom: string, validUntil: string): string {
  const minutes = Math.round((Date.parse(validUntil) - Date.parse(validFrom)) / 60_000);
  return Number.isFinite(minutes) && minutes > 0 ? `${minutes} 分钟` : "未知";
}

function formatPlanKeyParameter(
  definition: PlanKeyParameterDefinition,
  value: unknown,
): string {
  if (definition.display_format === "BOOLEAN_LABEL") {
    if (value === true) return definition.true_label ?? "是";
    if (value === false) return definition.false_label ?? "否";
    return "未配置";
  }
  if (definition.display_format === "PERCENT") {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? percent(numeric * 100) : "未配置";
  }
  if (value === null || value === undefined || value === "") return "未配置";
  const rendered = String(value);
  return definition.unit ? `${rendered} ${definition.unit}` : rendered;
}

function durationText(value: unknown): string {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) return "未知";
  const whole = Math.round(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const remainder = whole % 60;
  return [hours ? `${hours} 小时` : "", minutes ? `${minutes} 分钟` : "", `${remainder} 秒`].filter(Boolean).join(" ");
}

function liquidityText(value: unknown): string {
  const token = String(value ?? "").toUpperCase();
  if (token === "1" || token.includes("MAKER")) return "挂单成交（Maker）";
  if (token === "2" || token.includes("TAKER")) return "吃单成交（Taker）";
  return "未知";
}

function reviewConclusion(review: Record<string, unknown>): string {
  const owner = recordOf(recordOf(review.evaluations).owner_conclusion);
  return valueOf(owner, "result", "UNKNOWN");
}

function exitReason(result: Record<string, unknown>): string {
  const exitFill = [...recordsOf(result.fills)].reverse().find((fill) => valueOf(fill, "action_kind") !== "ENTRY");
  const kind = valueOf(exitFill, "action_kind", "UNKNOWN");
  return kind === "TAKE_PROFIT"
    ? "止盈成交"
    : kind === "PROTECTION"
      ? "保护止损"
      : kind === "EXIT"
        ? "策略退出"
        : kind === "EXTERNAL_ACCOUNT_CLOSURE"
          ? "外部应急平仓"
        : kind === "RISK_REDUCTION"
          ? "风险减仓"
          : "未知";
}

function percent(value: number): string {
  return `${new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 1 }).format(value)}%`;
}

const reviewResultLabels: Record<string, string> = {
  NO_ACTION: "未发生交易",
  COMPLETED: "已完成交易",
  PARTIAL: "部分完成",
  RESULT_UNKNOWN: "结果未知",
  HANDED_OVER: "已由用户接管",
};

const reviewStatusLabels: Record<string, string> = {
  DRAFT: "待评价",
  COMPLETE: "已完成",
  SUPERSEDED: "已被新版替代",
};

const protectionStateLabels: Record<string, string> = {
  NONE: "未入场",
  WORKING: "完整有效",
  UNKNOWN: "未知",
  GAP: "存在缺口",
  CLOSED: "已闭合",
};

const evaluationResultLabels: Record<string, string> = {
  AS_EXPECTED: "符合预期",
  ISSUE_FOUND: "发现问题",
  UNKNOWN: "尚不确定",
  NOT_APPLICABLE: "不适用",
};

type ReviewPnlFilter = "ALL" | "PROFIT" | "LOSS" | "BREAKEVEN" | "UNKNOWN";

type ReviewListFilters = {
  strategyId: string;
  instrumentRef: string;
  direction: string;
  pnl: ReviewPnlFilter;
  primaryResult: string;
  ownerConclusion: string;
};

const emptyReviewListFilters: ReviewListFilters = {
  strategyId: "ALL",
  instrumentRef: "ALL",
  direction: "ALL",
  pnl: "ALL",
  primaryResult: "ALL",
  ownerConclusion: "ALL",
};

const pnlFilterLabels: Record<ReviewPnlFilter, string> = {
  ALL: "全部盈亏",
  PROFIT: "盈利",
  LOSS: "亏损",
  BREAKEVEN: "持平",
  UNKNOWN: "盈亏未知",
};

function tradeResultForReview(review: Record<string, unknown>): Record<string, unknown> {
  return recordOf(review.resolved_trade_result);
}

function reviewPnlClass(review: Record<string, unknown>): Exclude<ReviewPnlFilter, "ALL"> {
  const result = tradeResultForReview(review);
  const netPnl = finiteNumber(result.net_pnl);
  if (result.calculation_complete !== true || result.closed !== true || netPnl === null) return "UNKNOWN";
  if (netPnl > 0) return "PROFIT";
  if (netPnl < 0) return "LOSS";
  return "BREAKEVEN";
}

function reviewMatchesFilters(review: Record<string, unknown>, filters: ReviewListFilters): boolean {
  const context = recordOf(review.trade_context);
  return (
    (filters.strategyId === "ALL" || valueOf(context, "strategy_id", "") === filters.strategyId)
    && (filters.instrumentRef === "ALL" || valueOf(context, "instrument_ref", "") === filters.instrumentRef)
    && (filters.direction === "ALL" || valueOf(context, "direction", "") === filters.direction)
    && (filters.pnl === "ALL" || reviewPnlClass(review) === filters.pnl)
    && (filters.primaryResult === "ALL" || valueOf(review, "primary_result", "") === filters.primaryResult)
    && (filters.ownerConclusion === "ALL" || reviewConclusion(review) === filters.ownerConclusion)
  );
}

const gateStateLabels: Record<string, string> = {
  OPEN: "已开启",
  CLOSED: "已关闭",
};

const executorStatusLabels: Record<string, string> = {
  READY: "已就绪",
  STARTING: "正在启动与核对",
  UNAVAILABLE: "未运行",
  BUILD_MISMATCH: "产品版本不一致",
  AMBIGUOUS: "存在多个执行器",
  UNKNOWN: "无法核对",
};

const lifecycleLabels: Record<string, string> = {
  RUNNING: "运行中",
  EXITING: "正在退出",
  USER_TAKEOVER: "用户已接管",
  COMPLETED: "已闭合",
  UNKNOWN: "未知",
};

const runStateLabels: Record<string, string> = {
  ACTIVE: "运行中",
  PAUSED: "已暂停",
};

const pauseReasonLabels: Record<string, string> = {
  WRITER_CONTINUITY_LOST: "执行连续性中断",
};

const actionKindLabels: Record<string, string> = {
  ENTRY: "入场",
  CANCEL: "撤单",
  PROTECTION: "保护",
  TAKE_PROFIT: "止盈",
  RISK_REDUCTION: "减仓",
  EXIT: "退出",
  EXTERNAL_ACCOUNT_CLOSURE: "外部应急平仓",
};

const actionStateLabels: Record<string, string> = {
  READY: "待提交",
  NOT_SUBMITTED: "未提交",
  SUBMITTING: "正在提交",
  UNKNOWN: "结果未决",
  OPEN: "责任开放",
  CLOSED: "已核对闭合",
  HANDED_OVER: "已交接",
};

const timelineSourceLabels: Record<string, string> = {
  PLAN_EVENT: "计划事件",
  EXECUTION_ACTION: "执行动作",
  VENUE_FACT: "交易所事实",
};

const directionLabels: Record<string, string> = {
  LONG: "做多",
  SHORT: "做空",
};

const entryNoActionReasonLabels: Record<string, string> = {
  ENTRY_EXTENSION_LIMIT_EXCEEDED: "执行前价格已超过计划的最大追价边界",
  ENTRY_SPREAD_TOO_WIDE: "当前买卖价差超过入场上限",
  STREAM_FACTS_STALE: "最新盘口或标记价格已经过期",
  STREAM_FACTS_UNKNOWN: "最新盘口或标记价格暂不可确认",
  TOP_OF_BOOK_UNKNOWN: "当前买一卖一暂不可确认",
  TOP_OF_BOOK_INVALID: "当前买一卖一数据无效",
  MARK_PRICE_STALE: "当前标记价格已经过期",
  PROPOSAL_EXPIRED: "本次入场意图已超过有效时间",
  ACCOUNT_FACT_QUERY_STALE: "账户事实已过期",
  ACCOUNT_TRADING_DISABLED: "账户当前不可交易",
};

function translatedLabel(labels: Record<string, string>, value: string): string {
  return labels[value] ?? value;
}

function venueFactSummary(fact: Record<string, unknown>): string {
  const kind = valueOf(fact, "kind", "");
  const payload = recordOf(fact.payload);
  if (kind === "ORDER_STATE") {
    const status = valueOf(payload, "status", "");
    return observedOrderStateText(translatedLabel(actionStateLabels, status));
  }
  if (kind === "FILL") {
    const quantity = valueOf(payload, "last_quantity", "");
    const price = valueOf(payload, "last_price", "");
    return `成交${quantity ? ` · ${marketVolume(quantity)} BTC` : ""}${price ? ` @ ${marketPrice(price)} USDT` : ""}`;
  }
  if (kind === "COMMISSION") {
    const amount = valueOf(payload, "amount", "");
    const currency = valueOf(payload, "currency", "");
    const currencySuffix = currency && !amount.toUpperCase().endsWith(currency.toUpperCase())
      ? ` ${currency}`
      : "";
    return `手续费${amount ? ` · ${amount}${currencySuffix}` : ""}`;
  }
  return kind || "未分类事实";
}

function planConfirmationError(error: unknown): string {
  const code = error instanceof ApiFailure ? error.code : "结果未知";
  if (code === "PARAMETER_OUT_OF_RANGE") return "策略参数超出页面标注范围，请编辑后重试";
  if (code === "TAKE_PROFIT_ORDER_INVALID") return "止盈二必须大于止盈一，请编辑后重试";
  return `${code}，请刷新当前计划后重试`;
}

function planDeletionError(error: unknown): string {
  const code = error instanceof ApiFailure ? error.code : "结果未知";
  if (code === "PLAN_VERSION_CONFLICT") return "草稿已变化，请关闭弹窗并刷新后重试";
  if (code === "PLAN_DRAFT_FIXED") return "计划已经确认，不能再删除草稿";
  if (code === "PLAN_NOT_FOUND") return "草稿已不存在，请刷新计划列表";
  return `草稿未删除：${code}`;
}

function AppLoading() {
  return (
    <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center" }} role="status" aria-live="polite">
      <Stack spacing={2} sx={{ alignItems: "center" }}>
        <CircularProgress size={26} />
        <Typography variant="body2" color="text.secondary">正在核对本机服务与当前构建…</Typography>
      </Stack>
    </Box>
  );
}

function ConnectionFailure({ retry }: { retry: () => void }) {
  return (
    <Box sx={{ width: "min(620px, calc(100% - clamp(32px, 4vw, 48px)))", mx: "auto", pt: 12 }}>
      <Typography variant="overline" color="text.secondary">LOCAL APP UNAVAILABLE</Typography>
      <Typography variant="h1" sx={{ mt: 1, mb: 3 }}>无法取得当前工作台状态</Typography>
      <Alert severity="error" variant="outlined" sx={{ mb: 3 }}>
        当前结果未知。页面没有使用缓存冒充服务器事实，也没有开放任何资本或交易指令。
      </Alert>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
        <Button variant="contained" onClick={retry}>重新查询</Button>
        <Button component="a" href="/operations" variant="outlined" endIcon={<OpenInNewOutlined />}>
          打开故障接管
        </Button>
      </Stack>
    </Box>
  );
}

type FrameContext = {
  status: SettingsStatus;
  marketColorScheme: MarketColorScheme;
  setMarketColorScheme: (scheme: MarketColorScheme) => void;
};

const navItems = [
  { label: "总览", path: "/overview", icon: <DashboardOutlined /> },
  { label: "策略计划", path: "/plans", icon: <AssignmentOutlined /> },
  { label: "复盘", path: "/reviews", icon: <ReviewsOutlined /> },
  { label: "设置", path: "/settings", icon: <SettingsOutlined /> },
];

function WorkbenchFrame({ status }: { status: SettingsStatus }) {
  const theme = useTheme();
  const narrow = useMediaQuery(theme.breakpoints.down("md"));
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [navigationCollapsed, setNavigationCollapsed] = useState(readNavigationCollapsed);
  const [loadedProductBuildId] = useState(status.product_build_id);
  const [marketColorScheme, setMarketColorSchemeState] = useState(readMarketColorScheme);
  const location = useLocation();
  const navigate = useNavigate();
  useLayoutEffect(() => { applyMarketColorScheme(marketColorScheme); }, [marketColorScheme]);
  const setMarketColorScheme = useCallback((scheme: MarketColorScheme) => {
    saveMarketColorScheme(scheme);
    setMarketColorSchemeState(scheme);
  }, []);
  const toggleNavigationCollapsed = useCallback(() => {
    setNavigationCollapsed((current) => {
      const next = !current;
      saveNavigationCollapsed(next);
      return next;
    });
  }, []);
  const drawerCollapsed = !narrow && navigationCollapsed;
  const desktopDrawerWidth = navigationCollapsed ? COLLAPSED_DRAWER_WIDTH : DRAWER_WIDTH;
  const productUpdateAvailable = Boolean(
    loadedProductBuildId
    && status.product_build_id
    && loadedProductBuildId !== status.product_build_id
  );
  const currentPrimaryPath = location.pathname.startsWith("/plans")
    ? "/plans"
    : location.pathname.startsWith("/reviews")
      ? "/reviews"
      : location.pathname.startsWith("/settings")
        ? "/settings"
        : "/overview";
  const pageTitle = location.pathname.startsWith("/activations/")
    ? "策略运行"
    : navItems.find((item) => item.path === currentPrimaryPath)?.label ?? "工作台";

  const drawer = (
    <Box component="aside" aria-label="工作台侧栏" sx={{ height: "100%", minHeight: 0, display: "flex", flexDirection: "column" }}>
      <Stack direction="row" spacing={.75} sx={{ height: 64, minHeight: 64, px: drawerCollapsed ? 1 : 1.5, alignItems: "center", justifyContent: drawerCollapsed ? "center" : "flex-start", borderBottom: 1, borderColor: "rgba(16,24,32,.09)" }}>
        {!drawerCollapsed && <Typography sx={{ fontSize: 22, lineHeight: 1, fontWeight: 760 }}>{narrow ? "Halpha 工作台" : "Halpha"}</Typography>}
        {!drawerCollapsed && <Chip label={narrow ? `环境 · ${status.environment_kind}` : status.environment_kind} size="small" color="primary" icon={<ShieldOutlined />} />}
        {!narrow && (
          <IconButton
            aria-label={drawerCollapsed ? "展开导航" : "折叠导航"}
            title={drawerCollapsed ? "展开导航" : "折叠导航"}
            onClick={toggleNavigationCollapsed}
            sx={{ ml: drawerCollapsed ? 0 : "auto", width: 36, height: 36, flexShrink: 0, border: 0, bgcolor: "transparent" }}
          >
            {drawerCollapsed ? <ChevronRightOutlined /> : <ChevronLeftOutlined />}
          </IconButton>
        )}
      </Stack>
      <Box component="nav" aria-label="工作台导航" sx={{ pt: 2, minHeight: 0, display: "flex", flexGrow: 1, flexDirection: "column" }}>
        <List aria-label="工作台主导航" sx={{ px: drawerCollapsed ? 1 : 1.75, py: 0, display: "grid", gap: .75 }}>
          {navItems.map((item) => (
            <ListItem key={item.path} disablePadding>
              <Tooltip title={drawerCollapsed ? item.label : ""} placement="right" disableHoverListener={!drawerCollapsed} disableFocusListener={!drawerCollapsed}>
                <ListItemButton
                  aria-label={item.label}
                  selected={item.path === currentPrimaryPath}
                  onClick={() => { navigate(item.path); setDrawerOpen(false); }}
                  sx={{ px: drawerCollapsed ? 0 : 1.5, justifyContent: drawerCollapsed ? "center" : "flex-start" }}
                >
                  <ListItemIcon sx={{ minWidth: drawerCollapsed ? 0 : 36, color: "inherit", justifyContent: "center" }}>{item.icon}</ListItemIcon>
                  {!drawerCollapsed && <ListItemText primary={item.label} slotProps={{ primary: { sx: { fontSize: 14, fontWeight: 700 } } }} />}
                </ListItemButton>
              </Tooltip>
            </ListItem>
          ))}
        </List>
        <Box sx={{ mt: "auto", p: drawerCollapsed ? 1 : 1.75 }}>
          <Divider sx={{ mb: 1.5 }} />
          {drawerCollapsed ? (
            <Tooltip title="故障接管" placement="right">
              <IconButton component="a" href="/operations" aria-label="故障接管" sx={{ mx: "auto", display: "flex" }}>
                <OpenInNewOutlined />
              </IconButton>
            </Tooltip>
          ) : (
            <Button component="a" href="/operations" fullWidth variant="text" endIcon={<OpenInNewOutlined />} sx={{ justifyContent: "space-between" }}>
              故障接管
            </Button>
          )}
        </Box>
      </Box>
    </Box>
  );

  return (
    <Box data-market-color-scheme={marketColorScheme} sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <AppBar
        position="fixed"
        color="transparent"
        sx={{
          zIndex: theme.zIndex.appBar,
          left: { xs: 0, md: `${desktopDrawerWidth}px` },
          width: { xs: "100%", md: `calc(100% - ${desktopDrawerWidth}px)` },
          transition: theme.transitions.create(["left", "width"], { duration: theme.transitions.duration.shorter }),
        }}
      >
        <Toolbar
          sx={{
            minHeight: { xs: 96, md: 64 },
            alignContent: "center",
            flexWrap: { xs: "wrap", md: "nowrap" },
            columnGap: { xs: 1, sm: 2 },
            rowGap: { xs: .25, md: 0 },
            px: { xs: 1.5, sm: 2.5, md: 3 },
          }}
        >
          {narrow && <IconButton aria-label="打开导航" onClick={() => setDrawerOpen(true)} edge="start"><MenuOutlined /></IconButton>}
          {narrow ? (
            <Stack direction="row" spacing={.5} sx={{ alignItems: "baseline", minWidth: 0 }}>
              <Typography component="span" sx={{ fontSize: 15, lineHeight: 1.1, fontWeight: 750 }}>Halpha</Typography>
              <Typography component="span" sx={{ fontSize: 15, lineHeight: 1.1, fontWeight: 650 }} noWrap>· {pageTitle}</Typography>
            </Stack>
          ) : (
            <Typography component="div" sx={{ fontSize: 24, lineHeight: 1.1, fontWeight: 650 }}>{pageTitle}</Typography>
          )}
          {(narrow || drawerCollapsed) && <Chip label={status.environment_kind} size="small" color="primary" icon={<ShieldOutlined />} />}
          <Typography
            className="mono"
            variant="caption"
            color="text.secondary"
            noWrap
            sx={{
              order: { xs: 5, md: 0 },
              flexBasis: { xs: "100%", md: "auto" },
              ml: { md: "auto" },
              maxWidth: { xs: "100%", md: 300 },
              fontSize: { xs: 10, md: 12 },
            }}
          >
            账户 · {status.account_id}
          </Typography>
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{
              display: "block",
              order: { xs: 6, md: 0 },
              flexBasis: { xs: "100%", md: "auto" },
              fontSize: { xs: 10, md: 12 },
            }}
          >
            事实截止 {formatUserVisibleTime(status.server_fact_cutoff)}
          </Typography>
          {status.environment_kind === "LIVE" && (
            <Chip
              label={`真实账户交易 · ${translatedLabel(gateStateLabels, status.runtime_real_write_gate)}`}
              size="small"
              color={status.runtime_real_write_gate === "OPEN" ? "error" : "warning"}
              variant="outlined"
            />
          )}
        </Toolbar>
      </AppBar>
      <Drawer
        variant={narrow ? "temporary" : "permanent"}
        open={narrow ? drawerOpen : true}
        onClose={() => setDrawerOpen(false)}
        ModalProps={{ keepMounted: true }}
        slotProps={{ paper: { "aria-label": narrow ? "工作台导航抽屉" : undefined } }}
        sx={{
          width: narrow ? DRAWER_WIDTH : desktopDrawerWidth,
          flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: narrow ? DRAWER_WIDTH : desktopDrawerWidth,
            top: 0,
            height: "100%",
            overflowX: "hidden",
            transition: theme.transitions.create("width", { duration: theme.transitions.duration.shorter }),
          },
        }}
      >
        {drawer}
      </Drawer>
      <Box component="main" sx={{ ml: { xs: 0, md: `${desktopDrawerWidth}px` }, pt: { xs: "96px", md: "64px" }, minHeight: "100vh", transition: theme.transitions.create("margin-left", { duration: theme.transitions.duration.shorter }) }}>
        {productUpdateAvailable && (
          <Alert
            severity="info"
            variant="standard"
            action={(
              <Button
                color="inherit"
                aria-label="刷新并加载当前产品版本"
                onClick={() => window.location.reload()}
                sx={{ flexShrink: 0, whiteSpace: "nowrap" }}
              >
                刷新页面
              </Button>
            )}
            sx={{ m: 2, mb: 0 }}
          >
            产品已更新。刷新页面后使用当前版本；尚未提交的表单内容不会自动保留。
          </Alert>
        )}
        <Outlet context={{ status, marketColorScheme, setMarketColorScheme } satisfies FrameContext} />
      </Box>
    </Box>
  );
}

function OverviewPage() {
  const navigate = useNavigate();
  const { status } = useOutletContext<FrameContext>();
  const [activeTab, setActiveTab] = useState<"POSITIONS" | "TRADES">("POSITIONS");
  const query = useQuery({ queryKey: ["overview"], queryFn: getOverview, refetchInterval: 30_000 });
  const activationsQuery = useQuery({ queryKey: ["activations"], queryFn: getActivations, refetchInterval: 30_000 });
  const reviewsQuery = useQuery({ queryKey: ["reviews"], queryFn: getReviews, refetchInterval: 30_000 });
  const strategiesQuery = useQuery({ queryKey: ["strategies"], queryFn: getStrategies });
  const data = query.data;
  const environmentContextMismatch = Boolean(
    data
    && (
      data.environment_kind !== status.environment_kind
      || data.account_id !== status.account_id
    )
  );
  const openActivations = (activationsQuery.data ?? []).filter((activation) => activation.lifecycle !== "COMPLETED");
  const activationDetailQueries = useQueries({
    queries: openActivations.map((activation) => ({
      queryKey: ["activation", activation.activation_id],
      queryFn: () => getActivation(activation.activation_id),
      refetchInterval: 30_000,
    })),
  });
  const recentClosedTrades = [...(reviewsQuery.data ?? [])]
    .filter((review) => {
      const result = tradeResultForReview(review);
      return ["COMPLETED", "PARTIAL"].includes(valueOf(review, "primary_result"))
        && result.calculation_complete === true
        && result.closed === true
        && result.result_scope !== "ACCOUNT_FACTS_WITH_EXTERNAL_CLOSURE"
        && Number.isFinite(Number(result.net_pnl));
    })
    .sort((left, right) => Date.parse(valueOf(right, "fact_cutoff", "")) - Date.parse(valueOf(left, "fact_cutoff", "")))
    .slice(0, 3);
  const recentTradeActivationQueries = useQueries({
    queries: recentClosedTrades.map((review) => ({
      queryKey: ["activation", valueOf(review, "activation_id")],
      queryFn: () => getActivation(valueOf(review, "activation_id")),
      staleTime: 30_000,
    })),
  });
  const recentNetPnl = recentClosedTrades.reduce((total, review) => (
    total + Number(tradeResultForReview(review).net_pnl)
  ), 0);
  const positionRows = openActivations.flatMap((summary, index) => {
    const detail = activationDetailQueries[index]?.data;
    const result = recordOf(detail?.trade_result);
    const quantity = Number(result.position_quantity);
    if (!detail || !Number.isFinite(quantity) || quantity === 0) return [];
    const facts = recordsOf(detail.venue_facts);
    const positionFact = facts
      .filter((fact) => valueOf(fact, "kind") === "POSITION_STATE")
      .sort((left, right) => Date.parse(valueOf(right, "cutoff", "")) - Date.parse(valueOf(left, "cutoff", "")))[0];
    const positionPayload = recordOf(positionFact?.payload);
    const markPrice = Number(positionPayload.mark_price);
    const entryPrice = Number(result.average_entry_price);
    const unrealizedPnl = Number.isFinite(markPrice) && Number.isFinite(entryPrice)
      ? (markPrice - entryPrice) * quantity
      : null;
    const strategyRef = valueOf(recordOf(detail.strategy), "strategy_ref");
    const strategyId = strategyRef.split("@", 1)[0];
    const strategy = strategiesQuery.data?.find((item) => item.strategy_id === strategyId);
    const planName = valueOf(recordOf(detail.plan), "plan_name", valueOf(summary, "plan_name", ""));
    return [{
      summary,
      detail,
      result,
      quantity,
      markPrice,
      entryPrice,
      unrealizedPnl,
      positionFact,
      strategyName: strategy?.display_name ?? strategyRef,
      planName,
    }];
  });
  return (
    <Box sx={{ width: "min(1120px, calc(100% - clamp(32px, 4vw, 48px)))", mx: "auto", py: { xs: 2, sm: 3 } }}>
      <Typography
        component="h1"
        sx={visuallyHiddenSx}
      >
        账户总览
      </Typography>
      {(query.isFetching || activationsQuery.isFetching || reviewsQuery.isFetching || activationDetailQueries.some((item) => item.isFetching)) && <LinearProgress aria-label="正在刷新总览" sx={{ mb: 1 }} />}
      {query.isError && (
        <Alert severity="error" variant="outlined" sx={{ mb: 3 }}>
          服务器事实当前不可确认。工作台没有把缓存显示为当前事实；请核对 PostgreSQL，必要时使用故障接管。
        </Alert>
      )}
      {environmentContextMismatch && (
        <Alert severity="error" variant="outlined">
          页面环境与账户事实不一致，已拒绝显示总览数据。请刷新页面并核对当前运行配置。
        </Alert>
      )}
      {data && !environmentContextMismatch && (
        <>
          <Stack
            component="section"
            direction={{ xs: "column", sm: "row" }}
            spacing={{ xs: 1, sm: 2 }}
            sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" } }}
          >
            <Tabs value={activeTab} onChange={(_event, value: "POSITIONS" | "TRADES") => setActiveTab(value)} aria-label="总览内容">
              <Tab value="POSITIONS" label={`当前仓位（${positionRows.length}）`} />
              <Tab value="TRADES" label="最近交易结果" />
            </Tabs>
            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: "nowrap" }}>
              刷新于 {formatUserVisibleTime(data.view_retrieved_at)} · 每 30 秒自动更新
            </Typography>
          </Stack>
          {activeTab === "POSITIONS" && (
            <Box component="section" aria-label="当前仓位" sx={{ mt: 2 }}>
              {activationsQuery.isError && <Alert severity="error">开放激活和仓位归属当前不可读；页面不显示缓存仓位。</Alert>}
              {!activationsQuery.isError && activationDetailQueries.some((item) => item.isPending) && <LinearProgress aria-label="正在读取当前仓位" />}
              {!activationsQuery.isError && !activationDetailQueries.some((item) => item.isPending) && positionRows.length === 0 && (
                <Alert severity="info" variant="outlined">当前没有已归属于 Halpha 激活的持仓。</Alert>
              )}
              <ExpandableList
                items={positionRows}
                initialCount={4}
                step={4}
                renderItem={(position) => {
                  const instrument = position.summary.instrument_ref;
                  const direction = position.quantity > 0 ? "做多" : "做空";
                  const notional = Number.isFinite(position.markPrice) ? Math.abs(position.quantity * position.markPrice) : null;
                  return (
                    <Box key={position.summary.activation_id} sx={{ ...surfaceFrameSx, overflow: "hidden" }}>
                      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ p: 2, justifyContent: "space-between", alignItems: { md: "center" } }}>
                        <Box sx={{ minWidth: 0 }}>
                          <Typography variant="overline" color="text.secondary">{position.strategyName}</Typography>
                          {position.planName && <Typography variant="h2" sx={{ mt: .25 }}>{position.planName}</Typography>}
                          <Typography sx={{ mt: position.planName ? .25 : 0, fontWeight: 750 }}>
                            {instrument} · <MarketToneText tone={marketToneForDirection(position.quantity > 0 ? "LONG" : "SHORT")}>{direction}</MarketToneText>
                          </Typography>
                          <Typography variant="caption" color="text.secondary">保护 {translatedLabel(protectionStateLabels, position.summary.protection_state)} · 激活 {shortDigest(position.summary.activation_id)}</Typography>
                        </Box>
                        <Button variant="outlined" onClick={() => navigate(`/activations/${position.summary.activation_id}`)}>查看运行与控制</Button>
                      </Stack>
                      <FactGrid facts={[
                        { label: "持仓数量", value: `${marketVolume(String(Math.abs(position.quantity)))} BTC`, note: direction },
                        { label: "持仓名义金额", value: notional === null ? "未知" : usdt(notional) },
                        { label: "平均入场价", value: Number.isFinite(position.entryPrice) ? `${marketPrice(String(position.entryPrice))} USDT` : "未知" },
                        { label: "标记价格", value: Number.isFinite(position.markPrice) ? `${marketPrice(String(position.markPrice))} USDT` : "未知", note: "来自最近一次归属仓位事实" },
                        { label: "未实现盈亏", value: position.unrealizedPnl === null ? "未知" : signedUsdt(position.unrealizedPnl), tone: marketToneForSignedValue(position.unrealizedPnl) },
                        { label: "已归属手续费", value: usdt(position.result.commission) },
                        { label: "仓位事实截止", value: formatUserVisibleTime(valueOf(position.positionFact, "cutoff")), note: "持续显示时间，避免把非实时数据误认为实时连接" },
                        { label: "强平价 / 保证金率", value: "未提供", note: "当前权威事实未包含，不推算" },
                      ]} />
                    </Box>
                  );
                }}
              />
              {openActivations.length > 0 && (
                <Box sx={{ mt: 4 }}>
                  <Typography variant="h2" sx={{ mb: 1 }}>运行中的策略</Typography>
                  <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>包含尚未入场的激活；它们不是当前仓位。</Typography>
                  <ExpandableList
                    items={openActivations}
                    initialCount={4}
                    step={4}
                    renderItem={(activation) => (
                      <Box key={activation.activation_id} sx={{ ...surfaceFrameSx, p: 2 }}>
                        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
                          <Box sx={{ minWidth: 0 }}>
                          <Typography sx={{ fontWeight: 750 }}>{valueOf(activation, "plan_name", "未命名计划")}</Typography>
                          <Typography variant="body2">
                            {activation.instrument_ref} · <MarketToneText tone={marketToneForDirection(activation.direction)}>{translatedLabel(directionLabels, activation.direction)}</MarketToneText>
                          </Typography>
                            <Typography variant="caption" color="text.secondary">{activation.lifecycle} · {activation.run_state} · 保护 {translatedLabel(protectionStateLabels, activation.protection_state)} · 更新于 {formatUserVisibleTime(activation.updated_at)}</Typography>
                          </Box>
                          <Button size="small" variant="outlined" onClick={() => navigate(`/activations/${activation.activation_id}`)}>查看详情</Button>
                        </Stack>
                      </Box>
                    )}
                  />
                </Box>
              )}
            </Box>
          )}
          {activeTab === "TRADES" && (
            <Box component="section" aria-label="最近交易结果" sx={{ mt: 2 }}>
              <Typography color="text.secondary" variant="body2" sx={{ mb: 2 }}>只统计成交和手续费均可完整归属的最近三笔闭合交易；净结果暂不含资金费。</Typography>
              {reviewsQuery.isError && <Alert severity="warning">最近交易结果当前不可读；不显示缓存或估算值。</Alert>}
              {!reviewsQuery.isError && recentClosedTrades.length === 0 && <Alert severity="info" variant="outlined">当前还没有可完整计算净结果的闭合交易。</Alert>}
              {recentClosedTrades.length > 0 && <>
                <FactGrid facts={[
                  { label: "已计算交易", value: `${recentClosedTrades.length} 笔` },
                  { label: "合计净结果", value: signedUsdt(recentNetPnl), tone: marketToneForSignedValue(recentNetPnl) },
                ]} />
                <Stack spacing={1.25} sx={{ mt: 2 }}>
                  {recentClosedTrades.map((review, index) => {
                    const result = tradeResultForReview(review);
                    const detail = recentTradeActivationQueries[index]?.data;
                    const activation = recordOf(detail?.activation);
                    const capital = recordOf(detail?.capital);
                    const strategyRef = valueOf(recordOf(detail?.strategy), "strategy_ref");
                    const strategy = strategiesQuery.data?.find((item) => item.strategy_id === strategyRef.split("@", 1)[0]);
                    return <Box key={valueOf(review, "review_id")} sx={{ ...surfaceFrameSx, p: 2 }}>
                      <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
                        <Box>
                          <Typography sx={{ fontWeight: 750 }}>
                            {valueOf(activation, "instrument_ref")} · <MarketToneText tone={marketToneForDirection(valueOf(activation, "direction"))}>{translatedLabel(directionLabels, valueOf(activation, "direction"))}</MarketToneText> · <MarketToneText tone={marketToneForSignedValue(result.net_pnl)}>{signedUsdt(result.net_pnl)}</MarketToneText>
                          </Typography>
                          <Typography variant="body2" color="text.secondary">{strategy?.display_name ?? strategyRef} · 交易金额 {usdt(capital.max_notional)}</Typography>
                          <Typography variant="caption" color="text.secondary">{formatUserVisibleTime(valueOf(review, "fact_cutoff"))} · 手续费 {usdt(result.commission)}</Typography>
                        </Box>
                        <Button size="small" variant="outlined" onClick={() => navigate(`/reviews/${valueOf(review, "review_id")}`)}>查看交易明细</Button>
                      </Stack>
                    </Box>;
                  })}
                </Stack>
                <Button variant="text" sx={{ mt: 1.5 }} onClick={() => navigate("/reviews")}>查看全部交易与复盘</Button>
              </>}
            </Box>
          )}
        </>
      )}
    </Box>
  );
}

function SettingsPage() {
  const { status, marketColorScheme, setMarketColorScheme } = useOutletContext<FrameContext>();
  const buildConsistency = status.app_executor_product_build_consistent === null
    ? "未核对"
    : status.app_executor_product_build_consistent ? "一致" : "不一致";
  const productVersionMismatch = status.executor_status === "PRODUCT_BUILD_MISMATCH"
    || status.app_executor_product_build_consistent === false;
  const emailMutation = useMutation({
    mutationFn: sendTestEmail,
  });
  return (
    <Box sx={{ width: "min(1120px, calc(100% - clamp(32px, 4vw, 48px)))", mx: "auto", py: { xs: 2.5, sm: 3 } }}>
      <PageHeader
        title="运行与产品版本"
        description={status.environment_kind === "LIVE"
          ? "显示服务、产品版本和交易所变更请求状态；凭据值不会进入浏览器。"
          : "显示服务和产品版本状态；凭据值不会进入浏览器。"}
      />
      {!status.database_available && <Alert severity="error" variant="outlined" sx={{ mb: 3 }}>数据库不可用；事实截止点未知。读取失败时不得向交易所提交变更请求。</Alert>}
      {productVersionMismatch && (
        <Alert severity="warning" variant="outlined" sx={{ mb: 3 }}>
          App 与 Executor 产品版本不一致。可以查看已有事实和执行退出控制；不能启动新的策略，也不能向交易所提交新的变更请求。
        </Alert>
      )}
      {!productVersionMismatch && status.executor_status !== "READY" && status.profile !== "BINANCE_LIVE_READ_ONLY" && (
        <Alert severity="warning" variant="outlined" sx={{ mb: 3 }}>
          执行器当前{translatedLabel(executorStatusLabels, status.executor_status)}。可以查看已有事实和执行退出控制，但不能启动新的策略。
        </Alert>
      )}
      <FactGrid facts={[
        { label: "本机监听", value: `${status.bind}:${status.port}` },
        { label: "数据库", value: status.database_available ? "可用" : "未知" },
        { label: "执行器", value: translatedLabel(executorStatusLabels, status.executor_status), note: `核对于 ${formatUserVisibleTime(status.executor_status_checked_at)}` },
        { label: "产品版本", value: shortDigest(status.product_build_id) },
        { label: "应用 / 执行器产品版本", value: buildConsistency },
        ...(status.environment_kind === "LIVE" ? [
          { label: "真实账户交易配置", value: translatedLabel(gateStateLabels, status.configured_runtime_real_write_gate) },
          { label: "当前真实账户交易", value: translatedLabel(gateStateLabels, status.runtime_real_write_gate) },
        ] : []),
        { label: "邮件投递", value: `${status.email_configuration_status === "CONFIGURED" ? "已配置" : "未配置"} · ${status.email_delivery_enabled ? "已启用" : "已停用"}` },
        { label: "视图取得时间", value: formatUserVisibleTime(status.view_retrieved_at) },
      ]} />
      {status.environment_kind === "LIVE" && status.live_write_gate_violations.length > 0 && (
        <Box component="section" sx={{ mt: 4 }}>
          <Typography variant="h2" sx={{ mb: 2 }}>交易所变更请求边界核对结果</Typography>
          <ExpandableList
            items={status.live_write_gate_violations}
            initialCount={8}
            step={8}
            spacing={1}
            renderItem={(violation) => <Typography key={violation} className="mono" variant="body2" color="text.secondary">{violation}</Typography>}
          />
        </Box>
      )}
      <Box component="section" sx={{ mt: 4, maxWidth: 720 }}>
        <Typography variant="h2" sx={{ mb: .5 }}>涨跌配色</Typography>
        <Typography variant="body2" color="text.secondary">只改变视觉映射，不改变方向、盈亏数值或交易行为；偏好保存在当前浏览器。</Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 1.5 }}>
          <Button
            variant={marketColorScheme === DEFAULT_MARKET_COLOR_SCHEME ? "contained" : "outlined"}
            aria-pressed={marketColorScheme === DEFAULT_MARKET_COLOR_SCHEME}
            onClick={() => setMarketColorScheme("RED_DOWN_GREEN_UP")}
          >
            红跌绿涨
          </Button>
          <Button
            variant={marketColorScheme === "RED_UP_GREEN_DOWN" ? "contained" : "outlined"}
            aria-pressed={marketColorScheme === "RED_UP_GREEN_DOWN"}
            onClick={() => setMarketColorScheme("RED_UP_GREEN_DOWN")}
          >
            红涨绿跌
          </Button>
        </Stack>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={{ xs: .5, sm: 2 }} sx={{ mt: 1.5 }} aria-label="当前涨跌配色预览">
          <Typography variant="body2" className="market-tone-up">上涨 · 做多 · +1.00 USDT</Typography>
          <Typography variant="body2" className="market-tone-down">下跌 · 做空 · -1.00 USDT</Typography>
        </Stack>
      </Box>
      <Box component="section" sx={{ mt: 4, maxWidth: 720 }}>
        <Typography variant="h2" sx={{ mb: 1 }}>实际测试邮件</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>只发送只读连通性消息，不包含秘密、完整账户信息、资本授权或可执行命令；投递结果不改变业务状态。</Typography>
        {!status.email_delivery_enabled && <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>当前配置未启用 SMTP。系统不会使用隐式或仓库内代理配置绕过。</Alert>}
        {emailMutation.isSuccess && <Alert severity="success" sx={{ mt: 2 }}>测试邮件已由 SMTP transport 投递；未改变任何交易或资本状态。</Alert>}
        {emailMutation.isError && <Alert severity="error" sx={{ mt: 2 }}>测试邮件未确认：{emailMutation.error instanceof ApiFailure ? emailMutation.error.code : "UNKNOWN"}</Alert>}
        <Button variant="outlined" sx={{ mt: 2 }} disabled={!status.email_delivery_enabled || emailMutation.isPending} onClick={() => emailMutation.mutate()}>发送测试邮件</Button>
      </Box>
    </Box>
  );
}

function PlansPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"CURRENT" | "HISTORY">("CURRENT");
  const [deleteTarget, setDeleteTarget] = useState<PlanSummary | null>(null);
  const query = useQuery({ queryKey: ["plans"], queryFn: getPlans });
  const strategiesQuery = useQuery({ queryKey: ["strategies"], queryFn: getStrategies });
  const fixMutation = useMutation({
    mutationFn: ({ planId, version }: { planId: string; version: number }) => fixPlan(planId, version),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["plans"] }); },
  });
  const deleteMutation = useMutation({
    mutationFn: (plan: PlanSummary) => deletePlan(plan.plan_id, plan.draft_version),
    onSuccess: async (_result, deletedPlan) => {
      queryClient.setQueryData<PlanSummary[]>(["plans"], (current) =>
        current?.filter((plan) => plan.plan_id !== deletedPlan.plan_id)
      );
      setDeleteTarget(null);
      await queryClient.invalidateQueries({ queryKey: ["plans"] });
    },
  });
  const plans = query.data ?? [];
  const historicalPlans = plans.filter((plan) => Boolean(
    plan.plan_version_id
    && (
      plan.product_build_consistent === false
      || (plan.fixed_valid_until && Date.parse(plan.fixed_valid_until) <= Date.now())
    )
  ));
  const currentPlans = plans.filter((plan) => !historicalPlans.includes(plan));
  const renderPlan = (plan: (typeof plans)[number]) => {
    const strategy = strategiesQuery.data?.find((item) => item.strategy_id === plan.strategy_id);
    const planParameters = plan.parameters ?? {};
    const keyParameterFacts = strategy?.plan_key_parameters?.map((definition) => ({
      label: definition.label,
      value: formatPlanKeyParameter(definition, planParameters[definition.parameter_key]),
    })) ?? [];
    const oldProductVersion = Boolean(plan.plan_version_id && plan.product_build_consistent === false);
    const expired = Boolean(plan.fixed_valid_until && Date.parse(plan.fixed_valid_until) <= Date.now());
    const unavailable = oldProductVersion || expired;
    const planState = oldProductVersion
      ? "旧产品版本"
      : expired
        ? "计划已过期"
        : plan.plan_version_id
          ? "已确认计划"
          : "可编辑草稿";
    const planName = plan.plan_name?.trim() || `未命名计划 · ${shortDigest(plan.plan_id)}`;
    const creatorLabel = plan.creator_kind === "AI"
      ? "AI 创建"
      : plan.creator_kind === "HUMAN" ? "人工创建" : "创建来源未知";
    const creationTime = plan.created_at
      ? `创建于 ${formatUserVisibleTime(plan.created_at)}`
      : "创建时间未知";
    return <Box component="article" aria-label={`计划 ${planName}`} key={plan.plan_id} sx={{ ...surfaceFrameSx, p: 2.5, borderColor: unavailable ? "warning.main" : "divider", opacity: unavailable ? .72 : 1 }}>
      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "center" } }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="overline" color={unavailable ? "warning.main" : "text.secondary"}>{planState}</Typography>
          <Typography variant="h2" sx={{ mt: .5 }}>{planName}</Typography>
          <Typography variant="body2" color="text.secondary">
            {strategy?.display_name ?? plan.strategy_id} · <Box component="span" className="mono">{plan.instrument_ref}</Box> · <MarketToneText tone={marketToneForDirection(plan.direction)}>{plan.direction === "LONG" ? "做多" : "做空"}</MarketToneText> · {plan.plan_version_id ? "已确认" : `草稿 v${plan.draft_version}`}
          </Typography>
          <Typography variant="caption" color="text.secondary">{creatorLabel} · {creationTime} · <Box component="span" className="mono">{shortDigest(plan.plan_version_id ?? plan.draft_content_digest)}</Box></Typography>
          {oldProductVersion && <Typography variant="body2" color="warning.main" sx={{ mt: 1 }}>该计划由旧产品版本确认，不能用于当前运行实例。</Typography>}
          {!oldProductVersion && expired && <Typography variant="body2" color="warning.main" sx={{ mt: 1 }}>计划有效期已结束，请新建当前计划。</Typography>}
        </Box>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          {!plan.plan_version_id && <Button variant="outlined" onClick={() => navigate(`/plans/${plan.plan_id}/edit`)}>编辑计划</Button>}
          {!plan.plan_version_id && <Button variant="outlined" color="error" disabled={deleteMutation.isPending} onClick={() => { deleteMutation.reset(); setDeleteTarget(plan); }}>删除草稿</Button>}
          {!plan.plan_version_id && <Button variant="contained" disabled={fixMutation.isPending} onClick={() => fixMutation.mutate({ planId: plan.plan_id, version: plan.draft_version })}>确认计划</Button>}
          {plan.plan_version_id && <Button variant="outlined" onClick={() => navigate(`/plans/new?copyFrom=${encodeURIComponent(plan.plan_id)}`)}>沿用参数新建</Button>}
          {plan.plan_version_id && !unavailable && <Button variant="contained" onClick={() => navigate(`/plans/${plan.plan_version_id}/activate`)}>启动策略</Button>}
        </Stack>
      </Stack>
      <Box component="details" sx={{ mt: 1.5, borderTop: 1, borderColor: "divider", pt: 1.25 }}>
        <Box component="summary" sx={{ display: "inline-flex", cursor: "pointer", color: "info.main", fontSize: 13, fontWeight: 700 }}>
          计划配置
        </Box>
        <Box sx={{ mt: 1.5 }}>
          <FactGrid
            columns={3}
            dense
            facts={[
              { label: "交易金额", value: usdt(plan.max_notional), note: "本计划的资金边界" },
              { label: "计划有效期", value: planDurationMinutes(plan.valid_from, plan.valid_until), note: `截至 ${formatUserVisibleTime(plan.valid_until)}` },
              ...keyParameterFacts,
            ]}
          />
          {!strategy && (
            <Typography variant="caption" color="warning.main" sx={{ display: "block", mt: 1 }}>
              策略关键参数定义当前不可读；页面未猜测或重写参数含义。
            </Typography>
          )}
        </Box>
      </Box>
    </Box>;
  };
  return (
    <Box sx={{ width: "min(1120px, calc(100% - clamp(32px, 4vw, 48px)))", mx: "auto", py: { xs: 2, sm: 3 } }}>
      <Typography
        component="h1"
        sx={visuallyHiddenSx}
      >
        策略计划
      </Typography>
      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={{ xs: 1.5, md: 2 }}
        sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", md: "center" }, mb: 2 }}
      >
        <Tabs value={activeTab} onChange={(_event, value: "CURRENT" | "HISTORY") => setActiveTab(value)} aria-label="计划范围">
          <Tab value="CURRENT" label={`当前计划（${currentPlans.length}）`} />
          <Tab value="HISTORY" label={`历史计划（${historicalPlans.length}）`} />
        </Tabs>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
          <Button variant="contained" onClick={() => navigate("/plans/new")}>新建交易计划</Button>
          <Button variant="outlined" onClick={() => void query.refetch()}>刷新</Button>
        </Stack>
      </Stack>
      {strategiesQuery.isError && <Alert severity="warning" sx={{ mb: 2 }}>策略定义当前不可读；计划身份与基础配置仍按计划事实显示，关键参数不做猜测。</Alert>}
      {query.isPending && <LinearProgress aria-label="正在读取计划" />}
      {query.isError && <Alert severity="error">计划事实不可用；页面没有显示缓存副本。</Alert>}
      {fixMutation.isError && <Alert severity="warning" sx={{ mb: 2 }}>确认失败：{planConfirmationError(fixMutation.error)}。</Alert>}
      <Dialog
        open={Boolean(deleteTarget)}
        onClose={() => { if (!deleteMutation.isPending) { setDeleteTarget(null); deleteMutation.reset(); } }}
        aria-labelledby="delete-plan-title"
        fullWidth
        maxWidth="xs"
      >
        <DialogTitle id="delete-plan-title">删除草稿？</DialogTitle>
        <DialogContent>
          <DialogContentText>
            将永久删除“{deleteTarget?.plan_name?.trim() || (deleteTarget ? `未命名计划 · ${shortDigest(deleteTarget.plan_id)}` : "当前计划")}”。此操作不可恢复，但不会影响策略定义、其他计划或任何已确认版本。
          </DialogContentText>
          {deleteMutation.isError && <Alert severity="error" sx={{ mt: 2 }}>{planDeletionError(deleteMutation.error)}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button variant="outlined" disabled={deleteMutation.isPending} onClick={() => { setDeleteTarget(null); deleteMutation.reset(); }}>取消</Button>
          <Button variant="contained" color="error" disabled={!deleteTarget || deleteMutation.isPending} onClick={() => { if (deleteTarget) deleteMutation.mutate(deleteTarget); }}>
            {deleteMutation.isPending ? "正在删除…" : "删除草稿"}
          </Button>
        </DialogActions>
      </Dialog>
      {activeTab === "CURRENT" && <>
        <ExpandableList items={currentPlans} initialCount={8} step={8} renderItem={renderPlan} />
        {query.data && currentPlans.length === 0 && <Alert severity="info" variant="outlined">当前没有可操作计划。</Alert>}
      </>}
      {activeTab === "HISTORY" && <>
        <ExpandableList items={historicalPlans} initialCount={8} step={8} renderItem={renderPlan} />
        {query.data && historicalPlans.length === 0 && <Alert severity="info" variant="outlined">还没有历史计划。</Alert>}
      </>}
    </Box>
  );
}

function PlanActivationRoute() {
  const { planVersionId = "" } = useParams();
  const navigate = useNavigate();
  const { status } = useOutletContext<FrameContext>();
  const preview = useQuery({ queryKey: ["activation-preview", planVersionId], queryFn: () => getActivationPreview(planVersionId), enabled: Boolean(planVersionId) });
  const parameters = recordOf(preview.data?.strategy_parameters);
  const instrumentRef = valueOf(preview.data, "instrument_ref");
  const direction = valueOf(preview.data, "direction");
  const channelLookback = Number(parameters.channel_lookback_15m) || 20;
  const market = useQuery({
    queryKey: ["activation-preview-market-context", planVersionId, instrumentRef, channelLookback],
    queryFn: () => getMarketContext(instrumentRef, channelLookback),
    enabled: Boolean(preview.data && instrumentRef),
    retry: 1,
    retryDelay: 2_000,
    refetchInterval: 15_000,
  });
  const liveWrite = status.profile === "BINANCE_LIVE_WRITE";
  const liveReadOnly = status.profile === "BINANCE_LIVE_READ_ONLY";
  const realAccountReady = Boolean(preview.data?.live_activation_eligible);
  const currentProductVersion = preview.data?.product_build_consistent === true;
  const executorReady = valueOf(preview.data, "executor_status") === "READY";
  const activationEnabled = Boolean(
    preview.data
    && !liveReadOnly
    && currentProductVersion
    && executorReady
    && (!liveWrite || realAccountReady),
  );
  const mutation = useMutation({
    mutationFn: () => createActivation({
      plan_version_id: planVersionId,
    }),
    onSuccess: (result) => { const activation = result.activation as Record<string, unknown> | undefined; navigate(`/activations/${valueOf(activation, "activation_id")}`); },
  });
  const currentMarket = market.data;
  const activationMarketReady = Boolean(
    currentMarket
    && !market.isError
    && !market.isFetching,
  );
  const currentSpread = currentMarket
    ? String(Number(currentMarket.ask_price) - Number(currentMarket.bid_price))
    : "";
  const currentSpreadBps = currentMarket
    ? Number(currentSpread) / Number(currentMarket.reference_price) * 10_000
    : Number.NaN;
  const longClosedBarBreakoutGap = currentMarket
    ? closedBarBreakoutGapPercent("LONG", currentMarket.latest_close_1m, currentMarket.channel_upper)
    : "";
  const shortClosedBarBreakoutGap = currentMarket
    ? closedBarBreakoutGapPercent("SHORT", currentMarket.latest_close_1m, currentMarket.channel_lower)
    : "";
  const planName = valueOf(preview.data, "plan_name", "");
  return (
    <Box sx={{ width: "min(920px, calc(100% - clamp(32px, 4vw, 48px)))", mx: "auto", py: { xs: 2.5, sm: 3 } }}>
      <PageHeader eyebrow="确认启动计划" title={planName || "未命名计划"} description="交易金额已在策略计划中确定。这里仅确认启动固定计划，不再进行资金授权，也不会立即向 Binance 下单。" />
      {preview.isPending && <LinearProgress aria-label="正在读取激活复核" />}
      {preview.isError && <Alert severity="error">当前复核事实不可用，不能启动策略。</Alert>}
      {preview.data && <>
        <FactGrid facts={[
          { label: "账户", value: valueOf(preview.data, "account_ref") },
          { label: "交易对象 / 方向", value: `${valueOf(preview.data, "instrument_ref")} / ${translatedLabel(directionLabels, valueOf(preview.data, "direction"))}`, tone: marketToneForDirection(valueOf(preview.data, "direction")) },
          { label: "策略", value: valueOf(preview.data, "strategy_ref") },
          { label: "交易金额", value: `${valueOf(preview.data, "trade_amount")} USDT` },
          { label: "有效期", value: formatUserVisibleTime(valueOf(preview.data, "valid_until")) },
          { label: "入场方式", value: parameters.demo_immediate_entry === true ? "下单流程验证 · 下一根有效闭合 1m" : `${valueOf(parameters, "channel_lookback_15m")} × 15m 通道 / ${valueOf(parameters, "confirmation_bars_1m")} × 1m 确认` },
          { label: "保护", value: `初始止损 ${valueOf(parameters, "initial_stop_atr_multiple")} ATR / 最大追价 ${valueOf(parameters, "max_entry_extension_atr")} ATR` },
          { label: "退出", value: `最大 ${valueOf(parameters, "max_hold_bars_15m")} × 15m / TP1 ${Number(valueOf(parameters, "take_profit_1_fraction")) * 100}% @ ${valueOf(parameters, "take_profit_1_r")}R / TP2 @ ${valueOf(parameters, "take_profit_2_r")}R` },
          { label: "产品版本", value: shortDigest(valueOf(preview.data, "product_build_id")) },
          { label: "当前版本一致", value: currentProductVersion ? "是" : "否" },
          { label: "执行器", value: translatedLabel(executorStatusLabels, valueOf(preview.data, "executor_status")), note: `核对于 ${formatUserVisibleTime(valueOf(preview.data, "executor_status_checked_at"))}` },
          ...(liveWrite ? [
            { label: "交易所变更请求", value: valueOf(preview.data, "configured_runtime_real_write_gate") },
          ] : []),
        ]} />
        <Box component="section" sx={{ mt: 3 }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" }, mb: 2 }}>
            <Box>
              <Typography variant="h2">当前市场位置</Typography>
              <Typography color="text.secondary" variant="body2" sx={{ mt: .75 }}>只读公开行情用于决定是否启动；策略仍只按固定参数和闭合 K 线执行。</Typography>
            </Box>
            <Button variant="outlined" onClick={() => market.refetch()} disabled={market.isFetching}>{market.isFetching ? "正在刷新…" : "刷新行情"}</Button>
          </Stack>
          {market.isPending && <LinearProgress aria-label="正在读取启动前行情" />}
          {market.isError && currentMarket && <Alert severity="warning" variant="outlined">
            行情刷新失败；以下保留上次成功行情（截止 {formatUserVisibleTime(currentMarket.source_cutoff)}），可能已经过期。请刷新成功后再决定是否启动。
          </Alert>}
          {market.isError && !currentMarket && <Alert severity="warning" variant="outlined">当前公开行情不可用。不要在无法判断价格、价差和突破位置时启动。</Alert>}
          {currentMarket && <FactGrid facts={[
            { label: "盘口中间价", value: `${marketPrice(currentMarket.reference_price)} USDT` },
            { label: "买一 / 卖一", value: `${marketPrice(currentMarket.bid_price)} / ${marketPrice(currentMarket.ask_price)} USDT` },
            { label: "买卖价差", value: `${marketPrice(currentSpread)} USDT`, note: Number.isFinite(currentSpreadBps) ? `${currentSpreadBps.toFixed(2)} bps` : undefined },
            { label: "通道上沿 / 下沿", value: `${marketPrice(currentMarket.channel_upper)} / ${marketPrice(currentMarket.channel_lower)} USDT`, note: `${direction === "LONG" ? "计划做多" : "计划做空"}；启动前同时比较两侧机会` },
            { label: "最近闭合 1m", value: `${marketPrice(currentMarket.latest_close_1m)} USDT` },
            { label: "1m 收盘距上沿 / 下沿", value: `${gapPercent(longClosedBarBreakoutGap)} / ${gapPercent(shortClosedBarBreakoutGap)}`, note: "策略触发口径；正值表示尚未突破，负值表示已经越过" },
            { label: "盘口中间价距上沿 / 下沿", value: `${gapPercent(currentMarket.long_breakout_gap_pct)} / ${gapPercent(currentMarket.short_breakout_gap_pct)}`, note: "仅用于启动前定位，不替代闭合 K 线与执行前检查" },
            { label: "行情截止", value: formatUserVisibleTime(currentMarket.source_cutoff) },
          ]} />}
          {Number.isFinite(currentSpreadBps) && currentSpreadBps > 10 && <Alert severity="warning" sx={{ mt: 2 }}>
            当前买卖价差约 {currentSpreadBps.toFixed(1)} bps，超过 10 bps 入场上限。可以启动策略等待，但只有价差收窄且其他固定条件同时满足时才会创建入场动作。
          </Alert>}
        </Box>
        <Alert severity="warning" variant="outlined" sx={{ mt: 3 }}>{valueOf(preview.data, "capital_notice")}</Alert>
      </>}
      {liveReadOnly && <Alert severity="warning" sx={{ mt: 3 }}>只读环境仅用于公共市场观察，不能激活计划或向交易所提交变更请求。</Alert>}
      {preview.data && !currentProductVersion && <Alert severity="warning" sx={{ mt: 2 }}>该计划由旧产品版本确认，不能由当前 App 与 Executor 运行。请返回计划列表并新建计划。</Alert>}
      {preview.data && !executorReady && <Alert severity="warning" sx={{ mt: 2 }}>执行器尚未完成连接、启动核对和历史预热，当前不能启动新策略。已有激活的退出与接管控制不受影响。</Alert>}
      {liveWrite && !realAccountReady && <Alert severity="warning" sx={{ mt: 2 }}>当前产品版本或交易所变更请求配置不一致；当前不能启动真实账户策略。</Alert>}
      {mutation.isError && <Alert severity="error" sx={{ mt: 2 }}>激活未提交：{mutation.error instanceof ApiFailure ? mutation.error.code : "结果未知"}</Alert>}
      <Button
        variant="contained"
        color="warning"
        sx={{ mt: 3 }}
        disabled={!activationEnabled || !activationMarketReady || mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending
          ? "正在启动…"
          : !executorReady
            ? "执行器未就绪，不能启动"
          : market.isPending || market.isFetching
            ? "正在读取启动前行情…"
            : market.isError || !currentMarket
              ? "行情不可用，不能启动"
              : liveWrite
                ? "启动真实账户策略"
                : "启动策略"}
      </Button>
    </Box>
  );
}

function ActivationRoute() {
  const { activationId = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["activation", activationId], queryFn: () => getActivation(activationId), enabled: Boolean(activationId), refetchInterval: 2_000 });
  const timelineQuery = useQuery({ queryKey: ["activation-timeline", activationId], queryFn: () => getActivationTimeline(activationId), enabled: Boolean(activationId), refetchInterval: 2_000 });
  const activation = query.data?.activation as Record<string, unknown> | undefined;
  const capital = recordOf(query.data?.capital);
  const tradeResult = recordOf(query.data?.trade_result);
  const actions = recordsOf(query.data?.execution_actions);
  const facts = recordsOf(query.data?.venue_facts);
  const rejectedEntryFact = facts.find((fact) => {
    const payload = recordOf(fact.payload);
    return valueOf(fact, "kind") === "ORDER_STATE"
      && valueOf(payload, "status") === "REJECTED";
  });
  const rejectedEntryReason = rejectedEntryFact
    ? venueReasonText(valueOf(recordOf(rejectedEntryFact.payload), "reason", "交易所拒绝了本次订单"))
    : "";
  const receipts = recordsOf(query.data?.receipts);
  const strategy = recordOf(query.data?.strategy);
  const plan = recordOf(query.data?.plan);
  const parameters = recordOf(strategy.parameters);
  const demoImmediateEntry = parameters.demo_immediate_entry === true;
  const stopped = Array.isArray(query.data?.stopped_categories) ? query.data.stopped_categories.map(String) : [];
  const newRiskStopped = stopped.includes("NEW_RISK");
  const openEntryActions = actions.filter((action) =>
    valueOf(action, "action_kind") === "ENTRY"
    && !["NOT_SUBMITTED", "CLOSED", "HANDED_OVER"].includes(valueOf(action, "state"))
  );
  const hasOpenEntryResponsibility = openEntryActions.length > 0;
  const unknownEntryCount = openEntryActions.filter(
    (action) => valueOf(action, "state") === "UNKNOWN"
  ).length;
  const channelLookback = Number(parameters.channel_lookback_15m) || 20;
  const market = useQuery({
    queryKey: ["activation-market-context", activationId, channelLookback],
    queryFn: () => getMarketContext(valueOf(activation, "instrument_ref"), channelLookback),
    enabled: Boolean(activationId && activation && valueOf(activation, "lifecycle") === "RUNNING"),
    retry: 1,
    retryDelay: 2_000,
    refetchInterval: 15_000,
  });
  const [intent, setIntent] = useState<ControlIntent | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const preview = useMutation({
    mutationFn: (next: ControlIntent) => previewControl(activationId, next),
    onSuccess: (_result, next) => {
      setIntent(next);
      setIdempotencyKey(crypto.randomUUID());
    },
  });
  const submit = useMutation({
    mutationFn: (next: ControlIntent) => {
      if (!idempotencyKey) throw new ApiFailure(409, "CONTROL_PREVIEW_REQUIRED");
      return submitActivationControl(
        activationId,
        next,
        {
          expected_version: Number(activation?.state_version ?? 0),
          takeover_scope: {},
        },
        idempotencyKey,
      );
    },
    onSuccess: async () => {
      setIntent(null);
      setIdempotencyKey(null);
      await queryClient.invalidateQueries({ queryKey: ["activation", activationId] });
      await queryClient.invalidateQueries({ queryKey: ["activation-timeline", activationId] });
    },
  });
  const resumeEligible =
    intent !== "RESUME_ACTIVATION" || preview.data?.resume_eligible === true;
  const controls: Array<{ intent: ControlIntent; label: string; color?: "warning" | "error" | "primary" }> = [
    { intent: "STOP_NEW_RISK", label: "停止新增风险", color: "warning" },
    { intent: "RESUME_ACTIVATION", label: "恢复连续性暂停" },
    { intent: "EXIT_STRATEGY", label: "退出策略", color: "error" },
    { intent: "USER_TAKEOVER", label: "用户接管", color: "error" },
  ];
  const selectedControlLabel = controls.find((control) => control.intent === intent)?.label;
  const lifecycle = valueOf(activation, "lifecycle");
  const takeover = lifecycle === "USER_TAKEOVER";
  const terminal = takeover || lifecycle === "COMPLETED";
  const runState = translatedLabel(runStateLabels, valueOf(activation, "run_state"));
  const pauseReason = valueOf(activation, "pause_reason", "");
  const runStateDisplay = lifecycle === "COMPLETED"
    ? "已闭合（无需运行）"
    : takeover
      ? "用户接管（机器不再运行）"
      : newRiskStopped
        ? `${runState} / 新增风险已停止`
        : pauseReason
          ? `${runState} / ${translatedLabel(pauseReasonLabels, pauseReason)}`
          : runState;
  const stopScopeDisplay = lifecycle === "COMPLETED"
    ? "已闭合（无需停止）"
    : stopped.length
      ? stopped.join(" · ")
      : "无停止项";
  const submittedReceipt = recordOf(submit.data);
  const submittedReceiptId = valueOf(submittedReceipt, "receipt_id", "");
  const currentSubmittedReceipt = receipts.find(
    (receipt) => valueOf(receipt, "receipt_id", "") === submittedReceiptId,
  ) ?? submittedReceipt;
  const submittedReceiptState = valueOf(currentSubmittedReceipt, "state", "");
  const protectionState = valueOf(activation, "protection_state", "NONE");
  const hasEntryFill = activation?.has_entry_fill === true;
  const protectionGap = hasEntryFill && tradeResult.closed !== true && !["WORKING", "CLOSED"].includes(protectionState);
  const protectionDisplay = hasEntryFill
    ? protectionState
    : unknownEntryCount > 0
      ? "成交未知（保护不可证明）"
      : "未入场（无需保护）";
  const direction = valueOf(activation, "direction");
  const currentMarket = market.data;
  const ruleState = recordOf(activation?.rule_state);
  const deadlines = recordOf(ruleState.deadlines);
  const entryValidUntil = valueOf(deadlines, "entry_valid_until", "");
  const entryWindowExpired = Boolean(
    entryValidUntil && Date.parse(entryValidUntil) <= Date.now()
  );
  const entryRemainingMinutes = entryValidUntil
    ? Math.max(0, Math.ceil((Date.parse(entryValidUntil) - Date.now()) / 60_000))
    : null;
  const currentSpread = currentMarket
    ? String(Number(currentMarket.ask_price) - Number(currentMarket.bid_price))
    : "";
  const currentSpreadBps = currentMarket
    ? Number(currentSpread) / Number(currentMarket.reference_price) * 10_000
    : Number.NaN;
  const latestClose1m = Number(currentMarket?.latest_close_1m);
  const breakoutBoundary = Number(
    direction === "LONG" ? currentMarket?.channel_upper : currentMarket?.channel_lower
  );
  const longClosedBarBreakoutGap = currentMarket
    ? closedBarBreakoutGapPercent("LONG", currentMarket.latest_close_1m, currentMarket.channel_upper)
    : "";
  const shortClosedBarBreakoutGap = currentMarket
    ? closedBarBreakoutGapPercent("SHORT", currentMarket.latest_close_1m, currentMarket.channel_lower)
    : "";
  const latestClosedBarBeyondBoundary = Number.isFinite(latestClose1m)
    && Number.isFinite(breakoutBoundary)
    && (direction === "LONG"
      ? latestClose1m > breakoutBoundary
      : latestClose1m < breakoutBoundary);
  const maxEntryExtensionAtr = valueOf(parameters, "max_entry_extension_atr");
  const entryExtensionLimit = currentMarket
    ? entryExtensionBoundary(
      direction === "SHORT" ? "SHORT" : "LONG",
      direction === "LONG" ? currentMarket.channel_upper : currentMarket.channel_lower,
      currentMarket.atr_14,
      maxEntryExtensionAtr,
    )
    : null;
  const latestClosedBarBeyondExtension = Number.isFinite(latestClose1m)
    && entryExtensionLimit !== null
    && (direction === "LONG"
      ? latestClose1m > entryExtensionLimit
      : latestClose1m < entryExtensionLimit);
  const confirmationBars = Number(parameters.confirmation_bars_1m) || 1;
  const latestNoActionEvent = [...(timelineQuery.data ?? [])].reverse().find((item) => {
    const detail = recordOf(item.detail);
    return valueOf(item, "source", "") === "PLAN_EVENT"
      && Boolean(valueOf(detail, "no_action_reason", ""));
  });
  const latestNoActionDetail = recordOf(latestNoActionEvent?.detail);
  const latestNoActionCode = valueOf(latestNoActionDetail, "no_action_reason", "");
  const latestNoActionText = latestNoActionCode
    ? entryNoActionReasonLabels[latestNoActionCode] ?? latestNoActionCode
    : "";
  const fillCount = Number(tradeResult.fill_count ?? 0);
  const fillCashFlow = Number(tradeResult.fill_cash_flow);
  const positionQuantity = Number(tradeResult.position_quantity);
  const attributedCommission = Number(tradeResult.commission);
  const referencePrice = Number(currentMarket?.reference_price);
  const firstFill = recordOf(ruleState.first_fill);
  const entryRiskContext = recordOf(firstFill.entry_risk_context);
  const immediateExitEstimate = tradeResult.calculation_complete === true
    ? estimateImmediateExit(
      positionQuantity,
      fillCashFlow,
      attributedCommission,
      Number(currentMarket?.bid_price),
      Number(currentMarket?.ask_price),
      Number(entryRiskContext.sizing_taker_fee_rate),
    )
    : null;
  const averageEntryPrice = Number(tradeResult.average_entry_price);
  const protectionTriggerPrice = actions
    .filter((action) => valueOf(action, "action_kind") === "PROTECTION")
    .map((action) => Number(recordOf(action.action_terms).trigger_price))
    .find(Number.isFinite);
  const takeProfitTriggerPrices = [...new Set(
    actions
      .filter((action) => valueOf(action, "action_kind") === "TAKE_PROFIT")
      .map((action) => Number(recordOf(action.action_terms).trigger_price))
      .filter(Number.isFinite),
  )].sort((left, right) => direction === "LONG" ? left - right : right - left);
  const closedNetAvailable = tradeResult.calculation_complete === true
    && tradeResult.closed === true
    && Number.isFinite(Number(tradeResult.net_pnl));
  const venueFactCutoff = latestUtc([
    valueOf(activation, "latest_venue_cutoff", ""),
    ...facts.map((fact) => valueOf(fact, "cutoff", "")),
  ]);
  const planName = valueOf(plan, "plan_name", "") || "未命名计划";
  return (
    <Box sx={{ width: "min(1000px, calc(100% - clamp(32px, 4vw, 48px)))", mx: "auto", py: { xs: 2.5, sm: 3 } }}>
      <PageHeader eyebrow="激活运行与控制" title={planName} description="按计划事件 → 执行动作 → 交易所事实 → 核对结论观察同一责任链；命令回执不冒充订单、成交、持仓或保护事实。" />
      {(query.isPending || timelineQuery.isPending) && <LinearProgress aria-label="正在读取激活与时间线" />}
      {(query.isError || timelineQuery.isError) && <Alert severity="error" sx={{ mb: 2 }}>当前服务器事实不可确认；页面不会把旧缓存冒充当前事实，也不会开放离线资本命令。</Alert>}
      {protectionGap && <Alert severity="error" variant="filled" sx={{ mb: 3 }}>存在已确认敞口，但交易所原生保护尚未证明为工作中。保持在线并核对 Binance 官方入口；任何“停止”或回执都不代表已经安全。</Alert>}
      {unknownEntryCount > 0 && <Alert severity="error" variant="filled" sx={{ mb: 3 }}>有 {unknownEntryCount} 个入场动作的交易所结果未决。未收到成交事实不等于未成交，保护也尚不可证明；系统只查询各自原 UUID，并禁止创建新的入场动作。</Alert>}
      {rejectedEntryReason && !hasEntryFill && <Alert severity="warning" variant="outlined" sx={{ mb: 3 }}>本次入场未成交：{rejectedEntryReason} 可重新启动一笔独立计划再次验证。</Alert>}
      {capital.max_loss_reached === true && <Alert severity="error" variant="filled" sx={{ mb: 3 }}>计划已触发停止新增风险。系统不得再开仓或加仓；退出、保护与核对仍需完成。</Alert>}
      {entryWindowExpired && !terminal && !hasEntryFill && !hasOpenEntryResponsibility && <Alert severity="warning" variant="outlined" sx={{ mb: 3 }}>入场窗口已经到期，不能再产生新的入场动作；Executor 正在闭合本次无入场激活。</Alert>}
      {demoImmediateEntry && !terminal && !hasEntryFill && !hasOpenEntryResponsibility && !newRiskStopped && <Alert severity="warning" variant="outlined" sx={{ mb: 3 }}>本次为下单流程验证：下一根有效闭合 1m 将触发一次入场，不代表策略出现突破信号。</Alert>}
      {takeover && <Alert severity="warning" variant="outlined" sx={{ mb: 3 }}>用户接管已持久化。Halpha 不再提交新的待执行动作，也不会自动撤单、补保护或平仓；请在 Binance 官方入口处理，页面仅只读核对迟到事实与开放责任。</Alert>}
      {activation && <FactGrid facts={[
        { label: "激活标识", value: valueOf(activation, "activation_id") },
        { label: "生命周期", value: translatedLabel(lifecycleLabels, lifecycle) },
        { label: "运行状态", value: runStateDisplay },
        { label: "状态版本", value: valueOf(activation, "state_version") },
        { label: "交易对象 / 方向", value: `${valueOf(activation, "instrument_ref")} / ${translatedLabel(directionLabels, valueOf(activation, "direction"))}`, tone: marketToneForDirection(valueOf(activation, "direction")) },
        { label: "入场截止", value: formatUserVisibleTime(entryValidUntil), note: terminal || entryRemainingMinutes === null ? undefined : hasOpenEntryResponsibility ? "已有入场责任，不再创建新入场" : entryWindowExpired ? hasEntryFill ? "入场机会已结束" : "已到期，等待闭合" : `剩余约 ${entryRemainingMinutes} 分钟` },
        { label: "保护", value: protectionDisplay },
        { label: "策略状态", value: translatedLabel(lifecycleLabels, valueOf(activation, "lifecycle")), note: terminal ? "本次激活已闭合" : unknownEntryCount > 0 ? "入场结果未决，正在核对原 UUID" : newRiskStopped || capital.max_loss_reached === true ? "已停止新增风险" : hasEntryFill ? "持仓按计划管理" : "等待入场条件" },
        ...(fillCount > 0 ? [{
          label: terminal ? "本次净结果" : "立即市价退出估算净结果",
          value: terminal
            ? closedNetAvailable ? signedUsdt(tradeResult.net_pnl) : "未知"
            : immediateExitEstimate ? signedUsdt(immediateExitEstimate.netResult) : "未知",
          tone: terminal
            ? closedNetAvailable ? marketToneForSignedValue(tradeResult.net_pnl) : undefined
            : immediateExitEstimate ? marketToneForSignedValue(immediateExitEstimate.netResult) : undefined,
          note: terminal
            ? "按本次成交价差减已归属手续费计算，不含资金费"
            : immediateExitEstimate
              ? `按${positionQuantity > 0 ? "买一" : "卖一"} ${marketPrice(String(immediateExitEstimate.exitPrice))} USDT，并扣除预计退出手续费 ${immediateExitEstimate.exitCommission.toFixed(8)} USDT；不含滑点和资金费`
              : "缺少当前买卖价或入场时冻结的手续费率，不能可靠估算",
        },
        ...(Number.isFinite(averageEntryPrice) ? [{ label: "平均入场价", value: `${marketPrice(String(averageEntryPrice))} USDT` }] : []),
        ...(!terminal && Number.isFinite(referencePrice) ? [{
          label: "当前盘口中间价",
          value: `${marketPrice(String(referencePrice))} USDT`,
          note: currentMarket?.source_cutoff
            ? `公开行情截止 ${formatUserVisibleTime(currentMarket.source_cutoff)}`
            : undefined,
        }] : []),
        ...(Number.isFinite(protectionTriggerPrice) ? [{ label: "止损价", value: `${marketPrice(String(protectionTriggerPrice))} USDT` }] : []),
        ...(takeProfitTriggerPrices.length > 0 ? [{
          label: "止盈价",
          value: takeProfitTriggerPrices.map((price, index) => `TP${index + 1} ${marketPrice(String(price))}`).join(" / ") + " USDT",
        }] : []),
        ] : []),
        { label: "交易所事实截止点", value: hasEntryFill || actions.length || facts.length ? venueFactCutoff ? formatUserVisibleTime(venueFactCutoff) : "未知" : "尚无交易所责任事实" },
      ]} />}

      {activation && lifecycle === "RUNNING" && !hasEntryFill && !hasOpenEntryResponsibility && !newRiskStopped && <Box component="section" sx={{ mt: 4 }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" }, mb: 2 }}>
          <Box>
            <Typography variant="h2">{demoImmediateEntry ? "等待验证入场" : "等待入场"}</Typography>
            <Typography color="text.secondary" variant="body2" sx={{ mt: .75 }}>公开行情每 15 秒更新；策略仍只按闭合 K 线和固定参数判断。</Typography>
          </Box>
          <Button variant="outlined" onClick={() => market.refetch()} disabled={market.isFetching}>{market.isFetching ? "正在刷新…" : "刷新行情"}</Button>
        </Stack>
        {market.isPending && <LinearProgress aria-label="正在读取激活行情" />}
        {market.isError && currentMarket && <Alert severity="warning" variant="outlined">行情刷新失败；以下保留上次成功行情（截止 {formatUserVisibleTime(currentMarket.source_cutoff)}），可能已经过期，仅用于定位。Executor 继续按框架收到的当前市场事件和固定规则运行。</Alert>}
        {market.isError && !currentMarket && <Alert severity="warning" variant="outlined">当前行情不可用，页面不能判断距离入场条件还有多远；Executor 不会因此放宽固定规则。</Alert>}
        {latestNoActionText && <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
          最近一次入场意图没有下单：{latestNoActionText}（{formatUserVisibleTime(valueOf(latestNoActionEvent, "at"))}）。策略仍在有效期内等待下一次满足条件的闭合 K 线。
        </Alert>}
        {Number.isFinite(currentSpreadBps) && currentSpreadBps > 10 && <Alert severity="warning" sx={{ mb: 2 }}>
          当前买卖价差约 {currentSpreadBps.toFixed(1)} bps，超过 10 bps 入场上限。系统正在等待价差收窄，不会在当前盘口创建入场动作。
        </Alert>}
        {latestClosedBarBeyondBoundary && latestClosedBarBeyondExtension && entryExtensionLimit !== null && <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>
          最近闭合 1m 虽已突破通道，但超过最大追价边界 {marketPrice(String(entryExtensionLimit))} USDT。策略不会追单；等待价格回到允许范围或入场窗口结束。
        </Alert>}
        {currentMarket && <FactGrid facts={[
          { label: "盘口中间价", value: `${marketPrice(currentMarket.reference_price)} USDT`, note: "仅用于页面定位；执行前会同时读取标记价格，并按方向采用更保守的价格" },
          { label: "最新闭合 1m", value: `${marketPrice(currentMarket.latest_close_1m)} USDT`, note: demoImmediateEntry ? "下一根有效闭合 1m 将用于验证入场" : latestClosedBarBeyondExtension ? "已突破，但超过最大追价边界；策略不会追单" : latestClosedBarBeyondBoundary ? confirmationBars > 1 ? "已突破；连续确认和执行前检查仍按闭合 K 线判断" : "已突破；仍需通过执行前价格、价差与账户检查" : pendingBreakoutNote(direction === "SHORT" ? "SHORT" : "LONG") },
          { label: "最近闭合 1m 成交量 / 笔数", value: `${marketVolume(currentMarket.latest_volume_1m)} BTC / ${currentMarket.latest_trade_count_1m} 笔`, note: "用于判断当前行情活跃度，不参与策略触发" },
          { label: "买一 / 卖一", value: `${marketPrice(currentMarket.bid_price)} / ${marketPrice(currentMarket.ask_price)} USDT` },
          { label: "买卖价差", value: `${marketPrice(currentSpread)} USDT`, note: Number.isFinite(currentSpreadBps) ? `${currentSpreadBps.toFixed(2)} bps` : undefined },
          { label: "通道上沿 / 下沿", value: `${marketPrice(currentMarket.channel_upper)} / ${marketPrice(currentMarket.channel_lower)} USDT`, note: `${direction === "LONG" ? "做多观察上沿" : "做空观察下沿"}；另一侧用于判断机会是否已经迁移` },
          ...(entryExtensionLimit !== null ? [{ label: "最大追价边界", value: `${marketPrice(String(entryExtensionLimit))} USDT`, note: `通道边界 ± ${maxEntryExtensionAtr} ATR（ATR ${marketPrice(currentMarket.atr_14)} USDT）` }] : []),
          { label: "1m 收盘距上沿 / 下沿", value: `${gapPercent(longClosedBarBreakoutGap)} / ${gapPercent(shortClosedBarBreakoutGap)}`, note: "策略触发口径；正值表示尚未突破，负值表示已越过" },
          { label: "盘口中间价距上沿 / 下沿", value: `${gapPercent(currentMarket.long_breakout_gap_pct)} / ${gapPercent(currentMarket.short_breakout_gap_pct)}`, note: "仅反映当前市场位置，不用于触发或替代执行前价格检查" },
          { label: "确认条件", value: demoImmediateEntry ? "1 × 1m 收盘（流程验证）" : `${valueOf(parameters, "confirmation_bars_1m")} × 1m 收盘` },
          { label: "1m 收盘时间", value: formatUserVisibleTime(currentMarket.latest_closed_1m_at) },
          { label: "行情截止", value: formatUserVisibleTime(currentMarket.source_cutoff) },
        ]} />}
      </Box>}

      <Box component="section" sx={{ mt: 5 }}>
        <Typography variant="overline" color="text.secondary">主要证据 · 系统机制</Typography>
        <Typography variant="h2" sx={{ mt: .75, mb: 1 }}>系统流程与机制</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>同一计划、资金检查、执行动作、交易所事实和复盘结果使用一致身份。系统首先验证持久动作、防重复、保护、核对、停止、恢复、接管和环境隔离。</Typography>
        <FactGrid facts={[
          { label: "策略检查", value: `${Object.keys(ruleState).length} 条规则状态 · v${valueOf(activation, "state_version")}` },
          { label: "交易金额", value: `${valueOf(capital, "max_notional")} USDT` },
          { label: "损失风控计数", value: `${valueOf(capital, "activation_loss")} / ${valueOf(capital, "max_allowed_loss")} USDT`, note: "用于停止新增风险，不等于当前盈亏" },
          { label: "已归属手续费", value: `${valueOf(tradeResult, "commission", "0")} USDT`, note: tradeResult.commission_complete === true ? "当前成交手续费已齐全" : fillCount > 0 ? "仍有成交手续费待核对" : "尚无成交" },
          { label: "执行动作", value: String(actions.length), note: actions.some((item) => valueOf(item, "state") === "UNKNOWN") ? "存在结果未决，只查询原 UUID" : "按持久身份展示" },
          { label: "交易所事实", value: String(facts.length), note: "订单状态不能推定持仓" },
          { label: "控制回执", value: String(receipts.length), note: receipts.some((item) => valueOf(item, "state") === "PROCESSING") ? "仍有命令效果待确认" : "没有处理中回执" },
          { label: "停止范围", value: stopScopeDisplay },
        ]} />
      </Box>

      <Box component="section" sx={{ mt: 4 }}>
        <Typography variant="overline" color="text.secondary">次要证据 · 策略行为</Typography>
        <Typography variant="h2" sx={{ mt: .75, mb: 1 }}>策略行为只作次要验证</Typography>
        <Alert severity="warning" variant="outlined" icon={false}>
          当前环境或历史结果不能证明其他环境中的流动性、排队、冲击、滑点、费用、资金费率、延迟、权限、可用性或真实收益能力；绿色状态也不能消除这些差异。
        </Alert>
      </Box>

      <Box component="section" sx={{ mt: 4 }}>
        <Typography variant="h2" sx={{ mb: 2 }}>动作、部分成交与保护责任</Typography>
        <ExpandableList
          items={actions}
          initialCount={6}
          step={6}
          spacing={1}
          renderItem={(action) => {
            const actionId = valueOf(action, "execution_action_id");
            const actionFacts = facts.filter((fact) => valueOf(fact, "action_ref", "") === actionId);
            const actionTerms = recordOf(action.action_terms);
            const actionQuantity = valueOf(actionTerms, "quantity", "");
            const actionPrice = valueOf(actionTerms, "trigger_price", valueOf(actionTerms, "price", ""));
            const actionKind = valueOf(action, "action_kind");
            const clientOrderId = valueOf(action, "client_order_id", "");
            const cancelTargetId = valueOf(recordOf(action.cancel_target), "client_order_id", "");
            const orderIdentity = clientOrderId || (actionKind === "CANCEL" && cancelTargetId ? `目标 ${cancelTargetId}` : "未提供订单身份");
            return (
              <Box key={actionId} sx={{ ...surfaceFrameSx, p: 2, borderColor: valueOf(action, "state") === "UNKNOWN" ? "warning.main" : "divider" }}>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
                  <Typography sx={{ fontWeight: 750 }}>{translatedLabel(actionKindLabels, actionKind)} · {translatedLabel(actionStateLabels, valueOf(action, "state"))}</Typography>
                </Stack>
                <Typography className="mono" variant="caption" color="text.secondary">{orderIdentity} · 更新于 {formatUserVisibleTime(valueOf(action, "updated_at"))}</Typography>
                {(actionQuantity || actionPrice) && <Typography variant="body2" sx={{ mt: 1 }}>
                  委托条款{actionQuantity ? ` · 数量 ${actionQuantity}` : ""}{actionPrice ? ` · ${valueOf(actionTerms, "trigger_price", "") ? "触发价" : "价格"} ${marketPrice(actionPrice)} USDT` : ""}{actionTerms.reduce_only === true ? " · 只减仓" : ""}
                </Typography>}
                {valueOf(action, "unknown_reason", "") && <Typography role="alert" variant="body2" color="warning.dark" sx={{ mt: 1 }}>结果未决 · {valueOf(action, "unknown_reason")}；系统只查询原订单 UUID，不会另建订单。</Typography>}
                {valueOf(action, "state") === "NOT_SUBMITTED" && <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{notSubmittedReasonText(valueOf(action, "not_submitted_reason", ""))}</Typography>}
                <ExpandableList
                  items={actionFacts}
                  initialCount={4}
                  step={4}
                  spacing={0}
                  renderItem={(fact) => {
                    const payload = recordOf(fact.payload);
                    const reason = venueReasonText(valueOf(payload, "reason", ""));
                    return (
                      <Box key={valueOf(fact, "venue_fact_id")} sx={{ mt: 1.25, pt: 1.25, borderTop: 1, borderColor: "divider" }}>
                        <Typography variant="body2">交易所事实 · {venueFactSummary(fact)}</Typography>
                        {reason && <Typography variant="caption" color="text.secondary" sx={{ display: "block", overflowWrap: "anywhere" }}>{reason}</Typography>}
                      </Box>
                    );
                  }}
                />
              </Box>
            );
          }}
        />
        {actions.length === 0 && <Alert severity="info" variant="outlined">尚无持久执行动作；这不表示条件未触发或交易所已经安全。</Alert>}
      </Box>

      <Box sx={{ mt: 4 }}><Typography variant="h2" sx={{ mb: 1 }}>稳定控制命令</Typography><Typography color="text.secondary" sx={{ mb: 2 }}>先查看当前后果预览，再明确确认提交。重复幂等键返回原回执；页面不会把处理中的回执显示成已闭合。</Typography><Stack direction={{ xs: "column", md: "row" }} spacing={1}>{controls.map((control) => <Button key={control.intent} variant="outlined" color={control.color} disabled={!activation || preview.isPending || terminal} onClick={() => preview.mutate(control.intent)}>{control.label}</Button>)}</Stack>{terminal && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>接管或闭合后不再提供机器自动恢复或其他控制。</Typography>}</Box>
      {intent && preview.data && <Box sx={{ ...surfaceFrameSx, mt: 3, p: 3, borderColor: intent === "EXIT_STRATEGY" || intent === "USER_TAKEOVER" ? "error.main" : "divider" }}><Typography variant="overline">{selectedControlLabel}</Typography><Typography sx={{ mt: 1, mb: 2 }}>{valueOf(preview.data, "consequence")}</Typography>{intent === "RESUME_ACTIVATION" && !resumeEligible && <Alert severity="warning" sx={{ mb: 2 }}>当前没有由唯一 Executor/EXE 核对链产生的可信恢复证据；系统拒绝恢复，不能用手工摘要替代。</Alert>}<Stack direction="row" spacing={1}><Button variant="contained" color={intent === "EXIT_STRATEGY" || intent === "USER_TAKEOVER" ? "error" : "primary"} disabled={submit.isPending || !resumeEligible} onClick={() => submit.mutate(intent)}>确认{selectedControlLabel}</Button><Button onClick={() => { setIntent(null); setIdempotencyKey(null); }}>取消</Button></Stack></Box>}
      {submit.isSuccess && submittedReceiptState === "PROCESSING" && <Alert severity="info" sx={{ mt: 2 }}>命令已接受，正在核对执行与闭合责任；请勿重复提交。</Alert>}
      {submit.isSuccess && submittedReceiptState === "EFFECTIVE" && <Alert severity="success" sx={{ mt: 2 }}>命令已生效，当前执行责任已经核对。</Alert>}
      {submit.isSuccess && !["PROCESSING", "EFFECTIVE", "REJECTED"].includes(submittedReceiptState) && <Alert severity="success" sx={{ mt: 2 }}>命令已持久化并返回“{submittedReceiptState || "UNKNOWN"}”回执；请按状态继续核对。</Alert>}
      {submit.isSuccess && submittedReceiptState === "REJECTED" && <Alert severity="error" sx={{ mt: 2 }}>命令被拒绝：{valueOf(currentSubmittedReceipt, "reason_code")}。页面未把已持久化的拒绝回执显示为成功效果。</Alert>}
      {submit.isError && <Alert severity="error" sx={{ mt: 2 }}>命令未确认：{submit.error instanceof ApiFailure ? submit.error.code : "结果未知"}</Alert>}

      <Box component="section" sx={{ mt: 4 }}>
        <Typography variant="h2" sx={{ mb: 2 }}>唯一权威时间线</Typography>
        <ExpandableList
          items={timelineQuery.data ?? []}
          initialCount={10}
          step={10}
          spacing={1}
          renderItem={(item) => {
            const detail = recordOf(item.detail);
            const source = valueOf(item, "source");
            const status = valueOf(item, "status");
            const ruleId = valueOf(detail, "rule_id", "");
            const summary = source === "PLAN_EVENT"
              ? planEventSummary(status, ruleId)
              : translatedLabel(actionStateLabels, status);
            return (
              <Box key={`${valueOf(item, "source")}:${valueOf(item, "source_ref")}`} sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "150px 160px minmax(0,1fr)" }, gap: 1, p: 1.5, borderTop: 1, borderColor: "divider" }}>
                <Typography variant="caption" color="text.secondary">{formatUserVisibleTime(valueOf(item, "at"))}</Typography>
                <Typography variant="caption" sx={{ fontWeight: 750 }}>{translatedLabel(timelineSourceLabels, source)}</Typography>
                <Box><Typography variant="body2">{summary}</Typography><Typography className="mono" variant="caption" color="text.secondary">{shortDigest(valueOf(item, "source_ref"))} · {translatedLabel(actionKindLabels, valueOf(detail, "action_kind", ruleId || valueOf(detail, "source_class", "")))}</Typography></Box>
              </Box>
            );
          }}
        />
        {timelineQuery.data?.length === 0 && <Alert severity="info" variant="outlined">当前尚无计划事件、执行动作或交易所事实。页面不会推测不存在责任。</Alert>}
      </Box>
    </Box>
  );
}

function ReviewsPage() {
  const navigate = useNavigate();
  const { marketColorScheme } = useOutletContext<FrameContext>();
  const [filter, setFilter] = useState<"TRADED" | "DRAFT" | "ALL">("TRADED");
  const [listFilters, setListFilters] = useState<ReviewListFilters>(emptyReviewListFilters);
  const [visibleCount, setVisibleCount] = useState(20);
  const query = useQuery({ queryKey: ["reviews"], queryFn: getReviews, refetchInterval: 30_000 });
  const strategiesQuery = useQuery({ queryKey: ["strategies"], queryFn: getStrategies });
  const reviews = [...(query.data ?? [])].sort((left, right) => {
    const rightCutoff = Date.parse(valueOf(right, "fact_cutoff", ""));
    const leftCutoff = Date.parse(valueOf(left, "fact_cutoff", ""));
    return (Number.isFinite(rightCutoff) ? rightCutoff : 0) - (Number.isFinite(leftCutoff) ? leftCutoff : 0);
  });
  const tradedReviews = reviews.filter((review) => ["COMPLETED", "PARTIAL"].includes(valueOf(review, "primary_result")));
  const scopeReviews = filter === "DRAFT"
    ? reviews.filter((review) => valueOf(review, "status") === "DRAFT")
    : filter === "TRADED"
      ? tradedReviews
      : reviews;
  const visibleReviews = scopeReviews.filter((review) => reviewMatchesFilters(review, listFilters));
  const strategyOptions = [...new Set(reviews.map((review) => valueOf(recordOf(review.trade_context), "strategy_id", "")).filter(Boolean))].sort();
  const instrumentOptions = [...new Set(reviews.map((review) => valueOf(recordOf(review.trade_context), "instrument_ref", "")).filter(Boolean))].sort();
  const activeFilterCount = Object.values(listFilters).filter((value) => value !== "ALL").length;
  const reliableTrades = tradedReviews.filter((review) => {
    const result = tradeResultForReview(review);
    return result.calculation_complete === true && result.closed === true && finiteNumber(result.net_pnl) !== null;
  });
  const netPnl = reliableTrades.reduce((sum, review) => sum + (finiteNumber(tradeResultForReview(review).net_pnl) ?? 0), 0);
  const commissions = reliableTrades.reduce((sum, review) => sum + (finiteNumber(tradeResultForReview(review).commission) ?? 0), 0);
  const wins = reliableTrades.filter((review) => (finiteNumber(tradeResultForReview(review).net_pnl) ?? 0) > 0).length;
  const holdingDurations = reliableTrades.flatMap((review) => {
    const duration = finiteNumber(tradeResultForReview(review).holding_duration_seconds);
    return duration === null ? [] : [duration];
  });
  const averageHolding = holdingDurations.length > 0
    ? holdingDurations.reduce((sum, value) => sum + value, 0) / holdingDurations.length
    : Number.NaN;
  let cumulative = 0;
  const trendPoints = [...reliableTrades].reverse().map((review) => {
    const result = tradeResultForReview(review);
    cumulative += finiteNumber(result.net_pnl) ?? 0;
    return { at: valueOf(result, "last_fill_time", valueOf(review, "fact_cutoff")), value: cumulative };
  });
  useEffect(() => { setVisibleCount(20); }, [filter, listFilters]);
  const updateListFilter = <Key extends keyof ReviewListFilters>(key: Key, value: ReviewListFilters[Key]) => {
    setListFilters((current) => ({ ...current, [key]: value }));
  };
  const shownReviews = visibleReviews.slice(0, visibleCount);
  const remaining = Math.max(0, visibleReviews.length - visibleCount);
  return (
    <Box sx={{ width: "min(1320px, calc(100% - clamp(24px, 4vw, 48px)))", mx: "auto", py: { xs: 2, sm: 2.5 } }}>
      <Typography component="h1" sx={visuallyHiddenSx}>激活复盘</Typography>
      {query.isPending && <LinearProgress aria-label="正在读取复盘列表" />}
      {query.isError && <Alert severity="error">复盘事实不可用；页面未生成替代结果。</Alert>}
      <Box sx={{ ...surfaceFrameSx, p: { xs: 1.5, sm: 2 }, mb: 2 }}>
        <Stack direction={{ xs: "column", lg: "row" }} spacing={2.5} sx={{ alignItems: { lg: "stretch" } }}>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, minmax(0,1fr))", sm: "repeat(5, minmax(110px,1fr))" }, flex: 1, gap: 1 }}>
            {[
              { label: "完整闭合", value: `${reliableTrades.length} 笔` },
              { label: "累计净盈亏", value: signedUsdt(netPnl), tone: marketToneForSignedValue(netPnl) },
              { label: "胜率", value: reliableTrades.length ? percent(wins / reliableTrades.length * 100) : "未知" },
              { label: "手续费", value: usdt(commissions) },
              { label: "平均持仓", value: durationText(averageHolding) },
            ].map((item) => (
              <Box key={item.label} sx={{ px: 1.25, py: 1 }}>
                <Typography variant="caption" color="text.secondary">{item.label}</Typography>
                <Typography className="mono" sx={{ mt: 0.25, fontWeight: 750 }}><MarketToneText tone={item.tone}>{item.value}</MarketToneText></Typography>
              </Box>
            ))}
          </Box>
          {trendPoints.length >= 2 && <Box sx={{ width: { lg: 360 }, minWidth: 0 }}><Suspense fallback={<LinearProgress aria-label="正在加载盈亏趋势图" />}><CumulativePnlChart points={trendPoints} marketColorScheme={marketColorScheme} /></Suspense></Box>}
        </Stack>
        {trendPoints.length >= 2 && <TradingViewAttribution />}
      </Box>

      <Tabs value={filter} onChange={(_event, value: typeof filter) => setFilter(value)} aria-label="复盘筛选" variant="scrollable" scrollButtons="auto" allowScrollButtonsMobile sx={{ mb: 1.5 }}>
        <Tab value="TRADED" label={`交易记录（${tradedReviews.length}）`} />
        <Tab value="DRAFT" label={`待评价（${reviews.filter((review) => valueOf(review, "status") === "DRAFT").length}）`} />
        <Tab value="ALL" label={`全部激活（${reviews.length}）`} />
      </Tabs>

      <Box component="section" aria-label="交易记录联合筛选" sx={{ ...surfaceFrameSx, p: 1.25, mb: 1.5 }}>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "repeat(2, minmax(0, 1fr))", md: "repeat(3, minmax(150px, 1fr))", lg: "repeat(6, minmax(130px, 1fr))" }, gap: 1 }}>
          <TextField select size="small" label="策略" value={listFilters.strategyId} onChange={(event) => updateListFilter("strategyId", event.target.value)}>
            <MenuItem value="ALL">全部策略</MenuItem>
            {strategyOptions.map((strategyId) => {
              const strategy = strategiesQuery.data?.find((item) => item.strategy_id === strategyId);
              return <MenuItem key={strategyId} value={strategyId}>{strategy?.display_name ?? strategyId}</MenuItem>;
            })}
          </TextField>
          <TextField select size="small" label="交易对象" value={listFilters.instrumentRef} onChange={(event) => updateListFilter("instrumentRef", event.target.value)}>
            <MenuItem value="ALL">全部交易对象</MenuItem>
            {instrumentOptions.map((instrumentRef) => <MenuItem key={instrumentRef} value={instrumentRef}>{instrumentRef}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="方向" value={listFilters.direction} onChange={(event) => updateListFilter("direction", event.target.value)}>
            <MenuItem value="ALL">全部方向</MenuItem>
            {Object.entries(directionLabels).map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="盈亏" value={listFilters.pnl} onChange={(event) => updateListFilter("pnl", event.target.value as ReviewPnlFilter)}>
            {(Object.entries(pnlFilterLabels) as Array<[ReviewPnlFilter, string]>).map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="交易结果" value={listFilters.primaryResult} onChange={(event) => updateListFilter("primaryResult", event.target.value)}>
            <MenuItem value="ALL">全部结果</MenuItem>
            {Object.entries(reviewResultLabels).map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="人工结论" value={listFilters.ownerConclusion} onChange={(event) => updateListFilter("ownerConclusion", event.target.value)}>
            <MenuItem value="ALL">全部结论</MenuItem>
            {Object.entries(evaluationResultLabels).map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
          </TextField>
        </Box>
        <Stack direction="row" spacing={1.5} sx={{ mt: 1, alignItems: "center", justifyContent: "space-between" }}>
          <Typography variant="caption" color="text.secondary">
            条件同时满足 · 匹配 {visibleReviews.length} / {scopeReviews.length} 条{activeFilterCount > 0 ? ` · 已选 ${activeFilterCount} 项` : ""}
          </Typography>
          <Button size="small" variant="text" disabled={activeFilterCount === 0} onClick={() => setListFilters(emptyReviewListFilters)}>重置筛选</Button>
        </Stack>
      </Box>

      <TableContainer className="table-scroll" role="region" aria-label="交易与复盘记录横向滚动区域" tabIndex={0} sx={{ ...surfaceFrameSx, overflowX: "auto" }}>
        <Table size="small" aria-label="交易与复盘记录" sx={{ minWidth: 1120, "& th": { whiteSpace: "nowrap" }, "& td": { verticalAlign: "top" } }}>
          <TableHead>
            <TableRow>
              <TableCell>闭合时间</TableCell>
              <TableCell>交易</TableCell>
              <TableCell>计划 / 策略</TableCell>
              <TableCell align="right">入场 / 出场</TableCell>
              <TableCell align="right">成交额</TableCell>
              <TableCell align="right">净盈亏</TableCell>
              <TableCell align="right">手续费</TableCell>
              <TableCell>持仓 / 退出</TableCell>
              <TableCell>结果</TableCell>
              <TableCell>人工结论</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {shownReviews.map((review) => {
              const result = tradeResultForReview(review);
              const context = recordOf(review.trade_context);
              const ownerConclusion = recordOf(recordOf(review.evaluations).owner_conclusion);
              const strategyId = valueOf(context, "strategy_id");
              const strategy = strategiesQuery.data?.find((item) => item.strategy_id === strategyId);
              const planName = valueOf(context, "plan_name", "");
              const resultAvailable = result.calculation_complete === true && result.closed === true && finiteNumber(result.net_pnl) !== null;
              const externalAccountResult = result.result_scope === "ACCOUNT_FACTS_WITH_EXTERNAL_CLOSURE";
              const reviewId = valueOf(review, "review_id");
              const closedAt = formatUserVisibleTime(valueOf(result, "last_fill_time", valueOf(review, "fact_cutoff")));
              const openReview = () => navigate(`/reviews/${reviewId}`);
              return (
                <TableRow
                  key={reviewId}
                  hover
                  tabIndex={0}
                  aria-label={`查看 ${valueOf(context, "instrument_ref")} ${translatedLabel(directionLabels, valueOf(context, "direction"))} ${closedAt} 复盘`}
                  onClick={openReview}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      openReview();
                    }
                  }}
                  sx={{ cursor: "pointer" }}
                >
                  <TableCell className="mono">
                    {closedAt}
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: 700 }}>{valueOf(context, "instrument_ref")}</Typography>
                    <MarketToneText tone={marketToneForDirection(valueOf(context, "direction"))}>{translatedLabel(directionLabels, valueOf(context, "direction"))}</MarketToneText>
                  </TableCell>
                  <TableCell>
                    <Typography variant="body2" sx={{ fontWeight: planName ? 700 : 400 }}>{planName || strategy?.display_name || strategyId}</Typography>
                    {planName && <Typography variant="caption" color="text.secondary">{strategy?.display_name ?? strategyId}</Typography>}
                  </TableCell>
                  <TableCell className="mono" align="right">{marketPrice(valueOf(result, "average_entry_price"))} / {marketPrice(valueOf(result, "average_exit_price"))}</TableCell>
                  <TableCell className="mono" align="right">{finiteNumber(result.entry_notional) === null ? "未知" : usdt(result.entry_notional)}</TableCell>
                  <TableCell className="mono" align="right">
                    {resultAvailable ? <MarketToneText tone={marketToneForSignedValue(result.net_pnl)}>{signedUsdt(result.net_pnl)}</MarketToneText> : "未知"}
                    {externalAccountResult && <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>账户结果</Typography>}
                  </TableCell>
                  <TableCell className="mono" align="right">{resultAvailable ? usdt(result.commission) : "未知"}</TableCell>
                  <TableCell>{durationText(result.holding_duration_seconds)}<Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{exitReason(result)}</Typography></TableCell>
                  <TableCell>{translatedLabel(reviewResultLabels, valueOf(review, "primary_result"))}</TableCell>
                  <TableCell sx={{ minWidth: 160, maxWidth: 200, verticalAlign: "top" }}>
                    {translatedLabel(evaluationResultLabels, reviewConclusion(review))}
                    <ClampedTooltipText text={valueOf(ownerConclusion, "reason", translatedLabel(reviewStatusLabels, valueOf(review, "status")))} />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </TableContainer>
      {remaining > 0 && <Button variant="text" sx={{ mt: 1.5 }} onClick={() => setVisibleCount((count) => count + 20)}>显示更多（剩余 {remaining} 条）</Button>}
      {visibleReviews.length === 0 && <Alert severity="info" variant="outlined">当前筛选下没有复盘记录。</Alert>}
    </Box>
  );
}

function ReviewRoute() {
  const { reviewId = "" } = useParams();
  const navigate = useNavigate();
  const { marketColorScheme } = useOutletContext<FrameContext>();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["review", reviewId], queryFn: () => getReview(reviewId), enabled: Boolean(reviewId), refetchInterval: 30_000 });
  const review = recordOf(query.data?.review);
  const activationId = valueOf(review, "activation_id", "");
  const activationQuery = useQuery({
    queryKey: ["activation", activationId],
    queryFn: () => getActivation(activationId),
    enabled: Boolean(activationId),
    refetchInterval: 30_000,
  });
  const timelineQuery = useQuery({
    queryKey: ["activation-timeline", activationId],
    queryFn: () => getActivationTimeline(activationId),
    enabled: Boolean(activationId),
  });
  const strategiesQuery = useQuery({ queryKey: ["strategies"], queryFn: getStrategies });
  const [conclusion, setConclusion] = useState("UNKNOWN");
  const [reviewNote, setReviewNote] = useState("");
  const [chartInterval, setChartInterval] = useState<"1m" | "15m">("1m");

  useEffect(() => {
    const ownerConclusion = recordOf(recordOf(review.evaluations).owner_conclusion);
    setConclusion(valueOf(ownerConclusion, "result", "UNKNOWN"));
    setReviewNote(valueOf(ownerConclusion, "reason", ""));
  }, [review.content_digest]);

  const refreshMutation = useMutation({
    mutationFn: () => refreshReview(reviewId, Number(review.review_version ?? 0)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["review", reviewId] });
      await queryClient.invalidateQueries({ queryKey: ["reviews"] });
    },
  });
  const completionMutation = useMutation({
    mutationFn: () => {
      const payload: ReviewCompletionPayload = {
        expected_version: Number(review.review_version ?? 0),
        conclusion: conclusion as ReviewCompletionPayload["conclusion"],
        note: reviewNote,
      };
      return completeReview(reviewId, payload);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["review", reviewId] });
      await queryClient.invalidateQueries({ queryKey: ["reviews"] });
    },
  });

  const inputRefs = recordOf(review.input_refs);
  const reviewTradeResult = tradeResultForReview(review);
  const tradeContext = recordOf(review.trade_context);
  const reviewPlan = recordOf(activationQuery.data?.plan);
  const planName = valueOf(tradeContext, "plan_name", valueOf(reviewPlan, "plan_name", ""));
  const strategyRef = valueOf(recordOf(activationQuery.data?.strategy), "strategy_ref", valueOf(tradeContext, "strategy_id"));
  const strategyId = strategyRef.split("@", 1)[0];
  const strategy = strategiesQuery.data?.find((item) => item.strategy_id === strategyId);
  const fills = recordsOf(reviewTradeResult.fills);
  const planEvents = (timelineQuery.data ?? []).filter((item) => valueOf(item, "source") === "PLAN_EVENT");
  const triggerEvent = planEvents.find((item) => {
    const detail = recordOf(item.detail);
    return valueOf(detail, "rule_id") === "ENTRY_BREAKOUT"
      && ["PROPOSED_ACTION_CAP_ACCEPTED", "DEMO_ORDER_FLOW_CHECK"].includes(valueOf(item, "status"));
  }) ?? planEvents.find((item) => valueOf(item, "status") === "PROPOSAL_CREATED");
  const triggerDetail = recordOf(triggerEvent?.detail);
  const reviewPrimaryResult = valueOf(review, "primary_result");
  const openResponsibilities = recordOf(review.open_responsibilities);
  const unknownActionRefs = Array.isArray(openResponsibilities.unknown_action_refs) ? openResponsibilities.unknown_action_refs : [];
  const openActionRefs = Array.isArray(openResponsibilities.execution_action_refs) ? openResponsibilities.execution_action_refs : [];
  const actions = recordsOf(activationQuery.data?.execution_actions);
  const firstFillAt = valueOf(reviewTradeResult, "first_fill_time", "");
  const lastFillAt = valueOf(reviewTradeResult, "last_fill_time", "");
  const activation = recordOf(activationQuery.data?.activation);
  const fallbackAt = valueOf(review, "fact_cutoff", valueOf(activation, "updated_at", ""));
  const baseStartMs = Date.parse(firstFillAt || fallbackAt);
  const baseEndMs = Date.parse(lastFillAt || fallbackAt);
  const intervalMs = chartInterval === "1m" ? 60_000 : 15 * 60_000;
  const paddingBars = chartInterval === "1m" ? 24 : 12;
  const latestCompleteBarOpenMs = Math.floor(Date.now() / intervalMs) * intervalMs - intervalMs;
  const chartStart = Number.isFinite(baseStartMs) ? new Date(baseStartMs - intervalMs * paddingBars).toISOString() : "";
  const chartEnd = Number.isFinite(baseEndMs)
    ? new Date(Math.min(baseEndMs + intervalMs * paddingBars, latestCompleteBarOpenMs)).toISOString()
    : "";
  const marketWindowQuery = useQuery({
    queryKey: ["review-market-window", valueOf(tradeContext, "instrument_ref", ""), chartInterval, chartStart, chartEnd],
    queryFn: () => getMarketWindow(valueOf(tradeContext, "instrument_ref"), chartStart, chartEnd, chartInterval),
    enabled: Boolean(valueOf(tradeContext, "instrument_ref", "") && chartStart && chartEnd),
    staleTime: 10 * 60_000,
  });
  const instrumentRef = valueOf(tradeContext, "instrument_ref");
  const direction = valueOf(tradeContext, "direction");
  const reviewClosed = reviewTradeResult.calculation_complete === true && reviewTradeResult.closed === true;
  const externalAccountResult = reviewTradeResult.result_scope === "ACCOUNT_FACTS_WITH_EXTERNAL_CLOSURE";
  const tradeExpected = reviewPrimaryResult !== "NO_ACTION";
  const hasAttributedFills = fills.length > 0;
  const ownerConclusion = recordOf(recordOf(review.evaluations).owner_conclusion);
  const status = valueOf(review, "status");
  const marketBars = marketWindowQuery.data?.bars ? Array.from(marketWindowQuery.data.bars) : [];

  return (
    <Box sx={{ width: "min(1320px, calc(100% - clamp(24px, 4vw, 48px)))", mx: "auto", py: { xs: 2, sm: 2.5 } }}>
      <Typography component="h1" sx={visuallyHiddenSx}>一次激活复盘</Typography>
      {query.isPending && <LinearProgress aria-label="正在读取复盘详情" />}
      {query.isError && <Alert severity="error">复盘身份或输入当前不可读；不会自动创建替代版本。</Alert>}
      {Object.keys(review).length > 0 && <>
        <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { md: "flex-end" }, mb: 2 }}>
          <Box>
            <Button variant="text" size="small" onClick={() => navigate("/reviews")} sx={{ px: 0, minWidth: 0, mb: 0.5 }}>← 交易记录</Button>
            {planName && <Typography variant="h1" sx={{ mb: .25 }}>{planName}</Typography>}
            <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", flexWrap: "wrap" }}>
              <Typography variant={planName ? "h2" : "h1"}>{instrumentRef}</Typography>
              <Typography sx={{ fontWeight: 750 }}><MarketToneText tone={marketToneForDirection(direction)}>{translatedLabel(directionLabels, direction)}</MarketToneText></Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary">{strategy?.display_name ?? strategyRef} · 闭合于 {formatUserVisibleTime(valueOf(reviewTradeResult, "last_fill_time", valueOf(review, "fact_cutoff")))}</Typography>
          </Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
            <Chip size="small" label={translatedLabel(reviewResultLabels, reviewPrimaryResult)} />
            <Chip size="small" variant="outlined" label={translatedLabel(reviewStatusLabels, status)} />
          </Stack>
        </Stack>

        <Box component="section" sx={{ ...surfaceFrameSx, p: { xs: 1.5, md: 2 }, mb: 2 }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" }, mb: 1 }}>
            <Box>
              <Typography variant="h2">交易价格回看</Typography>
              <Typography variant="caption" color="text.secondary">成交与盈亏只由该复盘明确引用的交易所成交和手续费事实还原；引用缺失或冲突时保持未知。止损和止盈线来自当前激活记录。</Typography>
            </Box>
            <ToggleButtonGroup
              exclusive
              size="small"
              value={chartInterval}
              onChange={(_event, value: "1m" | "15m" | null) => { if (value) setChartInterval(value); }}
              aria-label="K 线周期"
            >
              <ToggleButton value="1m">1 分钟</ToggleButton>
              <ToggleButton value="15m">15 分钟</ToggleButton>
            </ToggleButtonGroup>
          </Stack>
          {marketWindowQuery.isPending && <LinearProgress aria-label="正在读取复盘行情" />}
          {marketWindowQuery.isError && <Alert severity="warning" variant="outlined" sx={{ my: 1 }}>公开行情回看暂时不可用；成交、费用和复盘事实仍可核对。</Alert>}
          {marketBars.length > 0 && <Suspense fallback={<LinearProgress aria-label="正在加载 K 线图" />}><ReviewPriceChart bars={marketBars} fills={fills} actions={actions} interval={chartInterval} direction={direction} marketColorScheme={marketColorScheme} /></Suspense>}
          {!marketWindowQuery.isPending && !marketWindowQuery.isError && marketBars.length === 0 && <Alert severity="info" variant="outlined">当前时间窗没有可展示的 K 线。</Alert>}
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
            {marketWindowQuery.data ? `公开行情 · 截止 ${formatUserVisibleTime(marketWindowQuery.data.source_cutoff)}` : "公开行情仅提供事后价格上下文"}；图表不替代持久成交事实，也不证明当时可按图示价格成交。
          </Typography>
          <TradingViewAttribution />
        </Box>

        {externalAccountResult && <Alert severity="warning" variant="outlined" sx={{ mb: 2 }}>
          出场由明确选定的 Binance 只减仓应急订单完成。以下盈亏是交易所成交与手续费形成的账户结果，不记作 Halpha 策略退出。
        </Alert>}
        <FactGrid facts={[
          { label: externalAccountResult ? "账户净盈亏" : "净盈亏", value: tradeExpected && reviewClosed ? signedUsdt(reviewTradeResult.net_pnl) : tradeExpected ? "未知" : "不适用", tone: tradeExpected && reviewClosed ? marketToneForSignedValue(reviewTradeResult.net_pnl) : undefined },
          { label: externalAccountResult ? "账户毛盈亏" : "毛盈亏", value: tradeExpected && reviewClosed ? signedUsdt(reviewTradeResult.gross_pnl) : tradeExpected ? "未知" : "不适用", tone: tradeExpected && reviewClosed ? marketToneForSignedValue(reviewTradeResult.gross_pnl) : undefined },
          { label: "手续费", value: tradeExpected && hasAttributedFills ? usdt(reviewTradeResult.commission) : tradeExpected ? "未知" : "不适用", note: "净盈亏不含资金费" },
          { label: "持仓周期", value: tradeExpected ? durationText(reviewTradeResult.holding_duration_seconds) : "不适用" },
          { label: "平均入场价", value: tradeExpected && hasAttributedFills ? `${marketPrice(valueOf(reviewTradeResult, "average_entry_price"))} USDT` : tradeExpected ? "未知" : "不适用" },
          { label: "平均出场价", value: tradeExpected && hasAttributedFills ? `${marketPrice(valueOf(reviewTradeResult, "average_exit_price"))} USDT` : tradeExpected ? "未知" : "不适用" },
          { label: "入场成交额", value: tradeExpected && hasAttributedFills ? usdt(reviewTradeResult.entry_notional) : tradeExpected ? "未知" : "不适用" },
          { label: "退出原因", value: tradeExpected ? exitReason(reviewTradeResult) : "未发生交易" },
        ]} />

        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "minmax(0,1fr) minmax(360px,.8fr)" }, gap: 2, mt: 2 }}>
          <Box component="section" sx={{ ...surfaceFrameSx, p: 2 }}>
            <Typography variant="h2" sx={{ mb: 1.5 }}>机器为何交易</Typography>
            <FactGrid facts={[
              { label: "操作理由", value: triggerEvent ? planEventSummary(valueOf(triggerEvent, "status"), valueOf(triggerDetail, "rule_id", "")) : reviewPrimaryResult === "NO_ACTION" ? "未发生交易" : "未知" },
              { label: "触发来源", value: triggerEvent ? valueOf(triggerDetail, "source_identity") : reviewPrimaryResult === "NO_ACTION" ? "不适用" : "未知", note: triggerEvent ? `${formatUserVisibleTime(valueOf(triggerDetail, "source_cutoff"))} · ${shortDigest(valueOf(triggerEvent, "source_ref"))}` : reviewPrimaryResult === "NO_ACTION" ? "没有入场触发事件" : "没有可归属的入场触发事件" },
              { label: "首次成交", value: tradeExpected && hasAttributedFills ? formatUserVisibleTime(valueOf(reviewTradeResult, "first_fill_time")) : tradeExpected ? "未知" : "不适用" },
              { label: "末次成交", value: tradeExpected && hasAttributedFills ? formatUserVisibleTime(valueOf(reviewTradeResult, "last_fill_time")) : tradeExpected ? "未知" : "不适用" },
            ]} />
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>触发说明取自同一激活的时间线；成交结果仅使用该复盘明确引用的权威事实，缺失不补猜。</Typography>
          </Box>

          <Box component="section" sx={{ ...surfaceFrameSx, p: 2 }}>
            <Stack direction="row" spacing={1} sx={{ justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
              <Box><Typography variant="h2">我的结论</Typography><Typography variant="caption" color="text.secondary">记录会改变下一次判断的内容。</Typography></Box>
              <Button variant="text" size="small" disabled={refreshMutation.isPending || !review.review_version} onClick={() => refreshMutation.mutate()}>刷新事实</Button>
            </Stack>
            {refreshMutation.isError && <Alert severity="error" sx={{ mb: 1.5 }}>刷新失败；旧版本保持不变。</Alert>}
            <Stack spacing={1.5}>
              <TextField select size="small" label="结论" value={conclusion} onChange={(event) => setConclusion(event.target.value)} disabled={status !== "DRAFT"}>
                {["AS_EXPECTED", "ISSUE_FOUND", "UNKNOWN", "NOT_APPLICABLE"].map((value) => <MenuItem key={value} value={value}>{evaluationResultLabels[value]}</MenuItem>)}
              </TextField>
              <TextField size="small" label="可选备注" value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} disabled={status !== "DRAFT"} multiline minRows={3} slotProps={{ htmlInput: { maxLength: 2000 } }} />
            </Stack>
            {status === "DRAFT" && <>
              {completionMutation.isError && <Alert severity="error" sx={{ mt: 1.5 }}>评价未完成：{completionMutation.error instanceof ApiFailure ? completionMutation.error.code : "结果未知"}</Alert>}
              <Button variant="contained" sx={{ mt: 1.5 }} disabled={completionMutation.isPending} onClick={() => completionMutation.mutate()}>完成复盘</Button>
            </>}
            {status !== "DRAFT" && <Typography variant="body2" sx={{ mt: 1.5 }}>{translatedLabel(evaluationResultLabels, valueOf(ownerConclusion, "result"))}{valueOf(ownerConclusion, "reason", "") ? ` · ${valueOf(ownerConclusion, "reason")}` : ""}</Typography>}
          </Box>
        </Box>

        <Box component="section" sx={{ mt: 3 }}>
          <Typography variant="h2" sx={{ mb: 1.5 }}>成交明细</Typography>
          {fills.length > 0 ? <TableContainer className="table-scroll" role="region" aria-label="成交明细横向滚动区域" tabIndex={0} sx={{ ...surfaceFrameSx, overflowX: "auto" }}>
            <Table size="small" aria-label="本次复盘成交明细" sx={{ minWidth: 860 }}>
              <TableHead><TableRow>
                <TableCell>时间</TableCell><TableCell>行为</TableCell><TableCell align="right">数量</TableCell><TableCell align="right">价格</TableCell><TableCell align="right">成交额</TableCell><TableCell>流动性</TableCell><TableCell align="right">手续费</TableCell>
              </TableRow></TableHead>
              <TableBody>{fills.map((fill) => <TableRow key={valueOf(fill, "trade_id")} hover>
                <TableCell className="mono">{formatUserVisibleTime(valueOf(fill, "fill_time"))}</TableCell>
                <TableCell>{translatedLabel(actionKindLabels, valueOf(fill, "action_kind"))}</TableCell>
                <TableCell className="mono" align="right">{valueOf(fill, "quantity")}</TableCell>
                <TableCell className="mono" align="right">{marketPrice(valueOf(fill, "price"))}</TableCell>
                <TableCell className="mono" align="right">{usdt(fill.notional)}</TableCell>
                <TableCell>{liquidityText(fill.liquidity_side)}</TableCell>
                <TableCell className="mono" align="right">{valueOf(fill, "fee", "未知")} {valueOf(fill, "fee_currency", "")}</TableCell>
              </TableRow>)}</TableBody>
            </Table>
          </TableContainer> : <Alert severity="info" variant="outlined">本次没有可归属的成交明细。</Alert>}
        </Box>

        <Box component="details" sx={{ ...surfaceFrameSx, mt: 3, p: 2 }}>
          <Box component="summary" sx={{ cursor: "pointer", fontWeight: 750 }}>系统机制与原始证据</Box>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1.5, mb: 1.5 }}>用于故障定位和责任核对；不会把当前环境结果外推为其他环境中的收益能力。</Typography>
          <FactGrid facts={[
            { label: "复盘 / 版本", value: `${valueOf(review, "review_id")} / v${valueOf(review, "review_version")}` },
            { label: "激活", value: valueOf(review, "activation_id") },
            { label: "计划事件", value: String(recordsOf(inputRefs.plan_events).length) },
            { label: "执行动作", value: String(recordsOf(inputRefs.execution_actions).length) },
            { label: "交易所事实", value: String(recordsOf(inputRefs.venue_facts).length) },
            { label: "命令与回执", value: String(recordsOf(inputRefs.commands_and_receipts).length) },
            { label: "开放执行责任", value: String(openActionRefs.length) },
            { label: "结果未知责任", value: String(unknownActionRefs.length) },
          ]} />
          <Box component="details" sx={{ mt: 1.5 }}>
            <Box component="summary" sx={{ cursor: "pointer", fontWeight: 700 }}>查看 JSON 输入</Box>
            <Box component="pre" className="mono" role="region" aria-label="复盘权威输入与开放责任" tabIndex={0} sx={{ mt: 1.5, mb: 0, overflowX: "auto", fontSize: 11 }}>{JSON.stringify({ input_refs: review.input_refs, open_responsibilities: review.open_responsibilities }, null, 2)}</Box>
          </Box>
        </Box>
      </>}
    </Box>
  );
}

function WorkbenchRoutes({ status }: { status: SettingsStatus }) {
  return (
    <Routes>
      <Route element={<WorkbenchFrame status={status} />}>
        <Route path="/overview" element={<OverviewPage />} />
        <Route path="/plans" element={<PlansPage />} />
        <Route
          path="/plans/new"
          element={(
            <Suspense fallback={<AppLoading />}>
              <NewPlanPage />
            </Suspense>
          )}
        />
        <Route
          path="/plans/:planId/edit"
          element={(
            <Suspense fallback={<AppLoading />}>
              <NewPlanPage />
            </Suspense>
          )}
        />
        <Route path="/plans/:planVersionId/activate" element={<PlanActivationRoute />} />
        <Route path="/activations/:activationId" element={<ActivationRoute />} />
        <Route path="/reviews" element={<ReviewsPage />} />
        <Route path="/reviews/:reviewId" element={<ReviewRoute />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/overview" replace />} />
    </Routes>
  );
}

export default function App() {
  const query = useQuery({
    queryKey: STATUS_QUERY_KEY,
    queryFn: getSettingsStatus,
    refetchInterval: 30_000,
  });

  if (query.isPending) return <AppLoading />;
  if (query.isError || !query.data) {
    return <ConnectionFailure retry={() => void query.refetch()} />;
  }
  return <WorkbenchRoutes status={query.data} />;
}
