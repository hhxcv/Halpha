import {
  Alert,
  Box,
  Tooltip,
  Typography,
} from "@mui/material";
import type { ReactNode } from "react";

import {
  MarketToneText,
  marketToneForSignedValue,
  type MarketColorScheme,
} from "../marketColors";
import {
  LOSS_STREAK_ALERT_THRESHOLD,
  summarizeAccountAndStrategyPerformance,
  type ReviewPerformanceTrade,
} from "../reviewPerformanceSummary";
import { surfaceFrameSx } from "../theme";
import { CumulativePnlChart } from "./ReviewCharts";

export type ReviewPerformanceOverviewTrade = ReviewPerformanceTrade & {
  closedAt: string;
};

function signedUsdt(value: number | null | undefined): string {
  if (!Number.isFinite(value)) return "未知";
  const normalized = Math.abs(value as number) < 0.0000005 ? 0 : value as number;
  return `${new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
    signDisplay: "exceptZero",
  }).format(normalized)} USDT`;
}

function unsignedUsdt(value: number | null | undefined): string {
  if (!Number.isFinite(value)) return "未知";
  return `${new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 6,
  }).format(value as number)} USDT`;
}

function percent(value: number): string {
  return `${new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 1,
  }).format(value)}%`;
}

function signedReturnPercent(value: number | null | undefined): string {
  if (!Number.isFinite(value)) return "未知";
  const normalized = Math.abs(value as number) < 0.00005 ? 0 : value as number;
  return `${new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
    signDisplay: "exceptZero",
  }).format(normalized)}%`;
}

function profitLossRatio(grossProfit: number, grossLoss: number): string {
  if (grossLoss > 0) {
    return `${new Intl.NumberFormat("zh-CN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 3,
    }).format(grossProfit / grossLoss)} : 1`;
  }
  return grossProfit > 0 ? "无累计亏损" : "无可比结果";
}

