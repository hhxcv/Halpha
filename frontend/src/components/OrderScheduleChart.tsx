import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  LinearProgress,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import { InfoOutlined } from "@mui/icons-material";
import {
  dispose,
  init,
  type Chart,
  type KLineData,
  type OverlayEvent,
  type Point,
} from "klinecharts";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

import {
  ApiFailure,
  getMarketWindow,
  type MarketInterval,
  type OrderScheduleDirection,
  type OrderSchedulePreviewLeg,
  type OrderScheduleSpec,
} from "../api/client";

function requestMarketWindowReload(
  chart: Chart,
  instrumentRef: string,
  pricePrecision: number,
): void {
  chart.setSymbol({
    ticker: instrumentRef,
    pricePrecision,
    volumePrecision: 4,
  });
}
import type { MarketColorScheme } from "../marketColors";
import type {
  MarketStreamBar,
  MarketStreamClientStatus,
} from "../marketStream";
import {
  expectedMarketSourceForEnvironment,
  MARKET_STREAM_STALE_AFTER_MS,
  shouldUseMarketStreamBar,
} from "../marketStream";
import {
  buildOrderScheduleChartAnnotations,
  chartPeriod,
  chartPriceInput,
  expandedVisiblePriceRange,
  marketIntervalForPeriod,
  marketWindowBounds,
  ORDER_CHART_INTERVALS,
  ORDER_CHART_WINDOW_BAR_COUNT,
  orderedPriceRange,
  type OrderChartPriceAnnotation,
} from "./orderScheduleChartModel";

const SCHEDULE_GROUP = "halpha-order-schedule";
const ANALYSIS_GROUP = "halpha-analysis-drawings";
const ANALYSIS_TIME_FORMATTER = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Shanghai",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

type AnalysisDrawing = {
  id: string;
  name: "horizontalStraightLine" | "straightLine";
  points: Array<Partial<Point>>;
};

type DrawRange = {
  startY: number;
  currentY: number;
  startPrice: number;
  currentPrice: number;
};

export type OrderScheduleChartProps = {
  workspaceMode?: boolean;
  environmentId: string;
  environmentKind: string;
  instrumentRef: string;
  direction: OrderScheduleDirection;
  marketColorScheme: MarketColorScheme;
  interval: MarketInterval;
  onIntervalChange: (interval: MarketInterval) => void;
  liveBar: MarketStreamBar | null;
  streamStatus: MarketStreamClientStatus;
  streamGeneration: number;
  priceProjectionReady: boolean;
  priceTickSize: string | null;
  referencePrice: string | null;
  spec: OrderScheduleSpec;
  previewLegs: OrderSchedulePreviewLeg[];
  previewState: "PENDING" | "READY" | "BLOCKED";
  onRangeChange: (lowerPrice: string, upperPrice: string) => void;
  onSingleLimitPriceChange: (price: string) => void;
};

