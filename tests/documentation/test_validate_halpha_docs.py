from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = (
    REPO_ROOT
    / ".agents"
    / "skills"
    / "write-halpha-docs"
    / "scripts"
    / "validate_halpha_docs.py"
)
SPEC = importlib.util.spec_from_file_location(
    "halpha_docs_validator_for_tests", VALIDATOR_PATH
)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - importlib contract guard
    raise RuntimeError(f"Unable to load documentation validator from {VALIDATOR_PATH}")
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


class DocumentationValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write(self, relative_path: str, text: str) -> Path:
        path = self.repo / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def validate(self, path: Path, text: str | None = None) -> list[object]:
        document = text if text is not None else path.read_text(encoding="utf-8")
        return validator.validate_markdown(self.repo, path, document)

    def test_accepts_local_heading_duplicate_html_and_self_fragments(self) -> None:
        self.write(
            "docs/target.md",
            """# Target

## 2.1 范围【ABC-001】

## 重复

## 重复

<a id="manual-anchor"></a>
""",
        )
        source = self.write(
            "docs/source.md",
            """# Source

[heading](target.md#21-%E8%8C%83%E5%9B%B4abc-001)
[duplicate](target.md#重复-1 "optional title")
[manual](target.md#manual-anchor)
[self](#source)
[external](https://example.invalid/missing.md#L999)
""",
        )

        self.assertEqual(self.validate(source), [])

    def test_rejects_missing_markdown_fragment(self) -> None:
        self.write("docs/target.md", "# Existing\n")
        source = self.write("docs/source.md", "[missing](target.md#not-there)\n")

        issues = self.validate(source)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "ERROR")
        self.assertIn("Markdown fragment 不存在", issues[0].message)

    def test_does_not_treat_fenced_heading_as_a_fragment(self) -> None:
        source = self.write(
            "docs/source.md",
            """```markdown
# Not a rendered heading
```

[missing](#not-a-rendered-heading)
""",
        )

        issues = self.validate(source)

        self.assertEqual(len(issues), 1)
        self.assertIn("Markdown fragment 不存在", issues[0].message)

    def test_validates_local_github_line_fragments_and_skips_external_urls(
        self,
    ) -> None:
        self.write("docs/target.yaml", "one: 1\ntwo: 2\nthree: 3\n")
        source = self.write(
            "docs/source.md",
            """[single](target.yaml#L3)
[range](/docs/target.yaml#L1-L3)
[too-far](target.yaml#L4)
[reversed](target.yaml#L3-L2)
[bad-format](target.yaml#L01)
[zero-line](target.yaml#L0)
[external](https://github.com/example/project/blob/main/target.yaml#L999)
""",
        )

        issues = self.validate(source)
        messages = [issue.message for issue in issues]

        self.assertEqual(len(issues), 4)
        self.assertEqual({issue.severity for issue in issues}, {"ERROR"})
        self.assertTrue(any("超出目标范围" in message for message in messages))
        self.assertTrue(any("范围倒置" in message for message in messages))
        self.assertTrue(any("格式无效" in message for message in messages))

    def test_rejects_missing_relative_target(self) -> None:
        source = self.write("docs/source.md", "[missing](missing.md#fragment)\n")

        issues = self.validate(source)

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "ERROR")
        self.assertEqual(issues[0].message, "相对链接目标不存在：missing.md")

    def test_cli_fails_for_broken_local_fragment(self) -> None:
        self.write(".git/keep", "")
        self.write("docs/source.md", "# Existing\n\n[broken](#missing)\n")

        result = subprocess.run(
            [sys.executable, str(VALIDATOR_PATH), "docs/source.md"],
            cwd=self.repo,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn(b"[ERROR]", result.stdout)

    def l3_document(self, direct_dependencies: str) -> tuple[Path, str]:
        text = f"""# Validator fixture

**文档编号：** HALPHA-TST-002
**层级：** L3
**L3 类型：** DOMAIN
**主要语义所有者：** TST
**语言版本：** zh-CN
**上位文档或条款：** HALPHA-TST-001
**直接依赖：** {direct_dependencies}
**适用纵向约束：** HALPHA-ENG-001
**本文档负责：** 测试头格式
**本文档不负责：** 产品语义

---

# 0. Scope
"""
        path = self.write("docs/L3/HALPHA-TST-002-validator-fixture.zh-CN.md", text)
        return path, text

    def test_accepts_mechanically_complete_l3_header(self) -> None:
        path, text = self.l3_document("HALPHA-DAT-002")

        self.assertEqual(self.validate(path, text), [])

    def test_accepts_explicitly_empty_l3_direct_dependencies(self) -> None:
        path, text = self.l3_document("无 L3 直接依赖")

        self.assertEqual(self.validate(path, text), [])

    def test_requires_owner_for_declared_domain_l3(self) -> None:
        path, text = self.l3_document("HALPHA-DAT-002")
        text = text.replace("**主要语义所有者：** TST\n", "")

        messages = [issue.message for issue in self.validate(path, text)]

        self.assertIn("L3 文档头缺少主要语义所有者", messages)

    def test_requires_l3_type_dependencies_and_vertical_constraints(self) -> None:
        path, text = self.l3_document("HALPHA-DAT-002")
        text = text.replace("**L3 类型：** DOMAIN\n", "")
        text = text.replace("**主要语义所有者：** TST\n", "")
        text = text.replace("**直接依赖：** HALPHA-DAT-002\n", "")
        text = text.replace("**适用纵向约束：** HALPHA-ENG-001\n", "")

        messages = [issue.message for issue in self.validate(path, text)]

        self.assertIn("L3 文档头缺少 L3 类型", messages)
        self.assertIn("L3 文档头缺少直接依赖", messages)
        self.assertIn("L3 文档头缺少适用纵向约束", messages)

    def test_rejects_construction_identifier_in_l0_through_l3(self) -> None:
        path, text = self.l3_document("HALPHA-DAT-002")
        text += "\n当前先完成 P0，并等待 B04。\n"

        messages = [issue.message for issue in self.validate(path, text)]

        self.assertIn("L0–L3 不得包含当前阶段或建设包代号：B04、P0", messages)

    def test_rejects_generic_p_stage_label_in_l0_through_l3(self) -> None:
        path, text = self.l3_document("HALPHA-DAT-002")
        text += "\n具体 P 阶段由当前计划选择。\n"

        messages = [issue.message for issue in self.validate(path, text)]

        self.assertTrue(
            any("L0–L3 不得包含当前阶段或建设包代号：P 阶段" in item for item in messages)
        )

    def test_rejects_spaced_or_punctuated_construction_identifier(self) -> None:
        path, text = self.l3_document("HALPHA-DAT-002")
        text += "\n当前先完成 P 0、B-04 与 R_00。\n"

        messages = [issue.message for issue in self.validate(path, text)]

        self.assertTrue(
            any(
                "L0–L3 不得包含当前阶段或建设包代号：B-04、P 0、R_00"
                in item
                for item in messages
            )
        )

    def test_rejects_phase_narrative_without_construction_identifier(self) -> None:
        path, text = self.l3_document("HALPHA-DAT-002")
        text += "\n第一阶段完成接口，第二阶段再补失败处理。\n"

        messages = [issue.message for issue in self.validate(path, text)]

        self.assertTrue(
            any("L0–L3 不得承载建设阶段叙事" in item for item in messages)
        )

    def test_allows_domain_lifecycle_stage_language(self) -> None:
        path, text = self.l3_document("HALPHA-DAT-002")
        text += "\n订单处于场所生命周期的成交阶段时，仍以场所事实为准。\n"

        messages = [issue.message for issue in self.validate(path, text)]

        self.assertFalse(any("建设阶段叙事" in message for message in messages))

    def test_rejects_precise_build_artifact_in_l0_through_l2(self) -> None:
        text = """# Validator fixture

**文档编号：** HALPHA-TST-003
**层级：** L2
**语言版本：** zh-CN
**上位文档或条款：** HALPHA-TST-001
**本文档负责：** 测试头格式
**本文档不负责：** 产品语义

---

# 0. Scope

稳定规则要求 BuildManifest 和 qualification_digest。
"""
        path = self.write(
            "docs/L2/HALPHA-TST-003-layer-fixture.zh-CN.md", text
        )

        messages = [issue.message for issue in self.validate(path, text)]

        self.assertTrue(
            any("L0–L2 不得拥有具体构建制品名或摘要字段" in message for message in messages)
        )

    def test_rejects_phase_conditioned_stable_rule(self) -> None:
        path, text = self.l3_document("HALPHA-DAT-002")
        text += "\n只有当前阶段的当前设计明确允许时，才恢复原状态。\n"

        messages = [issue.message for issue in self.validate(path, text)]

        self.assertTrue(
            any("L0–L3 不得承载建设阶段叙事" in message for message in messages)
        )

    def test_rejects_l3_object_name_in_l1(self) -> None:
        text = """# Validator fixture

**文档编号：** HALPHA-TST-003
**层级：** L1-D
**语言版本：** zh-CN
**上位文档：** HALPHA-TST-001
**本文档负责：** 总体方向
**本文档不负责：** 技术对象

---

# 0. Scope

总体架构直接规定 ExecutionAction 和 PlanActivation。
"""
        path = self.write(
            "docs/L1/HALPHA-TST-003-layer-fixture.zh-CN.md", text
        )

        messages = [issue.message for issue in self.validate(path, text)]

        self.assertTrue(any("L0–L1 不得拥有 L2/L3 技术对象名" in item for item in messages))

    def test_rejects_diff_marker_before_markdown_heading(self) -> None:
        source = self.write("docs/source.md", "+ # Not a heading\n")

        messages = [issue.message for issue in self.validate(source)]

        self.assertEqual(messages, ["Markdown 标题残留 diff 加号"])

    def test_chinese_document_does_not_require_a_translation(self) -> None:
        zh = self.write(
            "docs/L1/HALPHA-TST-001-document.zh-CN.md",
            """# 中文文档

**文档编号：** HALPHA-TST-001
**层级：** L1-A
**语言版本：** zh-CN
**上位文档或条款：** HALPHA-CON-001
**本文档负责：** 测试
**本文档不负责：** 产品语义

## 规则
""",
        )

        self.assertEqual(self.validate(zh), [])

    def test_rejects_english_pair_file(self) -> None:
        en = self.write("docs/L1/HALPHA-TST-001-document.en-US.md", "# English\n")

        messages = [issue.message for issue in self.validate(en)]

        self.assertEqual(messages, ["L0–L4 只保留中文正文，不得创建英文配对文件"])

if __name__ == "__main__":
    unittest.main()
