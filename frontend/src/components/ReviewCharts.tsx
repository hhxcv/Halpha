import { Box, Typography } from "@mui/material";
import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  CrosshairMode,
  LineSeries,
  LineStyle,
  type CandlestickData,
  type IChartApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";

import type { MarketColorScheme } from "../marketColors";

type MarketBar = {
  open_at: string;
  open: string;
  high: string;
  low: string;
  close: string;
};

type Fill = {
  action_kind?: unknown;
  fill_time?: unknown;
  price?: unknown;
  quantity?: unknown;
};

type Action = {
  action_kind?: unknown;
  action_terms?: unknown;
  state?: unknown;
};

type TrendPoint = {
  at: string;
  value: number;
};

function tradingColors(scheme: MarketColorScheme) {
  return scheme === "RED_UP_GREEN_DOWN"
    ? { up: "#D14343", down: "#138A5B" }
    : { up: "#138A5B", down: "#D14343" };
}

function utcTimestamp(value: string): UTCTimestamp | null {
  const milliseconds = Date.parse(value);
  return Number.isFinite(milliseconds) ? Math.floor(milliseconds / 1000) as UTCTimestamp : null;
}

function formatShanghaiTime(time: Time): string {
  const seconds = typeof time === "number"
    ? time
    : typeof time === "string"
      ? Date.parse(time) / 1000
      : Date.UTC(time.year, time.month - 1, time.day) / 1000;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(seconds * 1000));
}

function formatChartPrice(value: number): string {
  return new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 }).format(value);
}

function chartBaseOptions(container: HTMLDivElement) {
  return {
    autoSize: true,
    height: container.clientHeight,
    layout: {
      background: { type: ColorType.Solid, color: "#FFFFFF" },
      textColor: "#64748B",
      fontFamily: 'Inter, "Segoe UI", sans-serif',
      fontSize: 11,
      attributionLogo: false,
    },
    grid: {
      vertLines: { color: "#EEF1F5" },
      horzLines: { color: "#EEF1F5" },
    },
    crosshair: { mode: CrosshairMode.Normal },
    rightPriceScale: { borderColor: "#D8DEE8" },
    timeScale: {
      borderColor: "#D8DEE8",
      timeVisible: true,
      secondsVisible: false,
      rightOffset: 4,
    },
    localization: { timeFormatter: formatShanghaiTime },
  } as const;
}

function destroyChart(chart: IChartApi | null) {
  if (chart) chart.remove();
}