export default function ReviewPerformanceOverview({
  tradesInClosingOrder,
  marketColorScheme,
  chartAttribution,
}: {
  tradesInClosingOrder: ReviewPerformanceOverviewTrade[];
  marketColorScheme: MarketColorScheme;
  chartAttribution: ReactNode;
}) {
  const { account: accountSummary, strategy: strategySummary } =
    summarizeAccountAndStrategyPerformance(tradesInClosingOrder);
  let cumulative = 0;
  const trendPoints = tradesInClosingOrder.map((trade) => {
    cumulative += trade.netPnl;
    return { at: trade.closedAt, value: cumulative };
  });
  const lossStreakAlert = (
    strategySummary.currentStreakKind === "LOSS"
    && strategySummary.currentStreakCount >= LOSS_STREAK_ALERT_THRESHOLD
  );
  const streakLabel = strategySummary.currentStreakKind === "WIN"
    ? "策略当前连盈"
    : strategySummary.currentStreakKind === "LOSS"
      ? "策略当前连亏"
      : "策略连续结果";

  return (
    <Box sx={{ ...surfaceFrameSx, p: { xs: 1.5, sm: 2 }, mb: 2 }}>
      <Box sx={{
        display: "grid",
        gridTemplateColumns: trendPoints.length >= 2
          ? {
            xs: "minmax(0, 1fr)",
            lg: "minmax(0, 1.35fr) minmax(400px, .65fr)",
          }
          : "minmax(0, 1fr)",
        gap: { xs: 1.5, lg: 2 },
        alignItems: "stretch",
      }}>
        <Box sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "repeat(2, minmax(0, 1fr))",
            sm: "repeat(3, minmax(0, 1fr))",
            md: "repeat(5, minmax(0, 1fr))",
            lg: "repeat(3, minmax(0, 1fr))",
            xl: "repeat(5, minmax(0, 1fr))",
          },
          gridAutoRows: "minmax(60px, 1fr)",
          gap: 0.5,
        }}>
          {[
            { label: "账户完整闭合", value: `${accountSummary.tradeCount} 笔` },
            {
              label: "账户累计净盈亏",
              value: signedUsdt(accountSummary.netPnl),
              tone: marketToneForSignedValue(accountSummary.netPnl),
            },
            {
              label: "账户累计净回报",
              value: signedReturnPercent(accountSummary.notionalReturnPercent),
              tone: marketToneForSignedValue(accountSummary.notionalReturnPercent),
              help: accountSummary.notionalReturnPercent === null
                ? `需要每笔完整闭合交易都有可靠的正入场成交额；当前覆盖 ${accountSummary.entryNotionalTradeCount}/${accountSummary.tradeCount} 笔。不会用部分样本替代。`
                : `账户累计净盈亏 ÷ 全部可靠闭合交易的入场成交额合计；当前分母 ${unsignedUsdt(accountSummary.totalEntryNotional)}。保留验证性交易和工具问题造成的真实账户结果，但不是账户权益或保证金收益率。`,
            },
            {
              label: "策略样本",
              value: `${strategySummary.tradeCount} 笔`,
              help: "只包含“可用交易样本”“交易决策需改进”和兼容的历史“符合预期”；验证性交易、工具问题影响、待评价和证据不足不进入策略统计。",
            },
            {
              label: "策略单笔净期望",
              value: signedUsdt(strategySummary.averageNetPnl),
              tone: marketToneForSignedValue(strategySummary.averageNetPnl),
              help: "合格策略样本累计净盈亏 ÷ 策略样本数；是费用后的历史平均结果，不是未来收益预测。",
            },
            {
              label: "策略累计盈亏比",
              value: profitLossRatio(strategySummary.grossProfit, strategySummary.grossLoss),
              help: "合格策略样本累计盈利净额 ÷ 累计亏损净额绝对值。",
            },
            {
              label: "策略胜率",
              value: strategySummary.tradeCount
                ? percent(strategySummary.wins / strategySummary.tradeCount * 100)
                : "未知",
            },
            {
              label: "账户最大回撤",
              value: signedUsdt(-accountSummary.maximumDrawdown),
              tone: marketToneForSignedValue(-accountSummary.maximumDrawdown),
              help: "按全部可靠闭合交易的真实账户净结果依次累加，从此前最高点到后续最低点的最大下降；起始值按 0 计算。",
            },
            {
              label: streakLabel,
              value: strategySummary.currentStreakCount > 0
                ? `${strategySummary.currentStreakCount} 笔`
                : "无",
              tone: strategySummary.currentStreakKind === "LOSS"
                ? marketToneForSignedValue(-1)
                : strategySummary.currentStreakKind === "WIN"
                  ? marketToneForSignedValue(1)
                  : undefined,
              help: "只按最近一段合格策略样本的净结果统计；方向改变或持平会结束当前连续结果。",
            },
            { label: "账户累计手续费", value: unsignedUsdt(accountSummary.commissions) },
          ].map((item) => (
            <Box
              key={item.label}
              sx={{
                px: 1.25,
                py: 0.75,
                display: "flex",
                flexDirection: "column",
                justifyContent: "center",
              }}
            >
              {item.help
                ? (
                  <Tooltip title={item.help} arrow>
                    <Typography
                      component="span"
                      tabIndex={0}
                      variant="caption"
                      color="text.secondary"
                      sx={{
                        alignSelf: "flex-start",
                        cursor: "help",
                        textDecoration: "underline dotted",
                        textUnderlineOffset: 2,
                      }}
                    >
                      {item.label}
                    </Typography>
                  </Tooltip>
                )
                : (
                  <Typography variant="caption" color="text.secondary">
                    {item.label}
                  </Typography>
                )}
              <Typography className="mono" sx={{ mt: 0.25, fontWeight: 750 }}>
                <MarketToneText tone={item.tone}>{item.value}</MarketToneText>
              </Typography>
            </Box>
          ))}
        </Box>

        {trendPoints.length >= 2 && (
          <Box sx={{ minWidth: 0, display: "flex", flexDirection: "column" }}>
            <CumulativePnlChart
              points={trendPoints}
              marketColorScheme={marketColorScheme}
            />
            {chartAttribution}
          </Box>
        )}

        {lossStreakAlert && (
          <Alert
            severity="warning"
            variant="outlined"
            sx={{
              gridColumn: "1 / -1",
              py: 0,
              "& .MuiAlert-message": { py: 0.5 },
            }}
          >
            合格策略样本连续亏损 {strategySummary.currentStreakCount} 笔，已触发连续亏损提醒；新的合格策略样本净结果大于或等于零时自动解除。
          </Alert>
        )}
      </Box>
    </Box>
  );
}
