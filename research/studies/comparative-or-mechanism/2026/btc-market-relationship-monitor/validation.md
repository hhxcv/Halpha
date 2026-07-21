# 研究与页面验证记录

最终评估：`READY_TO_SHARE_WITH_CAVEATS`。统计结论标签为 `SUPPORTS_WITHIN_SCOPE`。验证没有把关联升级为 Alpha、策略或盈利证据。

## 数据与计算一致性

运行：

```powershell
research/.venv/Scripts/python.exe -m unittest discover -s research/studies/comparative-or-mechanism/2026/btc-market-relationship-monitor/tests -v
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/btc-market-relationship-monitor/monitor.py refresh --offline
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/btc-market-relationship-monitor/validate_results.py
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/btc-market-relationship-monitor/monitor.py refresh
research/.venv/Scripts/python.exe research/studies/comparative-or-mechanism/2026/btc-market-relationship-monitor/validate_results.py
```

结果：

- 5 个单元测试全部通过：已闭合 cutoff、开放/无效/重复 bar 清理、缺失日期不跨日拼接、已知 beta 合成数据恢复、universe 排除与 DGB 例外。
- 410 行结果、402 个已分析、385 个显著、238 个强关联、8 个样本不足与摘要完全对账。
- 检查 BTC 加 410 个对象共 411 个缓存文件：重复 open time 0、非正 close 0、cutoff 后 bar 0。
- 独立于主分析函数，直接从缓存重算 ETH/SOL/SUI/DOGE 的 Pearson、beta、波动倍数；所有绝对误差小于 `5e-10`。
- Coin Metrics 可用的 ETH/DOGE 均方向一致，Pearson 跨源差分别为 0.0013/0.0014，低于预设质量检查的 0.02。
- 离线结果 CSV SHA-256 为 `bfeb1557edcda65fb1645d5c885c4193101650d65ef6c5926e6c69ef16831e6b`，在线结果 CSV 为 `2268bca6e540a044be3c65699d0f0ad0720af0f037cac5452204c5d4b4682f31`；差异来自 `fetch_status` 运行来源。剔除该运行态字段后，两次分析身份均为 `581d0b3361cdfb4d404b24cd49aef04d2b69da258c6f46930a0133134e9055fb`。
- 最终 `evidence/validation.json` 为零错误，保留逐项重算值和全部 Git 固定证据哈希。

## 页面浏览器验证

使用本地研究服务 `127.0.0.1:8766` 和真实最终产物验证，没有启动或修改产品运行时。原默认端口 8765 已被现有核心进程占用；连通性探测只得到 `ROUTE_NOT_FOUND`，没有读取或持久化产品业务数据，随后将研究默认端口改为 8766。首次研究页面检查发现 Plotly 内联布局样式被 CSP 阻止、WebGL 在硬化测试浏览器不可用、favicon 404；修订为自托管脚本加 inline CSS、SVG scatter 和空 favicon 响应后重新验证。

最终 Playwright 结果：

- 1440×1000 桌面：摘要、散点、滚动相关、完整结果表和跨源状态可见；console 0 error / 0 warning。
- 搜索 `SUI` 后只剩 1 行；点击该行，滚动相关标题变为 `SUIUSDT · 90 日滚动相关`。
- 打开“仅强关联”后计数由 385 变为 238；console 仍为 0 error / 0 warning。
- 390×844 窄屏：header、四项摘要和图表无横向页面溢出；宽表保留自身横向滚动，不压缩字段含义；console 0 error / 0 warning。
- 启动顺序测试确认 HTTP server 先绑定、初始公开数据刷新再进入后台；使用持久快照重启后，页面与摘要 API 连续请求实测约 52 ms，不再等待约一分钟才能访问页面。
- 证据截图：`evidence/playwright/desktop-1440x1000.png`、`evidence/playwright/narrow-390x844.png`。

## 仍需保留的限制

- 当前名单而非历史 point-in-time universe，存在幸存者偏差。
- 只有 Binance Spot UTC 日收盘；不覆盖日内、跨场所和执行机制。
- bStock 排除是结果揭示后的语义修订，已公开记录，不能倒签成原始预注册规则。
- Coin Metrics Community 不能免费覆盖 SOL/SUI，本轮不能对这两个锚点做同样的跨源核对。
- 页面每 15 分钟检查一次，但日线统计只在新 UTC 日线闭合后变化；它不是实时交易终端。