export function ReviewPriceChart({
  bars,
  fills,
  actions,
  interval,
  direction,
  marketColorScheme,
}: {
  bars: MarketBar[];
  fills: Fill[];
  actions: Action[];
  interval: "1m" | "15m";
  direction: string;
  marketColorScheme: MarketColorScheme;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [hoverText, setHoverText] = useState("移动光标查看 K 线价格");

  useEffect(() => {
    const container = containerRef.current;
    if (!container || bars.length === 0) return undefined;
    const colors = tradingColors(marketColorScheme);
    const chart = createChart(container, chartBaseOptions(container));
    const series = chart.addSeries(CandlestickSeries, {
      upColor: colors.up,
      downColor: colors.down,
      borderUpColor: colors.up,
      borderDownColor: colors.down,
      wickUpColor: colors.up,
      wickDownColor: colors.down,
      priceLineVisible: false,
    });
    const candles = bars.flatMap<CandlestickData<UTCTimestamp>>((bar) => {
      const time = utcTimestamp(bar.open_at);
      const open = Number(bar.open);
      const high = Number(bar.high);
      const low = Number(bar.low);
      const close = Number(bar.close);
      return time !== null && [open, high, low, close].every(Number.isFinite)
        ? [{ time, open, high, low, close }]
        : [];
    });
    series.setData(candles);

    const intervalSeconds = interval === "1m" ? 60 : 15 * 60;
    const firstTime = candles[0]?.time as number | undefined;
    const lastTime = candles.at(-1)?.time as number | undefined;
    const markers = fills.flatMap<SeriesMarker<UTCTimestamp>>((fill) => {
      const fillTime = utcTimestamp(String(fill.fill_time ?? ""));
      if (fillTime === null || firstTime === undefined || lastTime === undefined) return [];
      const aligned = Math.floor(fillTime / intervalSeconds) * intervalSeconds;
      if (aligned < firstTime || aligned > lastTime) return [];
      const kind = String(fill.action_kind ?? "");
      const entry = kind === "ENTRY";
      const markerBelow = entry ? direction === "LONG" : direction === "SHORT";
      return [{
        time: aligned as UTCTimestamp,
        position: markerBelow ? "belowBar" : "aboveBar",
        color: entry ? (direction === "LONG" ? colors.up : colors.down) : (direction === "LONG" ? colors.down : colors.up),
        shape: markerBelow ? "arrowUp" : "arrowDown",
        text: `${entry ? "入场" : kind === "TAKE_PROFIT" ? "止盈" : kind === "PROTECTION" ? "止损" : "退出"} ${String(fill.price ?? "")}`,
      }];
    });
    createSeriesMarkers(series, markers.sort((left, right) => Number(left.time) - Number(right.time)));

    const triggerActions = actions.filter((action) => ["PROTECTION", "TAKE_PROFIT"].includes(String(action.action_kind ?? "")));
    let takeProfitIndex = 0;
    triggerActions.forEach((action) => {
      const terms = typeof action.action_terms === "object" && action.action_terms !== null
        ? action.action_terms as Record<string, unknown>
        : {};
      const price = Number(terms.trigger_price);
      if (!Number.isFinite(price)) return;
      const protection = String(action.action_kind) === "PROTECTION";
      if (!protection) takeProfitIndex += 1;
      series.createPriceLine({
        price,
        color: protection ? "#D14343" : "#138A5B",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: `${protection ? "止损" : `止盈${takeProfitIndex}`} · ${String(action.state ?? "未知")}`,
      });
    });

    chart.subscribeCrosshairMove((param) => {
      const item = param.seriesData.get(series) as CandlestickData<UTCTimestamp> | undefined;
      if (!item || param.time === undefined) {
        setHoverText("移动光标查看 K 线价格");
        return;
      }
      setHoverText(`${formatShanghaiTime(param.time)} · 开 ${formatChartPrice(item.open)}  高 ${formatChartPrice(item.high)}  低 ${formatChartPrice(item.low)}  收 ${formatChartPrice(item.close)}`);
    });
    chart.timeScale().fitContent();
    return () => destroyChart(chart);
  }, [actions, bars, direction, fills, interval, marketColorScheme]);

  return (
    <Box>
      <Typography className="mono" variant="caption" color="text.secondary" sx={{ display: "block", minHeight: 20, mb: 0.5 }}>{hoverText}</Typography>
      <Box
        ref={containerRef}
        role="group"
        aria-label={`${interval} K 线图，包含入场、退出、止损和止盈标记`}
        sx={{ height: { xs: 320, md: 430 }, width: "100%" }}
      />
    </Box>
  );
}

export function CumulativePnlChart({
  points,
  marketColorScheme,
}: {
  points: TrendPoint[];
  marketColorScheme: MarketColorScheme;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || points.length < 2) return undefined;
    const chart = createChart(container, { ...chartBaseOptions(container), height: 180 });
    const chronologicalPoints = [...points].sort((left, right) => Date.parse(left.at) - Date.parse(right.at));
    const uniquePoints = new Map<number, number>();
    chronologicalPoints.forEach((point) => {
      const time = utcTimestamp(point.at);
      if (time !== null && Number.isFinite(point.value)) uniquePoints.set(time, point.value);
    });
    const data = [...uniquePoints.entries()].map(([time, value]) => ({ time: time as UTCTimestamp, value }));
    const finalValue = data.at(-1)?.value ?? 0;
    const colors = tradingColors(marketColorScheme);
    const series = chart.addSeries(LineSeries, {
      color: finalValue >= 0 ? colors.up : colors.down,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    series.setData(data);
    chart.timeScale().fitContent();
    return () => destroyChart(chart);
  }, [marketColorScheme, points]);

  return <Box ref={containerRef} role="group" aria-label="近期已闭合交易累计净盈亏趋势" sx={{ height: 180, width: "100%" }} />;
}
