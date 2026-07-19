#!/usr/bin/env python3
"""Run mechanical checks for Halpha design documentation.

This script intentionally does not encode product semantics. It checks document
structure, metadata, YAML, links, and a few stable layer rules so that human or
agent review can focus on ownership, level, consumers, and failure behavior.
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import yaml


DOC_NAME_RE = re.compile(
    r"^(HALPHA-[A-Z]+-\d{3})-[a-z0-9]+(?:-[a-z0-9]+)*\.(zh-CN|en-US)\.md$"
)
METADATA_RE = re.compile(r"^\*\*([^*]+?)[：:]\*\*\s*(.*?)\s*$")
SEMANTIC_ANCHOR_RE = re.compile(r"【([A-Z][A-Z0-9-]+)】")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?:[ \t]+|$)(.*)$")
MARKDOWN_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
HTML_FRAGMENT_RE = re.compile(
    r'''(?<![-\w])(?:id|name)\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s"'=<>`]+))''',
    re.IGNORECASE,
)
GITHUB_LINE_FRAGMENT_RE = re.compile(r"^L([1-9]\d*)(?:-L([1-9]\d*))?$")
DOCUMENT_REFERENCE_RE = re.compile(r"\bHALPHA-[A-Z]+-\d{3}\b")
CONSTRUCTION_IDENTIFIER_RE = re.compile(
    r"(?<![A-Za-z0-9_])(?:(?:P|B|R)[\s_-]*\d{1,3}|P\s*阶段|P\s+stages?)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
STABLE_LAYER_CONSTRUCTION_PHASE_RE = re.compile(
    r"(?:"
    r"(?:当前|本|建设|实施|开发|交付|后续|第[一二三四五六七八九十0-9]+)\s*阶段|"
    r"阶段性(?:目标|范围|顺序|计划|进度|交付|建设|实现)|"
    r"(?<![A-Za-z0-9_])(?:current|this|construction|implementation|development|delivery|"
    r"next|first|second|third|\d+(?:st|nd|rd|th))\s+(?:stage|phase)(?![A-Za-z0-9_])|"
    r"(?<![A-Za-z0-9_])(?:stage|phase)[ -]specific(?![A-Za-z0-9_])"
    r")",
    re.IGNORECASE,
)
STABLE_LAYER_BUILD_ARTIFACT_RE = re.compile(
    r"(?:BuildManifest|Release[ -]Candidate|build_digest|qualification_digest|"
    r"source_tree_sha256)",
    re.IGNORECASE,
)
HIGH_LEVEL_TECHNICAL_OBJECT_RE = re.compile(
    r"(?:ExecutionAction|PlanActivation|TradePlanVersion|"
    r"VenueFact|ProposedAction|PlanEvent)"
)
MALFORMED_ADDED_HEADING_RE = re.compile(r"^\s*\+\s*#{1,6}(?:\s|$)")


@dataclass(frozen=True)
class Issue:
    severity: str
    path: Path
    message: str


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("找不到包含 .git 的仓库根目录")


def run_git_paths(repo: Path, args: list[str]) -> set[Path]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        (repo / item.decode("utf-8")).resolve()
        for item in result.stdout.split(b"\0")
        if item
    }


def changed_files(repo: Path) -> set[Path]:
    paths = set()
    paths |= run_git_paths(repo, ["diff", "--name-only", "-z"])
    paths |= run_git_paths(repo, ["diff", "--cached", "--name-only", "-z"])
    paths |= run_git_paths(repo, ["ls-files", "--others", "--exclude-standard", "-z"])
    return {path for path in paths if path.is_file()}


def decode_utf8(path: Path) -> tuple[str | None, list[Issue]]:
    try:
        return path.read_bytes().decode("utf-8-sig"), []
    except UnicodeDecodeError as exc:
        return None, [Issue("ERROR", path, f"不是有效 UTF-8：{exc}")]


def parse_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in text.splitlines():
        match = METADATA_RE.match(line)
        if match:
            metadata[match.group(1).strip()] = match.group(2).strip()
    return metadata


def first_value(metadata: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        if key in metadata:
            return metadata[key]
    return None


def heading_anchor_signature(text: str) -> tuple[tuple[int, tuple[str, ...]], ...]:
    """Return language-neutral heading levels and semantic anchors."""

    signature: list[tuple[int, tuple[str, ...]]] = []
    for line in text.splitlines():
        heading = MARKDOWN_HEADING_RE.match(line)
        if not heading:
            continue
        marker = line.lstrip().split(maxsplit=1)[0]
        signature.append(
            (len(marker), tuple(SEMANTIC_ANCHOR_RE.findall(heading.group(1))))
        )
    return tuple(signature)


def validate_bilingual_pairs(repo: Path, targets: set[Path]) -> list[Issue]:
    """Check L0/L1 language pairs directly from their ordinary filenames."""

    issues: list[Issue] = []
    checked: set[tuple[Path, Path]] = set()
    for path in sorted(targets, key=lambda item: str(item).lower()):
        match = DOC_NAME_RE.match(path.name)
        rel = relative_path(repo, path)
        if (
            not match
            or len(rel.parts) < 2
            or rel.parts[0] != "docs"
            or rel.parts[1] not in {"L0", "L1"}
        ):
            continue
        language = match.group(2)
        other_language = "en-US" if language == "zh-CN" else "zh-CN"
        counterpart = path.with_name(
            path.name.replace(f".{language}.md", f".{other_language}.md")
        )
        pair = tuple(sorted((path.resolve(), counterpart.resolve()), key=str))
        if pair in checked:
            continue
        checked.add(pair)
        if not counterpart.is_file():
            issues.append(Issue("ERROR", path, f"缺少双语配对文件：{counterpart.name}"))
            continue

        first_text, first_decode_issues = decode_utf8(path)
        second_text, second_decode_issues = decode_utf8(counterpart)
        issues.extend(first_decode_issues)
        issues.extend(second_decode_issues)
        if first_text is None or second_text is None:
            continue

        first_metadata = parse_metadata(first_text)
        second_metadata = parse_metadata(second_text)
        for label, keys in (
            ("文档编号", ("文档编号", "Document ID")),
            ("层级", ("层级", "Level")),
        ):
            if first_value(first_metadata, *keys) != first_value(second_metadata, *keys):
                issues.append(Issue("ERROR", path, f"双语配对{label}不一致：{counterpart.name}"))
        if heading_anchor_signature(first_text) != heading_anchor_signature(second_text):
            issues.append(
                Issue("ERROR", path, f"双语配对标题层级或语义锚点不一致：{counterpart.name}")
            )
    return issues


def relative_path(repo: Path, path: Path) -> Path:
    try:
        return path.resolve().relative_to(repo.resolve())
    except ValueError:
        return path.resolve()


def github_heading_slug(value: str) -> str:
    """Return the GitHub-style slug used by headings in Halpha Markdown."""

    value = html.unescape(value)
    value = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("`", "").strip().lower()
    value = "".join(
        character
        for character in value
        if character in {"-", "_"}
        or unicodedata.category(character)[0] not in {"C", "P", "S"}
    )
    return re.sub(r"\s", "-", value)


def markdown_fragment_ids(text: str) -> set[str]:
    """Collect GitHub heading slugs and explicit HTML fragment identifiers."""

    fragments: set[str] = set()
    heading_fragments: set[str] = set()
    fence_character: str | None = None
    fence_length = 0

    for line in text.splitlines():
        fence = MARKDOWN_FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            if fence_character is None:
                fence_character = marker[0]
                fence_length = len(marker)
            elif marker[0] == fence_character and len(marker) >= fence_length:
                fence_character = None
                fence_length = 0
            continue
        if fence_character is not None:
            continue

        heading = MARKDOWN_HEADING_RE.match(line)
        if heading:
            heading_text = re.sub(r"[ \t]+#+[ \t]*$", "", heading.group(1))
            base = github_heading_slug(heading_text)
            if base:
                candidate = base
                suffix = 0
                while candidate in heading_fragments:
                    suffix += 1
                    candidate = f"{base}-{suffix}"
                heading_fragments.add(candidate)
                fragments.add(candidate)

        for match in HTML_FRAGMENT_RE.finditer(line):
            fragment = next(group for group in match.groups() if group is not None)
            fragments.add(html.unescape(fragment))

    return fragments


def markdown_link_destination(raw_target: str) -> str:
    """Remove Markdown angle brackets or an optional destination title."""

    target = raw_target.strip()
    if target.startswith("<"):
        closing = target.find(">")
        return target[1:closing] if closing >= 0 else target
    return target.split(maxsplit=1)[0] if target else ""


def local_link_target(
    repo: Path, source: Path, raw_target: str
) -> tuple[Path, str | None, str] | None:
    """Resolve a repository-local Markdown destination, or skip an external URL."""

    target = markdown_link_destination(raw_target)
    if (
        not target
        or target.startswith("//")
        or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target)
    ):
        return None

    path_part, separator, raw_fragment = target.partition("#")
    decoded_path = unquote(path_part.split("?", 1)[0])
    fragment = unquote(raw_fragment) if separator else None

    if not decoded_path:
        linked = source.resolve()
    elif decoded_path.startswith(("/", "\\")):
        linked = (repo / decoded_path.lstrip("/\\")).resolve()
    else:
        linked = (source.parent / decoded_path).resolve()

    repo_root = repo.resolve()
    if not linked.is_relative_to(repo_root):
        return None
    return linked, fragment, decoded_path


def validate_l3_header(path: Path, metadata: dict[str, str]) -> list[Issue]:
    """Check only the mechanical shape of an L3 header and its references."""

    # Deliberately do not decide whether a dependency is semantically direct; that
    # check has a separate owner.
    issues: list[Issue] = []
    l3_type = first_value(metadata, "L3 类型", "L3 Type")
    direct_dependencies = first_value(metadata, "直接依赖", "Direct Dependencies")
    vertical_constraints = first_value(
        metadata, "适用纵向约束", "Applicable Vertical Constraints"
    )

    if not l3_type:
        issues.append(Issue("ERROR", path, "L3 文档头缺少 L3 类型"))
    elif l3_type not in {"DOMAIN", "ORCHESTRATION"}:
        issues.append(Issue("ERROR", path, f"L3 类型无效：{l3_type}"))

    owner_key = "主要语义所有者" if l3_type == "DOMAIN" else "协调所有者"
    owner_label = (
        "Primary Semantic Owner" if l3_type == "DOMAIN" else "Coordination Owner"
    )
    if l3_type in {"DOMAIN", "ORCHESTRATION"} and not first_value(
        metadata, owner_key, owner_label
    ):
        issues.append(Issue("ERROR", path, f"L3 文档头缺少{owner_key}"))

    if not direct_dependencies:
        issues.append(Issue("ERROR", path, "L3 文档头缺少直接依赖"))
    else:
        references = list(DOCUMENT_REFERENCE_RE.finditer(direct_dependencies))
        declares_none = re.match(r"^\s*(?:无|None)\b", direct_dependencies) is not None
        if not references and not declares_none:
            issues.append(
                Issue(
                    "ERROR",
                    path,
                    "L3 直接依赖必须列出 HALPHA 文档引用或明确为无",
                )
            )

    if not vertical_constraints:
        issues.append(Issue("ERROR", path, "L3 文档头缺少适用纵向约束"))

    return issues


def validate_markdown(repo: Path, path: Path, text: str) -> list[Issue]:
    issues: list[Issue] = []
    rel = relative_path(repo, path)
    match = DOC_NAME_RE.match(path.name)

    if match and rel.parts and rel.parts[0] == "docs":
        metadata = parse_metadata(text)
        doc_id = first_value(metadata, "文档编号", "Document ID")
        level = first_value(metadata, "层级", "Level")
        language = first_value(metadata, "语言版本", "Language Edition")

        expected_id, expected_language = match.groups()

        required = {
            "文档编号/Document ID": doc_id,
            "层级/Level": level,
            "语言版本/Language Edition": language,
        }
        for label, value in required.items():
            if not value:
                issues.append(Issue("ERROR", path, f"缺少核心元数据：{label}"))

        if doc_id and doc_id != expected_id:
            issues.append(
                Issue("ERROR", path, f"文件名文档编号 {expected_id} 与元数据 {doc_id} 不一致")
            )
        if language and language != expected_language:
            issues.append(
                Issue(
                    "ERROR",
                    path,
                    f"文件名语言 {expected_language} 与元数据 {language} 不一致",
                )
            )
        if (
            len(rel.parts) > 1
            and re.fullmatch(r"L[0-3]", rel.parts[1])
            and level
            and not level.startswith(rel.parts[1])
        ):
            issues.append(
                Issue("ERROR", path, f"目录 {rel.parts[1]} 与元数据层级 {level} 不一致")
            )

        if level and not level.startswith("L0"):
            upstream = first_value(
                metadata,
                "上位文档",
                "上位文档或条款",
                "Upstream Documents",
                "Parent Documents",
            )
            governs = first_value(metadata, "本文档负责", "This Document Governs")
            not_governs = first_value(
                metadata, "本文档不负责", "This Document Does Not Govern"
            )
            if not upstream:
                issues.append(Issue("ERROR", path, "缺少上位文档或条款元数据"))
            if not governs:
                issues.append(Issue("ERROR", path, "缺少本文档负责范围元数据"))
            if not not_governs:
                issues.append(Issue("ERROR", path, "缺少本文档不负责范围元数据"))

        if level and level.startswith("L3"):
            issues.extend(validate_l3_header(path, metadata))

        if level and any(level.startswith(item) for item in ("L0", "L1", "L2", "L3")):
            identifiers = sorted(set(CONSTRUCTION_IDENTIFIER_RE.findall(text)))
            if identifiers:
                issues.append(
                    Issue(
                        "ERROR",
                        path,
                        "L0–L3 不得包含当前阶段或建设包代号："
                        + "、".join(identifiers),
                    )
                )
            phase_language = STABLE_LAYER_CONSTRUCTION_PHASE_RE.search(text)
            if phase_language:
                issues.append(
                    Issue(
                        "ERROR",
                        path,
                        "L0–L3 不得承载建设阶段叙事；当前实施标识、范围、顺序和进度只属于 L4："
                        + phase_language.group(0),
                    )
                )

        if level and any(level.startswith(item) for item in ("L0", "L1", "L2")):
            artifacts = sorted(
                set(STABLE_LAYER_BUILD_ARTIFACT_RE.findall(text)),
                key=str.casefold,
            )
            if artifacts:
                issues.append(
                    Issue(
                        "ERROR",
                        path,
                        "L0–L2 不得拥有具体构建制品名或摘要字段："
                        + "、".join(artifacts),
                    )
                )

        if level and any(level.startswith(item) for item in ("L0", "L1")):
            objects = sorted(set(HIGH_LEVEL_TECHNICAL_OBJECT_RE.findall(text)))
            if objects:
                issues.append(
                    Issue(
                        "ERROR",
                        path,
                        "L0–L1 不得拥有 L2/L3 技术对象名：" + "、".join(objects),
                    )
                )

    if any(MALFORMED_ADDED_HEADING_RE.match(line) for line in text.splitlines()):
        issues.append(Issue("ERROR", path, "Markdown 标题残留 diff 加号"))

    anchors = [
        anchor
        for line in text.splitlines()
        if re.match(r"^#{1,6}\s", line)
        for anchor in SEMANTIC_ANCHOR_RE.findall(line)
    ]
    for anchor, count in Counter(anchors).items():
        if count > 1:
            issues.append(Issue("ERROR", path, f"显式语义锚点重复 {count} 次：{anchor}"))

    target_cache: dict[Path, tuple[str, int, set[str]]] = {}
    for raw_target in MARKDOWN_LINK_RE.findall(text):
        local_target = local_link_target(repo, path, raw_target)
        if local_target is None:
            continue
        linked, fragment, display_path = local_target
        if not linked.exists():
            issues.append(Issue("ERROR", path, f"相对链接目标不存在：{display_path}"))
            continue
        if linked.is_dir() or fragment is None or not fragment:
            continue

        if linked not in target_cache:
            if linked == path.resolve():
                linked_text = text
            else:
                try:
                    linked_text = linked.read_bytes().decode("utf-8-sig")
                except UnicodeDecodeError as exc:
                    issues.append(
                        Issue(
                            "WARNING",
                            path,
                            f"无法检查链接 fragment，目标不是有效 UTF-8：{display_path}（{exc}）",
                        )
                    )
                    continue
            target_cache[linked] = (
                linked_text,
                len(linked_text.splitlines()),
                markdown_fragment_ids(linked_text)
                if linked.suffix.lower() == ".md"
                else set(),
            )

        _, line_count, fragments = target_cache[linked]
        line_fragment = GITHUB_LINE_FRAGMENT_RE.fullmatch(fragment)
        if line_fragment:
            start_line = int(line_fragment.group(1))
            end_line = int(line_fragment.group(2) or line_fragment.group(1))
            if end_line < start_line:
                issues.append(
                    Issue(
                        "ERROR",
                        path,
                        f"GitHub 行号 fragment 范围倒置：{display_path}#{fragment}",
                    )
                )
            elif end_line > line_count:
                issues.append(
                    Issue(
                        "ERROR",
                        path,
                        f"GitHub 行号 fragment 超出目标范围（共 {line_count} 行）："
                        f"{display_path}#{fragment}",
                    )
                )
            continue
        if re.match(r"^L\d", fragment):
            issues.append(
                Issue(
                    "ERROR",
                    path,
                    f"GitHub 行号 fragment 格式无效：{display_path}#{fragment}",
                )
            )
            continue
        if linked.suffix.lower() == ".md" and fragment not in fragments:
            issues.append(
                Issue(
                    "ERROR",
                    path,
                    f"Markdown fragment 不存在：{display_path}#{fragment}",
                )
            )

    return issues


def validate_yaml(path: Path, text: str) -> tuple[object | None, list[Issue]]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, [Issue("ERROR", path, f"YAML 无法解析：{exc}")]

    issues: list[Issue] = []
    if not isinstance(data, dict):
        issues.append(Issue("WARNING", path, "YAML 顶层不是映射"))
        return data, issues

    if data.get("document_id") == "HALPHA-PLAN-001":
        required_plan_keys = {
            "schema_version",
            "document_id",
            "level",
            "as_of",
            "language",
        }
        for key in required_plan_keys:
            if key not in data:
                issues.append(Issue("ERROR", path, f"当前建设计划缺少键：{key}"))
        if data.get("schema_version") != 3:
            issues.append(Issue("ERROR", path, "当前建设计划 schema_version 必须为 3"))
        if data.get("level") != "L4":
            issues.append(Issue("ERROR", path, "HALPHA-PLAN-001 的 level 必须为 L4"))
    if data.get("registry_kind") == "non_normative_machine_index":
        responsibilities = data.get("responsibilities")
        if not isinstance(responsibilities, list):
            issues.append(Issue("ERROR", path, "L2 责任登记缺少 responsibilities 列表"))
        else:
            ids = [item.get("id") for item in responsibilities if isinstance(item, dict)]
            duplicates = [item for item, count in Counter(ids).items() if item and count > 1]
            for item in duplicates:
                issues.append(Issue("ERROR", path, f"L2 责任编号重复：{item}"))
        if data.get("schema_version") != 3:
            issues.append(Issue("ERROR", path, "当前 L2 责任登记 schema_version 必须为 3"))
        for key in ("language",):
            if key not in data:
                issues.append(Issue("ERROR", path, f"当前 L2 责任登记缺少键：{key}"))
        if isinstance(responsibilities, list):
            required_item_keys = {
                "id",
                "shape",
                "responsibility_source",
                "l2_document",
                "scope_source",
                "owned_stable_semantics",
            }
            for index, item in enumerate(responsibilities):
                if not isinstance(item, dict):
                    issues.append(Issue("ERROR", path, f"L2 责任第 {index + 1} 项不是映射"))
                    continue
                for key in sorted(required_item_keys.difference(item)):
                    issues.append(
                        Issue("ERROR", path, f"L2 责任 {item.get('id', index + 1)} 缺少键：{key}")
                    )
                if item.get("shape") not in {"horizontal", "vertical"}:
                    issues.append(
                        Issue("ERROR", path, f"L2 责任 {item.get('id', index + 1)} 的 shape 无效")
                    )
    return data, issues


def collect_targets(repo: Path, raw_paths: list[str], use_changed: bool) -> set[Path]:
    targets = changed_files(repo) if use_changed else set()
    for raw in raw_paths:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = repo / candidate
        candidate = candidate.resolve()
        if candidate.is_dir():
            targets.update(path.resolve() for path in candidate.rglob("*") if path.is_file())
        else:
            targets.add(candidate)
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="要检查的仓库相对路径；目录会递归展开")
    parser.add_argument("--changed", action="store_true", help="检查 Git 工作区全部改动")
    args = parser.parse_args()

    try:
        repo = find_repo_root(Path.cwd())
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    if not args.paths and not args.changed:
        args.changed = True
    try:
        targets = collect_targets(repo, args.paths, args.changed)
    except subprocess.CalledProcessError as exc:
        print(f"[ERROR] 无法读取 Git 改动：{exc.stderr.decode('utf-8', errors='replace')}")
        return 2

    issues: list[Issue] = []
    checked = 0
    issues.extend(validate_bilingual_pairs(repo, targets))
    for path in sorted(targets, key=lambda item: str(item).lower()):
        if not path.exists():
            issues.append(Issue("ERROR", path, "路径不存在"))
            continue
        if path.is_dir():
            continue
        if path.suffix.lower() not in {".md", ".yaml", ".yml"}:
            continue

        checked += 1
        text, decode_issues = decode_utf8(path)
        issues.extend(decode_issues)
        if text is None:
            continue

        if path.suffix.lower() == ".md":
            issues.extend(validate_markdown(repo, path, text))
        else:
            _, yaml_issues = validate_yaml(path, text)
            issues.extend(yaml_issues)

    severity_order = {"ERROR": 0, "WARNING": 1}
    for issue in sorted(
        issues,
        key=lambda item: (
            severity_order.get(item.severity, 9),
            str(relative_path(repo, item.path)).lower(),
            item.message,
        ),
    ):
        print(f"[{issue.severity}] {relative_path(repo, issue.path)}: {issue.message}")

    errors = sum(issue.severity == "ERROR" for issue in issues)
    warnings = sum(issue.severity == "WARNING" for issue in issues)
    print(f"Checked {checked} file(s): {errors} error(s), {warnings} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
