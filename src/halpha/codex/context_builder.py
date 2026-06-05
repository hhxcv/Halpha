from __future__ import annotations

from typing import Any

from halpha.pipeline import PipelineError, RunContext


STAGE_NAME = "build_codex_context"
RESEARCH_CONTEXT_ARTIFACT = "analysis/research_context.md"
CODEX_CONTEXT_ARTIFACT = "codex_context/context.md"
CODEX_PROMPT_ARTIFACT = "codex_context/prompt.md"


def build_codex_context(config: dict[str, Any], run: RunContext) -> list[str]:
    research_context = _read_research_context(run)
    artifact_index = _artifact_index(run)
    context = render_context(artifact_index=artifact_index, research_context=research_context)
    prompt = render_prompt(context)

    context_path = run.codex_context_dir / "context.md"
    prompt_path = run.codex_context_dir / "prompt.md"
    context_path.write_text(context, encoding="utf-8")
    prompt_path.write_text(prompt, encoding="utf-8")

    run.manifest["artifacts"]["codex_context"] = CODEX_CONTEXT_ARTIFACT
    run.manifest["artifacts"]["codex_prompt"] = CODEX_PROMPT_ARTIFACT
    return [CODEX_CONTEXT_ARTIFACT, CODEX_PROMPT_ARTIFACT]


def render_context(*, artifact_index: dict[str, Any], research_context: str) -> str:
    return "\n".join(
        [
            "# codex_context",
            "",
            "## artifact_index",
            "",
            "```yaml",
            _yaml_block(artifact_index).rstrip(),
            "```",
            "",
            "## research_context",
            "",
            f'<embed path="{RESEARCH_CONTEXT_ARTIFACT}">',
            research_context.rstrip(),
            "</embed>",
            "",
        ]
    )


def render_prompt(context: str) -> str:
    return "\n".join(
        [
            "You are the report-generation step for Halpha.",
            "",
            "Generate a Simplified Chinese Markdown market intelligence report from the local context below.",
            "",
            "Rules:",
            "",
            "1. Use only the facts, source text, and derived material in the provided context.",
            "2. Do not invent prices, events, links, sources, or certainty.",
            "3. Preserve source awareness. When a fact is used, keep its source name nearby.",
            "4. If a source URL is missing, say that the source URL was not provided.",
            "5. Distinguish facts, assumptions, uncertainties, and judgment.",
            "6. Use cautious language for market interpretation.",
            "7. Include a risk notice.",
            "8. The report is personal research material and is not financial advice.",
            "9. Do not modify repository files or execute actions; write the report content only.",
            "",
            "Required sections:",
            "",
            "- Title",
            "- Core Summary",
            "- Market Overview",
            "- Text Events",
            "- Synthesis",
            "- Watch Points",
            "- Risk Notice",
            "",
            "<context>",
            context.rstrip(),
            "</context>",
            "",
        ]
    )


def _read_research_context(run: RunContext) -> str:
    path = run.analysis_dir / "research_context.md"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PipelineError(
            f"{RESEARCH_CONTEXT_ARTIFACT} was not found; build_research_context must run first.",
            stage=STAGE_NAME,
            exit_code=3,
        ) from exc


def _artifact_index(run: RunContext) -> dict[str, Any]:
    artifacts = run.manifest.get("artifacts", {})
    return {
        "raw_market": artifacts.get("raw_market"),
        "raw_text_events": artifacts.get("raw_text_events"),
        "market_material": artifacts.get("market_material"),
        "text_material": artifacts.get("text_material"),
        "research_context": artifacts.get("research_context"),
        "codex_context": CODEX_CONTEXT_ARTIFACT,
        "codex_prompt": CODEX_PROMPT_ARTIFACT,
    }


def _yaml_block(data: dict[str, Any]) -> str:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise PipelineError(
            "PyYAML is required to write YAML Codex context records.",
            stage=STAGE_NAME,
            exit_code=1,
        ) from exc

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
