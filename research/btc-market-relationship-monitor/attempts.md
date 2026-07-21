# 重要尝试与失败

- 2026-07-21：首次 UI 概念图生成请求因图像服务网络错误失败；第二次缩短提示后成功。失败未改变页面数据契约或统计方法。
- 2026-07-21：启封前确认全局 Python `D:/Environment/python313/python.exe` 没有 Pandas；研究必须使用独立 `research/.venv`，其中已有 pandas 3.0.3、NumPy 2.4.6、SciPy 1.18.0、Plotly 6.9.0，但缺 statsmodels。决定在研究依赖锁增加 statsmodels 0.14.6，不进入产品依赖。
- 2026-07-21：Coin Metrics Community `ReferenceRateUSD` 对五个锚点只返回约 6 个最新观测，未达到 120 日门，不能作为跨源证据。改用官方说明为 daily close 的 `PriceUSD` 并逐资产请求；BTC、ETH、DOGE 有完整免费历史，SOL、SUI 返回 403，后两项保留为不可用，不用短样本替代。
- 2026-07-21：首次全 universe 抓取中 CELRUSDT 与 LPTUSDT 单次 read timeout；主流程正确保留失败而未静默缩小分母。公开 GET 增加最多三次、0.5/1 秒退避的有限重试后重跑。
- 2026-07-21：首次结果后审查 44 个短历史对象，发现 NVDAB、TSLAB、SPYB 等 36 个 Binance bStock 被当前上游 Spot 名单因缺 taxonomy 默认归为 `CRYPTO_NATIVE`。Binance 官方资料确认它们是股票支持的 tokenized securities。新增窄合取排除规则并记录精确名单；这是结果揭示后的 attempt 2 数据语义修正，不能倒签为预注册。由于 36 个对象均不足 120 日，它只纠正 universe/短样本分母，不改变已分析结果。
- 2026-07-21：第一次实现 bStock 后缀合取规则时还误排除了 DGB（DigiByte），使已分析对象从 402 变为 401。离线重演哈希检查与精确排除名单审查发现该问题；增加固定快照下的 DGB 显式例外。最终 36 个排除对象全部是本轮识别的 bStock，未来 universe 变化必须重新审核。
- 2026-07-21：UTC cutoff 最初以秒序列化，丢失了真实边界的 `.999` 毫秒；计算未受影响，但独立缓存检查会把最后一根合法日线误判为超过边界。改为毫秒精度并增加全缓存 cutoff 检查。
- 2026-07-21：最终缓存离线重演与在线重抓均为 410/402/385/238，剔除运行来源 `fetch_status` 后的分析身份 SHA-256 同为 `581d0b3361cdfb4d404b24cd49aef04d2b69da258c6f46930a0133134e9055fb`。完整 CSV 哈希分别为离线 `bfeb1557...31e6b`、在线 `2268bca6...2f31`，差异被明确保留而未伪装成 byte-identical。
- 2026-07-21：原默认端口 8765 已被现有核心进程占用，首次连通性探测只得到 `ROUTE_NOT_FOUND`，没有取得或持久化产品业务数据。研究页改用独立默认端口 8766；没有启动或修改核心运行时。
- 2026-07-21：首次真实研究页面检查发现 Plotly inline style 被 CSP 阻止、测试浏览器无 WebGL、favicon 404。调整为仅放开 inline CSS、SVG scatter 和空 favicon 响应后，桌面和 390px 窄屏均为 0 console error / 0 warning；搜索、行选择和强关联过滤通过。
- 2026-07-21：正常 `serve` 原先在绑定端口前同步刷新约 411 个 symbol，导致首次可访问需要约 50–60 秒。调整为先绑定并立即显示已持久化快照，初始刷新进入后台；新增启动顺序测试，未增加常驻组件。
