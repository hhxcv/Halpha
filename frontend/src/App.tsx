import { lazy, Suspense, useEffect, useState } from "react";
import {
  Alert,
  AppBar,
  Box,
  Button,
  Chip,
  CircularProgress,
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
  TextField,
  Toolbar,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import AssignmentOutlined from "@mui/icons-material/AssignmentOutlined";
import DashboardOutlined from "@mui/icons-material/DashboardOutlined";
import MenuOutlined from "@mui/icons-material/MenuOutlined";
import OpenInNewOutlined from "@mui/icons-material/OpenInNewOutlined";
import ReviewsOutlined from "@mui/icons-material/ReviewsOutlined";
import SettingsOutlined from "@mui/icons-material/SettingsOutlined";
import ShieldOutlined from "@mui/icons-material/ShieldOutlined";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  fixPlan,
  getActivation,
  getActivations,
  getActivationTimeline,
  getActivationPreview,
  getOverview,
  getPlans,
  getReview,
  getReviews,
  getSettingsStatus,
  previewControl,
  refreshReview,
  sendTestEmail,
  submitActivationControl,
  type ControlIntent,
  type ReviewCompletionPayload,
  type SettingsStatus,
} from "./api/client";
import { formatUtc, shortDigest } from "./format";

const DRAWER_WIDTH = 236;
const STATUS_QUERY_KEY = ["settings-status"] as const;
const NewPlanPage = lazy(() => import("./pages/NewPlanPage"));

function valueOf(record: Record<string, unknown> | undefined, key: string, fallback = "UNKNOWN"): string {
  const value = record?.[key];
  return value === null || value === undefined ? fallback : String(value);
}

function recordOf(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordsOf(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.map(recordOf) : [];
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
    <Box sx={{ width: "min(620px, calc(100% - 32px))", mx: "auto", pt: 12 }}>
      <Typography variant="overline" color="text.secondary">LOCAL APP UNAVAILABLE</Typography>
      <Typography variant="h1" sx={{ mt: 1, mb: 3 }}>无法取得当前工作台状态</Typography>
      <Alert severity="error" variant="outlined" sx={{ mb: 3 }}>
        当前结果未知。页面没有使用缓存冒充服务器事实，也没有开放任何资本或交易指令。
      </Alert>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
        <Button variant="contained" onClick={retry}>重新查询</Button>
        <Button component="a" href="/operations" variant="outlined" endIcon={<OpenInNewOutlined />}>
          打开本机有限操作入口
        </Button>
      </Stack>
    </Box>
  );
}

type FrameContext = { status: SettingsStatus };

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
  const location = useLocation();
  const navigate = useNavigate();

  const drawer = (
    <Box component="nav" aria-label="工作台导航" sx={{ pt: 1, height: "100%", display: "flex", flexDirection: "column" }}>
      <List aria-label="工作台主导航" sx={{ px: 1 }}>
        {navItems.map((item) => (
          <ListItem key={item.path} disablePadding>
            <ListItemButton
              selected={location.pathname === item.path || (item.path !== "/overview" && location.pathname.startsWith(`${item.path}/`))}
              onClick={() => { navigate(item.path); setDrawerOpen(false); }}
              sx={{ minHeight: 44, mb: .5 }}
            >
              <ListItemIcon sx={{ minWidth: 36, color: "inherit" }}>{item.icon}</ListItemIcon>
              <ListItemText primary={item.label} slotProps={{ primary: { sx: { fontSize: 14, fontWeight: 650 } } }} />
            </ListItemButton>
          </ListItem>
        ))}
      </List>
      <Box sx={{ mt: "auto", p: 2 }}>
        <Divider sx={{ mb: 2 }} />
        <Button component="a" href="/operations" fullWidth variant="text" endIcon={<OpenInNewOutlined />} sx={{ justifyContent: "space-between", color: "text.secondary" }}>
          有限操作入口
        </Button>
      </Box>
    </Box>
  );

  return (
    <Box sx={{ minHeight: "100vh" }}>
      <AppBar position="fixed" color="transparent" sx={{ zIndex: theme.zIndex.drawer + 1, bgcolor: "rgba(11,16,23,.97)", borderBottom: 1, borderColor: "divider", boxShadow: "none" }}>
        <Toolbar
          variant="dense"
          sx={{
            minHeight: { xs: 96, md: 52 },
            alignContent: "center",
            flexWrap: { xs: "wrap", md: "nowrap" },
            columnGap: { xs: 1, sm: 2 },
            rowGap: { xs: .25, md: 0 },
            px: { xs: 1.5, sm: 2.5 },
          }}
        >
          {narrow && <IconButton aria-label="打开导航" onClick={() => setDrawerOpen(true)} edge="start"><MenuOutlined /></IconButton>}
          <Typography sx={{ fontWeight: 850, letterSpacing: "-.03em", mr: { xs: 0, sm: 1 } }}>Halpha</Typography>
          <Chip label={status.environment_kind} size="small" color="info" variant="outlined" icon={<ShieldOutlined />} />
          <Typography
            className="mono"
            variant="caption"
            color="text.secondary"
            noWrap
            sx={{
              order: { xs: 5, md: 0 },
              flexBasis: { xs: "100%", md: "auto" },
              maxWidth: { xs: "100%", md: 280 },
              fontSize: { xs: 10, md: 12 },
            }}
          >
            账户 · {status.account_id}
          </Typography>
          <Box sx={{ flexGrow: 1 }} />
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
            事实截止 {formatUtc(status.server_fact_cutoff)}
          </Typography>
          <Chip
            label={`REAL WRITE · ${status.runtime_real_write_gate}`}
            size="small"
            color={status.runtime_real_write_gate === "OPEN" ? "error" : "warning"}
            variant="outlined"
          />
        </Toolbar>
      </AppBar>
      <Drawer
        variant={narrow ? "temporary" : "permanent"}
        open={narrow ? drawerOpen : true}
        onClose={() => setDrawerOpen(false)}
        ModalProps={{ keepMounted: true }}
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: DRAWER_WIDTH,
            top: { xs: 96, md: 52 },
            height: { xs: "calc(100% - 96px)", md: "calc(100% - 52px)" },
          },
        }}
      >
        {drawer}
      </Drawer>
      <Box component="main" sx={{ ml: { xs: 0, md: `${DRAWER_WIDTH}px` }, pt: { xs: "96px", md: "52px" }, minHeight: "100vh" }}>
        <Outlet context={{ status } satisfies FrameContext} />
      </Box>
    </Box>
  );
}