function finitePrice(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function pricePrecision(values: string[]): number {
  return Math.min(
    8,
    Math.max(
      1,
      ...values.map((value) => value.split(".")[1]?.replace(/0+$/, "").length ?? 0),
    ),
  );
}

function marketFailureText(error: unknown): string {
  if (
    error instanceof Error
    && error.message === "MARKET_WINDOW_SOURCE_MISMATCH"
  ) {
    return "K 线来源与当前环境不一致，已拒绝显示；请核对运行环境后重试。";
  }
  if (!(error instanceof ApiFailure)) return "K 线窗口读取失败；数字输入仍可继续使用。";
  if (error.code === "MARKET_WINDOW_RANGE_INVALID") {
    return "K 线窗口范围不可用；请刷新当前行情后重试。";
  }
  return `K 线窗口读取失败（${error.code}）；数字输入仍可继续使用。`;
}

function toKLineData(bar: MarketStreamBar["bar"]): KLineData | null {
  const timestamp = Date.parse(bar.open_at);
  const open = Number(bar.open);
  const high = Number(bar.high);
  const low = Number(bar.low);
  const close = Number(bar.close);
  const volume = Number(bar.volume);
  if (
    !Number.isFinite(timestamp)
    || ![open, high, low, close].every(Number.isFinite)
  ) {
    return null;
  }
  return {
    timestamp,
    open,
    high,
    low,
    close,
    ...(Number.isFinite(volume) ? { volume } : {}),
  };
}

function streamStatusLabel(
  status: MarketStreamClientStatus,
  hasAppliedLiveBar: boolean,
): string {
  if (status === "LIVE") return "K线实时";
  if (status === "STALE") return hasAppliedLiveBar ? "K线已过期" : "K线待同步";
  if (status === "RECONNECTING") return "K线重连中";
  if (status === "CONNECTING") return "K线连接中";
  if (status === "FAILED") return "K线实时流不可用";
  return "K线实时流未启用";
}

function streamStatusColor(
  status: MarketStreamClientStatus,
): "success" | "warning" | "error" | "default" {
  if (status === "LIVE") return "success";
  if (status === "STALE" || status === "RECONNECTING") return "warning";
  if (status === "FAILED") return "error";
  return "default";
}

function chartMarketSourceLabel(source: string): string {
  if (source === "BINANCE_LIVE_PUBLIC") return "Live · Binance K线";
  if (source === "BINANCE_DEMO_PUBLIC") return "Demo · Binance K线";
  return "来源不匹配";
}

function chartMarketSourceDescription(source: string): string {
  return `图表历史、实时 K 线和当前价均使用 ${source}；不同环境的数据不会在本图中拼接。`;
}

function compactMarketCutoff(sourceCutoff: string | null): string | null {
  if (!sourceCutoff || !Number.isFinite(Date.parse(sourceCutoff))) return null;
  return ANALYSIS_TIME_FORMATTER.format(new Date(sourceCutoff));
}

function annotationTagName(annotation: OrderChartPriceAnnotation): string {
  if (annotation.role === "REFERENCE") return "参考";
  if (annotation.role === "SINGLE_LIMIT") return "限价";
  if (annotation.role === "RANGE_LOWER") return "下限";
  if (annotation.role === "RANGE_UPPER") return "上限";
  if (annotation.role === "MARK_CONDITION") return "触发";
  return annotation.label.replace("标准化入场 ", "档 ");
}

function groupNearbyAnnotations(
  annotations: OrderChartPriceAnnotation[],
  tolerance: number,
): OrderChartPriceAnnotation[][] {
  const groups: OrderChartPriceAnnotation[][] = [];
  [...annotations]
    .sort((left, right) => left.price - right.price)
    .forEach((annotation) => {
      const group = groups.at(-1);
      const groupLast = group?.at(-1);
      if (group && groupLast && annotation.price - groupLast.price <= tolerance) {
        group.push(annotation);
      } else {
        groups.push([annotation]);
      }
    });
  return groups;
}

function annotationGroupTag(
  group: OrderChartPriceAnnotation[],
  compact: boolean,
  precision: number,
): string {
  const primary = group.find((annotation) => annotation.draggable) ?? group[0];
  if (!primary) return "";
  const compactNames: Record<OrderChartPriceAnnotation["role"], string> = {
    REFERENCE: "参",
    SINGLE_LIMIT: "限",
    RANGE_LOWER: "下",
    RANGE_UPPER: "上",
    NORMALIZED_LEG: "档",
    MARK_CONDITION: "触",
  };
  const name = compact ? compactNames[primary.role] : annotationTagName(primary);
  const displayPrice = compact
    ? chartPriceInput(Number(primary.price.toFixed(Math.min(precision, 4))))
    : chartPriceInput(primary.price);
  if (group.length > 1) {
    return compact
      ? `${name} ${displayPrice} ×${group.length}`
      : `${name} ${displayPrice} · ${group.length} 线`;
  }
  const effectiveAmounts = group.flatMap((annotation) => {
    const amount = annotation.detail.match(/有效 ([^\s]+) USDT/)?.[1];
    return amount ? [amount] : [];
  });
  const amount = !compact && effectiveAmounts.length === 1
    ? ` · ${effectiveAmounts[0]}U`
    : "";
  return `${name} ${displayPrice}${amount}`;
}

function clonePoints(points: Array<Partial<Point>>): Array<Partial<Point>> {
  return points.map((point) => ({ ...point }));
}

function analysisPriceText(point: Partial<Point> | undefined): string {
  if (!point || !Number.isFinite(point.value)) return "价格未定";
  return `${chartPriceInput(point.value as number)} USDT`;
}

function analysisPointText(point: Partial<Point> | undefined): string {
  const price = analysisPriceText(point);
  if (!point || price === "价格未定") return price;
  if (!Number.isFinite(point.timestamp)) return price;
  return `${ANALYSIS_TIME_FORMATTER.format(new Date(point.timestamp as number))} @ ${price}`;
}

function analysisDrawingText(drawing: AnalysisDrawing, index: number): string {
  if (drawing.name === "horizontalStraightLine") {
    return `分析 ${index + 1} · 支撑 / 阻力 · ${analysisPriceText(drawing.points[0])}`;
  }
  return `分析 ${index + 1} · 趋势线 · ${analysisPointText(drawing.points[0])} → ${analysisPointText(drawing.points[1])}`;
}

function eventDrawing(event: OverlayEvent<unknown>): AnalysisDrawing | null {
  const name = event.overlay.name;
  if (name !== "horizontalStraightLine" && name !== "straightLine") return null;
  return {
    id: event.overlay.id,
    name,
    points: clonePoints(event.overlay.points),
  };
}

function chartPointAt(chart: Chart, x: number, y: number): Partial<Point> | null {
  const converted = chart.convertFromPixel(
    [{ x, y }],
    { paneId: "candle_pane" },
  );
  const point = Array.isArray(converted) ? converted[0] : converted;
  return point && Number.isFinite(point.value) ? point : null;
}

function lineStyle(
  color: string,
  style: OrderChartPriceAnnotation["lineStyle"] = "solid",
) {
  const dashed = style !== "solid";
  return {
    line: {
      color,
      size: dashed ? 1 : 2,
      style: dashed ? "dashed" as const : "solid" as const,
      dashedValue: style === "dotted" ? [2, 4] : dashed ? [6, 4] : [4, 2],
    },
    point: {
      color,
      borderColor: "#FFFFFF",
      activeColor: color,
      activeBorderColor: "#FFFFFF",
    },
    text: {
      color: "#FFFFFF",
      backgroundColor: color,
    },
  };
}

function annotationColor(
  annotation: OrderChartPriceAnnotation,
  direction: OrderScheduleDirection,
): string {
  if (annotation.role === "REFERENCE") return "#64748B";
  if (annotation.role === "SINGLE_LIMIT") return "#2563EB";
  if (annotation.role === "RANGE_LOWER") return "#2563EB";
  if (annotation.role === "RANGE_UPPER") return "#7C3AED";
  if (annotation.role === "MARK_CONDITION") return "#B45309";
  return direction === "LONG" ? "#0F766E" : "#B45309";
}

function annotationAuthorityLabel(
  authority: OrderChartPriceAnnotation["authority"],
): string {
  if (authority === "MARKET") return "行情事实";
  if (authority === "SERVER_PREVIEW") return "服务端草稿";
  return "输入草稿";
}

function annotationLineStyleLabel(
  style: OrderChartPriceAnnotation["lineStyle"],
): string {
  if (style === "solid") return "实线";
  if (style === "dotted") return "点线";
  return "虚线";
}

export default function OrderScheduleChart({
  workspaceMode = false,
  environmentId,
  environmentKind,
  instrumentRef,
  direction,
  marketColorScheme,
  interval,
  onIntervalChange,
  liveBar,
  streamStatus,
  streamGeneration,
  priceProjectionReady,
  priceTickSize,
  referencePrice,
  spec,
  previewLegs,
  previewState,
  onRangeChange,
  onSingleLimitPriceChange,
}: OrderScheduleChartProps) {
  const theme = useTheme();
  const narrow = useMediaQuery(theme.breakpoints.down("sm"));
  const environmentScope = `${environmentKind}:${environmentId}`;
  const expectedMarketSource = expectedMarketSourceForEnvironment(environmentKind);
  const pricePlan = spec.price_distribution;
  const lowerPrice = pricePlan.kind === "LADDER" ? pricePlan.lower_price : "";
  const upperPrice = pricePlan.kind === "LADDER" ? pricePlan.upper_price : "";
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<Chart | null>(null);
  const instrumentRefRef = useRef(instrumentRef);
  const intervalRef = useRef(interval);
  const expectedMarketSourceRef = useRef(expectedMarketSource);
  const appliedIntervalRef = useRef<MarketInterval | null>(null);
  const loaderRequestRef = useRef(0);
  const liveSubscriptionRef = useRef<{
    interval: MarketInterval;
    callback: (data: KLineData) => void;
  } | null>(null);
  const streamGenerationRef = useRef(streamGeneration);
  const lastStreamGenerationRef = useRef(streamGeneration);
  const latestRangeRef = useRef({ lowerPrice, upperPrice });
  const onRangeChangeRef = useRef(onRangeChange);
  const onSingleLimitPriceChangeRef = useRef(onSingleLimitPriceChange);
  const precisionRef = useRef(4);
  const narrowRef = useRef(narrow);
  const analysisDrawingsRef = useRef<AnalysisDrawing[]>([]);
  const activeAnalysisOverlayRef = useRef<string | null>(null);
  const undoRangeRef = useRef<{ lowerPrice: string; upperPrice: string } | null>(null);
  const undoSingleLimitRef = useRef<string | null>(null);
  const analysisHandlersRef = useRef<{
    persist: (event: OverlayEvent<unknown>) => void;
    remove: (event: OverlayEvent<unknown>) => void;
  }>({ persist: () => undefined, remove: () => undefined });
  const [chartGeneration, setChartGeneration] = useState(0);
  const [rangeMode, setRangeMode] = useState(false);
  const [drawRange, setDrawRange] = useState<DrawRange | null>(null);
  const [activeTool, setActiveTool] = useState<"SUPPORT" | "TREND" | null>(null);
  const [analysisDrawings, setAnalysisDrawings] = useState<AnalysisDrawing[]>([]);
  const [bars, setBars] = useState<KLineData[]>([]);
  const [marketWindowLoading, setMarketWindowLoading] = useState(false);
  const [marketWindowError, setMarketWindowError] = useState<unknown>(null);
  const [marketWindowSource, setMarketWindowSource] = useState<string | null>(null);
  const [marketWindowSourceCutoff, setMarketWindowSourceCutoff] = useState<string | null>(null);
  const [freshnessRevision, setFreshnessRevision] = useState(0);
  const [statusMessage, setStatusMessage] = useState("图表只编辑计划草稿，不会保存、激活或下单。");

  instrumentRefRef.current = instrumentRef;
  intervalRef.current = interval;
  expectedMarketSourceRef.current = expectedMarketSource;
  streamGenerationRef.current = streamGeneration;
  latestRangeRef.current = { lowerPrice, upperPrice };
  onRangeChangeRef.current = onRangeChange;
  onSingleLimitPriceChangeRef.current = onSingleLimitPriceChange;
  narrowRef.current = narrow;
  analysisDrawingsRef.current = analysisDrawings;

  const annotations = useMemo(
    () => priceProjectionReady
      ? buildOrderScheduleChartAnnotations({
        direction,
        referencePrice,
        spec,
        previewLegs,
        previewState,
      })
      : { priceAnnotations: [], relativeRules: [] },
    [
      direction,
      previewLegs,
      previewState,
      priceProjectionReady,
      referencePrice,
      spec,
    ],
  );
  const precision = useMemo(() => {
    if (priceTickSize) return pricePrecision([priceTickSize]);
    const visiblePrices = annotations.priceAnnotations.map((item) => chartPriceInput(item.price));
    if (visiblePrices.length > 0) return Math.min(4, pricePrecision(visiblePrices));
    return 4;
  }, [annotations.priceAnnotations, priceTickSize]);
  precisionRef.current = precision;

  const replaceDrawing = useCallback((drawing: AnalysisDrawing) => {
    setAnalysisDrawings((current) => {
      const existing = current.some((item) => item.id === drawing.id);
      return existing
        ? current.map((item) => item.id === drawing.id ? drawing : item)
        : [...current, drawing];
    });
  }, []);

  analysisHandlersRef.current = {
    persist: (event) => {
      const drawing = eventDrawing(event);
      if (!drawing) return;
      replaceDrawing(drawing);
      activeAnalysisOverlayRef.current = null;
      setActiveTool(null);
      setStatusMessage(
        drawing.name === "straightLine"
          ? "趋势线已保留为本页分析绘图；它不会自动移动任何真实订单。"
          : "支撑/阻力线已保留为本页分析绘图；它不会自动形成订单或保护。",
      );
    },
    remove: (event) => {
      setAnalysisDrawings((current) => current.filter((item) => item.id !== event.overlay.id));
      if (activeAnalysisOverlayRef.current === event.overlay.id) {
        activeAnalysisOverlayRef.current = null;
        setActiveTool(null);
      }
    },
  };

  const analysisOverlay = useCallback((
    name: AnalysisDrawing["name"],
    options?: { id?: string; points?: Array<Partial<Point>>; locked?: boolean },
  ) => ({
    name,
    groupId: ANALYSIS_GROUP,
    ...(options?.id ? { id: options.id } : {}),
    ...(options?.points ? { points: options.points } : {}),
    mode: "weak_magnet" as const,
    lock: options?.locked ?? false,
    modeSensitivity: 8,
    needDefaultPointFigure: true,
    needDefaultXAxisFigure: true,
    needDefaultYAxisFigure: false,
    styles: lineStyle("#64748B"),
    onDrawEnd: (event: OverlayEvent<unknown>) => analysisHandlersRef.current.persist(event),
    onPressedMoveEnd: (event: OverlayEvent<unknown>) => analysisHandlersRef.current.persist(event),
    onRemoved: (event: OverlayEvent<unknown>) => analysisHandlersRef.current.remove(event),
  }), []);

  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container) return undefined;
    const colors = marketColorScheme === "RED_UP_GREEN_DOWN"
      ? { up: "#D14343", down: "#138A5B" }
      : { up: "#138A5B", down: "#D14343" };
    const chart = init(container, {
      locale: "zh-CN",
      timezone: "Asia/Shanghai",
      styles: {
        grid: {
          horizontal: { color: "#EEF1F5" },
          vertical: { color: "#EEF1F5" },
        },
        yAxis: {
          size: narrowRef.current ? 96 : 136,
        },
        candle: {
          type: "candle_solid",
          tooltip: {
            showRule: narrowRef.current ? "none" : "follow_cross",
          },
          bar: {
            upColor: colors.up,
            downColor: colors.down,
            noChangeColor: "#64748B",
            upBorderColor: colors.up,
            downBorderColor: colors.down,
            noChangeBorderColor: "#64748B",
            upWickColor: colors.up,
            downWickColor: colors.down,
            noChangeWickColor: "#64748B",
          },
        },
      },
    });
    if (!chart) return undefined;
    chartRef.current = chart;
    chart.setDataLoader({
      getBars: async ({ type, period, callback }) => {
        const requestedInterval = marketIntervalForPeriod(period);
        if (type === "backward" || type === "forward" || requestedInterval === null) {
          callback([], { backward: false, forward: false });
          return;
        }
        const bounds = marketWindowBounds(
          new Date().toISOString(),
          requestedInterval,
        );
        if (!bounds) {
          setBars([]);
          setMarketWindowSource(null);
          setMarketWindowSourceCutoff(null);
          setMarketWindowLoading(false);
          callback([], { backward: false, forward: false });
          return;
        }
        const requestId = ++loaderRequestRef.current;
        setMarketWindowLoading(true);
        setMarketWindowError(null);
        setBars([]);
        setMarketWindowSource(null);
        setMarketWindowSourceCutoff(null);
        try {
          const window = await getMarketWindow(
            instrumentRefRef.current,
            bounds.startAt,
            bounds.endAt,
            requestedInterval,
            "EXECUTION_REVIEW",
          );
          if (
            requestId !== loaderRequestRef.current
            || requestedInterval !== intervalRef.current
          ) {
            return;
          }
          if (
            expectedMarketSourceRef.current === null
            || window.source !== expectedMarketSourceRef.current
          ) {
            throw new Error("MARKET_WINDOW_SOURCE_MISMATCH");
          }
          const nextBars = window.bars.flatMap((marketBar) => {
            const normalized = toKLineData(marketBar);
            return normalized ? [normalized] : [];
          });
          setMarketWindowSource(window.source);
          setMarketWindowSourceCutoff(window.source_cutoff);
          setBars(nextBars);
          setMarketWindowLoading(false);
          callback(nextBars, { backward: false, forward: false });
        } catch (error) {
          if (
            requestId !== loaderRequestRef.current
            || requestedInterval !== intervalRef.current
          ) {
            return;
          }
          setBars([]);
          setMarketWindowSource(null);
          setMarketWindowSourceCutoff(null);
          setMarketWindowLoading(false);
          setMarketWindowError(error);
          callback([], { backward: false, forward: false });
        }
      },
      subscribeBar: ({ period, callback }) => {
        const requestedInterval = marketIntervalForPeriod(period);
        liveSubscriptionRef.current = requestedInterval
          ? { interval: requestedInterval, callback }
          : null;
      },
      unsubscribeBar: ({ period }) => {
        const requestedInterval = marketIntervalForPeriod(period);
        if (liveSubscriptionRef.current?.interval === requestedInterval) {
          liveSubscriptionRef.current = null;
        }
      },
    });
    chart.setSymbol({
      ticker: instrumentRefRef.current,
      pricePrecision: precisionRef.current,
      volumePrecision: 4,
    });
    appliedIntervalRef.current = intervalRef.current;
    chart.setPeriod(chartPeriod(intervalRef.current));
    chart.setOffsetRightDistance(72);
    container.querySelector<HTMLElement>('[tabindex="1"]')?.setAttribute("tabindex", "-1");
    analysisDrawingsRef.current.forEach((drawing) => {
      chart.createOverlay(analysisOverlay(drawing.name, {
        id: drawing.id,
        points: drawing.points,
        locked: narrowRef.current,
      }));
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(container);
    lastStreamGenerationRef.current = streamGenerationRef.current;
    setChartGeneration((current) => current + 1);
    return () => {
      observer.disconnect();
      loaderRequestRef.current += 1;
      liveSubscriptionRef.current = null;
      if (chartRef.current === chart) chartRef.current = null;
      dispose(chart);
    };
  }, [analysisOverlay, marketColorScheme]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || chartGeneration === 0) return;
    const currentSymbol = chart.getSymbol();
    if (
      currentSymbol?.ticker === instrumentRef
      && currentSymbol.pricePrecision === precision
    ) {
      return;
    }
    chart.setSymbol({
      ticker: instrumentRef,
      pricePrecision: precision,
      volumePrecision: 4,
    });
  }, [chartGeneration, instrumentRef, precision]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || chartGeneration === 0) return;
    if (narrow) {
      setRangeMode(false);
      setDrawRange(null);
      if (activeAnalysisOverlayRef.current) {
        chart.removeOverlay({ id: activeAnalysisOverlayRef.current });
        activeAnalysisOverlayRef.current = null;
        setActiveTool(null);
      }
    }
    chart.overrideOverlay({ groupId: ANALYSIS_GROUP, lock: narrow });
    chart.setStyles({
      yAxis: { size: narrow ? 96 : 136 },
      candle: { tooltip: { showRule: narrow ? "none" : "follow_cross" } },
    });
  }, [chartGeneration, narrow]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || chartGeneration === 0 || appliedIntervalRef.current === interval) return;
    appliedIntervalRef.current = interval;
    setBars([]);
    setMarketWindowError(null);
    setMarketWindowSource(null);
    setMarketWindowSourceCutoff(null);
    chart.setPeriod(chartPeriod(interval));
  }, [chartGeneration, interval]);

  useEffect(() => {
    if (
      streamGeneration <= 0
      || streamGeneration === lastStreamGenerationRef.current
    ) {
      return;
    }
    lastStreamGenerationRef.current = streamGeneration;
    const chart = chartRef.current;
    if (!chart || chartGeneration === 0) return;
    requestMarketWindowReload(
      chart,
      instrumentRefRef.current,
      precisionRef.current,
    );
  }, [chartGeneration, streamGeneration]);

  useEffect(() => {
    if (
      !liveBar
      || !marketWindowSource
      || !shouldUseMarketStreamBar(
        liveBar,
        instrumentRef,
        interval,
        marketWindowSource,
      )
    ) {
      return;
    }
    const subscription = liveSubscriptionRef.current;
    if (!subscription || subscription.interval !== liveBar.interval) return;
    const nextBar = toKLineData(liveBar.bar);
    if (nextBar) subscription.callback(nextBar);
  }, [instrumentRef, interval, liveBar, marketWindowSource]);

  const matchingLiveBar = liveBar
    && marketWindowSource
    && shouldUseMarketStreamBar(
      liveBar,
      instrumentRef,
      interval,
      marketWindowSource,
    )
    ? liveBar
    : null;

  useEffect(() => {
    if (!matchingLiveBar) return undefined;
    const staleAt = Date.parse(matchingLiveBar.received_at)
      + MARKET_STREAM_STALE_AFTER_MS;
    const remaining = staleAt - Date.now();
    if (remaining <= 0) return undefined;
    const timer = window.setTimeout(
      () => setFreshnessRevision((current) => current + 1),
      remaining + 25,
    );
    return () => window.clearTimeout(timer);
  }, [matchingLiveBar]);

  useEffect(() => {
    if (pricePlan.kind === "LADDER") return;
    setRangeMode(false);
    setDrawRange(null);
  }, [pricePlan.kind]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || chartGeneration === 0) return;
    chart.removeOverlay({ groupId: SCHEDULE_GROUP });
    const lastTimestamp = bars.at(-1)?.timestamp;
    if (!lastTimestamp) return;
    const visibleSchedulePrices = annotations.priceAnnotations.map(
      (annotation) => annotation.price,
    );
    chart.overrideYAxis({
      paneId: "candle_pane",
      createRange: ({ defaultRange }) => {
        const [from, to] = expandedVisiblePriceRange(
          defaultRange.from,
          defaultRange.to,
          visibleSchedulePrices,
          Math.pow(10, -precision) * 4,
        );
        if (from === defaultRange.from && to === defaultRange.to) {
          return defaultRange;
        }
        const range = to - from;
        return {
          from,
          to,
          range,
          realFrom: from,
          realTo: to,
          realRange: range,
          displayFrom: from,
          displayTo: to,
          displayRange: range,
        };
      },
    });

    const commitBoundary = (kind: "LOWER" | "UPPER", event: OverlayEvent<unknown>) => {
      const moved = event.overlay.points[0]?.value;
      const other = finitePrice(
        kind === "LOWER"
          ? latestRangeRef.current.upperPrice
          : latestRangeRef.current.lowerPrice,
      );
      if (!Number.isFinite(moved) || other === null) return;
      const [nextLower, nextUpper] = orderedPriceRange(moved as number, other);
      onRangeChangeRef.current(chartPriceInput(nextLower), chartPriceInput(nextUpper));
      setStatusMessage("区间手柄已更新草稿；等待服务端重新标准化档位。");
    };
    const editableAnnotation = (annotation: OrderChartPriceAnnotation) => ({
      name: "horizontalStraightLine",
      id: `${annotation.id}-handle`,
      groupId: SCHEDULE_GROUP,
      points: [{ timestamp: lastTimestamp, value: annotation.price }],
      mode: "normal" as const,
      lock: narrow,
      needDefaultPointFigure: true,
      needDefaultXAxisFigure: false,
      needDefaultYAxisFigure: true,
      styles: lineStyle(annotationColor(annotation, direction), annotation.lineStyle),
      onPressedMoveStart: () => {
        if (annotation.role === "SINGLE_LIMIT") {
          undoSingleLimitRef.current = chartPriceInput(annotation.price);
          undoRangeRef.current = null;
        } else {
          undoRangeRef.current = { ...latestRangeRef.current };
          undoSingleLimitRef.current = null;
        }
        setStatusMessage(`${annotation.label}正在移动；松开后才写入草稿。`);
      },
      onPressedMoveEnd: (event: OverlayEvent<unknown>) => {
        if (annotation.role === "SINGLE_LIMIT") {
          const moved = event.overlay.points[0]?.value;
          if (!Number.isFinite(moved)) return;
          onSingleLimitPriceChangeRef.current(chartPriceInput(moved as number));
          setStatusMessage("单笔限价已更新草稿；等待服务端重新标准化。");
          return;
        }
        commitBoundary(
          annotation.role === "RANGE_LOWER" ? "LOWER" : "UPPER",
          event,
        );
      },
      onRightClick: (event: OverlayEvent<unknown>) => event.preventDefault?.(),
    });

    annotations.priceAnnotations.forEach((annotation) => {
      if (annotation.draggable) {
        chart.createOverlay(editableAnnotation(annotation));
      }
    });

    const visibleBarPrices = bars.flatMap((bar) => [bar.high, bar.low]);
    const visiblePriceSpan = visibleBarPrices.length > 0
      ? Math.max(...visibleBarPrices, ...visibleSchedulePrices)
        - Math.min(...visibleBarPrices, ...visibleSchedulePrices)
      : 0;
    const tagTolerance = Math.max(
      Math.pow(10, -precision),
      visiblePriceSpan / Math.max(chartContainerRef.current?.clientHeight ?? 320, 1) * 18,
    );
    groupNearbyAnnotations(
      annotations.priceAnnotations,
      tagTolerance,
    ).forEach((group, index) => {
      const primary = group.find((annotation) => annotation.draggable) ?? group[0];
      if (!primary) return;
      chart.createOverlay({
        name: "simpleTag",
        id: `halpha-price-label-${index}`,
        groupId: SCHEDULE_GROUP,
        lock: true,
        zLevel: primary.draggable ? 3 : 2,
        points: [{ timestamp: lastTimestamp, value: primary.price }],
        extendData: annotationGroupTag(group, narrow, precision),
        needDefaultPointFigure: false,
        needDefaultXAxisFigure: false,
        needDefaultYAxisFigure: !primary.draggable,
        styles: lineStyle(
          annotationColor(primary, direction),
          primary.lineStyle,
        ),
      });
    });
  }, [
    annotations.priceAnnotations,
    bars,
    chartGeneration,
    direction,
    narrow,
    precision,
  ]);

  const rememberCurrentRange = () => {
    const lower = finitePrice(latestRangeRef.current.lowerPrice);
    const upper = finitePrice(latestRangeRef.current.upperPrice);
    if (lower !== null && upper !== null) {
      undoRangeRef.current = { ...latestRangeRef.current };
    }
  };

  const startRangeMode = () => {
    if (narrow || pricePlan.kind !== "LADDER" || !chartRef.current) return;
    if (activeAnalysisOverlayRef.current) {
      chartRef.current.removeOverlay({ id: activeAnalysisOverlayRef.current });
      activeAnalysisOverlayRef.current = null;
    }
    rememberCurrentRange();
    setActiveTool(null);
    setRangeMode(true);
    setStatusMessage("在 K 线主图内按下并纵向拖动；松开后只更新区间草稿。按 Esc 取消。");
  };

  const startAnalysis = (tool: "SUPPORT" | "TREND") => {
    const chart = chartRef.current;
    if (narrow || !chart) return;
    if (activeAnalysisOverlayRef.current) {
      chart.removeOverlay({ id: activeAnalysisOverlayRef.current });
    }
    setRangeMode(false);
    setDrawRange(null);
    setActiveTool(tool);
    const result = chart.createOverlay(analysisOverlay(
      tool === "SUPPORT" ? "horizontalStraightLine" : "straightLine",
    ));
    activeAnalysisOverlayRef.current = typeof result === "string" ? result : null;
    setStatusMessage(
      tool === "SUPPORT"
        ? "在图上点击一次放置支撑/阻力线；之后可以拖动，右键可删除。"
        : "在图上依次点击两个锚点绘制趋势线；之后可以拖动，右键可删除。",
    );
  };

  const cancelActiveInteraction = () => {
    const chart = chartRef.current;
    if (rangeMode || drawRange) {
      setRangeMode(false);
      setDrawRange(null);
      setStatusMessage("已取消本次区间绘制，计划草稿没有变化。");
      return true;
    }
    if (chart && activeAnalysisOverlayRef.current) {
      chart.removeOverlay({ id: activeAnalysisOverlayRef.current });
      activeAnalysisOverlayRef.current = null;
      setActiveTool(null);
      setStatusMessage("已取消未完成的分析绘图。");
      return true;
    }
    if (undoSingleLimitRef.current !== null) {
      const previous = undoSingleLimitRef.current;
      undoSingleLimitRef.current = null;
      onSingleLimitPriceChangeRef.current(previous);
      setStatusMessage("已撤销最近一次图上单笔限价修改。");
      return true;
    }
    if (undoRangeRef.current) {
      const previous = undoRangeRef.current;
      undoRangeRef.current = null;
      onRangeChangeRef.current(previous.lowerPrice, previous.upperPrice);
      setStatusMessage("已撤销最近一次图上区间修改。");
      return true;
    }
    return false;
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape" && cancelActiveInteraction()) {
      event.preventDefault();
      event.stopPropagation();
    }
  };

  const pointerPrice = (event: PointerEvent<HTMLDivElement>): number | null => {
    const chart = chartRef.current;
    const container = chartContainerRef.current;
    if (!chart || !container) return null;
    const bounds = container.getBoundingClientRect();
    const point = chartPointAt(
      chart,
      event.clientX - bounds.left,
      event.clientY - bounds.top,
    );
    return point?.value ?? null;
  };

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (!rangeMode || event.button !== 0) return;
    const price = pointerPrice(event);
    if (price === null) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrawRange({
      startY: event.nativeEvent.offsetY,
      currentY: event.nativeEvent.offsetY,
      startPrice: price,
      currentPrice: price,
    });
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (!drawRange || !event.currentTarget.hasPointerCapture(event.pointerId)) return;
    const price = pointerPrice(event);
    if (price === null) return;
    setDrawRange((current) => current ? {
      ...current,
      currentY: event.nativeEvent.offsetY,
      currentPrice: price,
    } : null);
  };

  const handlePointerUp = (event: PointerEvent<HTMLDivElement>) => {
    if (!drawRange) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const distance = Math.abs(drawRange.currentY - drawRange.startY);
    if (distance < 8) {
      setDrawRange(null);
      setStatusMessage("拖动距离过小，区间草稿没有变化。请按住并纵向拖动。");
      return;
    }
    const [nextLower, nextUpper] = orderedPriceRange(
      drawRange.startPrice,
      drawRange.currentPrice,
    );
    onRangeChangeRef.current(chartPriceInput(nextLower), chartPriceInput(nextUpper));
    setDrawRange(null);
    setRangeMode(false);
    setStatusMessage("图上区间已写入草稿；档位线将在服务端标准化成功后显示。");
  };

  const clearAnalysis = () => {
    chartRef.current?.removeOverlay({ groupId: ANALYSIS_GROUP });
    activeAnalysisOverlayRef.current = null;
    setActiveTool(null);
    setAnalysisDrawings([]);
    setStatusMessage("已清除本页分析绘图；订单计划草稿没有变化。");
  };

  const reloadMarketWindow = () => {
    const chart = chartRef.current;
    if (!chart) return;
    setMarketWindowError(null);
    requestMarketWindowReload(
      chart,
      instrumentRefRef.current,
      precisionRef.current,
    );
  };

  const previewStatus = previewState === "READY"
    ? `${previewLegs.length} 条服务端归一化草稿线`
    : previewState === "PENDING"
      ? "档位预览更新中，旧草稿线已隐藏"
      : "档位预览不可用，执行草稿线未显示";
  const pricePlanStatus = pricePlan.kind === "LADDER"
    ? `区间 ${pricePlan.lower_price || "未填写"} – ${pricePlan.upper_price || "未填写"}`
    : spec.venue_policy.order_type === "MARKET"
      ? "单笔市价 · 场所决定"
      : spec.venue_policy.price_match !== null
        ? `单笔 priceMatch · ${spec.venue_policy.price_match}`
        : `单笔限价 ${pricePlan.limit_price || "未填写"}`;
  const chartEmptyMessage = marketWindowLoading
    ? `正在读取最近 ${ORDER_CHART_WINDOW_BAR_COUNT} 根 ${interval} K 线。`
    : marketWindowError
      ? marketFailureText(marketWindowError)
      : `当前时间窗没有可展示的 ${interval} K 线；数字输入和服务端预览仍可继续。`;
  const chartSourceCutoff = matchingLiveBar?.source_cutoff
    ?? marketWindowSourceCutoff;
  const compactChartSourceCutoff = compactMarketCutoff(chartSourceCutoff);
  const appliedLiveBarFresh = Boolean(
    matchingLiveBar
    && Date.now() - Date.parse(matchingLiveBar.received_at)
      < MARKET_STREAM_STALE_AFTER_MS,
  );
  // The revision is advanced by a one-shot expiry timer so the status becomes
  // stale even when the execution quote stream also stops rendering updates.
  void freshnessRevision;
  const chartStreamStatus: MarketStreamClientStatus = appliedLiveBarFresh
    ? "LIVE"
    : streamStatus === "CONNECTING"
      || streamStatus === "RECONNECTING"
      || streamStatus === "FAILED"
      || streamStatus === "DISABLED"
      ? streamStatus
      : "STALE";

  return (
    <Box
      component="section"
      aria-labelledby="order-schedule-chart-title"
      onKeyDown={handleKeyDown}
      sx={{
        border: 1,
        borderColor: "divider",
        borderRadius: 1,
        overflow: { xs: "visible", md: "hidden" },
        bgcolor: "background.paper",
        height: workspaceMode ? "100%" : "auto",
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
      }}
    >
      <Box sx={{ px: { xs: 1.25, sm: 1.5 }, py: 1, borderBottom: 1, borderColor: "divider", flex: "0 0 auto" }}>
        <Stack
          direction={{ xs: "column", lg: "row" }}
          spacing={1}
          sx={{ alignItems: { xs: "stretch", lg: "center" } }}
        >
          <Box sx={{ minWidth: 0, flex: "1 1 auto" }}>
            <Stack
              direction="row"
              spacing={.5}
              useFlexGap
              sx={{ alignItems: "center", flexWrap: "wrap" }}
            >
              <Typography id="order-schedule-chart-title" component="h2" variant="subtitle2">
                {interval} K 线 · 草稿投影
              </Typography>
              <Tooltip
                arrow
                title="图表与右侧字段写回同一份草稿。服务端预览线不是已提交订单；分析线不会自动改单或移动止盈止损。"
              >
                <IconButton size="small" aria-label="了解图表草稿和订单事实的区别">
                  <InfoOutlined sx={{ fontSize: 16 }} />
                </IconButton>
              </Tooltip>
              <Chip
                size="small"
                color={streamStatusColor(chartStreamStatus)}
                variant="outlined"
                label={streamStatusLabel(
                  chartStreamStatus,
                  matchingLiveBar !== null,
                )}
                sx={{
                  ml: .5,
                  height: 22,
                  ...(chartStreamStatus === "LIVE" ? {
                    color: "#166534",
                    borderColor: "#86B69F",
                    bgcolor: "#F0FDF4",
                  } : {}),
                }}
              />
              {marketWindowSource ? (
                <Tooltip
                  arrow
                  title={`${chartMarketSourceDescription(marketWindowSource)} 来源截止 ${chartSourceCutoff ?? "未知"}。`}
                >
                  <Chip
                    size="small"
                    variant="outlined"
                    data-testid="order-schedule-chart-market-source"
                    label={chartMarketSourceLabel(marketWindowSource)}
                    sx={{ height: 22, bgcolor: "#EFF6FF", borderColor: "#93C5FD", color: "#1D4ED8" }}
                  />
                </Tooltip>
              ) : null}
            </Stack>
            <Typography
              variant="caption"
              color="text.secondary"
              data-testid="order-schedule-chart-subtitle"
              sx={{ display: "block", overflowWrap: "anywhere" }}
            >
              {instrumentRef}
              {compactChartSourceCutoff ? ` · K线截止 ${compactChartSourceCutoff}` : ""}
              {" · 输入线可拖动 · Esc 撤销最近一次图上修改"}
            </Typography>
            {narrow ? (
              <TextField
                select
                size="small"
                label="K 线周期"
                value={interval}
                onChange={(event) => onIntervalChange(event.target.value as MarketInterval)}
                sx={{ width: 112, mt: .75 }}
              >
                {ORDER_CHART_INTERVALS.map((option) => (
                  <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                ))}
              </TextField>
            ) : (
              <ToggleButtonGroup
                exclusive
                size="small"
                value={interval}
                aria-label="K 线周期"
                onChange={(_event, next: MarketInterval | null) => {
                  if (next) onIntervalChange(next);
                }}
                sx={{
                  mt: .75,
                  "& .MuiToggleButton-root": {
                    minWidth: 42,
                    minHeight: 28,
                    px: .8,
                    py: .25,
                    textTransform: "none",
                    fontWeight: 750,
                  },
                }}
              >
                {ORDER_CHART_INTERVALS.map((option) => (
                  <ToggleButton key={option.value} value={option.value}>
                    {option.label}
                  </ToggleButton>
                ))}
              </ToggleButtonGroup>
            )}
          </Box>
          <Stack
            data-testid="order-schedule-chart-tools"
            direction="row"
            spacing={0.75}
            useFlexGap
            sx={{ flexWrap: "wrap", ml: { lg: "auto" }, justifyContent: { lg: "flex-end" } }}
          >
            <Button
              size="small"
              variant={rangeMode ? "contained" : "outlined"}
              aria-pressed={rangeMode}
              disabled={narrow || bars.length === 0 || pricePlan.kind !== "LADDER"}
              onClick={() => rangeMode ? cancelActiveInteraction() : startRangeMode()}
            >
              拖动选择区间
            </Button>
            <Button
              size="small"
              variant={activeTool === "SUPPORT" ? "contained" : "outlined"}
              aria-pressed={activeTool === "SUPPORT"}
              disabled={narrow || bars.length === 0}
              onClick={() => startAnalysis("SUPPORT")}
            >
              支撑 / 阻力
            </Button>
            <Button
              size="small"
              variant={activeTool === "TREND" ? "contained" : "outlined"}
              aria-pressed={activeTool === "TREND"}
              disabled={narrow || bars.length === 0}
              onClick={() => startAnalysis("TREND")}
            >
              趋势线
            </Button>
            <Button
              size="small"
              color="inherit"
              disabled={analysisDrawings.length === 0 && !activeAnalysisOverlayRef.current}
              onClick={clearAnalysis}
            >
              清除分析线
            </Button>
          </Stack>
        </Stack>
        {narrow ? (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
            窄屏保留查看与精确数值输入；绘图和多档拖动仅在桌面开放。
          </Typography>
        ) : null}
      </Box>

      <Box
        tabIndex={0}
        role="group"
        aria-label={`订单计划 ${interval} K 线主图；可在桌面编辑单笔限价、区间、支撑阻力和趋势线`}
        sx={{
          position: "relative",
          height: workspaceMode ? { xs: 340, md: "auto" } : { xs: 330, sm: 430 },
          flex: workspaceMode ? { xs: "0 0 auto", md: "1 1 0" } : "0 0 auto",
          minHeight: workspaceMode ? { xs: 340, md: 320 } : undefined,
          outline: "none",
          bgcolor: "action.hover",
          "&:focus-visible": {
            boxShadow: `inset 0 0 0 3px ${theme.palette.primary.main}`,
          },
        }}
      >
        <Box
          ref={chartContainerRef}
          data-testid="order-schedule-kline-chart"
          data-market-environment={environmentScope}
          data-market-history-source={marketWindowSource ?? undefined}
          data-market-live-source={matchingLiveBar?.source ?? undefined}
          sx={{ position: "absolute", inset: 0 }}
        />
        {bars.length === 0 ? (
          <Stack
            role="status"
            spacing={1.25}
            sx={{
              position: "absolute",
              inset: 0,
              zIndex: 2,
              alignItems: "center",
              justifyContent: "center",
              px: 3,
              textAlign: "center",
              bgcolor: "background.paper",
            }}
          >
            {marketWindowLoading ? (
              <Box sx={{ width: "min(360px, 100%)" }}>
                <LinearProgress aria-label="正在读取订单计划 K 线窗口" />
              </Box>
            ) : null}
            <Typography variant="body2" color="text.secondary">
              {chartEmptyMessage}
            </Typography>
            {marketWindowError ? (
              <Button size="small" variant="outlined" onClick={reloadMarketWindow}>
                重试 K 线
              </Button>
            ) : null}
          </Stack>
        ) : null}
        {rangeMode ? (
          <Box
            data-testid="order-schedule-range-drag-layer"
            aria-hidden="true"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={() => setDrawRange(null)}
            sx={{
              position: "absolute",
              inset: 0,
              zIndex: 4,
              cursor: "ns-resize",
              touchAction: "none",
              bgcolor: "rgba(37, 99, 235, 0.025)",
            }}
          >
            {drawRange ? (
              <Box
                sx={{
                  position: "absolute",
                  left: 0,
                  right: 0,
                  top: Math.min(drawRange.startY, drawRange.currentY),
                  height: Math.max(2, Math.abs(drawRange.currentY - drawRange.startY)),
                  bgcolor: "rgba(37, 99, 235, 0.12)",
                  borderTop: "2px solid #2563EB",
                  borderBottom: "2px solid #7C3AED",
                  pointerEvents: "none",
                }}
              />
            ) : null}
          </Box>
        ) : null}
      </Box>

      <Box
        data-testid="order-schedule-chart-detail-scroll"
        sx={{
          px: { xs: 1.25, sm: 1.5 },
          py: 1,
          borderTop: 1,
          borderColor: "divider",
          flex: { xs: "0 0 auto", md: "0 1 auto" },
          minHeight: 0,
          maxHeight: workspaceMode ? { md: "42%" } : undefined,
          overflowY: workspaceMode ? { xs: "visible", md: "auto" } : "visible",
          overscrollBehavior: "contain",
        }}
      >
        <Stack direction="row" spacing={0.75} useFlexGap sx={{ flexWrap: "wrap", mb: .5 }}>
          <Chip size="small" variant="outlined" label={pricePlanStatus} />
          <Chip size="small" variant="outlined" label={previewStatus} />
          <Chip
            size="small"
            variant="outlined"
            label={annotations.relativeRules
              .slice(0, 2)
              .map((rule) => rule.label)
              .join(" · ")}
          />
        </Stack>
        <Typography aria-live="polite" variant="caption" color="text.secondary">
          {drawRange
            ? `选择中：${chartPriceInput(Math.min(drawRange.startPrice, drawRange.currentPrice))} – ${chartPriceInput(Math.max(drawRange.startPrice, drawRange.currentPrice))} USDT`
            : statusMessage}
        </Typography>

        <Box
          component="details"
          sx={{
            mt: .65,
            "& > summary": {
              cursor: "pointer",
              color: "text.secondary",
              fontSize: 12,
              fontWeight: 700,
            },
          }}
        >
          <Box component="summary">
            图线、动态规则与等价数值 · {annotations.priceAnnotations.length + annotations.relativeRules.length} 项
          </Box>
        <Box sx={{ mt: 1 }}>
          <Typography variant="caption" sx={{ fontWeight: 750 }}>
            图中价格线与等价数值
          </Typography>
          {annotations.priceAnnotations.length > 0 ? (
            <Box
              component="ol"
              aria-label="图中价格标注及等价数值"
              tabIndex={0}
              sx={{
                mt: 0.75,
                mb: 0,
                pl: 2.5,
                display: "grid",
                gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
                gap: 0.65,
                maxHeight: { lg: 180 },
                overflowY: { lg: "auto" },
              }}
            >
              {annotations.priceAnnotations.map((annotation) => (
                <Typography
                  component="li"
                  variant="caption"
                  key={annotation.id}
                  sx={{ minWidth: 0, overflowWrap: "anywhere" }}
                >
                  <Box
                    component="span"
                    aria-hidden="true"
                    sx={{
                      display: "inline-block",
                      width: 16,
                      mr: .75,
                      verticalAlign: "middle",
                      borderTop: 2,
                      borderColor: annotationColor(annotation, direction),
                      borderStyle: annotation.lineStyle,
                    }}
                  />
                  <Box component="span" sx={{ fontWeight: 700 }}>{annotation.label}</Box>
                  {" · "}
                  <Box component="span" className="mono">{chartPriceInput(annotation.price)} USDT</Box>
                  {" · "}
                  {annotationAuthorityLabel(annotation.authority)} / {annotationLineStyleLabel(annotation.lineStyle)}
                  <Box
                    component="span"
                    color="text.secondary"
                    sx={{ display: "block", ml: 3, minWidth: 0, overflowWrap: "anywhere" }}
                  >
                    {annotation.detail}
                  </Box>
                </Typography>
              ))}
            </Box>
          ) : (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: .75 }}>
              当前没有可画成固定水平线的有效绝对价格。
            </Typography>
          )}
        </Box>

        {annotations.relativeRules.length > 0 ? (
          <Box sx={{ mt: 1.25 }}>
            <Typography variant="caption" sx={{ fontWeight: 750 }}>
              图内动态价格规则（无固定水平线）
            </Typography>
            <Box
              component="ul"
              aria-label="图中相对和动态价格规则"
              sx={{ mt: .75, mb: 0, pl: 2.5, display: "grid", gap: .6 }}
            >
              {annotations.relativeRules.map((rule) => (
                <Typography
                  component="li"
                  variant="caption"
                  key={rule.id}
                  sx={{ minWidth: 0, overflowWrap: "anywhere" }}
                >
                  <Box component="span" sx={{ fontWeight: 700 }}>{rule.label}</Box>
                  <Box component="span" color="text.secondary"> · {rule.detail}</Box>
                </Typography>
              ))}
            </Box>
          </Box>
        ) : null}

        {analysisDrawings.length > 0 ? (
          <Box sx={{ mt: 1.25 }}>
            <Typography variant="caption" sx={{ fontWeight: 750 }}>
              分析绘图的等价数值列表
            </Typography>
            <Box
              component="ol"
              aria-label="图中分析绘图及锚点"
              sx={{ mt: 0.75, mb: 0, pl: 2.5, display: "grid", gap: 0.5 }}
            >
              {analysisDrawings.map((drawing, index) => (
                <Typography component="li" variant="caption" key={drawing.id}>
                  {analysisDrawingText(drawing, index)}
                </Typography>
              ))}
            </Box>
          </Box>
        ) : null}

        <Alert severity="info" variant="outlined" sx={{ mt: 1.25 }}>
          水平线和趋势线目前只用于分析。沿趋势线自动移动入场、止盈或止损尚未开放；该能力需要服务端限次、价格步进、撤单确认、部分成交竞态和重启恢复，不能由浏览器绘图直接触发。
        </Alert>
        </Box>
      </Box>
    </Box>
  );
}
