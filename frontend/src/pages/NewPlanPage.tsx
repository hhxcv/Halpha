import { Fragment, useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  Collapse,
  FormControlLabel,
  IconButton,
  LinearProgress,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import { InfoOutlined, RefreshOutlined } from "@mui/icons-material";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useOutletContext, useParams, useSearchParams } from "react-router";

import {
  ApiFailure,
  createPlan,
  getMarketContext,
  getPlan,
  getStrategies,
  type PlanCreatePayload,
  type PlanDraftPayload,
  type OrderScheduleSpec,
  type SettingsStatus,
  type StrategySummary,
  updatePlan,
} from "../api/client";
import PageHeader from "../components/PageHeader";
import FactGrid from "../components/FactGrid";
import OrderScheduleEditor, {
  createDefaultOrderScheduleSpec,
} from "../components/OrderScheduleEditor";
import StrategyIntroduction from "../components/StrategyIntroduction";
import { closedBarBreakoutGapPercent, entryExtensionBoundary, formatUserVisibleTime, gapPercent, marketPrice, marketVolume } from "../format";
import {
  MarketToneText,
  marketToneClassName,
  marketToneForDirection,
  type MarketColorScheme,
} from "../marketColors";
import {
  expectedMarketSourceForEnvironment,
  isMarketSourceForEnvironment,
  isUsableExecutionQuote,
  usePublicMarketStream,
  type MarketInterval,
  type MarketStreamClientStatus,
} from "../marketStream";
import { surfaceFrameSx } from "../theme";


type Direction = "LONG" | "SHORT";
type PlanCreatorKind = "HUMAN" | "AI";
type StrategyDirectionFilter = "ALL" | Direction;
type StrategySort = "NAME_ASC" | "NAME_DESC" | "VERSION_DESC";

const DIRECT_EXECUTION_REF = "DIRECT_EXECUTION@1";

function marketStreamStatusText(status: MarketStreamClientStatus): string {
  if (status === "LIVE") return "实时";
  if (status === "STALE") return "已过期";
  if (status === "RECONNECTING") return "重连中";
  if (status === "CONNECTING") return "连接中";
  if (status === "FAILED") return "实时流不可用";
  return "实时流未启用";
}

function marketStreamStatusColor(
  status: MarketStreamClientStatus,
): "success" | "warning" | "error" | "default" {
  if (status === "LIVE") return "success";
  if (status === "STALE" || status === "RECONNECTING") return "warning";
  if (status === "FAILED") return "error";
  return "default";
}

type StrategyParameters = {
  direction: Direction;
  demo_immediate_entry: boolean;
  channel_lookback_15m: number;
  confirmation_bars_1m: number;
  entry_valid_minutes: number;
  initial_stop_atr_multiple: string;
  max_entry_extension_atr: string;
  max_hold_bars_15m: number;
  take_profit_1_fraction: string;
  take_profit_1_r: string;
  take_profit_2_r: string;
};

const DEFAULT_PARAMETERS: StrategyParameters = {
  direction: "LONG",
  demo_immediate_entry: false,
  channel_lookback_15m: 20,
  confirmation_bars_1m: 2,
  entry_valid_minutes: 60,
  initial_stop_atr_multiple: "1.5",
  max_entry_extension_atr: "0.5",
  max_hold_bars_15m: 4,
  take_profit_1_fraction: "0.5",
  take_profit_1_r: "1.5",
  take_profit_2_r: "3.0",
};


const strategySortLabels: Record<StrategySort, string> = {
  NAME_ASC: "策略名称 A–Z",
  NAME_DESC: "策略名称 Z–A",
  VERSION_DESC: "策略版本（新到旧）",
};