function PageHeader({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return (
    <Box component="header" sx={{ mb: 5 }}>
      <Typography variant="overline" color="text.secondary">{eyebrow}</Typography>
      <Typography variant="h1" sx={{ mt: .75, mb: 1.5 }}>{title}</Typography>
      <Typography color="text.secondary" sx={{ maxWidth: 760, lineHeight: 1.7 }}>{description}</Typography>
    </Box>
  );
}

function FactGrid({ facts }: { facts: Array<{ label: string; value: string; note?: string }> }) {
  return (
    <Box component="dl" sx={{ m: 0, display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(2,minmax(0,1fr))" }, borderTop: 1, borderLeft: 1, borderColor: "divider" }}>
      {facts.map((fact) => (
        <Box key={fact.label} sx={{ minWidth: 0, p: 2, borderRight: 1, borderBottom: 1, borderColor: "divider", bgcolor: "background.paper" }}>
          <Typography component="dt" variant="caption" color="text.secondary">{fact.label}</Typography>
          <Box component="dd" sx={{ m: 0, mt: .75 }}>
            <Typography component="span" className="mono" sx={{ display: "block", fontFamily: '"Cascadia Mono", Consolas, monospace', fontSize: 13, fontWeight: 650, overflowWrap: "anywhere" }}>{fact.value}</Typography>
            {fact.note && <Typography component="span" variant="caption" color="text.secondary" sx={{ display: "block", mt: .75 }}>{fact.note}</Typography>}
          </Box>
        </Box>
      ))}
    </Box>
  );
}

function OverviewPage() {
  const navigate = useNavigate();
  const query = useQuery({ queryKey: ["overview"], queryFn: getOverview, refetchInterval: 30_000 });
  const activationsQuery = useQuery({ queryKey: ["activations"], queryFn: getActivations, refetchInterval: 30_000 });
  const data = query.data;
  const openActivations = (activationsQuery.data ?? []).filter((activation) => activation.lifecycle !== "COMPLETED");
  const title = data && data.open_activation_count === 0 ? "当前无开放激活" : data ? `${data.open_activation_count} 个开放激活` : "正在取得当前事实";

  return (
    <Box sx={{ width: "min(1120px, calc(100% - 32px))", mx: "auto", py: { xs: 4, sm: 6 } }}>
      <PageHeader
        eyebrow="CURRENT ACCOUNT FACTS"
        title={title}
        description="总览只读取当前数据库投影。命令已接收、ExecutionAction、场所事实、保护和闭合始终保持不同状态；任何未知都不会由页面补齐。"
      />
      {(query.isFetching || activationsQuery.isFetching) && <LinearProgress aria-label="正在刷新总览" sx={{ mb: 2 }} />}
      {query.isError && (
        <Alert severity="error" variant="outlined" sx={{ mb: 3 }}>
          服务器事实当前不可确认。工作台没有把缓存显示为当前事实；请核对 PostgreSQL 或使用本机有限操作入口。
        </Alert>
      )}
      {data && (
        <>
          <FactGrid facts={[
            { label: "开放激活", value: String(data.open_activation_count), note: data.open_activation_count === 0 ? "当前没有产品激活" : "需要进入稳定激活身份核对" },
            { label: "环境", value: data.environment_kind },
            { label: "交易所变更请求", value: data.runtime_real_write_gate, note: "控制是否可向交易所提交订单、撤单等账户变更请求" },
            { label: "服务器事实截止点", value: formatUtc(data.server_fact_cutoff) },
            { label: "视图取得时间", value: formatUtc(data.view_retrieved_at) },
          ]} />
          {data.open_activation_count > 0 && (
            <Box component="section" sx={{ mt: 5, pt: 3, borderTop: 1, borderColor: "divider" }}>
              <Typography variant="h2" sx={{ mb: 1 }}>开放激活</Typography>
              <Typography color="text.secondary" sx={{ mb: 2 }}>浏览器重开后仍从这里返回同一激活身份；详情页负责展示运行、保护、动作、事实和控制。</Typography>
              {activationsQuery.isError && <Alert severity="error">开放激活列表当前不可读；数量不会被当作可操作详情。</Alert>}
              {!activationsQuery.isError && openActivations.length === 0 && <Alert severity="warning">总览计数与激活列表暂不一致，请刷新后再核对。</Alert>}
              <Stack spacing={1.5}>
                {openActivations.map((activation) => (
                  <Box key={activation.activation_id} sx={{ p: 2.5, border: 1, borderColor: "divider", bgcolor: "background.paper" }}>
                    <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
                      <Box sx={{ minWidth: 0 }}>
                        <Typography variant="overline" color="text.secondary">{activation.lifecycle} · {activation.run_state}</Typography>
                        <Typography variant="h2" sx={{ mt: .5 }}>{activation.instrument_ref} · {activation.direction}</Typography>
                        <Typography className="mono" variant="caption" color="text.secondary">
                          protection {activation.protection_state} · v{activation.state_version} · updated {formatUtc(activation.updated_at)}
                        </Typography>
                      </Box>
                      <Button variant="outlined" onClick={() => navigate(`/activations/${activation.activation_id}`)}>查看运行与控制</Button>
                    </Stack>
                  </Box>
                ))}
              </Stack>
            </Box>
          )}
        </>
      )}
    </Box>
  );
}

function SettingsPage() {
  const { status } = useOutletContext<FrameContext>();
  const emailMutation = useMutation({
    mutationFn: sendTestEmail,
  });
  return (
    <Box sx={{ width: "min(1120px, calc(100% - 32px))", mx: "auto", py: { xs: 4, sm: 6 } }}>
      <PageHeader eyebrow="READ-ONLY RUNTIME CONFIGURATION" title="环境与构建状态" description="仅显示非秘密运行身份、摘要和当前门禁。凭据值与 CSRF 签名材料不会进入浏览器。" />
      {!status.database_available && <Alert severity="error" variant="outlined" sx={{ mb: 3 }}>数据库不可用；事实截止点为 UNKNOWN。读取失败时不得向交易所提交变更请求。</Alert>}
      {status.build_manifest_status !== "VERIFIED" && (
        <Alert severity="warning" variant="outlined" sx={{ mb: 3 }}>
          产品构建状态为 {status.build_manifest_status}。当前不允许向交易所提交变更请求。
        </Alert>
      )}
      <FactGrid facts={[
        { label: "环境身份", value: `${status.environment_kind} · ${status.environment_id}` },
        { label: "Profile", value: status.profile },
        { label: "账户身份", value: status.account_id },
        { label: "执行模式", value: status.authority_class },
        { label: "本机监听", value: `${status.bind}:${status.port}` },
        { label: "数据库", value: `${status.database_name} · ${status.database_available ? "AVAILABLE" : "UNKNOWN"}` },
        { label: "配置摘要", value: shortDigest(status.config_digest) },
        { label: "产品构建", value: `${status.build_manifest_status} · ${shortDigest(status.build_manifest_digest)}` },
        { label: "真实账户交易实现", value: status.live_write_build_capability },
        { label: "交易所变更请求配置", value: status.configured_runtime_real_write_gate },
        { label: "当前交易所变更请求", value: status.runtime_real_write_gate },
        { label: "邮件投递", value: `${status.email_configuration_status} · ${status.email_delivery_enabled ? "ENABLED" : "DISABLED"}` },
        { label: "视图取得时间", value: formatUtc(status.view_retrieved_at) },
      ]} />
      {status.build_manifest_violations.length > 0 && (
        <Box component="section" sx={{ mt: 5, pt: 3, borderTop: 1, borderColor: "divider" }}>
          <Typography variant="h2" sx={{ mb: 2 }}>Manifest 核对结果</Typography>
          <Stack component="ul" spacing={1} sx={{ pl: 2.5, color: "text.secondary" }}>
            {status.build_manifest_violations.map((violation) => <Typography component="li" key={violation} className="mono" variant="body2">{violation}</Typography>)}
          </Stack>
        </Box>
      )}
      {status.live_write_gate_violations.length > 0 && (
        <Box component="section" sx={{ mt: 5, pt: 3, borderTop: 1, borderColor: "divider" }}>
          <Typography variant="h2" sx={{ mb: 2 }}>交易所变更请求边界核对结果</Typography>
          <Stack component="ul" spacing={1} sx={{ pl: 2.5, color: "text.secondary" }}>
            {status.live_write_gate_violations.map((violation) => <Typography component="li" key={violation} className="mono" variant="body2">{violation}</Typography>)}
          </Stack>
        </Box>
      )}
      <Box component="section" sx={{ mt: 5, pt: 3, borderTop: 1, borderColor: "divider", maxWidth: 720 }}>
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
  const query = useQuery({ queryKey: ["plans"], queryFn: getPlans });
  const fixMutation = useMutation({
    mutationFn: ({ planId, version }: { planId: string; version: number }) => fixPlan(planId, version),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["plans"] }); },
  });
  return (
    <Box sx={{ width: "min(1120px, calc(100% - 32px))", mx: "auto", py: { xs: 4, sm: 6 } }}>
      <PageHeader eyebrow="TRADING PLAN" title="策略计划" description="开始交易只需三步：填写计划、确认计划、启动策略。启动后策略等待入场条件，不会在确认计划时下单。" />
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mb: 3 }}>
        <Button variant="contained" onClick={() => navigate("/plans/new")}>新建交易计划</Button>
        <Button variant="outlined" onClick={() => void query.refetch()}>刷新当前事实</Button>
      </Stack>
      {query.isPending && <LinearProgress aria-label="正在读取计划" />}
      {query.isError && <Alert severity="error">计划事实不可用；页面没有显示缓存副本。</Alert>}
      {fixMutation.isError && <Alert severity="warning" sx={{ mb: 2 }}>固定失败：{fixMutation.error instanceof ApiFailure ? fixMutation.error.code : "结果未知"}。产品构建输入漂移时必须先重建并核对。</Alert>}
      <Stack spacing={1.5}>
        {(query.data ?? []).map((plan) => (
          <Box key={plan.plan_id} sx={{ p: 2.5, border: 1, borderColor: "divider", bgcolor: "background.paper" }}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { md: "center" } }}>
              <Box sx={{ minWidth: 0 }}>
                <Typography variant="overline" color="text.secondary">{plan.plan_version_id ? "FIXED VERSION AVAILABLE" : "MUTABLE DRAFT"}</Typography>
                <Typography variant="h2" sx={{ mt: .5 }}>{plan.strategy_id}</Typography>
                <Typography className="mono" variant="body2" color="text.secondary">{plan.instrument_ref} · {plan.direction} · draft v{plan.draft_version}</Typography>
                <Typography className="mono" variant="caption" color="text.secondary">{shortDigest(plan.plan_version_id ?? plan.draft_content_digest)}</Typography>
              </Box>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                {!plan.plan_version_id && <Button variant="outlined" onClick={() => navigate(`/plans/${plan.plan_id}/edit`)}>编辑计划</Button>}
                {!plan.plan_version_id && <Button variant="contained" disabled={fixMutation.isPending} onClick={() => fixMutation.mutate({ planId: plan.plan_id, version: plan.draft_version })}>确认计划</Button>}
                {plan.plan_version_id && <Button variant="contained" onClick={() => navigate(`/plans/${plan.plan_version_id}/activate`)}>启动策略</Button>}
              </Stack>
            </Stack>
          </Box>
        ))}
        {query.data?.length === 0 && <Alert severity="info" variant="outlined">还没有计划草稿。先选择随构建发布的代码策略并保存参数。</Alert>}
      </Stack>
    </Box>
  );
}

