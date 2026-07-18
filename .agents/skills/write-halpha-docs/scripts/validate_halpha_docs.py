#!/usr/bin/env python3
"""Run mechanical checks for Halpha design documentation.

This script intentionally does not encode product semantics. It checks file structure,
metadata, YAML, links, target-document candidate placement, forbidden version-carrier
directories, and accepted bundle digests so that human
or agent review can focus on ownership, level, consumers, and failure behavior.
"""

from __future__ import annotations

import argparse
import hashlib
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


VALID_STATUSES = {"PROPOSED", "ACCEPTED", "SUPERSEDED", "WITHDRAWN"}
DOC_NAME_RE = re.compile(
    r"^(HALPHA-[A-Z]+-\d{3})-[a-z0-9]+(?:-[a-z0-9]+)*\.(zh-CN|en-US)\.md$"
)
METADATA_RE = re.compile(r"^\*\*([^*]+?)[：:]\*\*\s*(.*?)\s*$")
SEMANTIC_ANCHOR_RE = re.compile(r"【([A-Z][A-Z0-9-]+)】")
NUMBERED_SECTION_RE = re.compile(r"^#\s+\d+(?:[.\s])")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}(?:[ \t]+|$)(.*)$")
MARKDOWN_FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
HTML_FRAGMENT_RE = re.compile(
    r'''(?<![-\w])(?:id|name)\s*=\s*(?:"([^"]+)"|'([^']+)'|([^\s"'=<>`]+))''',
    re.IGNORECASE,
)
GITHUB_LINE_FRAGMENT_RE = re.compile(r"^L([1-9]\d*)(?:-L([1-9]\d*))?$")
DOCUMENT_REFERENCE_RE = re.compile(r"\bHALPHA-[A-Z]+-\d{3}\b")
DOCUMENT_VERSION_AFTER_REFERENCE_RE = re.compile(
    r"\s+v\d+\.\d+\.\d+(?:#[A-Z][A-Z0-9-]+)?\b"
)


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

    # Deliberately do not resolve references against accepted_design_set or decide
    # whether a dependency is semantically direct; those checks have separate owners.
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
                    "L3 直接依赖必须列出带版本的 HALPHA 文档引用或明确为无",
                )
            )
        for reference in references:
            suffix = direct_dependencies[reference.end() :]
            if not DOCUMENT_VERSION_AFTER_REFERENCE_RE.match(suffix):
                issues.append(
                    Issue(
                        "ERROR",
                        path,
                        f"L3 直接依赖引用缺少 ` vX.Y.Z` 版本：{reference.group(0)}",
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
        version = first_value(metadata, "版本", "Version")
        status = first_value(
            metadata, "文档状态", "Document Status", "决策状态", "Decision Status"
        )
        level = first_value(metadata, "层级", "Level")
        language = first_value(metadata, "语言版本", "Language Edition")

        expected_id, expected_language = match.groups()
        if expected_id == "HALPHA-CON-001" and not level:
            # The accepted constitution predates the explicit level field; its stable
            # identity and L0 directory make the level unambiguous.
            level = "L0"

        required = {
            "文档编号/Document ID": doc_id,
            "版本/Version": version,
            "文档状态/Document Status": status,
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
        if status and status not in VALID_STATUSES:
            issues.append(Issue("ERROR", path, f"未知文档状态：{status}"))

        in_target_document_path = (
            len(rel.parts) > 1
            and rel.parts[0] == "docs"
            and re.fullmatch(r"L[0-3]", rel.parts[1]) is not None
        )
        if in_target_document_path and status not in {"ACCEPTED", "PROPOSED"}:
            issues.append(Issue("ERROR", path, "L0–L3 目标路径中的文档必须标为 ACCEPTED 或 PROPOSED"))

        if in_target_document_path:
            deprecated = {
                "当前效力",
                "Current Effect",
                "日期",
                "Date",
                "设计基线",
                "设计接受记录",
            }
            for key in sorted(deprecated.intersection(metadata)):
                issues.append(Issue("ERROR", path, f"当前规范头包含已移除元数据：{key}"))

            if status == "PROPOSED":
                supersedes = first_value(metadata, "替代版本", "Supersedes")
                if not supersedes:
                    issues.append(Issue("ERROR", path, "PROPOSED 目标文档头缺少候选基线或替代版本"))
                premature_acceptance = {
                    "批准人",
                    "Approver",
                    "接受时间",
                    "Accepted At",
                    "生效时间",
                    "Effective Time",
                }
                for key in sorted(premature_acceptance.intersection(metadata)):
                    issues.append(Issue("ERROR", path, f"PROPOSED 目标文档不得提前登记接受信息：{key}"))

            if level and (level.startswith("L0") or level.startswith("L1")):
                co_normative_required = {
                    "共同规范集标识/Joint Normative Set ID": first_value(
                        metadata, "共同规范集标识", "Joint Normative Set ID"
                    ),
                    "配对文本/Paired Text": first_value(metadata, "配对文本", "Paired Text"),
                    "共同规范集登记/Joint Set Registry": first_value(
                        metadata, "共同规范集登记", "Joint Set Registry"
                    ),
                }
                if status == "ACCEPTED":
                    co_normative_required["生效时间/Effective Time"] = first_value(
                        metadata, "生效时间", "Effective Time"
                    )
                for label, value in co_normative_required.items():
                    if not value:
                        issues.append(Issue("ERROR", path, f"共同规范文本头缺少：{label}"))

            if (
                status == "ACCEPTED"
                and level
                and (level.startswith("L2") or level.startswith("L3"))
            ):
                acceptance_required = {
                    "批准人/Approver": first_value(metadata, "批准人", "Approver"),
                    "接受时间/Accepted At": first_value(metadata, "接受时间", "Accepted At"),
                    "替代版本/Supersedes": first_value(metadata, "替代版本", "Supersedes"),
                }
                for label, value in acceptance_required.items():
                    if not value:
                        issues.append(Issue("ERROR", path, f"单语言 ACCEPTED 文档头缺少：{label}"))

                accepted_at = acceptance_required["接受时间/Accepted At"]
                effective_at = first_value(metadata, "生效时间", "Effective Time")
                if accepted_at and effective_at and accepted_at == effective_at:
                    issues.append(Issue("ERROR", path, "接受后立即生效时不得重复记录生效时间"))

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
        plan_status = data.get("status")
        required_plan_keys = {
            "schema_version",
            "level",
            "status",
            "as_of",
            "language",
            "basis",
        }
        if plan_status == "ACCEPTED":
            required_plan_keys.update({"accepted_by", "accepted_at"})
        for key in required_plan_keys:
            if key not in data:
                issues.append(Issue("ERROR", path, f"当前建设计划缺少键：{key}"))
        if data.get("schema_version") != 3:
            issues.append(Issue("ERROR", path, "当前建设计划 schema_version 必须为 3"))
        if data.get("level") != "L4":
            issues.append(Issue("ERROR", path, "HALPHA-PLAN-001 的 level 必须为 L4"))
        if plan_status not in {"ACCEPTED", "PROPOSED"}:
            issues.append(Issue("ERROR", path, "HALPHA-PLAN-001 的 status 必须为 ACCEPTED 或 PROPOSED"))
        if plan_status == "PROPOSED" and not data.get("supersedes"):
            issues.append(Issue("ERROR", path, "PROPOSED HALPHA-PLAN-001 必须声明替代版本"))
        for key in ("current_path", "approved_by", "approved_at"):
            if key in data:
                issues.append(Issue("ERROR", path, f"当前建设计划包含已移除键：{key}"))
        if plan_status == "ACCEPTED" and data.get("effective_at") == data.get("accepted_at"):
            issues.append(Issue("ERROR", path, "当前建设计划立即生效时不得重复 effective_at"))

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
        for key in ("language", "current_depth_authority", "upstream_versions"):
            if key not in data:
                issues.append(Issue("ERROR", path, f"当前 L2 责任登记缺少键：{key}"))
        removed_registry_keys = {
            "status",
            "current_path",
            "approved_by",
            "approved_at",
            "effective_at",
            "normative_text_copied",
            "current_depth_recorded_here",
            "note",
            "direct_upstream_version_sets",
        }
        for key in sorted(removed_registry_keys.intersection(data)):
            issues.append(Issue("ERROR", path, f"当前 L2 责任登记包含已移除键：{key}"))
        for key in data:
            if key.startswith("current_depth") and key != "current_depth_authority":
                issues.append(Issue("ERROR", path, f"L2 责任登记不得记录当前深度：{key}"))

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
                for key in ("direct_upstream_version_set", "l2_status"):
                    if key in item:
                        issues.append(
                            Issue("ERROR", path, f"L2 责任 {item.get('id', index + 1)} 包含已移除键：{key}")
                        )
                for key in item:
                    if key.startswith("current_depth"):
                        issues.append(
                            Issue("ERROR", path, f"L2 责任 {item.get('id', index + 1)} 不得记录当前深度")
                        )

    return data, issues


def normalized_text(path: Path) -> str:
    return (
        path.read_bytes()
        .decode("utf-8-sig")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def normative_body(path: Path) -> str:
    lines = normalized_text(path).splitlines(keepends=True)
    for index, line in enumerate(lines):
        if NUMBERED_SECTION_RE.match(line):
            return "".join(lines[index:])
    raise ValueError("找不到首个编号章节标题")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_bundle(repo: Path, path: Path, data: object | None = None) -> list[Issue]:
    issues: list[Issue] = []
    if data is None:
        text, decode_issues = decode_utf8(path)
        issues.extend(decode_issues)
        if text is None:
            return issues
        data, yaml_issues = validate_yaml(path, text)
        issues.extend(yaml_issues)
    if not isinstance(data, dict):
        return issues

    schema_version = data.get("schema_version", 2)
    bundle_status = data.get("status")

    if bundle_status == "ACCEPTED" and data.get("alignment") != "ALIGNED":
        issues.append(Issue("ERROR", path, "ACCEPTED 共同规范 bundle 必须为 ALIGNED"))
    elif bundle_status == "PROPOSED" and data.get("alignment") not in {"PENDING", "NOT_ALIGNED"}:
        issues.append(Issue("ERROR", path, "PROPOSED 共同规范 bundle 必须为 PENDING 或 NOT_ALIGNED"))
    elif bundle_status not in {"ACCEPTED", "PROPOSED"}:
        issues.append(Issue("ERROR", path, "当前共同规范 bundle 必须为 ACCEPTED 或 PROPOSED"))

    if schema_version == 3:
        required = {
            "schema_version",
            "document_id",
            "version",
            "bundle_id",
            "status",
            "alignment",
            "supersedes",
            "normative_languages",
            "language_authority",
            "files",
            "joint_set",
        }
        if bundle_status == "ACCEPTED":
            required.update({"accepted_by", "accepted_at"})
        for key in sorted(required.difference(data)):
            issues.append(Issue("ERROR", path, f"schema 3 bundle 缺少键：{key}"))
        if bundle_status == "PROPOSED":
            for key in ("accepted_by", "accepted_at", "effective_at"):
                if key in data:
                    issues.append(Issue("ERROR", path, f"PROPOSED bundle 不得提前登记：{key}"))
        if data.get("language_authority") != "co_normative_equal":
            issues.append(Issue("ERROR", path, "schema 3 bundle 的语言权威必须为 co_normative_equal"))
        removed = {
            "title",
            "parents",
            "language_priority",
            "final_interpretive_language",
            "digest_rules",
            "owner_and_approver",
            "approval_time",
            "effective_time",
            "standalone_use",
        }
        for key in sorted(removed.intersection(data)):
            issues.append(Issue("ERROR", path, f"schema 3 bundle 包含已移除键：{key}"))
    else:
        issues.append(Issue("ERROR", path, "当前共同规范 bundle 必须使用 schema_version 3"))

    files = data.get("files")
    if not isinstance(files, dict):
        issues.append(Issue("ERROR", path, "bundle 缺少 files 映射"))
        return issues

    languages = data.get("normative_languages")
    if not isinstance(languages, list) or not languages:
        issues.append(Issue("ERROR", path, "bundle 缺少规范语言顺序"))
        languages = []
    elif schema_version == 3 and list(files) != languages:
        issues.append(Issue("ERROR", path, "schema 3 bundle 的 files 顺序必须与规范语言顺序一致"))

    actual_hashes: dict[str, str] = {}
    for language, metadata in files.items():
        if not isinstance(metadata, dict) or not metadata.get("path"):
            issues.append(Issue("ERROR", path, f"bundle 的 {language} 文件登记无效"))
            continue
        document_path = (repo / str(metadata["path"])).resolve()
        if not document_path.exists():
            issues.append(Issue("ERROR", path, f"bundle 正文不存在：{metadata['path']}"))
            continue
        try:
            actual = sha256_text(normative_body(document_path))
        except (UnicodeDecodeError, ValueError) as exc:
            issues.append(Issue("ERROR", document_path, f"无法计算规范正文哈希：{exc}"))
            continue
        actual_hashes[str(language)] = actual
        expected = metadata.get("body_sha256")
        if actual != expected:
            issues.append(
                Issue(
                    "ERROR",
                    document_path,
                    f"正文哈希与 {path.name} 不一致：登记 {expected}，实际 {actual}",
                )
            )

        if schema_version == 3:
            unexpected_file_keys = set(metadata).difference({"path", "body_sha256"})
            for key in sorted(unexpected_file_keys):
                issues.append(Issue("ERROR", path, f"schema 3 bundle 的 {language} 文件包含多余键：{key}"))

            document_text, document_issues = decode_utf8(document_path)
            issues.extend(document_issues)
            if document_text is not None:
                header = parse_metadata(document_text)
                expected_effective_at = str(data.get("effective_at", data.get("accepted_at", "")))
                bindings = {
                    "文档编号/Document ID": (
                        first_value(header, "文档编号", "Document ID"),
                        str(data.get("document_id", "")),
                    ),
                    "版本/Version": (
                        first_value(header, "版本", "Version"),
                        str(data.get("version", "")),
                    ),
                    "状态/Status": (
                        first_value(
                            header,
                            "文档状态",
                            "Document Status",
                            "决策状态",
                            "Decision Status",
                        ),
                        str(data.get("status", "")),
                    ),
                    "语言/Language": (
                        first_value(header, "语言版本", "Language Edition"),
                        str(language),
                    ),
                    "共同规范集标识/Joint Set ID": (
                        first_value(header, "共同规范集标识", "Joint Normative Set ID"),
                        str(data.get("bundle_id", "")),
                    ),
                    "生效时间/Effective Time": (
                        first_value(header, "生效时间", "Effective Time"),
                        expected_effective_at,
                    ),
                }
                for label, (actual_binding, expected_binding) in bindings.items():
                    if actual_binding != expected_binding:
                        issues.append(
                            Issue(
                                "ERROR",
                                document_path,
                                f"文本头与 bundle 的 {label} 不一致：{actual_binding} != {expected_binding}",
                            )
                        )

                registry = first_value(header, "共同规范集登记", "Joint Set Registry")
                if registry != path.name:
                    issues.append(Issue("ERROR", document_path, "文本头引用的 bundle 文件名不一致"))

                other_paths = [
                    Path(str(other_metadata.get("path"))).name
                    for other_language, other_metadata in files.items()
                    if other_language != language and isinstance(other_metadata, dict)
                ]
                paired = first_value(header, "配对文本", "Paired Text") or ""
                if len(other_paths) != 1 or not paired.startswith(other_paths[0]):
                    issues.append(Issue("ERROR", document_path, "文本头的配对文本与 bundle 不一致"))

    joint_set = data.get("joint_set")
    if not isinstance(joint_set, dict):
        issues.append(Issue("ERROR", path, "bundle 缺少 joint_set"))
        return issues

    joint_hash = joint_set.get("sha256")
    if not isinstance(joint_hash, str):
        issues.append(Issue("ERROR", path, "joint_set 缺少 sha256"))
        return issues

    if languages and all(str(item) in actual_hashes for item in languages):
        expected_input = (
            f"{data.get('document_id')}\n{data.get('version')}\n"
            + "".join(f"{language}:{actual_hashes[str(language)]}\n" for language in languages)
        )
        if schema_version == 3:
            if "input" in joint_set:
                issues.append(Issue("ERROR", path, "schema 3 bundle 不得保存可重建的 joint_set.input"))
            actual_joint_hash = sha256_text(expected_input)
        else:
            joint_input = joint_set.get("input")
            if not isinstance(joint_input, str):
                issues.append(Issue("ERROR", path, "旧版 joint_set 必须同时登记 input 和 sha256"))
                return issues
            normalized_input = joint_input.replace("\r\n", "\n").replace("\r", "\n")
            if normalized_input != expected_input:
                issues.append(Issue("ERROR", path, "joint_set.input 与当前文档编号、版本或正文哈希不一致"))
            actual_joint_hash = sha256_text(normalized_input)

        if actual_joint_hash != joint_hash:
            issues.append(
                Issue(
                    "ERROR",
                    path,
                    f"联合包哈希不一致：登记 {joint_hash}，实际 {actual_joint_hash}",
                )
            )

    return issues


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
    parser.add_argument(
        "--accepted-integrity",
        action="store_true",
        help="检查 docs/L0–L3 当前 bundle 的正文与联合包哈希",
    )
    args = parser.parse_args()

    try:
        repo = find_repo_root(Path.cwd())
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    if not args.paths and not args.changed and not args.accepted_integrity:
        args.changed = True
    try:
        targets = collect_targets(repo, args.paths, args.changed)
    except subprocess.CalledProcessError as exc:
        print(f"[ERROR] 无法读取 Git 改动：{exc.stderr.decode('utf-8', errors='replace')}")
        return 2

    bundle_paths: set[Path] = set()
    if args.accepted_integrity:
        bundle_paths = {
            path.resolve() for path in repo.glob("docs/L[0-3]/*.bundle.yaml") if path.is_file()
        }
        targets |= bundle_paths

    issues: list[Issue] = []
    checked = 0
    for path in sorted(targets, key=lambda item: str(item).lower()):
        if not path.exists():
            issues.append(Issue("ERROR", path, "路径不存在"))
            continue
        if path.is_dir():
            continue
        rel = relative_path(repo, path)
        if len(rel.parts) > 1 and rel.parts[0] == "docs" and (
            rel.parts[1] == "proposals" or "archive" in rel.parts
        ):
            issues.append(
                Issue(
                    "ERROR",
                    path,
                    "文档版本不得使用 docs/proposals 或任何 archive 目录承载",
                )
            )
        if path.suffix.lower() not in {".md", ".yaml", ".yml"}:
            continue

        checked += 1
        text, decode_issues = decode_utf8(path)
        issues.extend(decode_issues)
        if text is None:
            continue

        yaml_data: object | None = None
        if path.suffix.lower() == ".md":
            issues.extend(validate_markdown(repo, path, text))
        else:
            yaml_data, yaml_issues = validate_yaml(path, text)
            issues.extend(yaml_issues)

        if path in bundle_paths or path.name.endswith(".bundle.yaml"):
            issues.extend(validate_bundle(repo, path, yaml_data))

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