function StrategySelection({
  strategies,
  loading,
  failed,
  onSelect,
  onSelectDirect,
  onCancel,
}: {
  strategies: StrategySummary[];
  loading: boolean;
  failed: boolean;
  onSelect: (strategyId: string) => void;
  onSelectDirect: () => void;
  onCancel: () => void;
}) {
  const [search, setSearch] = useState("");
  const [direction, setDirection] = useState<StrategyDirectionFilter>("ALL");
  const [sort, setSort] = useState<StrategySort>("NAME_ASC");
  const [expandedStrategyId, setExpandedStrategyId] = useState<string | null>(null);
  const normalizedSearch = search.trim().toLocaleLowerCase("zh-CN");
  const visibleStrategies = strategies
    .filter((strategy) => {
      const matchesSearch = normalizedSearch.length === 0 || [
        strategy.display_name,
        strategy.strategy_id,
        strategy.value_logic,
        strategy.applicable_scenarios,
        strategy.execution_behavior,
      ].some((value) => value.toLocaleLowerCase("zh-CN").includes(normalizedSearch));
      const matchesDirection = direction === "ALL"
        || strategy.supported_directions.includes(direction);
      return matchesSearch && matchesDirection;
    })
    .sort((left, right) => {
      if (sort === "VERSION_DESC") {
        const byVersion = right.strategy_version.localeCompare(left.strategy_version, "zh-CN", { numeric: true });
        if (byVersion !== 0) return byVersion;
      }
      const byName = left.display_name.localeCompare(right.display_name, "zh-CN", { numeric: true });
      return sort === "NAME_DESC" ? -byName : byName;
    });
  const filtersActive = normalizedSearch.length > 0 || direction !== "ALL" || sort !== "NAME_ASC";
  const resetFilters = () => {
    setSearch("");
    setDirection("ALL");
    setSort("NAME_ASC");
  };

  return (
    <Box sx={{ width: "min(1040px, calc(100% - clamp(32px, 4vw, 48px)))", mx: "auto", py: { xs: 2.5, sm: 3 } }}>
      <PageHeader
        eyebrow="新建交易计划 · 第 1 步 / 2"
        title="选择执行依据"
        description="可以让策略产生入场决定，也可以直接定义一组不可变订单；两种方式都经过相同的资金边界、确认与启动流程。"
      />
      <Box
        component="section"
        aria-labelledby="direct-execution-title"
        sx={{ ...surfaceFrameSx, p: { xs: 1.75, sm: 2 }, mb: 2, borderColor: "primary.main" }}
      >
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" } }}>
          <Box>
            <Typography id="direct-execution-title" variant="h2">直接执行订单计划</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: .5, maxWidth: 680 }}>
              不等待策略信号。自行配置市价或限价、区间档位、金额分布、组合条件、逐成交止损止盈，以及到期或短时异动撤单。
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: .75 }}>
              当前仅开放已具备运行时消费者的串行受保护模式；预览不会提交订单。
            </Typography>
          </Box>
          <Button variant="contained" onClick={onSelectDirect}>配置订单计划</Button>
        </Stack>
      </Box>
      {loading && <LinearProgress aria-label="正在读取策略列表" />}
      {failed && <Alert severity="warning">策略列表当前不可用；仍可使用上方的直接执行订单计划。</Alert>}

      {!failed && <>
        <Box component="section" aria-label="策略筛选与排序" sx={{ ...surfaceFrameSx, p: { xs: 1.5, sm: 2 }, mb: 1.5 }}>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "minmax(240px, 1.6fr) minmax(150px, .8fr) minmax(190px, 1fr)" }, gap: 1.25 }}>
            <TextField
              size="small"
              label="筛选策略"
              placeholder="名称、标识、逻辑或适用场景"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <TextField
              select
              size="small"
              label="支持方向"
              value={direction}
              onChange={(event) => setDirection(event.target.value as StrategyDirectionFilter)}
            >
              <MenuItem value="ALL">全部方向</MenuItem>
              <MenuItem value="LONG">做多</MenuItem>
              <MenuItem value="SHORT">做空</MenuItem>
            </TextField>
            <TextField
              select
              size="small"
              label="排序"
              value={sort}
              onChange={(event) => setSort(event.target.value as StrategySort)}
            >
              {(Object.entries(strategySortLabels) as Array<[StrategySort, string]>).map(([value, label]) => (
                <MenuItem key={value} value={value}>{label}</MenuItem>
              ))}
            </TextField>
          </Box>
          <Stack direction="row" spacing={1.5} sx={{ mt: 1, alignItems: "center", justifyContent: "space-between" }}>
            <Typography variant="caption" color="text.secondary" role="status">
              匹配 {visibleStrategies.length} / {strategies.length} 个策略
            </Typography>
            <Button size="small" variant="outlined" disabled={!filtersActive} onClick={resetFilters}>重置筛选</Button>
          </Stack>
        </Box>

        <TableContainer className="table-scroll" role="region" aria-label="可用策略列表" tabIndex={0} sx={{ ...surfaceFrameSx, overflowX: "auto" }}>
          <Table size="small" aria-label="选择交易策略">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: 40, px: .5 }}>
                  <Box component="span" sx={{ position: "absolute", width: "1px", height: "1px", p: 0, m: -1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap", border: 0 }}>
                    策略介绍
                  </Box>
                </TableCell>
                <TableCell>策略</TableCell>
                <TableCell align="right" sx={{ width: { xs: 112, sm: 128 } }}>操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {visibleStrategies.map((strategy) => {
                const expanded = expandedStrategyId === strategy.strategy_id;
                const directionLabels = strategy.supported_directions
                  .map((item) => item === "LONG" ? "做多" : item === "SHORT" ? "做空" : item)
                  .join(" / ");
                return <Fragment key={strategy.strategy_id}>
                  <TableRow
                    hover
                    tabIndex={0}
                    aria-label={`选择策略：${strategy.display_name}`}
                    onClick={() => onSelect(strategy.strategy_id)}
                    onKeyDown={(event) => {
                      if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) {
                        event.preventDefault();
                        onSelect(strategy.strategy_id);
                      }
                    }}
                    sx={{ cursor: "pointer", "&:focus-visible": { bgcolor: "action.hover" } }}
                  >
                    <TableCell sx={{ width: 40, px: .5 }}>
                      <IconButton
                        size="small"
                        aria-label={`${expanded ? "收起" : "展开"}${strategy.display_name}策略介绍`}
                        aria-expanded={expanded}
                        aria-controls={`strategy-introduction-${strategy.strategy_id}`}
                        onClick={(event) => {
                          event.stopPropagation();
                          setExpandedStrategyId(expanded ? null : strategy.strategy_id);
                        }}
                        sx={{ width: 32, height: 32, border: 0, bgcolor: "transparent", fontSize: 18 }}
                      >
                        <Box component="span" aria-hidden="true" sx={{ lineHeight: 1 }}>{expanded ? "▾" : "▸"}</Box>
                      </IconButton>
                    </TableCell>
                    <TableCell sx={{ py: 1.5 }}>
                      <Typography sx={{ fontWeight: 750 }}>{strategy.display_name}</Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: .25, overflowWrap: "anywhere" }}>
                        {strategy.strategy_id} · v{strategy.strategy_version} · {directionLabels || "方向未声明"}
                      </Typography>
                    </TableCell>
                    <TableCell align="right" sx={{ py: 1 }}>
                      <Stack direction="row" spacing={.5} sx={{ justifyContent: "flex-end" }}>
                        <Button
                          size="small"
                          variant="outlined"
                          onClick={(event) => {
                            event.stopPropagation();
                            onSelect(strategy.strategy_id);
                          }}
                        >
                          配置策略
                        </Button>
                      </Stack>
                    </TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell colSpan={3} sx={{ p: 0, borderBottom: expanded ? undefined : 0 }}>
                      <Collapse in={expanded} timeout="auto" unmountOnExit>
                        <Box id={`strategy-introduction-${strategy.strategy_id}`} sx={{ px: { xs: 1.5, sm: 2 }, pb: 2, bgcolor: "background.default" }}>
                          <StrategyIntroduction strategy={strategy} embedded />
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </Fragment>;
              })}
              {!loading && visibleStrategies.length === 0 && (
                <TableRow>
                  <TableCell colSpan={3} sx={{ py: 5, textAlign: "center" }}>
                    <Typography sx={{ fontWeight: 700 }}>没有匹配的策略</Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mt: .5, mb: 1 }}>调整关键词或方向后重试。</Typography>
                    <Button size="small" onClick={resetFilters}>清除筛选</Button>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </>}

      <Button variant="outlined" onClick={onCancel} sx={{ mt: 2 }}>取消</Button>
    </Box>
  );
}


function numberInRange(value: string | number, minimum: number, maximum: number): boolean {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= minimum && parsed <= maximum;
}


function integerInRange(value: number, minimum: number, maximum: number): boolean {
  return Number.isInteger(value) && value >= minimum && value <= maximum;
}


