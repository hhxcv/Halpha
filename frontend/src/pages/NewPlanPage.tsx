import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Divider,
  LinearProgress,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router";

import {
  ApiFailure,
  createPlan,
  getPlan,
  getStrategies,
  type PlanDraftPayload,
  updatePlan,
} from "../api/client";


type Direction = "LONG" | "SHORT";

type StrategyParameters = {
  direction: Direction;
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
  channel_lookback_15m: 20,
  confirmation_bars_1m: 2,
  entry_valid_minutes: 1440,
  initial_stop_atr_multiple: "1.5",
  max_entry_extension_atr: "0.5",
  max_hold_bars_15m: 96,
  take_profit_1_fraction: "0.5",
  take_profit_1_r: "1.5",
  take_profit_2_r: "3.0",
};


function PageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <Box component="header" sx={{ mb: 5 }}>
      <Typography variant="overline" color="text.secondary">{eyebrow}</Typography>
      <Typography variant="h1" sx={{ mt: .75, mb: 1.5 }}>{title}</Typography>
      <Typography color="text.secondary" sx={{ maxWidth: 760, lineHeight: 1.7 }}>{description}</Typography>
    </Box>
  );
}


export default function NewPlanPage() {
  const navigate = useNavigate();
  const { planId } = useParams();
  const editing = Boolean(planId);
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: getStrategies });
  const draft = useQuery({
    queryKey: ["plan", planId],
    queryFn: () => getPlan(planId ?? ""),
    enabled: editing,
  });
  const strategyId = draft.data?.content.strategy_id
    ?? strategies.data?.[0]?.strategy_id
    ?? "ONE_SHOT_DONCHIAN_ATR_BREAKOUT";
  const [parameters, setParameters] = useState<StrategyParameters>(DEFAULT_PARAMETERS);
  const [instrument, setInstrument] = useState("BTCUSDT-PERP");
  const [tradeAmount, setTradeAmount] = useState("500");
  const [validMinutes, setValidMinutes] = useState("1440");

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
  const takeProfitOrderValid = Number(parameters.take_profit_2_r) > Number(parameters.take_profit_1_r);
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

  const loading = strategies.isPending || (editing && draft.isPending);
  const loadFailed = strategies.isError || (editing && draft.isError);
  const mutationCode = mutation.error instanceof ApiFailure
    ? mutation.error.code
    : "结果未知";
  const mutationMessage = mutationCode === "PLAN_VERSION_CONFLICT"
    ? "草稿已被其他请求更新，请返回列表后重新打开。"
    : `${editing ? "草稿未更新" : "草稿未保存"}：${mutationCode}`;

  return (
    <Box component="form" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }} sx={{ width: "min(920px, calc(100% - 32px))", mx: "auto", py: { xs: 4, sm: 6 } }}>
      <PageHeader
        eyebrow={`MUTABLE DRAFT${draft.data ? ` · v${draft.data.draft_version}` : ""}`}
        title={editing ? "编辑策略计划" : "新建策略计划"}
        description="选择方向并填写本次交易金额即可；高级参数已有默认值。保存后回到计划列表确认并启动。"
      />
      <Alert severity="info" variant="outlined" sx={{ mb: 3 }}>DEMO 主要验证交易闭环和安全机制，模拟结果不能直接外推到 LIVE。</Alert>
      {loading && <LinearProgress aria-label={editing ? "正在读取草稿" : "正在读取策略"} />}
      {loadFailed && <Alert severity="error">{editing ? "草稿或策略当前不可用，不能编辑。" : "策略当前不可用。"}</Alert>}
      {mutation.isError && <Alert severity="error" sx={{ mb: 2 }}>{mutationMessage}</Alert>}

      <Typography variant="h2" sx={{ mb: 2 }}>下单设置</Typography>
      <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2,minmax(0,1fr))" }, gap: 2 }}>
        <TextField select label="方向" value={parameters.direction} onChange={(event) => update("direction", event.target.value as Direction)}>
          <MenuItem value="LONG">LONG</MenuItem>
          <MenuItem value="SHORT">SHORT</MenuItem>
        </TextField>
        <TextField label="Instrument" value={instrument} onChange={(event) => setInstrument(event.target.value)} required helperText="当前真实账户交易对象为 BTCUSDT-PERP" />
        <TextField label="交易金额（USDT）" value={tradeAmount} onChange={(event) => setTradeAmount(event.target.value)} required helperText="该金额就是本计划的资金边界，启动时无需再次授权" />
        <TextField label="计划有效分钟" type="number" value={validMinutes} onChange={(event) => setValidMinutes(event.target.value)} required />
      </Box>
      <Alert severity="warning" variant="outlined" sx={{ mt: 3 }}>交易金额限制策略可新增的风险，但不是 Binance 资金冻结，也不能保证最终损失不会超过该值。</Alert>

      <Divider sx={{ my: 4 }} />
      <Box component="details" sx={{ borderTop: 1, borderBottom: 1, borderColor: "divider", py: 1.5 }}>
        <Box component="summary" sx={{ cursor: "pointer", fontWeight: 750, py: 1 }}>高级策略参数（可保持默认）</Box>
        <Typography color="text.secondary" sx={{ mt: 1, mb: 2 }}>只有需要调整入场、止损和止盈逻辑时再修改。</Typography>
        <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2,minmax(0,1fr))" }, gap: 2 }}>
          <TextField label="15m 通道回看" type="number" value={parameters.channel_lookback_15m} onChange={(event) => update("channel_lookback_15m", Number(event.target.value))} slotProps={{ htmlInput: { min: 20, max: 96 } }} required />
          <TextField label="1m 确认根数" type="number" value={parameters.confirmation_bars_1m} onChange={(event) => update("confirmation_bars_1m", Number(event.target.value))} slotProps={{ htmlInput: { min: 1, max: 3 } }} required />
          <TextField label="入场有效分钟" type="number" value={parameters.entry_valid_minutes} onChange={(event) => update("entry_valid_minutes", Number(event.target.value))} slotProps={{ htmlInput: { min: 15, max: 10080 } }} required />
          <TextField label="初始止损 ATR 倍数" value={parameters.initial_stop_atr_multiple} onChange={(event) => update("initial_stop_atr_multiple", event.target.value)} required />
          <TextField label="最大追价 ATR" value={parameters.max_entry_extension_atr} onChange={(event) => update("max_entry_extension_atr", event.target.value)} required />
          <TextField label="最大持仓 15m 根数" type="number" value={parameters.max_hold_bars_15m} onChange={(event) => update("max_hold_bars_15m", Number(event.target.value))} slotProps={{ htmlInput: { min: 4, max: 672 } }} required />
          <TextField label="止盈一仓位比例" value={parameters.take_profit_1_fraction} onChange={(event) => update("take_profit_1_fraction", event.target.value)} required />
          <TextField label="止盈一 R 倍数" value={parameters.take_profit_1_r} onChange={(event) => update("take_profit_1_r", event.target.value)} error={!takeProfitOrderValid} required />
          <TextField label="止盈二 R 倍数" value={parameters.take_profit_2_r} onChange={(event) => update("take_profit_2_r", event.target.value)} error={!takeProfitOrderValid} helperText={!takeProfitOrderValid ? "止盈二必须大于止盈一" : ""} required />
        </Box>
      </Box>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 3 }}>
        <Button type="submit" variant="contained" disabled={loading || loadFailed || mutation.isPending || !takeProfitOrderValid}>{mutation.isPending ? "正在保存…" : editing ? "保存计划修改" : "保存计划"}</Button>
        <Button variant="text" onClick={() => navigate("/plans")}>取消</Button>
      </Stack>
    </Box>
  );
}
