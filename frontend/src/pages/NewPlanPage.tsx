import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  LinearProgress,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useOutletContext, useParams, useSearchParams } from "react-router";

import {
  ApiFailure,
  createPlan,
  getMarketContext,
  getPlan,
  getStrategies,
  type PlanDraftPayload,
  type SettingsStatus,
  updatePlan,
} from "../api/client";
import PageHeader from "../components/PageHeader";
import FactGrid from "../components/FactGrid";
import StrategyIntroduction from "../components/StrategyIntroduction";
import { closedBarBreakoutGapPercent, entryExtensionBoundary, formatUserVisibleTime, gapPercent, marketPrice, marketVolume } from "../format";
import { MarketToneText, marketToneClassName, marketToneForDirection } from "../marketColors";
import { surfaceFrameSx } from "../theme";


type Direction = "LONG" | "SHORT";

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


function numberInRange(value: string | number, minimum: number, maximum: number): boolean {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= minimum && parsed <= maximum;
}


function integerInRange(value: number, minimum: number, maximum: number): boolean {
  return Number.isInteger(value) && value >= minimum && value <= maximum;
}


export default function NewPlanPage() {
  const navigate = useNavigate();
  const { status } = useOutletContext<{ status: SettingsStatus }>();
  const { planId } = useParams();
  const [searchParams] = useSearchParams();
  const sourcePlanId = searchParams.get("copyFrom");
  const editing = Boolean(planId);
  const copying = Boolean(!editing && sourcePlanId);
  const loadedPlanId = planId ?? sourcePlanId;
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: getStrategies });
  const draft = useQuery({
    queryKey: ["plan", loadedPlanId],
    queryFn: () => getPlan(loadedPlanId ?? ""),
    enabled: Boolean(loadedPlanId),
  });
  const strategyId = draft.data?.content.strategy_id
    ?? strategies.data?.[0]?.strategy_id
    ?? "ONE_SHOT_DONCHIAN_ATR_BREAKOUT";
  const selectedStrategy = strategies.data?.find((strategy) => strategy.strategy_id === strategyId);
  const [parameters, setParameters] = useState<StrategyParameters>(DEFAULT_PARAMETERS);
  const [instrument, setInstrument] = useState("BTCUSDT-PERP");
  const [tradeAmount, setTradeAmount] = useState("500");
  const [validMinutes, setValidMinutes] = useState("60");
  const channelLookbackValid = integerInRange(parameters.channel_lookback_15m, 4, 96);
  const market = useQuery({
    queryKey: ["market-context", instrument, parameters.channel_lookback_15m],
    queryFn: () => getMarketContext(instrument, parameters.channel_lookback_15m),
    enabled: channelLookbackValid,
    retry: 1,
    retryDelay: 2_000,
  });

  useEffect(() => {
    const source = draft.data?.content;
    if (!source) return;
    setParameters({
      ...DEFAULT_PARAMETERS,
      ...source.parameters,
      direction: source.direction as Direction,
    } as StrategyParameters);
    setInstrument(source.instrument_ref);
    setTradeAmount(source.requested_limits.max_notional);
    const duration = Math.round(
      (Date.parse(source.valid_until) - Date.parse(source.valid_from)) / 60_000,
    );
    if (Number.isFinite(duration) && duration > 0) setValidMinutes(String(duration));
  }, [draft.data?.content_digest]);

  const update = <K extends keyof StrategyParameters>(key: K, value: StrategyParameters[K]) => {
    setParameters((current) => ({ ...current, [key]: value }));
  };
  const confirmationBarsValid = integerInRange(parameters.confirmation_bars_1m, 1, 3);
  const entryValidityValid = integerInRange(parameters.entry_valid_minutes, 15, 10080);
  const maxHoldingBarsValid = integerInRange(parameters.max_hold_bars_15m, 4, 672);
  const planValidityValid = numberInRange(validMinutes, 15, 10080)
    && Number.isInteger(Number(validMinutes));
  const tradeAmountValid = Number(tradeAmount) > 0 && Number.isFinite(Number(tradeAmount));
  const initialStopValid = numberInRange(parameters.initial_stop_atr_multiple, 1, 3);
  const maxExtensionValid = numberInRange(parameters.max_entry_extension_atr, .1, 1);
  const takeProfitFractionValid = numberInRange(parameters.take_profit_1_fraction, .25, .75);
  const takeProfit1Valid = numberInRange(parameters.take_profit_1_r, 1, 3);
  const takeProfit2Valid = numberInRange(parameters.take_profit_2_r, 2, 6);
  const takeProfitOrderValid = takeProfit1Valid
    && takeProfit2Valid
    && Number(parameters.take_profit_2_r) > Number(parameters.take_profit_1_r);
  const parameterRangesValid = channelLookbackValid
    && confirmationBarsValid
    && entryValidityValid
    && maxHoldingBarsValid
    && planValidityValid
    && tradeAmountValid
    && initialStopValid
    && maxExtensionValid
    && takeProfitFractionValid
    && takeProfitOrderValid;
  const currentMarket = market.data?.channel_lookback_15m === parameters.channel_lookback_15m
    ? market.data
    : undefined;
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
      const payload = {
        strategy_id: strategyId,
        parameters,
        venue_ref: "BINANCE_USDM",
        instrument_ref: instrument,
        direction: parameters.direction,
        target_exposure: tradeAmount,
        max_margin: tradeAmount,
        max_notional: tradeAmount,
        max_allowed_loss: tradeAmount,
        valid_minutes: Number(validMinutes),
      } satisfies PlanDraftPayload;
      return editing && draft.data
        ? updatePlan(draft.data.plan_id, draft.data.draft_version, payload)
        : createPlan(payload);
    },
    onSuccess: () => navigate("/plans"),
  });

  const loading = strategies.isPending || (Boolean(loadedPlanId) && draft.isPending);
  const loadFailed = strategies.isError || (Boolean(loadedPlanId) && draft.isError);
  const mutationCode = mutation.error instanceof ApiFailure
    ? mutation.error.code
    : "结果未知";
  const mutationMessage = mutationCode === "PLAN_VERSION_CONFLICT"
    ? "草稿已被其他请求更新，请返回列表后重新打开。"
    : `${editing ? "草稿未更新" : "草稿未保存"}：${mutationCode}`;

  return (
    <Box component="form" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }} sx={{ width: "min(920px, calc(100% - clamp(32px, 4vw, 48px)))", mx: "auto", py: { xs: 2.5, sm: 3 } }}>
      <PageHeader
        eyebrow={copying ? "沿用计划参数 · 新草稿" : `可编辑草稿${draft.data ? ` · v${draft.data.draft_version}` : ""}`}
        title={editing ? "编辑策略计划" : copying ? "沿用参数新建计划" : "新建策略计划"}
        description={copying
          ? "原计划的方向、交易金额和策略参数已带入；新计划的有效期从保存时重新计算。你仍可修改，并需要再次确认和启动。"
          : "选择方向并填写本次交易金额即可；高级参数已有默认值。保存后回到计划列表确认并启动。"}
      />
      {loading && <LinearProgress aria-label={editing ? "正在读取草稿" : "正在读取策略"} />}
      {loadFailed && <Alert severity="error">{editing ? "草稿或策略当前不可用，不能编辑。" : "策略当前不可用。"}</Alert>}
      {mutation.isError && <Alert severity="error" sx={{ mb: 2 }}>{mutationMessage}</Alert>}

      {selectedStrategy && (
        <Box component="details" sx={{ ...surfaceFrameSx, mb: 3, p: 2 }}>
          <Box component="summary" sx={{ cursor: "pointer", fontWeight: 700 }}>查看策略详情</Box>
          <Box sx={{ mt: 1 }}><StrategyIntroduction strategy={selectedStrategy} embedded /></Box>
        </Box>
      )}

      <Box component="section" aria-labelledby="market-context-title" sx={{ ...surfaceFrameSx, mb: 4, p: { xs: 2, sm: 2.5 } }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ justifyContent: "space-between", alignItems: { xs: "stretch", sm: "center" }, mb: 2 }}>
          <Box>
            <Typography id="market-context-title" variant="h2">当前策略输入</Typography>
            <Typography color="text.secondary" variant="body2" sx={{ mt: .75 }}>Binance 当前环境公开行情；仅辅助选择方向，不承诺盈利。</Typography>
          </Box>
          <Button variant="outlined" onClick={() => market.refetch()} disabled={!channelLookbackValid || market.isFetching}>{market.isFetching ? "正在刷新…" : "刷新行情"}</Button>
        </Stack>
        {!channelLookbackValid && <Alert severity="warning" variant="outlined">通道回看必须是 4–96 根 15m K 线；修正参数后才读取对应行情。</Alert>}
        {channelLookbackValid && market.isPending && <LinearProgress aria-label="正在读取当前公开行情" />}
        {channelLookbackValid && market.isError && currentMarket && <Alert severity="warning" variant="outlined">
          行情刷新失败；以下保留上次成功行情（截止 {formatUserVisibleTime(currentMarket.source_cutoff)}），可能已经过期，仅用于定位。请刷新成功后再据此选择方向。
        </Alert>}
        {channelLookbackValid && market.isError && !currentMarket && <Alert severity="warning" variant="outlined">当前行情不可用，方向判断缺少产品内依据。可以稍后刷新，不应把空值视为安全或无波动。</Alert>}
        {currentMarket && <>
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
          <Alert severity="info" variant="outlined" sx={{ mt: 2 }}>
            当前选择 <MarketToneText tone={marketToneForDirection(parameters.direction)}>{parameters.direction === "LONG" ? "做多" : "做空"}</MarketToneText>：1m 收盘距离{parameters.direction === "LONG" ? "通道上沿" : "通道下沿"} {gapPercent(selectedClosedBarBreakoutGap)}（策略触发口径）；
            盘口中间价距离 {gapPercent(selectedBreakoutGap ?? "")}。正值表示尚未突破，负值表示已经越过；入场仍需连续 {parameters.confirmation_bars_1m} 根 1m 收盘确认，并通过标记价格与买卖一形成的执行前保守价格检查。行情截止 {formatUserVisibleTime(currentMarket.source_cutoff)}。
          </Alert>
          {latestClosedBarBeyondBoundary && latestClosedBarBeyondExtension && entryExtensionLimit !== null && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              最近闭合 1m 已突破，但超过最大追价边界 {marketPrice(String(entryExtensionLimit))} USDT；按当前参数不应追入。启动后策略只会等待价格回到允许范围并重新通过闭合 K 线与执行前检查。
            </Alert>
          )}
          {Number.isFinite(currentSpreadBps) && currentSpreadBps > 10 && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              当前买卖价差约 {currentSpreadBps.toFixed(1)} bps，超过策略提交上限 10 bps。系统不会在该盘口创建入场动作，会等待后续有效闭合 1m 再判断。
            </Alert>
          )}
        </>}
      </Box>

      <Typography variant="h2" sx={{ mb: 2 }}>下单设置</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2,minmax(0,1fr))" }, gap: 2 }}>
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
        <TextField label="交易对象" value={instrument} required helperText="当前唯一策略对象固定为 BTCUSDT-PERP" slotProps={{ htmlInput: { readOnly: true } }} />
        <TextField label="交易金额（USDT）" value={tradeAmount} onChange={(event) => setTradeAmount(event.target.value)} error={!tradeAmountValid} required helperText={tradeAmountValid ? "该金额就是本计划的资金边界，启动时无需再次授权" : "必须填写大于 0 的金额"} />
        <TextField label="计划有效分钟" type="number" value={validMinutes} onChange={(event) => setValidMinutes(event.target.value)} error={!planValidityValid} helperText="范围 15–10080 分钟" slotProps={{ htmlInput: { min: 15, max: 10080, step: 1 } }} required />
      </Box>
      <Alert severity="warning" variant="outlined" sx={{ mt: 3 }}>交易金额限制策略可新增的风险，但不是 Binance 资金冻结，也不能保证最终损失不会超过该值。</Alert>

      {status.environment_kind === "DEMO" && <Box sx={{ ...surfaceFrameSx, mt: 3, p: 2, borderColor: parameters.demo_immediate_entry ? "warning.main" : "divider" }}>
        <FormControlLabel
          control={<Checkbox checked={parameters.demo_immediate_entry} onChange={(event) => update("demo_immediate_entry", event.target.checked)} />}
          label="下单流程验证"
        />
        <Typography color="text.secondary" variant="body2">
          开启后，同一策略在下一根有效闭合 1m 上执行一次入场，用于验证下单、成交、保护和退出链路；它不是突破信号。
        </Typography>
      </Box>}

      <Box component="details" sx={{ ...surfaceFrameSx, mt: 4, p: 2 }}>
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
      </Box>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 3 }}>
        <Button type="submit" variant="contained" disabled={loading || loadFailed || mutation.isPending || marketContextRefreshing || !parameterRangesValid}>{mutation.isPending ? "正在保存…" : marketContextRefreshing ? "正在按当前回看更新行情…" : editing ? "保存计划修改" : "保存计划"}</Button>
        <Button variant="text" onClick={() => navigate("/plans")}>取消</Button>
      </Stack>
    </Box>
  );
}