export default function NewPlanPage() {
  const navigate = useNavigate();
  const { status, marketColorScheme } = useOutletContext<{
    status: SettingsStatus;
    marketColorScheme: MarketColorScheme;
  }>();
  const { planId } = useParams();
  const [searchParams] = useSearchParams();
  const sourcePlanId = searchParams.get("copyFrom");
  const editing = Boolean(planId);
  const copying = Boolean(!editing && sourcePlanId);
  const loadedPlanId = planId ?? sourcePlanId;
  const [creationStep, setCreationStep] = useState<"strategy" | "configuration">("strategy");
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null);
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: getStrategies });
  const draft = useQuery({
    queryKey: ["plan", loadedPlanId],
    queryFn: () => getPlan(loadedPlanId ?? ""),
    enabled: Boolean(loadedPlanId),
  });
  const draftBasis = draft.data?.content.decision_basis;
  const selectedBasisRef = draftBasis?.decision_basis_ref
    ?? draft.data?.content.strategy_id
    ?? selectedStrategyId
    ?? "";
  const directExecution = draftBasis?.kind === "DIRECT_EXECUTION"
    || selectedBasisRef === DIRECT_EXECUTION_REF;
  const strategyId = directExecution ? "" : selectedBasisRef;
  const selectingStrategy = !editing && !copying && creationStep === "strategy";
  const selectedStrategy = strategies.data?.find((strategy) => strategy.strategy_id === strategyId);
  const [planName, setPlanName] = useState("");
  const [creatorKind, setCreatorKind] = useState<PlanCreatorKind>("HUMAN");
  const [parameters, setParameters] = useState<StrategyParameters>(DEFAULT_PARAMETERS);
  const [instrument, setInstrument] = useState("BTCUSDT-PERP");
  const [tradeAmount, setTradeAmount] = useState("500");
  const [validMinutes, setValidMinutes] = useState("60");
  const [orderSchedule, setOrderSchedule] = useState<OrderScheduleSpec>(() => (
    createDefaultOrderScheduleSpec()
  ));
  const [chartInterval, setChartInterval] = useState<MarketInterval>("15m");
  const directReferenceSeededRef = useRef(false);
  const directReferenceSeedValueRef = useRef<string | null>(null);
  const [orderScheduleReady, setOrderScheduleReady] = useState(false);
  const handleOrderScheduleValidation = useCallback((ready: boolean) => {
    setOrderScheduleReady(ready);
  }, []);
  const channelLookbackValid = integerInRange(parameters.channel_lookback_15m, 4, 96);
  const expectedMarketSource = expectedMarketSourceForEnvironment(
    status.environment_kind,
  );
  const environmentScope = `${status.environment_kind}:${status.environment_id}`;
  const market = useQuery({
    queryKey: [
      "market-context",
      environmentScope,
      expectedMarketSource,
      instrument,
      parameters.channel_lookback_15m,
    ],
    queryFn: () => getMarketContext(instrument, parameters.channel_lookback_15m),
    enabled: !selectingStrategy
      && (directExecution || Boolean(strategyId))
      && channelLookbackValid,
    retry: 1,
    retryDelay: 2_000,
  });
  const marketStream = usePublicMarketStream(
    !selectingStrategy && directExecution,
    instrument,
    chartInterval,
    environmentScope,
    expectedMarketSource,
  );
  const recoveredMarketGenerationRef = useRef(0);
  useEffect(() => {
    recoveredMarketGenerationRef.current = 0;
    directReferenceSeededRef.current = false;
    const seededPrice = directReferenceSeedValueRef.current;
    directReferenceSeedValueRef.current = null;
    setOrderScheduleReady(false);
    if (seededPrice === null) return;
    setOrderSchedule((current) => (
      current.price_distribution.kind === "SINGLE"
      && current.price_distribution.limit_price === seededPrice
        ? {
          ...current,
          price_distribution: {
            ...current.price_distribution,
            limit_price: "",
          },
        }
        : current
    ));
  }, [environmentScope]);
  useEffect(() => {
    if (!directExecution) {
      recoveredMarketGenerationRef.current = 0;
      return;
    }
    if (marketStream.generation <= recoveredMarketGenerationRef.current) return;
    recoveredMarketGenerationRef.current = marketStream.generation;
    void market.refetch();
  }, [directExecution, market.refetch, marketStream.generation]);

  useEffect(() => {
    const source = draft.data?.content;
    if (!source) return;
    const sourceParameters = source.decision_basis?.parameters
      ?? source.parameters
      ?? {};
    setParameters({
      ...DEFAULT_PARAMETERS,
      ...sourceParameters,
      direction: source.direction as Direction,
    } as StrategyParameters);
    if (source.order_schedule_spec) {
      setOrderSchedule(source.order_schedule_spec);
      setOrderScheduleReady(false);
    }
    setInstrument(source.instrument_ref);
    setTradeAmount(source.requested_limits.max_notional);
    setPlanName(editing
      ? source.plan_name ?? ""
      : `${source.plan_name?.trim() || "未命名计划"} 副本`.slice(0, 80));
    const duration = Math.round(
      (Date.parse(source.valid_until) - Date.parse(source.valid_from)) / 60_000,
    );
    if (Number.isFinite(duration) && duration > 0) setValidMinutes(String(duration));
  }, [draft.data?.content_digest, editing]);

  const update = <K extends keyof StrategyParameters>(key: K, value: StrategyParameters[K]) => {
    setParameters((current) => ({ ...current, [key]: value }));
  };
  const updateDirectTradeAmount = (nextAmount: string) => {
    const previousAmount = Number(tradeAmount);
    const distribution = orderSchedule.amount_distribution;
    const pricePlan = orderSchedule.price_distribution;
    const baseNotional = Number(distribution.base_notional);
    const shouldSyncSingle = pricePlan.kind === "SINGLE"
      && distribution.mode === "FIXED"
      && Number.isFinite(previousAmount)
      && Math.abs(baseNotional - previousAmount) <= Math.max(1, Math.abs(previousAmount)) * 1e-9;
    const shouldSyncLadder = pricePlan.kind === "LADDER"
      && distribution.mode === "FIXED"
      && Number.isFinite(previousAmount)
      && Math.abs(baseNotional * pricePlan.level_count - previousAmount)
        <= Math.max(1, Math.abs(previousAmount)) * 1e-9;
    setTradeAmount(nextAmount);
    if (!shouldSyncSingle && !shouldSyncLadder) return;
    const nextNumeric = Number(nextAmount);
    const nextBase = shouldSyncLadder && Number.isFinite(nextNumeric)
      && pricePlan.kind === "LADDER"
      && Number.isInteger(pricePlan.level_count)
      && pricePlan.level_count > 0
      ? String(Number((nextNumeric / pricePlan.level_count).toFixed(8)))
      : nextAmount;
    setOrderSchedule((current) => ({
      ...current,
      amount_distribution: {
        ...current.amount_distribution,
        base_notional: nextBase,
      },
    }));
    setOrderScheduleReady(false);
  };
  const selectStrategy = (nextStrategyId: string) => {
    if (nextStrategyId !== selectedStrategyId) setParameters(DEFAULT_PARAMETERS);
    setSelectedStrategyId(nextStrategyId);
    setCreationStep("configuration");
  };
  const selectDirectExecution = () => {
    setSelectedStrategyId(DIRECT_EXECUTION_REF);
    setParameters(DEFAULT_PARAMETERS);
    setOrderSchedule(createDefaultOrderScheduleSpec());
    setPlanName((current) => current.trim()
      ? current
      : `BTCUSDT 直接执行 ${formatUserVisibleTime(new Date().toISOString())}`.slice(0, 80));
    directReferenceSeededRef.current = false;
    directReferenceSeedValueRef.current = null;
    setOrderScheduleReady(false);
    setCreationStep("configuration");
  };
  const confirmationBarsValid = integerInRange(parameters.confirmation_bars_1m, 1, 3);
  const entryValidityValid = integerInRange(parameters.entry_valid_minutes, 15, 10080);
  const maxHoldingBarsValid = integerInRange(parameters.max_hold_bars_15m, 4, 672);
  const planValidityValid = numberInRange(validMinutes, 15, 10080)
    && Number.isInteger(Number(validMinutes));
  const normalizedPlanName = planName.trim();
  const planNameValid = normalizedPlanName.length > 0 && normalizedPlanName.length <= 80;
  const tradeAmountValid = Number(tradeAmount) > 0 && Number.isFinite(Number(tradeAmount));
  const initialStopValid = numberInRange(parameters.initial_stop_atr_multiple, 1, 3);
  const maxExtensionValid = numberInRange(parameters.max_entry_extension_atr, .1, 1);
  const takeProfitFractionValid = numberInRange(parameters.take_profit_1_fraction, .25, .75);
  const takeProfit1Valid = numberInRange(parameters.take_profit_1_r, 1, 3);
  const takeProfit2Valid = numberInRange(parameters.take_profit_2_r, 2, 6);
  const takeProfitOrderValid = takeProfit1Valid
    && takeProfit2Valid
    && Number(parameters.take_profit_2_r) > Number(parameters.take_profit_1_r);
  const strategyParameterRangesValid = channelLookbackValid
    && confirmationBarsValid
    && entryValidityValid
    && maxHoldingBarsValid
    && initialStopValid
    && maxExtensionValid
    && takeProfitFractionValid
    && takeProfitOrderValid;
  const configurationValid = planValidityValid
    && tradeAmountValid
    && (directExecution ? orderScheduleReady : strategyParameterRangesValid);
  const marketSourceMismatch = Boolean(
    market.data
    && !isMarketSourceForEnvironment(
      market.data.source,
      status.environment_kind,
    ),
  );
  const currentMarket = market.data?.channel_lookback_15m === parameters.channel_lookback_15m
    && !marketSourceMismatch
    ? market.data
    : undefined;
  useEffect(() => {
    if (
      directReferenceSeededRef.current
      || !directExecution
      || editing
      || copying
      || !currentMarket?.reference_price
    ) {
      return;
    }
    directReferenceSeededRef.current = true;
    if (
      orderSchedule.price_distribution.kind !== "SINGLE"
      || orderSchedule.venue_policy.order_type !== "LIMIT"
      || orderSchedule.venue_policy.price_match !== null
      || orderSchedule.price_distribution.limit_price?.trim()
    ) {
      return;
    }
    setOrderSchedule({
      ...orderSchedule,
      price_distribution: {
        ...orderSchedule.price_distribution,
        limit_price: currentMarket.reference_price,
      },
    });
    directReferenceSeedValueRef.current = currentMarket.reference_price;
    setOrderScheduleReady(false);
  }, [
    copying,
    currentMarket?.reference_price,
    directExecution,
    editing,
    orderSchedule,
  ]);
  const marketContextRefreshing = channelLookbackValid && market.isFetching;
  const selectedBreakoutGap = currentMarket
    ? parameters.direction === "LONG"
      ? currentMarket.long_breakout_gap_pct
      : currentMarket.short_breakout_gap_pct
    : null;
  const selectedClosedBarBreakoutGap = currentMarket
    ? closedBarBreakoutGapPercent(
      parameters.direction,
      currentMarket.latest_close_1m,
      parameters.direction === "LONG" ? currentMarket.channel_upper : currentMarket.channel_lower,
    )
    : "";
  const currentSpread = currentMarket
    ? String(Number(currentMarket.ask_price) - Number(currentMarket.bid_price))
    : "";
  const usableLiveQuote = isUsableExecutionQuote(
    marketStream.quote,
    expectedMarketSource,
    Date.now(),
  )
    ? marketStream.quote
    : null;
  const visibleReferencePrice = usableLiveQuote?.reference_price
    ?? currentMarket?.reference_price
    ?? null;
  const visibleBidPrice = usableLiveQuote?.bid_price
    ?? currentMarket?.bid_price
    ?? null;
  const visibleAskPrice = usableLiveQuote?.ask_price
    ?? currentMarket?.ask_price
    ?? null;
  const visibleSourceCutoff = usableLiveQuote?.source_cutoff
    ?? currentMarket?.source_cutoff
    ?? null;
  const visibleSpread = visibleBidPrice && visibleAskPrice
    ? String(Number(visibleAskPrice) - Number(visibleBidPrice))
    : null;
  const currentSpreadBps = currentMarket
    ? Number(currentSpread) / Number(currentMarket.reference_price) * 10_000
    : Number.NaN;
  const selectedChannelBoundary = currentMarket
    ? parameters.direction === "LONG"
      ? currentMarket.channel_upper
      : currentMarket.channel_lower
    : "";
  const entryExtensionLimit = currentMarket
    ? entryExtensionBoundary(
      parameters.direction,
      selectedChannelBoundary,
      currentMarket.atr_14,
      parameters.max_entry_extension_atr,
    )
    : null;
  const latestClose1m = currentMarket ? Number(currentMarket.latest_close_1m) : Number.NaN;
  const latestClosedBarBeyondBoundary = currentMarket
    ? parameters.direction === "LONG"
      ? latestClose1m > Number(currentMarket.channel_upper)
      : latestClose1m < Number(currentMarket.channel_lower)
    : false;
  const latestClosedBarBeyondExtension = Number.isFinite(latestClose1m)
    && entryExtensionLimit !== null
    && (parameters.direction === "LONG"
      ? latestClose1m > entryExtensionLimit
      : latestClose1m < entryExtensionLimit);
  const mutation = useMutation({
    mutationFn: () => {
      const commonPayload = {
        plan_name: normalizedPlanName,
        venue_ref: "BINANCE_USDM",
        instrument_ref: instrument,
        direction: parameters.direction,
        target_exposure: tradeAmount,
        max_margin: tradeAmount,
        max_notional: tradeAmount,
        max_allowed_loss: tradeAmount,
        valid_minutes: Number(validMinutes),
      };
      const payload: PlanDraftPayload = directExecution
        ? {
            ...commonPayload,
            decision_basis: {
              kind: "DIRECT_EXECUTION",
              decision_basis_ref: DIRECT_EXECUTION_REF,
              parameters: {},
            },
            order_schedule_spec: orderSchedule,
          }
        : {
            ...commonPayload,
            strategy_id: strategyId,
            parameters,
          };
      return editing && draft.data
        ? updatePlan(draft.data.plan_id, draft.data.draft_version, payload)
        : createPlan({
          ...payload,
          creator_kind: creatorKind,
        } satisfies PlanCreatePayload);
    },
    onSuccess: () => navigate("/plans"),
  });

  const loading = (Boolean(loadedPlanId) && draft.isPending)
    || (!directExecution && strategies.isPending);
  const loadFailed = (Boolean(loadedPlanId) && draft.isError)
    || (!directExecution && strategies.isError)
    || (!loading && !selectingStrategy && !directExecution && !selectedStrategy);
  const mutationCode = mutation.error instanceof ApiFailure
    ? mutation.error.code
    : "结果未知";
  const mutationMessage = mutationCode === "PLAN_VERSION_CONFLICT"
    ? "草稿已被其他请求更新，请返回列表后重新打开。"
    : `${editing ? "草稿未更新" : "草稿未保存"}：${mutationCode}`;
  const canSubmit = !loading
    && !loadFailed
    && !mutation.isPending
    && !marketContextRefreshing
    && (!directExecution || !market.isError)
    && !marketSourceMismatch
    && expectedMarketSource !== null
    && configurationValid
    && planNameValid;
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!canSubmit) return;
    mutation.mutate();
  };
  const orderSettings = (
    <Box
      component="section"
      aria-labelledby="order-settings-title"
      sx={directExecution ? { ...surfaceFrameSx, p: { xs: 1.75, sm: 2 } } : undefined}
    >
      <Typography
        id="order-settings-title"
        variant={directExecution ? "h3" : "h2"}
        sx={{ mb: directExecution ? 1.5 : 2 }}
      >
        下单设置
      </Typography>
      <Box sx={{
        display: "grid",
        gridTemplateColumns: { xs: "1fr", sm: "repeat(2,minmax(0,1fr))" },
        gap: 2,
      }}>
        <TextField
          select
          label="方向"
          value={parameters.direction}
          onChange={(event) => update("direction", event.target.value as Direction)}
          sx={{ "& .MuiSelect-select": { color: parameters.direction === "LONG" ? "var(--halpha-market-up)" : "var(--halpha-market-down)", fontWeight: 750 } }}
        >
          <MenuItem value="LONG" className={marketToneClassName("up")}>做多</MenuItem>
          <MenuItem value="SHORT" className={marketToneClassName("down")}>做空</MenuItem>
        </TextField>
        <TextField label="交易对象" value={instrument} required helperText={`当前唯一${directExecution ? "订单计划" : "策略"}对象固定为 BTCUSDT-PERP`} slotProps={{ htmlInput: { readOnly: true } }} />
        <TextField label="交易金额（USDT）" value={tradeAmount} onChange={(event) => setTradeAmount(event.target.value)} error={!tradeAmountValid} required helperText={tradeAmountValid ? "该金额就是本计划的资金边界，启动时无需再次授权" : "必须填写大于 0 的金额"} />
        <TextField label="计划有效分钟" type="number" value={validMinutes} onChange={(event) => setValidMinutes(event.target.value)} error={!planValidityValid} helperText="范围 15–10080 分钟" slotProps={{ htmlInput: { min: 15, max: 10080, step: 1 } }} required />
      </Box>
      <Alert severity="warning" variant="outlined" sx={{ mt: directExecution ? 2 : 3 }}>
        交易金额限制本计划可新增的风险，但不是 Binance 资金冻结，也不能保证最终损失不会超过该值。
      </Alert>
    </Box>
  );

  if (selectingStrategy) {
    return <StrategySelection
      strategies={strategies.data ?? []}
      loading={strategies.isPending}
      failed={strategies.isError}
      onSelect={selectStrategy}
      onSelectDirect={selectDirectExecution}
      onCancel={() => navigate("/plans")}
    />;
  }

  if (directExecution) {
    const directBlockingReason = loadFailed
      ? "草稿或直接执行依据当前不可用。"
      : !planNameValid
        ? "在“计划选项”中填写有效计划名称。"
        : !tradeAmountValid
          ? "计划资金上限必须大于 0。"
          : !planValidityValid
            ? "在“计划选项”中填写 15–10080 分钟的有效期。"
            : market.isError
              ? "行情刷新失败；刷新成功并取得当前事实后才能保存。"
              : marketContextRefreshing
                ? "正在刷新当前行情并重新生成预览。"
                : !orderScheduleReady
                  ? "修正输入并等待当前版本的服务端预览通过。"
                  : null;
    const levelCount = orderSchedule.price_distribution.kind === "LADDER"
      ? orderSchedule.price_distribution.level_count
      : 1;
    const planOptions = (
      <Box
        component="details"
        sx={{
          "& > summary": {
            minHeight: 44,
            px: 1.5,
            py: 1.1,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 1,
            listStyle: "none",
            "&::-webkit-details-marker": { display: "none" },
          },
        }}
      >
        <Box component="summary">
          <Box sx={{ minWidth: 0 }}>
            <Typography component="h2" variant="subtitle2">计划选项</Typography>
            <Typography variant="caption" color="text.secondary" noWrap sx={{ display: "block" }}>
              {planName || "待命名"} · {validMinutes || "—"} 分钟
            </Typography>
          </Box>
          <Typography aria-hidden="true" color="text.secondary">⌄</Typography>
        </Box>
        <Stack spacing={1.25} sx={{ px: 1.5, pb: 1.5 }}>
          <TextField
            size="small"
            label="计划名称"
            value={planName}
            onChange={(event) => setPlanName(event.target.value)}
            error={planName.length > 0 && !planNameValid}
            helperText={planNameValid ? "自动生成，可按需修改" : "必填，最多 80 个字符"}
            slotProps={{ htmlInput: { maxLength: 80 } }}
            required
          />
          <Box sx={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: 1 }}>
            <TextField
              size="small"
              label="计划有效分钟"
              type="number"
              value={validMinutes}
              onChange={(event) => setValidMinutes(event.target.value)}
              error={!planValidityValid}
              slotProps={{ htmlInput: { min: 15, max: 10080, step: 1 } }}
              required
            />
            {!editing ? (
              <TextField
                select
                size="small"
                label="创建方式"
                value={creatorKind}
                onChange={(event) => setCreatorKind(event.target.value as PlanCreatorKind)}
                helperText="AI 代创建时须选择 AI 创建"
              >
                <MenuItem value="HUMAN">人工创建</MenuItem>
                <MenuItem value="AI">AI 创建</MenuItem>
              </TextField>
            ) : (
              <TextField
                size="small"
                label="创建来源"
                value={draft.data?.content.creator_kind === "AI" ? "AI 创建" : draft.data?.content.creator_kind === "HUMAN" ? "人工创建" : "未知"}
                slotProps={{ htmlInput: { readOnly: true } }}
              />
            )}
          </Box>
          <TextField
            size="small"
            label="执行依据"
            value={`${DIRECT_EXECUTION_REF} · 无策略信号`}
            slotProps={{ htmlInput: { readOnly: true } }}
          />
        </Stack>
      </Box>
    );
    const workspaceHeader = (
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", width: "100%", minWidth: 0 }}>
        <Stack direction="row" spacing={.25} sx={{ alignItems: "center", flex: "0 0 auto" }}>
          <Typography component="h1" variant="subtitle1" sx={{ fontWeight: 800 }}>直接执行</Typography>
          <Tooltip
            arrow
            title="直接执行不会再选择策略。保存只创建计划草稿；确认并启动后才会按固定档位和条件进入执行链路。"
          >
            <IconButton size="small" aria-label="了解直接执行与保存草稿">
              <InfoOutlined sx={{ fontSize: 16 }} />
            </IconButton>
          </Tooltip>
        </Stack>
        <Chip size="small" variant="outlined" label={instrument} />
        <Chip
          size="small"
          variant="outlined"
          label={status.environment_kind}
          sx={{ display: { xs: "none", sm: "inline-flex" } }}
        />
        <Tooltip
          arrow
          title={visibleSourceCutoff
            ? `公开行情截止 ${formatUserVisibleTime(visibleSourceCutoff)}；实时展示不替代保存与启动时的服务端核验。`
            : "公开实时行情尚未形成；规划仍使用服务端快照。"}
        >
          <Chip
            size="small"
            color={marketStreamStatusColor(marketStream.status)}
            variant="outlined"
            label={marketStreamStatusText(marketStream.status)}
            sx={marketStream.status === "LIVE" ? {
              color: "#166534",
              borderColor: "#86B69F",
              bgcolor: "#F0FDF4",
            } : undefined}
          />
        </Tooltip>
        <Stack
          direction="row"
          spacing={{ sm: 1.5, md: 2.25 }}
          sx={{ ml: "auto", alignItems: "center", minWidth: 0, overflow: "hidden" }}
        >
          <Box sx={{ display: { xs: "none", sm: "block" }, minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>中间价</Typography>
            <Typography className="mono" variant="body2" noWrap sx={{ fontWeight: 750 }}>
              {visibleReferencePrice ? marketPrice(visibleReferencePrice) : "未知"}
            </Typography>
          </Box>
          <Box sx={{ display: { xs: "none", sm: "block" }, minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>买一 / 卖一</Typography>
            <Typography className="mono" variant="body2" noWrap sx={{ fontWeight: 700 }}>
              {visibleBidPrice && visibleAskPrice
                ? `${marketPrice(visibleBidPrice)} / ${marketPrice(visibleAskPrice)}`
                : "未知"}
            </Typography>
          </Box>
          <Box sx={{ display: { xs: "none", md: "block" }, minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>价差</Typography>
            <Typography className="mono" variant="body2" noWrap sx={{ fontWeight: 700 }}>
              {visibleSpread ? `${marketPrice(visibleSpread)} USDT` : "未知"}
            </Typography>
          </Box>
          <Box sx={{ display: { xs: "none", lg: "block" }, minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>行情截止</Typography>
            <Typography variant="caption" noWrap>
              {visibleSourceCutoff ? formatUserVisibleTime(visibleSourceCutoff) : "未知"}
            </Typography>
          </Box>
        </Stack>
        <Tooltip title="刷新规划快照与订单预览" arrow>
          <span>
            <IconButton
              size="small"
              aria-label="刷新规划快照与订单预览"
              onClick={() => market.refetch()}
              disabled={!channelLookbackValid || market.isFetching}
            >
              <RefreshOutlined fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>
    );
    const quickControls = (
      <Box sx={{ px: 1.5, py: 1.35, borderBottom: 1, borderColor: "divider" }}>
        {loading ? <LinearProgress aria-label="正在读取直接执行计划" sx={{ mb: 1.25 }} /> : null}
        {loadFailed ? <Alert severity="error" sx={{ mb: 1.25 }}>草稿或直接执行依据当前不可用，不能编辑。</Alert> : null}
        {mutation.isError ? <Alert severity="error" sx={{ mb: 1.25 }}>{mutationMessage}</Alert> : null}
        {market.isError ? (
          <Alert severity={currentMarket ? "warning" : "error"} variant="outlined" sx={{ mb: 1.25 }}>
            {currentMarket
              ? `行情刷新失败；保留截至 ${formatUserVisibleTime(currentMarket.source_cutoff)} 的上次事实，需刷新成功后再保存。`
              : "当前行情不可用；参考价格和服务端预览不能据此视为安全。"}
          </Alert>
        ) : null}
        {marketSourceMismatch ? (
          <Alert severity="error" variant="outlined" sx={{ mb: 1.25 }}>
            行情来源与当前 {status.environment_kind} 环境不一致，已拒绝显示和预览；请核对运行配置后刷新。
          </Alert>
        ) : null}
        <Box sx={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: 1 }}>
          <ToggleButtonGroup
            exclusive
            fullWidth
            size="small"
            value={parameters.direction}
            aria-label="交易方向"
            onChange={(_event, next: Direction | null) => {
              if (!next || next === parameters.direction) return;
              setOrderScheduleReady(false);
              update("direction", next);
            }}
            sx={{ "& .MuiToggleButton-root": { minHeight: 40, py: .5, fontWeight: 800 } }}
          >
            <ToggleButton value="LONG">做多</ToggleButton>
            <ToggleButton value="SHORT">做空</ToggleButton>
          </ToggleButtonGroup>
          <TextField
            size="small"
            label="资金上限（USDT）"
            value={tradeAmount}
            onChange={(event) => updateDirectTradeAmount(event.target.value)}
            error={!tradeAmountValid}
            slotProps={{ htmlInput: { inputMode: "decimal" } }}
            required
          />
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: .75 }}>
          资金上限约束本计划新增风险，不是交易所冻结金额；实际下单额在下方单独配置。
        </Typography>
      </Box>
    );
    const footerControls = (
      <Stack spacing={.8}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between" }}>
          <Typography variant="caption" color="text.secondary">
            {levelCount} 档 · 资金上限 {tradeAmount || "—"} USDT
          </Typography>
          <Chip
            size="small"
            variant="outlined"
            color="default"
            label={orderScheduleReady ? "预览可保存" : "等待有效预览"}
            sx={{ fontWeight: 750 }}
          />
        </Stack>
        {directBlockingReason ? (
          <Typography variant="caption" color="text.secondary" aria-live="polite">
            {directBlockingReason}
          </Typography>
        ) : null}
        <Stack direction="row" spacing={1}>
          <Button
            type="submit"
            variant="contained"
            fullWidth
            disabled={!canSubmit}
            sx={{
              "&.Mui-disabled": {
                color: "#475569",
                bgcolor: "#E2E8F0",
              },
            }}
          >
            {mutation.isPending ? "正在保存…" : "保存并检查"}
          </Button>
          <Button variant="outlined" onClick={() => navigate("/plans")} sx={{ minWidth: 76 }}>取消</Button>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          仅保存计划草稿，不会提交订单；仍需在计划页确认并启动。
        </Typography>
      </Stack>
    );

    return (
      <Box
        component="form"
        onSubmit={handleSubmit}
        data-testid="direct-execution-workspace"
        sx={{
          width: "100%",
          height: { xs: "auto", md: "calc(100dvh - 64px)" },
          minHeight: { xs: "calc(100dvh - 96px)", md: 620 },
          overflow: { xs: "visible", md: "hidden" },
        }}
      >
        <OrderScheduleEditor
          value={orderSchedule}
          onChange={(next) => {
            setOrderScheduleReady(false);
            setOrderSchedule(next);
          }}
          environmentId={status.environment_id}
          environmentKind={status.environment_kind}
          instrumentRef={instrument}
          direction={parameters.direction}
          maxNotional={tradeAmount}
          referencePrice={currentMarket?.reference_price ?? null}
          liveReferencePrice={visibleReferencePrice}
          bidPrice={visibleBidPrice}
          askPrice={visibleAskPrice}
          chartInterval={chartInterval}
          onChartIntervalChange={setChartInterval}
          liveBar={marketStream.liveBar}
          streamStatus={marketStream.status}
          streamGeneration={marketStream.generation}
          marketProjectionReady={Boolean(currentMarket && expectedMarketSource)}
          marketColorScheme={marketColorScheme}
          scheduleRef={draft.data?.plan_id ?? loadedPlanId ?? "new-direct-order-plan"}
          workspaceHeader={workspaceHeader}
          leadingControls={quickControls}
          planOptions={planOptions}
          footerControls={footerControls}
          onValidationChange={handleOrderScheduleValidation}
        />
      </Box>
    );
  }

  return (
    <Box component="form" onSubmit={handleSubmit} sx={{ width: "min(920px, calc(100% - clamp(32px, 4vw, 48px)))", mx: "auto", py: { xs: 2.5, sm: 3 } }}>
      <PageHeader
        eyebrow={copying
          ? "沿用计划参数 · 新草稿"
          : editing
            ? `可编辑草稿${draft.data ? ` · v${draft.data.draft_version}` : ""}`
            : "新建交易计划 · 第 2 步 / 2"}
        title={editing
          ? directExecution ? "编辑直接执行计划" : "编辑策略计划"
          : copying
            ? "沿用参数新建计划"
            : directExecution ? "配置直接执行计划" : "配置策略计划"}
        description={copying
          ? `原计划的方向、交易金额和${directExecution ? "订单计划" : "策略参数"}已带入；新计划的有效期从保存时重新计算。你仍可修改，并需要再次确认和启动。`
          : directExecution
            ? "配置方向、资金边界和订单计划。只有服务端预览通过后才能保存；保存后仍需确认并启动。"
            : "配置方向与本次交易金额；高级参数已有默认值。保存后回到计划列表确认并启动。"}
      />
      {loading && <LinearProgress aria-label={editing ? "正在读取草稿" : directExecution ? "正在读取订单计划" : "正在读取策略"} />}
      {loadFailed && <Alert severity="error">{editing ? "草稿或执行依据当前不可用，不能编辑。" : "执行依据当前不可用。"}</Alert>}
      {mutation.isError && <Alert severity="error" sx={{ mb: 2 }}>{mutationMessage}</Alert>}

      <Box component="section" aria-labelledby="plan-identity-title" sx={{ ...surfaceFrameSx, mb: 3, p: 2 }}>
        <Typography id="plan-identity-title" variant="h2" sx={{ mb: 2 }}>计划信息</Typography>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2,minmax(0,1fr))" }, gap: 2 }}>
          <TextField
            label="计划名称"
            value={planName}
            onChange={(event) => setPlanName(event.target.value)}
            error={planName.length > 0 && !planNameValid}
            helperText={planNameValid ? "用于区分不同交易计划" : "必填，最多 80 个字符"}
            slotProps={{ htmlInput: { maxLength: 80 } }}
            required
          />
          {!editing ? (
            <TextField
              select
              label="创建方式"
              value={creatorKind}
              onChange={(event) => setCreatorKind(event.target.value as PlanCreatorKind)}
              helperText="AI 代为创建时必须主动选择“AI 创建”"
            >
              <MenuItem value="HUMAN">人工创建</MenuItem>
              <MenuItem value="AI">AI 创建</MenuItem>
            </TextField>
          ) : (
            <TextField
              label="创建来源"
              value={draft.data?.content.creator_kind === "AI" ? "AI 创建" : draft.data?.content.creator_kind === "HUMAN" ? "人工创建" : "未知"}
              helperText={draft.data?.content.created_at ? `创建于 ${formatUserVisibleTime(draft.data.content.created_at)}` : "创建时间未知"}
              slotProps={{ htmlInput: { readOnly: true } }}
            />
          )}
        </Box>
      </Box>

      {directExecution ? (
        <Box sx={{ ...surfaceFrameSx, mb: 3, p: 2, borderColor: "primary.main" }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "flex-start" } }}>
            <Box>
              <Typography variant="caption" color="text.secondary">已选执行依据</Typography>
              <Typography variant="h2" sx={{ mt: .25 }}>直接执行订单计划</Typography>
              <Typography variant="caption" className="mono" color="text.secondary" sx={{ display: "block", mt: .5 }}>
                {DIRECT_EXECUTION_REF} · 无策略信号
              </Typography>
            </Box>
            {!editing && !copying && <Button variant="outlined" onClick={() => setCreationStep("strategy")}>重新选择执行依据</Button>}
          </Stack>
          <Alert severity="info" variant="outlined" sx={{ mt: 1.5 }}>
            启动后只按已确认的档位和条件执行；修改价格、金额或保护规则需要回到草稿重新确认，不会静默改变运行中的计划。
          </Alert>
        </Box>
      ) : selectedStrategy ? (
        <Box sx={{ ...surfaceFrameSx, mb: 3, p: 2 }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "flex-start" } }}>
            <Box>
              <Typography variant="caption" color="text.secondary">已选策略</Typography>
              <Typography variant="h2" sx={{ mt: .25 }}>{selectedStrategy.display_name}</Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: .5, overflowWrap: "anywhere" }}>
                {selectedStrategy.strategy_id} · v{selectedStrategy.strategy_version}
              </Typography>
            </Box>
            {!editing && !copying && <Button variant="outlined" onClick={() => setCreationStep("strategy")}>重新选择策略</Button>}
          </Stack>
          <Box component="details" sx={{ mt: 1.5 }}>
            <Box component="summary" sx={{ cursor: "pointer", fontWeight: 700 }}>查看策略介绍</Box>
            <StrategyIntroduction strategy={selectedStrategy} embedded />
          </Box>
        </Box>
      ) : null}

      <Box
        component="section"
        aria-labelledby="market-context-title"
        sx={{
          ...surfaceFrameSx,
          mb: directExecution ? 2.5 : 4,
          p: directExecution ? 1.5 : { xs: 2, sm: 2.5 },
        }}
      >
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.25} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" }, mb: directExecution ? 1.25 : 2 }}>
          <Box>
            <Typography id="market-context-title" variant="h2">{directExecution ? "当前公开行情" : "当前策略输入"}</Typography>
            <Typography color="text.secondary" variant="body2" sx={{ mt: .75 }}>
              {directExecution
                ? "Binance 当前环境公开行情；作为市价、priceMatch 与服务端标准化的参考，不是成交承诺。"
                : "Binance 当前环境公开行情；仅辅助选择方向，不承诺盈利。"}
            </Typography>
          </Box>
          <Button size={directExecution ? "small" : "medium"} variant="outlined" onClick={() => market.refetch()} disabled={!channelLookbackValid || market.isFetching}>{market.isFetching ? "正在刷新…" : "刷新行情"}</Button>
        </Stack>
        {!directExecution && !channelLookbackValid && <Alert severity="warning" variant="outlined">通道回看必须是 4–96 根 15m K 线；修正参数后才读取对应行情。</Alert>}
        {channelLookbackValid && market.isPending && <LinearProgress aria-label="正在读取当前公开行情" />}
        {channelLookbackValid && market.isError && currentMarket && <Alert severity="warning" variant="outlined">
          行情刷新失败；以下保留上次成功行情（截止 {formatUserVisibleTime(currentMarket.source_cutoff)}），可能已经过期，仅用于定位。请刷新成功后再据此选择方向。
        </Alert>}
        {channelLookbackValid && market.isError && !currentMarket && <Alert severity="warning" variant="outlined">当前行情不可用，方向判断缺少产品内依据。可以稍后刷新，不应把空值视为安全或无波动。</Alert>}
        {channelLookbackValid && marketSourceMismatch && <Alert severity="error" variant="outlined">
          返回行情不属于当前 {status.environment_kind} 环境，已拒绝显示；不同环境数据不会用于方向判断、价格预览或下单。
        </Alert>}
        {currentMarket && <>
          {directExecution ? (
            <Box
              component="dl"
              sx={{
                m: 0,
                display: "grid",
                gridTemplateColumns: { xs: "repeat(2,minmax(0,1fr))", md: "repeat(4,minmax(0,1fr))" },
                gap: 1,
              }}
            >
              {[
                ["盘口中间价", `${marketPrice(currentMarket.reference_price)} USDT`],
                ["买一 / 卖一", `${marketPrice(currentMarket.bid_price)} / ${marketPrice(currentMarket.ask_price)}`],
                ["买卖价差", `${marketPrice(currentSpread)} USDT`],
                ["最近闭合 15m", `${marketPrice(currentMarket.latest_close_15m)} USDT`],
              ].map(([label, display]) => (
                <Box key={label} sx={{ minWidth: 0, px: 1.25, py: 1, bgcolor: "action.hover", borderRadius: 1 }}>
                  <Typography component="dt" variant="caption" color="text.secondary">{label}</Typography>
                  <Typography component="dd" className="mono" variant="body2" sx={{ m: 0, mt: .25, fontWeight: 700, overflowWrap: "anywhere" }}>
                    {display}
                  </Typography>
                </Box>
              ))}
              <Box sx={{ gridColumn: "1 / -1" }}>
                <Typography component="dt" variant="caption" color="text.secondary">行情截止</Typography>
                <Typography component="dd" variant="caption" color="text.secondary" sx={{ m: 0 }}>
                  {formatUserVisibleTime(currentMarket.source_cutoff)}；完整价格历史与当前参考价已标注在下方订单计划主图。
                </Typography>
              </Box>
            </Box>
          ) : (
            <FactGrid columns={3} dense facts={[
              ["盘口中间价", `${marketPrice(currentMarket.reference_price)} USDT`],
              ["买一 / 卖一", `${marketPrice(currentMarket.bid_price)} / ${marketPrice(currentMarket.ask_price)}`],
              ["买卖价差", `${marketPrice(currentSpread)} USDT`],
              ["最近闭合 1m", `${marketPrice(currentMarket.latest_close_1m)} USDT`],
              ["最近闭合 1m 成交量 / 笔数", `${marketVolume(currentMarket.latest_volume_1m)} BTC / ${currentMarket.latest_trade_count_1m} 笔`],
              ["最近闭合 15m", `${marketPrice(currentMarket.latest_close_15m)} USDT`],
              ["通道回看", `${currentMarket.channel_lookback_15m} × 15m`],
              ["通道上沿", `${marketPrice(currentMarket.channel_upper)} USDT`],
              ["通道下沿", `${marketPrice(currentMarket.channel_lower)} USDT`],
              ...(entryExtensionLimit !== null ? [["最大追价边界", `${marketPrice(String(entryExtensionLimit))} USDT`]] : []),
              ["1m 收盘距上沿 / 下沿", `${gapPercent(closedBarBreakoutGapPercent("LONG", currentMarket.latest_close_1m, currentMarket.channel_upper))} / ${gapPercent(closedBarBreakoutGapPercent("SHORT", currentMarket.latest_close_1m, currentMarket.channel_lower))}`],
              ["盘口中间价距上沿 / 下沿", `${gapPercent(currentMarket.long_breakout_gap_pct)} / ${gapPercent(currentMarket.short_breakout_gap_pct)}`],
              ["ATR(14)", `${marketPrice(currentMarket.atr_14)} USDT`],
            ].map(([label = "", value = ""]) => ({ label, value }))} />
          )}
          {!directExecution && <Alert severity="info" variant="outlined" sx={{ mt: 2 }}>
            当前选择 <MarketToneText tone={marketToneForDirection(parameters.direction)}>{parameters.direction === "LONG" ? "做多" : "做空"}</MarketToneText>：1m 收盘距离{parameters.direction === "LONG" ? "通道上沿" : "通道下沿"} {gapPercent(selectedClosedBarBreakoutGap)}（策略触发口径）；
            盘口中间价距离 {gapPercent(selectedBreakoutGap ?? "")}。正值表示尚未突破，负值表示已经越过；入场仍需连续 {parameters.confirmation_bars_1m} 根 1m 收盘确认，并通过标记价格与买卖一形成的执行前保守价格检查。行情截止 {formatUserVisibleTime(currentMarket.source_cutoff)}。
          </Alert>}
          {!directExecution && latestClosedBarBeyondBoundary && latestClosedBarBeyondExtension && entryExtensionLimit !== null && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              最近闭合 1m 已突破，但超过最大追价边界 {marketPrice(String(entryExtensionLimit))} USDT；按当前参数不应追入。启动后策略只会等待价格回到允许范围并重新通过闭合 K 线与执行前检查。
            </Alert>
          )}
          {!directExecution && Number.isFinite(currentSpreadBps) && currentSpreadBps > 10 && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              当前买卖价差约 {currentSpreadBps.toFixed(1)} bps，超过策略提交上限 10 bps。系统不会在该盘口创建入场动作，会等待后续有效闭合 1m 再判断。
            </Alert>
          )}
        </>}
      </Box>

      {!directExecution ? orderSettings : null}

      {directExecution && <Box sx={{ mt: 3 }}>
        <OrderScheduleEditor
          value={orderSchedule}
          onChange={(next) => {
            setOrderScheduleReady(false);
            setOrderSchedule(next);
          }}
          environmentId={status.environment_id}
          environmentKind={status.environment_kind}
          instrumentRef={instrument}
          direction={parameters.direction}
          maxNotional={tradeAmount}
          referencePrice={currentMarket?.reference_price ?? null}
          liveReferencePrice={visibleReferencePrice}
          bidPrice={visibleBidPrice}
          askPrice={visibleAskPrice}
          chartInterval={chartInterval}
          onChartIntervalChange={setChartInterval}
          liveBar={marketStream.liveBar}
          streamStatus={marketStream.status}
          streamGeneration={marketStream.generation}
          marketProjectionReady={Boolean(currentMarket && expectedMarketSource)}
          marketColorScheme={marketColorScheme}
          scheduleRef={draft.data?.plan_id ?? loadedPlanId ?? "new-direct-order-plan"}
          leadingControls={orderSettings}
          onValidationChange={handleOrderScheduleValidation}
        />
      </Box>}

      {!directExecution && status.environment_kind === "DEMO" && <Box sx={{ ...surfaceFrameSx, mt: 3, p: 2, borderColor: parameters.demo_immediate_entry ? "warning.main" : "divider" }}>
        <FormControlLabel
          control={<Checkbox checked={parameters.demo_immediate_entry} onChange={(event) => update("demo_immediate_entry", event.target.checked)} />}
          label="下单流程验证"
        />
        <Typography color="text.secondary" variant="body2">
          开启后，同一策略在下一根有效闭合 1m 上执行一次入场，用于验证下单、成交、保护和退出链路；它不是突破信号。
        </Typography>
      </Box>}

      {!directExecution && <Box component="details" sx={{ ...surfaceFrameSx, mt: 4, p: 2 }}>
        <Box component="summary" sx={{ cursor: "pointer", fontWeight: 750 }}>高级策略参数（可保持默认）</Box>
        <Typography color="text.secondary" sx={{ mt: 1, mb: 2 }}>只有需要调整入场、止损和止盈逻辑时再修改。</Typography>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2,minmax(0,1fr))" }, gap: 2 }}>
          <TextField label="15m 通道回看" type="number" value={parameters.channel_lookback_15m} onChange={(event) => update("channel_lookback_15m", Number(event.target.value))} error={!channelLookbackValid} helperText="范围 4–96 根；越短触发越频繁，噪声也越多" slotProps={{ htmlInput: { min: 4, max: 96, step: 1 } }} required />
          <TextField label="1m 确认根数" type="number" value={parameters.confirmation_bars_1m} onChange={(event) => update("confirmation_bars_1m", Number(event.target.value))} error={!confirmationBarsValid} helperText="范围 1–3 根" slotProps={{ htmlInput: { min: 1, max: 3, step: 1 } }} required />
          <TextField label="入场有效分钟" type="number" value={parameters.entry_valid_minutes} onChange={(event) => update("entry_valid_minutes", Number(event.target.value))} error={!entryValidityValid} helperText="范围 15–10080 分钟" slotProps={{ htmlInput: { min: 15, max: 10080, step: 1 } }} required />
          <TextField label="初始止损 ATR 倍数" type="number" value={parameters.initial_stop_atr_multiple} onChange={(event) => update("initial_stop_atr_multiple", event.target.value)} error={!initialStopValid} helperText="范围 1–3 ATR" slotProps={{ htmlInput: { min: 1, max: 3, step: "any" } }} required />
          <TextField label="最大追价 ATR" type="number" value={parameters.max_entry_extension_atr} onChange={(event) => update("max_entry_extension_atr", event.target.value)} error={!maxExtensionValid} helperText="范围 0.1–1 ATR" slotProps={{ htmlInput: { min: .1, max: 1, step: "any" } }} required />
          <TextField label="最大持仓 15m 根数" type="number" value={parameters.max_hold_bars_15m} onChange={(event) => update("max_hold_bars_15m", Number(event.target.value))} error={!maxHoldingBarsValid} helperText="范围 4–672 根" slotProps={{ htmlInput: { min: 4, max: 672, step: 1 } }} required />
          <TextField label="止盈一仓位比例" type="number" value={parameters.take_profit_1_fraction} onChange={(event) => update("take_profit_1_fraction", event.target.value)} error={!takeProfitFractionValid} helperText="范围 0.25–0.75" slotProps={{ htmlInput: { min: .25, max: .75, step: "any" } }} required />
          <TextField label="止盈一 R 倍数" type="number" value={parameters.take_profit_1_r} onChange={(event) => update("take_profit_1_r", event.target.value)} error={!takeProfit1Valid} helperText="范围 1–3R" slotProps={{ htmlInput: { min: 1, max: 3, step: "any" } }} required />
          <TextField label="止盈二 R 倍数" type="number" value={parameters.take_profit_2_r} onChange={(event) => update("take_profit_2_r", event.target.value)} error={!takeProfit2Valid || !takeProfitOrderValid} helperText="范围 2–6R，且必须大于止盈一" slotProps={{ htmlInput: { min: 2, max: 6, step: "any" } }} required />
        </Box>
      </Box>}
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 3 }}>
        <Button type="submit" variant="contained" disabled={!canSubmit}>{mutation.isPending ? "正在保存…" : marketContextRefreshing ? "正在按当前行情更新预览…" : editing ? "保存计划修改" : "保存计划"}</Button>
        <Button variant="outlined" onClick={() => navigate("/plans")}>取消</Button>
      </Stack>
    </Box>
  );
}
