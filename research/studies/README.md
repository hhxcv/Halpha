# 研究问题目录契约

本目录只保存具体、可证伪且可独立复现的研究问题。一个叶目录对应一个问题；目录位置表达开题时确定的主要研究类型和开题年份，不表达结论、进度、资产类别或产品状态。

## 路径格式

```text
studies/<research-kind>/<opening-year>/<question-slug>/
```

`research-kind` 与 checkpoint 中的主要研究类型一一对应：

| checkpoint 类型 | 目录名 |
|---|---|
| `DESCRIPTIVE` | `descriptive` |
| `COMPARATIVE_OR_MECHANISM` | `comparative-or-mechanism` |
| `PREDICTIVE` | `predictive` |
| `STRATEGY_CANDIDATE` | `strategy-candidate` |

- `opening-year` 是查看结果前固定问题和否定条件的年份。
- `question-slug` 使用稳定的英文 kebab-case 名称，描述问题而不是预期结论。
- 叶目录按问题实际需要保留 README、checkpoint、来源、数据身份、代码、命令、尝试、失败、结果与限制；不为了统一外观强制增加空文件或通用流水线。
- 机制、对象、场所、数据区间、父问题和结论属于问题证据，不再增加目录层级。使用 `rg` 检索这些字段。
- 不创建 `active`、`completed`、`failed`、`supported` 等状态目录，也不在结论变化时移动问题。

## 类型和主张变化

混合多个类型的研究采用其最强预期主张对应的类型。若已经查看结果后才准备扩大主张，例如从描述相关性转为预测收益或可交易策略，应新建更高门槛的问题并引用原问题；不得移动旧目录来制造事前分类或预注册的假象。

## 历史迁移

`legacy/2026/` 保存目录契约建立前已经完成的 32 个问题。本次只把它们从 `research/<question>/` 等距迁移到 `research/studies/legacy/2026/<question>/`，没有重新分类、重演或改写研究结论。

历史 `attempts`、checkpoint 和结果文件中的旧命令、路径与时间戳记录的是当时实际发生的执行，继续原样保留。当前复现入口只在 README、`commands.md` 等面向当前操作的说明中使用新路径。`research/catalog-2026-07-21.json` 是迁移前 33 个问题的冻结完整性快照，不是需要持续维护的注册表。

## 持续更新型问题

持续更新不改变“一问题一目录”的原则。固定 cutoff、可审计并支持结论的产物保存在问题目录的 `evidence/`；最新刷新状态、下载缓存和可重取的大型数据保存在 Git 外。页面或 API 可以优先读取 Git 外最新状态，在其不存在时回退到固定证据，但不得反复覆盖已经完成的证据。共享 raw 身份、外部数据生命周期和兼容迁移规则由 `research/README.md` 统一说明。

## 字节身份与换行

问题目录中的 checkpoint、manifest 和结果可能使用 SHA-256 固定文件字节。`research/studies/.gitattributes` 因此对已采用字节身份的新增证据族禁止 Git 换行转换：这些研究文件按产生时的原始字节提交和检出，避免 Windows 的 CRLF 与 Git 的 LF 规范化使同一证据在新工作树中失去身份；未列入的既有历史目录继续沿用仓库规则。新增或重演研究仍应由生成代码显式选择稳定换行；本规则只保证已经记录的字节不被 Git 隐式改写。