function PlanActivationRoute() {
  const { planVersionId = "" } = useParams();
  const navigate = useNavigate();
  const { status } = useOutletContext<FrameContext>();
  const preview = useQuery({ queryKey: ["activation-preview", planVersionId], queryFn: () => getActivationPreview(planVersionId), enabled: Boolean(planVersionId) });
  const liveWrite = status.profile === "BINANCE_LIVE_WRITE";
  const liveReadOnly = status.profile === "BINANCE_LIVE_READ_ONLY";
  const realAccountReady = Boolean(preview.data?.live_activation_eligible);
  const activationEnabled = Boolean(
    preview.data
    && !liveReadOnly
    && (!liveWrite || realAccountReady),
  );
  const mutation = useMutation({
    mutationFn: () => createActivation({
      plan_version_id: planVersionId,
    }),
    onSuccess: (result) => { const activation = result.activation as Record<string, unknown> | undefined; navigate(`/activations/${valueOf(activation, "activation_id")}`); },
  });
  return (
    <Box sx={{ width: "min(920px, calc(100% - 32px))", mx: "auto", py: { xs: 4, sm: 6 } }}>
      <PageHeader eyebrow="ACTIVATION REVIEW" title="确认启动策略" description="交易金额已在策略计划中确定。这里仅确认启动固定计划，不再进行资金授权，也不会立即向 Binance 下单。" />
      {preview.isPending && <LinearProgress aria-label="正在读取激活复核" />}
      {preview.isError && <Alert severity="error">当前复核事实不可用，不能启动策略。</Alert>}
      {preview.data && <>
        <FactGrid facts={[
          { label: "环境", value: valueOf(preview.data, "environment_kind") },
          { label: "账户", value: valueOf(preview.data, "account_ref") },
          { label: "交易对象 / 方向", value: `${valueOf(preview.data, "instrument_ref")} / ${valueOf(preview.data, "direction")}` },
          { label: "策略", value: valueOf(preview.data, "strategy_ref") },
          { label: "交易金额", value: `${valueOf(preview.data, "trade_amount")} USDT` },
          { label: "有效期", value: formatUtc(valueOf(preview.data, "valid_until")) },
          ...(liveWrite ? [
            { label: "真实账户交易实现", value: valueOf(preview.data, "live_write_build_capability") },
            { label: "交易所变更请求", value: valueOf(preview.data, "configured_runtime_real_write_gate") },
          ] : []),
        ]} />
        <Alert severity="warning" variant="outlined" sx={{ mt: 3 }}>{valueOf(preview.data, "capital_notice")}</Alert>
      </>}
      {!liveWrite && !liveReadOnly && <Alert severity="info" variant="outlined" sx={{ mt: 3 }}>Demo 首要验证系统流程、持久动作、防重复、保护、核对、停止、恢复与接管机制；策略表现验证是次要目标，且不能直接外推到实盘。</Alert>}
      {liveReadOnly && <Alert severity="warning" sx={{ mt: 3 }}>LIVE_READ_ONLY 仅用于公共市场观察，不能激活计划或向交易所提交变更请求。</Alert>}
      {liveWrite && !realAccountReady && <Alert severity="warning" sx={{ mt: 2 }}>真实账户交易实现或当前事实尚未满足；当前不能启动 REAL 策略。</Alert>}
      {mutation.isError && <Alert severity="error" sx={{ mt: 2 }}>激活未提交：{mutation.error instanceof ApiFailure ? mutation.error.code : "结果未知"}</Alert>}
      <Button variant="contained" color="warning" sx={{ mt: 3 }} disabled={!activationEnabled || mutation.isPending} onClick={() => mutation.mutate()}>{mutation.isPending ? "正在启动…" : liveWrite ? "启动 REAL 策略" : "启动 DEMO 策略"}</Button>
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
  const actions = recordsOf(query.data?.execution_actions);
  const facts = recordsOf(query.data?.venue_facts);
  const receipts = recordsOf(query.data?.receipts);
  const stopped = Array.isArray(query.data?.stopped_categories) ? query.data.stopped_categories.map(String) : [];
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
  const lifecycle = valueOf(activation, "lifecycle");
  const takeover = lifecycle === "USER_TAKEOVER";
  const terminal = takeover || lifecycle === "COMPLETED";
  const submittedReceipt = recordOf(submit.data);
  const protectionState = valueOf(activation, "protection_state", "NONE");
  const protectionGap = activation?.has_entry_fill === true && !["WORKING", "CLOSED"].includes(protectionState);
  const ruleState = recordOf(activation?.rule_state);
  return (
    <Box sx={{ width: "min(1000px, calc(100% - 32px))", mx: "auto", py: { xs: 4, sm: 6 } }}>
      <PageHeader eyebrow="ACTIVE RESPONSIBILITY" title="激活运行与控制" description="按计划事件 → ExecutionAction → 场所事实 → 核对结论观察同一责任链；命令回执不冒充订单、成交、持仓或保护事实。" />
      {(query.isPending || timelineQuery.isPending) && <LinearProgress aria-label="正在读取激活与时间线" />}
      {(query.isError || timelineQuery.isError) && <Alert severity="error" sx={{ mb: 2 }}>当前服务器事实不可确认；页面不会把旧缓存冒充当前事实，也不会开放离线资本命令。</Alert>}
      {query.isFetching && !query.isPending && <Alert severity="info" variant="outlined" sx={{ mb: 2 }}>正在刷新服务器事实；现有值标记为过渡显示。</Alert>}
      {protectionGap && <Alert severity="error" variant="filled" sx={{ mb: 3 }}>存在已确认敞口，但场所原生保护尚未证明为 WORKING。保持在线并核对 Binance 官方入口；任何“停止”或 Receipt 都不代表已经安全。</Alert>}
      {capital.max_loss_reached === true && <Alert severity="error" variant="filled" sx={{ mb: 3 }}>计划已触发停止新增风险。系统不得再开仓或加仓；退出、保护与核对仍需完成。</Alert>}
      {takeover && <Alert severity="warning" variant="outlined" sx={{ mb: 3 }}>用户接管已持久化。Halpha 不再提交新的 READY 动作，也不会自动撤单、补保护或平仓；请在 Binance 官方入口处理，页面仅只读核对迟到事实与开放责任。</Alert>}
      {activation && <FactGrid facts={[
        { label: "Activation", value: valueOf(activation, "activation_id") },
        { label: "生命周期", value: lifecycle },
        { label: "运行状态", value: `${valueOf(activation, "run_state")} / ${valueOf(activation, "pause_reason", "NONE")}` },
        { label: "状态版本", value: valueOf(activation, "state_version") },
        { label: "Instrument / 方向", value: `${valueOf(activation, "instrument_ref")} / ${valueOf(activation, "direction")}` },
        { label: "保护", value: protectionState },
        { label: "策略状态 / 当前损失", value: `${valueOf(activation, "lifecycle")} / ${valueOf(capital, "activation_loss")} USDT`, note: capital.max_loss_reached === true ? "已停止新增风险" : "可继续按计划检查" },
        { label: "事实截止点", value: formatUtc(valueOf(activation, "latest_venue_cutoff")) },
        { label: "交易所变更请求", value: valueOf(query.data, "runtime_real_write_gate") },
      ]} />}

      <Box component="section" sx={{ mt: 5 }}>
        <Typography variant="overline" color="text.secondary">SYSTEM MECHANISM EVIDENCE · PRIMARY</Typography>
        <Typography variant="h2" sx={{ mt: .75, mb: 1 }}>Demo 系统流程与机制</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>同一 TRADEPLAN → CAP → EXE → DAT → OUT 链使用环境限定身份。系统首先验证持久动作、防重复、保护、核对、停止、恢复、接管和环境隔离。</Typography>
        <FactGrid facts={[
          { label: "策略检查", value: `${Object.keys(ruleState).length} 条规则状态 · v${valueOf(activation, "state_version")}` },
          { label: "交易金额", value: `${valueOf(capital, "max_notional")} USDT` },
          { label: "ExecutionAction", value: String(actions.length), note: actions.some((item) => valueOf(item, "state") === "SUBMITTED_UNKNOWN") ? "存在结果未决，只查询原 UUID" : "按持久身份展示" },
          { label: "VenueFact", value: String(facts.length), note: "订单状态不能推定持仓" },
          { label: "控制回执", value: String(receipts.length), note: receipts.some((item) => valueOf(item, "state") === "PROCESSING") ? "仍有命令效果待确认" : "无 PROCESSING 回执" },
          { label: "停止范围", value: stopped.length ? stopped.join(" · ") : "CLEAR" },
        ]} />
      </Box>

      <Box component="section" sx={{ mt: 5, pt: 3, borderTop: 1, borderColor: "divider" }}>
        <Typography variant="overline" color="text.secondary">STRATEGY BEHAVIOR EVIDENCE · SECONDARY</Typography>
        <Typography variant="h2" sx={{ mt: .75, mb: 1 }}>策略行为只作次要验证</Typography>
        <Alert severity="warning" variant="outlined" icon={false}>
          Demo 或历史结果不证明 LIVE 的流动性、排队、冲击、滑点、费用、资金费率、延迟、权限、可用性或真实 Alpha；绿色状态也不能消除这些差异。
        </Alert>
      </Box>

      <Box component="section" sx={{ mt: 5, pt: 3, borderTop: 1, borderColor: "divider" }}>
        <Typography variant="h2" sx={{ mb: 2 }}>动作、部分成交与保护责任</Typography>
        <Stack spacing={1}>
          {actions.map((action) => (
            <Box key={valueOf(action, "execution_action_id")} sx={{ p: 2, border: 1, borderColor: valueOf(action, "state") === "SUBMITTED_UNKNOWN" ? "warning.main" : "divider", bgcolor: "background.paper" }}>
              <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between" }}>
                <Typography sx={{ fontWeight: 750 }}>{valueOf(action, "action_kind")} · {valueOf(action, "state")}</Typography>
                <Chip size="small" variant="outlined" label={`${valueOf(action, "execution_profile_ref")} · ${valueOf(action, "authority_class")}`} />
              </Stack>
              <Typography className="mono" variant="caption" color="text.secondary">{valueOf(action, "client_order_id", "NO CLIENT UUID")} · updated {formatUtc(valueOf(action, "updated_at"))}</Typography>
              {valueOf(action, "unknown_reason", "") && <Typography role="alert" variant="body2" color="warning.main" sx={{ mt: 1 }}>UNKNOWN · {valueOf(action, "unknown_reason")}</Typography>}
            </Box>
          ))}
          {actions.length === 0 && <Alert severity="info" variant="outlined">尚无持久 ExecutionAction；这不表示条件未触发或场所已经安全。</Alert>}
        </Stack>
      </Box>

      <Box sx={{ mt: 5, pt: 3, borderTop: 1, borderColor: "divider" }}><Typography variant="h2" sx={{ mb: 1 }}>稳定控制命令</Typography><Typography color="text.secondary" sx={{ mb: 2 }}>先查看当前后果预览，再明确确认提交。重复 Idempotency-Key 返回原 Receipt；页面不会把 PROCESSING 显示成已闭合。</Typography><Stack direction={{ xs: "column", md: "row" }} spacing={1}>{controls.map((control) => <Button key={control.intent} variant="outlined" color={control.color} disabled={!activation || preview.isPending || terminal} onClick={() => preview.mutate(control.intent)}>{control.label}</Button>)}</Stack>{terminal && <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1.5 }}>接管或闭合后不再提供机器写恢复或其他控制。</Typography>}</Box>
      {intent && preview.data && <Box sx={{ mt: 3, p: 3, border: 1, borderColor: intent === "EXIT_STRATEGY" || intent === "USER_TAKEOVER" ? "error.main" : "divider", bgcolor: "background.paper" }}><Typography variant="overline">{intent}</Typography><Typography sx={{ mt: 1, mb: 2 }}>{valueOf(preview.data, "consequence")}</Typography>{intent === "RESUME_ACTIVATION" && !resumeEligible && <Alert severity="warning" sx={{ mb: 2 }}>当前没有由唯一 Executor/EXE 核对链产生的可信恢复证据；系统拒绝恢复，不能用手工摘要替代。</Alert>}<Stack direction="row" spacing={1}><Button variant="contained" color={intent === "EXIT_STRATEGY" || intent === "USER_TAKEOVER" ? "error" : "primary"} disabled={submit.isPending || !resumeEligible} onClick={() => submit.mutate(intent)}>确认提交 {intent}</Button><Button onClick={() => { setIntent(null); setIdempotencyKey(null); }}>取消</Button></Stack></Box>}
      {submit.isSuccess && valueOf(submittedReceipt, "state") !== "REJECTED" && <Alert severity="success" sx={{ mt: 2 }}>命令已持久化并返回 {valueOf(submittedReceipt, "state")} Receipt；请按状态继续核对。</Alert>}
      {submit.isSuccess && valueOf(submittedReceipt, "state") === "REJECTED" && <Alert severity="error" sx={{ mt: 2 }}>命令被拒绝：{valueOf(submittedReceipt, "reason_code")}。页面未把已持久化的拒绝 Receipt 显示为成功效果。</Alert>}
      {submit.isError && <Alert severity="error" sx={{ mt: 2 }}>命令未确认：{submit.error instanceof ApiFailure ? submit.error.code : "UNKNOWN"}</Alert>}

      <Box component="section" sx={{ mt: 5, pt: 3, borderTop: 1, borderColor: "divider" }}>
        <Typography variant="h2" sx={{ mb: 2 }}>唯一权威时间线</Typography>
        <Stack spacing={1}>
          {(timelineQuery.data ?? []).map((item) => {
            const detail = recordOf(item.detail);
            return (
              <Box key={`${valueOf(item, "source")}:${valueOf(item, "source_ref")}`} sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "150px 160px minmax(0,1fr)" }, gap: 1, p: 1.5, borderTop: 1, borderColor: "divider" }}>
                <Typography variant="caption" color="text.secondary">{formatUtc(valueOf(item, "at"))}</Typography>
                <Typography variant="caption" sx={{ fontWeight: 750 }}>{valueOf(item, "source")}</Typography>
                <Box><Typography variant="body2">{valueOf(item, "status")}</Typography><Typography className="mono" variant="caption" color="text.secondary">{shortDigest(valueOf(item, "source_ref"))} · {valueOf(detail, "action_kind", valueOf(detail, "rule_id", valueOf(detail, "source_class", "")))}</Typography></Box>
              </Box>
            );
          })}
          {timelineQuery.data?.length === 0 && <Alert severity="info" variant="outlined">当前尚无 PlanEvent、ExecutionAction 或 VenueFact。前端不会推测不存在责任。</Alert>}
        </Stack>
      </Box>
    </Box>
  );
}

