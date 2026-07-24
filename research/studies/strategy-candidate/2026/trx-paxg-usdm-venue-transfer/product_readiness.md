# 产品可达性审计（历史记录，当前暂停）

> 2026-07-22 研究复核已将候选降为 `INSUFFICIENT_EVIDENCE`。即使以下技术路径可达，也不再构成实施理由；不得据此修改 L4、产品契约、Demo instrument 或创建计划。详见 `../trx-paxg-overfit-logic-audit/result.md`。

## 已确认可达

- 2026-07-22 读取 `https://demo-fapi.binance.com/fapi/v1/exchangeInfo`：TRXUSDT、PAXGUSDT 均为 `TRADING`、`PERPETUAL`，所以 Binance Demo 场所本身提供两条腿。
- 当前产品已使用 NautilusTrader Binance USD-M Demo 适配器，成熟组件能够加载多个 instrument；不需要自研行情、时钟、订单、成交或 funding 基础框架。
- 当前计划创建 API 已要求 `creator_kind`，AI 创建时可显式提交 `AI`。

## 当前产品不能忠实表达

- L4 当前只允许一个正式策略 `ONE_SHOT_DONCHIAN_ATR_BREAKOUT`，Demo instrument 只有 BTCUSDT/ETHUSDT，并明确排除第二个正式策略。
- `TradePlanContent`、`TradePlanVersion`、`PlanActivation` 都只有一个 `instrument_ref`、一个 `direction` 和一个 `target_exposure`。
- `PlanEvent` 只有一个 `proposed_action`；当前 transition 还强制提议 instrument 等于 activation 的单一 instrument。
- 策略清单只返回一个 one-shot 策略，参数校验和 runtime 均直接依赖 `OneShotParameters`/`OneShotDonchianAtrLogic`。
- Demo runtime 只加载 BTCUSDT/ETHUSDT；公共行情工作台当前只映射 BTCUSDT。
- 当前 TRADEPLAN 契约是一轮入场后平仓即结束的单次计划，未定义同一激活的两腿月度目标、部分成交、组合退出和重启恢复。

因此，创建两个互不协调的单腿计划、复用现有 Donchian 策略名或通过手工脚本下两笔单，都不能算该候选的产品 Demo 验证。

## 所需所有者决定

HALPHA-ALP-002/003 要求项目所有者明确选中候选后才能进入产品。忠实实现还会改变当前 L4 的策略与 instrument 选择，并需要为多工具目标更新 ALP/TRADEPLAN 的稳定契约；这属于产品方向和跨领域语义变化，不能由研究结果自动生效。

## 若所有者选中，最小忠实切片

1. 先决定候选是替换当前正式策略还是作为第二个正式策略；明确 Demo-only、两腿、最大 gross 0.5、无真实资金。
2. 在稳定设计中定义一个计划携带多个固定 instrument target，以及同一月度触发产生一组动作时的身份、部分结果、停止、整组退出和恢复语义；不建设组合优化或通用篮子平台。
3. 产品只实现这一个固定 25/25 候选和薄 NautilusTrader 适配，增加 TRX/PAXG Demo load ids；不导入研究运行时。
4. 先用 `decision_trace.json` 对齐纯决策，再做 Nautilus 离线事件/订单/funding/保证金验证。
5. 最后通过工作台创建 `creator_kind: AI` 的小额 Demo 计划，验证两腿下单、部分结果、事实核对、停止和退出；计划创建不等于激活，激活也不等于已成交。

这是一个明确但不小的产品切片，不应隐藏成“加两个 symbol”。在所有者选择前，产品改动保持停止。
