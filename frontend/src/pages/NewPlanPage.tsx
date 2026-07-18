import { useMemo, useState } from "react";
import { Alert, Box, Button, Divider, LinearProgress, Stack, TextField, Typography } from "@mui/material";
import Form from "@rjsf/mui";
import { createPrecompiledValidator } from "@rjsf/validator-ajv8";
import type { IChangeEvent } from "@rjsf/core";
import { deepEquals, type RJSFSchema } from "@rjsf/utils";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import {
  ApiFailure,
  createPlan,
  getStrategies,
  getStrategySchema,
  type PlanDraftPayload,
} from "../api/client";
import oneShotStrategySchema from "../generated/oneShotStrategySchema.json";
import oneShotValidationFunctions from "../generated/oneShotStrategyValidator.cjs";


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
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: getStrategies });
  const strategyId = strategies.data?.[0]?.strategy_id ?? "ONE_SHOT_DONCHIAN_ATR_BREAKOUT";
  const schema = useQuery({ queryKey: ["strategy-schema", strategyId], queryFn: () => getStrategySchema(strategyId), enabled: Boolean(strategyId) });
  const schemaMatchesBuild = Boolean(schema.data && deepEquals(schema.data, oneShotStrategySchema));
  const validator = useMemo(
    () => schemaMatchesBuild
      ? createPrecompiledValidator(oneShotValidationFunctions, oneShotStrategySchema as RJSFSchema)
      : null,
    [schemaMatchesBuild],
  );
  const [formData, setFormData] = useState<Record<string, unknown>>({ direction: "LONG" });
  const [instrument, setInstrument] = useState("BTCUSDT-PERP");
  const [targetExposure, setTargetExposure] = useState("0.01");
  const [maxMargin, setMaxMargin] = useState("100");
  const [maxNotional, setMaxNotional] = useState("500");
  const [maxLoss, setMaxLoss] = useState("50");
  const [validMinutes, setValidMinutes] = useState("1440");
  const mutation = useMutation({
    mutationFn: (parameters: Record<string, unknown>) => createPlan({
      strategy_id: strategyId,
      parameters,
      venue_ref: "BINANCE_USDM",
      instrument_ref: instrument,
      direction: String(parameters.direction ?? ""),
      target_exposure: targetExposure,
      max_margin: maxMargin,
      max_notional: maxNotional,
      max_allowed_loss: maxLoss,
      valid_minutes: Number(validMinutes),
    } satisfies PlanDraftPayload),
    onSuccess: () => navigate("/plans"),
  });
  return (
    <Box sx={{ width: "min(920px, calc(100% - 32px))", mx: "auto", py: { xs: 4, sm: 6 } }}>
      <PageHeader eyebrow="B02 · MUTABLE DRAFT" title="新建策略计划" description="参数表单由服务端策略 JSON Schema 生成，服务端 Pydantic 仍是最终校验权威。保存草稿不占额度、不激活策略。" />
      <Alert severity="info" variant="outlined" sx={{ mb: 3 }}>DEMO 主要验证系统流程与机制，其次才是策略行为；模拟结果不能直接外推到 LIVE。</Alert>
      {(strategies.isPending || schema.isPending) && <LinearProgress aria-label="正在读取策略与参数规范" />}
      {(strategies.isError || schema.isError) && <Alert severity="error">策略登记或 schema 当前不可用。</Alert>}
      {schema.data && !schemaMatchesBuild && <Alert severity="error">策略 schema 与当前构建不一致；已拒绝生成或提交表单。</Alert>}
      {mutation.isError && <Alert severity="error" sx={{ mb: 2 }}>草稿未保存：{mutation.error instanceof ApiFailure ? mutation.error.code : "结果未知"}</Alert>}
      {schema.data && validator && (
        <>
          <Typography variant="h2" sx={{ mb: 2 }}>策略参数</Typography>
          <Form
            schema={schema.data as RJSFSchema}
            validator={validator}
            formData={formData}
            onChange={(event: IChangeEvent) => setFormData((event.formData ?? {}) as Record<string, unknown>)}
            onSubmit={(event: IChangeEvent) => mutation.mutate((event.formData ?? {}) as Record<string, unknown>)}
            uiSchema={{ "ui:title": "", "ui:submitButtonOptions": { norender: true } }}
            noHtml5Validate
          >
            <Divider sx={{ my: 4 }} />
            <Typography variant="h2" sx={{ mb: 2 }}>计划、时间与互斥额度</Typography>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2,minmax(0,1fr))" }, gap: 2 }}>
            <TextField label="Instrument" value={instrument} onChange={(event) => setInstrument(event.target.value)} required helperText="P0 真实资格目标为 BTCUSDT-PERP" />
            <TextField label="目标暴露数量" value={targetExposure} onChange={(event) => setTargetExposure(event.target.value)} required />
            <TextField label="max_margin (USDT)" value={maxMargin} onChange={(event) => setMaxMargin(event.target.value)} required />
            <TextField label="max_notional (USDT)" value={maxNotional} onChange={(event) => setMaxNotional(event.target.value)} required />
            <TextField label="max_allowed_loss (USDT)" value={maxLoss} onChange={(event) => setMaxLoss(event.target.value)} required />
            <TextField label="有效分钟" type="number" value={validMinutes} onChange={(event) => setValidMinutes(event.target.value)} required />
          </Box>
          <Alert severity="warning" variant="outlined" sx={{ mt: 3 }}>三轴额度是 Halpha 内部互斥承诺，不是 Binance 冻结资金，也不是最终损失保证。</Alert>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 3 }}>
            <Button type="submit" variant="contained" disabled={mutation.isPending}>{mutation.isPending ? "正在保存…" : "保存草稿"}</Button>
            <Button variant="text" onClick={() => navigate("/plans")}>取消</Button>
          </Stack>
          </Form>
        </>
      )}
    </Box>
  );
}