const reviewEvaluationFields = [
  { key: "system_maintenance", label: "系统与维护（机制证据优先）" },
  { key: "execution_facts", label: "执行与事实" },
  { key: "capital_authority", label: "资金与权限" },
  { key: "plan", label: "计划" },
  { key: "interaction", label: "交互" },
  { key: "account_result", label: "账户结果" },
] as const;

type EvaluationDraft = Record<string, { result: string; reason: string; evidence_refs: string[] }>;

function ReviewsPage() {
  const navigate = useNavigate();
  const query = useQuery({ queryKey: ["reviews"], queryFn: getReviews, refetchInterval: 30_000 });
  return (
    <Box sx={{ width: "min(1120px, calc(100% - 32px))", mx: "auto", py: { xs: 4, sm: 6 } }}>
      <PageHeader eyebrow="OUT · ONE ACTIVATION, ONE VERSION CHAIN" title="激活复盘" description="复盘只引用计划、CAP、ExecutionAction、VenueFact 与指令回执；读取页面不会隐式建立或更新 Review。" />
      {query.isPending && <LinearProgress aria-label="正在读取复盘列表" />}
      {query.isError && <Alert severity="error">复盘事实不可用；页面未生成替代结果。</Alert>}
      <Stack spacing={1.5}>
        {(query.data ?? []).map((review) => (
          <Box key={valueOf(review, "review_id")} sx={{ p: 2.5, border: 1, borderColor: "divider", bgcolor: "background.paper" }}>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2} sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}>
              <Box>
                <Typography variant="overline" color="text.secondary">{valueOf(review, "evidence_purpose")}</Typography>
                <Typography variant="h2" sx={{ mt: .5 }}>{valueOf(review, "primary_result")} · {valueOf(review, "status")}</Typography>
                <Typography className="mono" variant="caption" color="text.secondary">activation {shortDigest(valueOf(review, "activation_id"))} · review v{valueOf(review, "review_version")}</Typography>
              </Box>
              <Button variant="outlined" onClick={() => navigate(`/reviews/${valueOf(review, "review_id")}`)}>查看证据与评价</Button>
            </Stack>
          </Box>
        ))}
        {query.data?.length === 0 && <Alert severity="info" variant="outlined">尚无已闭合激活的 Review。运行页读取不会创建复盘。</Alert>}
      </Stack>
    </Box>
  );
}

