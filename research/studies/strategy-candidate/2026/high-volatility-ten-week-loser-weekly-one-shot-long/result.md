# 结果：高波动中期输家 one-shot LONG

## 结论

`DOES_NOT_SUPPORT`

固定的 RV28 高半区、MOM70 底部 30%、`0.25x LONG / 7d` 在 `development` 未通过预注册门。后期不打开、handoff 不生成；按 family stop rule，不再搜索中期反转的 size、波动 cutoff、窗口、币种或方向邻域。

## 关键证据

- 交易 / entry dates / 目标：`125 / 50 / 21`
- base / stress 扣全资金门槛周日期均值：`0.620030% / 0.530429%`
- stress 95% 区间：`[-0.464572%, 1.754131%]`
- base 相对无条件输家 / 低波输家 / 高波无筛选 / 高波赢家：`0.253732% / 0.535328% / -0.015853% / 0.235444%`
- gross 市场超额：`0.292492%`
- base MDD：`-12.647372%`
- 失败门：`base_beats_highvol_scheduled, minimum_positive_categories, positive_pnl_concentration_below_limit`

这只判断当前幸存永续、固定单目标和零售成本转换；不推翻论文的 spot long-short 多币组合，也不证明其他数据机制不存在。