function ReviewRoute() {
  const { reviewId = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["review", reviewId], queryFn: () => getReview(reviewId), enabled: Boolean(reviewId), refetchInterval: 30_000 });
  const review = recordOf(query.data?.review);
  const [evaluations, setEvaluations] = useState<EvaluationDraft>({});

  useEffect(() => {
    const source = recordOf(review.evaluations);
    if (!Object.keys(source).length) return;
    const next: EvaluationDraft = {};
    for (const field of reviewEvaluationFields) {
      const item = recordOf(source[field.key]);
      next[field.key] = {
        result: valueOf(item, "result", "UNKNOWN"),
        reason: valueOf(item, "reason", "Owner evaluation required."),
        evidence_refs: Array.isArray(item.evidence_refs) ? item.evidence_refs.map(String) : [],
      };
    }
    setEvaluations(next);
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
        evaluations,
      };
      return completeReview(reviewId, payload);
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["review", reviewId] });
      await queryClient.invalidateQueries({ queryKey: ["reviews"] });
    },
  });

  const updateEvaluation = (key: string, field: "result" | "reason", value: string) => {
    setEvaluations((current) => ({
      ...current,
      [key]: { ...(current[key] ?? { result: "UNKNOWN", reason: "", evidence_refs: [] }), [field]: value },
    }));
  };
  const canComplete = Object.keys(evaluations).length === reviewEvaluationFields.length;

  return (
    <Box sx={{ width: "min(1000px, calc(100% - 32px))", mx: "auto", py: { xs: 4, sm: 6 } }}>
      <PageHeader eyebrow="OUT · STABLE REVIEW IDENTITY" title="一次激活复盘" description="系统机制评价置于策略行为之前。COMPLETE 不会释放额度、恢复权限、重发动作或关闭未知。" />
      {query.isPending && <LinearProgress aria-label="正在读取复盘详情" />}
      {query.isError && <Alert severity="error">复盘身份或输入当前不可读；不会自动创建替代版本。</Alert>}
      {Object.keys(review).length > 0 && <FactGrid facts={[
        { label: "Review / 版本", value: `${valueOf(review, "review_id")} / v${valueOf(review, "review_version")}` },
        { label: "Activation", value: valueOf(review, "activation_id") },
        { label: "主要结果", value: valueOf(review, "primary_result") },
        { label: "状态", value: valueOf(review, "status") },
        { label: "证据目的", value: valueOf(review, "evidence_purpose") },
        { label: "事实截止点", value: formatUtc(valueOf(review, "fact_cutoff")) },
      ]} />}

      <Box component="section" sx={{ mt: 5 }}>
        <Typography variant="overline" color="text.secondary">PRIMARY · SYSTEM PROCESS AND MECHANISM</Typography>
        <Typography variant="h2" sx={{ mt: .75, mb: 1 }}>系统机制证据</Typography>
        <Typography color="text.secondary" sx={{ mb: 2 }}>核对同一计划→CAP→EXE→DAT→OUT 链、防重复、保护、核对、停止、恢复、接管、回执和环境隔离。</Typography>
        <Box component="pre" className="mono" role="region" aria-label="Review 权威输入与开放责任" tabIndex={0} sx={{ p: 2, bgcolor: "background.paper", border: 1, borderColor: "divider", overflowX: "auto", fontSize: 11 }}>{JSON.stringify({ input_refs: review.input_refs, open_responsibilities: review.open_responsibilities }, null, 2)}</Box>
      </Box>

      <Box component="section" sx={{ mt: 5, pt: 3, borderTop: 1, borderColor: "divider" }}>
        <Typography variant="overline" color="text.secondary">SECONDARY · STRATEGY BEHAVIOR</Typography>
        <Typography variant="h2" sx={{ mt: .75, mb: 1 }}>策略行为证据</Typography>
        <Alert severity="warning" variant="outlined" icon={false}>模拟成交质量、收益或胜率不能无条件外推到 LIVE。流动性、排队、冲击、滑点、费用、资金费、延迟、权限与可用性仍可能不同。</Alert>
      </Box>

      <Box component="section" sx={{ mt: 5, pt: 3, borderTop: 1, borderColor: "divider" }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ justifyContent: "space-between", alignItems: { sm: "center" }, mb: 2 }}>
          <Box><Typography variant="h2">六项评价</Typography><Typography variant="body2" color="text.secondary">UNKNOWN 和 NOT_APPLICABLE 都必须说明原因。</Typography></Box>
          <Button variant="outlined" disabled={refreshMutation.isPending || !review.review_version} onClick={() => refreshMutation.mutate()}>按当前权威输入刷新</Button>
        </Stack>
        {refreshMutation.isError && <Alert severity="error" sx={{ mb: 2 }}>刷新失败；旧版本保持不变。</Alert>}
        <Stack spacing={2}>
          {reviewEvaluationFields.map((field) => {
            const item = evaluations[field.key] ?? { result: "UNKNOWN", reason: "", evidence_refs: [] };
            return (
              <Box key={field.key} sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", md: "240px minmax(0,1fr)" }, gap: 2, p: 2, border: 1, borderColor: "divider", bgcolor: "background.paper" }}>
                <TextField select label={field.label} value={item.result} onChange={(event) => updateEvaluation(field.key, "result", event.target.value)} disabled={valueOf(review, "status") !== "DRAFT"}>
                  {["AS_EXPECTED", "ISSUE_FOUND", "UNKNOWN", "NOT_APPLICABLE"].map((value) => <MenuItem key={value} value={value}>{value}</MenuItem>)}
                </TextField>
                <TextField label="依据与理由" value={item.reason} onChange={(event) => updateEvaluation(field.key, "reason", event.target.value)} disabled={valueOf(review, "status") !== "DRAFT"} multiline minRows={2} required />
              </Box>
            );
          })}
        </Stack>
      </Box>

      {valueOf(review, "status") === "DRAFT" && (
        <Box component="section" sx={{ mt: 5, pt: 3, borderTop: 1, borderColor: "divider" }}>
          <Typography variant="h2" sx={{ mb: 1 }}>完成本版本评价</Typography>
          <Typography color="text.secondary" sx={{ mb: 2 }}>完成只固化六项评价；每项理由已经承载发现与依据，不创建额外工作流记录。</Typography>
          {completionMutation.isError && <Alert severity="error" sx={{ mt: 2 }}>评价未完成：{completionMutation.error instanceof ApiFailure ? completionMutation.error.code : "UNKNOWN"}</Alert>}
          <Button variant="contained" sx={{ mt: 2 }} disabled={!canComplete || completionMutation.isPending} onClick={() => completionMutation.mutate()}>完成 Review v{valueOf(review, "review_version")}</Button>
        </Box>
      )}
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
