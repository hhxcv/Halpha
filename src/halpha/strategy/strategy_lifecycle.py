from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from halpha.runtime.pipeline_contracts import RunContext
from halpha.storage import write_json


STAGE_NAME = "build_strategy_lifecycle_state"
STRATEGY_LIFECYCLE_STATE_ARTIFACT = "analysis/strategy_lifecycle_state.json"
SCHEMA_VERSION = 1

QUANT_STRATEGY_RUNS_ARTIFACT = "analysis/quant_strategy_runs.json"
STRATEGY_EVALUATION_SUMMARY_ARTIFACT = "analysis/strategy_evaluation_summary.json"
STRATEGY_EXPERIMENT_ARTIFACT = "analysis/strategy_experiment.json"
STRATEGY_EFFECTIVENESS_GATES_ARTIFACT = "analysis/strategy_effectiveness_gates.json"
OUTCOME_TARGETS_ARTIFACT = "analysis/outcome_targets.json"
OUTCOME_EVALUATIONS_ARTIFACT = "analysis/outcome_evaluations.json"
MARKET_REGIME_ASSESSMENT_ARTIFACT = "analysis/market_regime_assessment.json"
RISK_ASSESSMENT_ARTIFACT = "analysis/risk_assessment.json"
DATA_QUALITY_SUMMARY_ARTIFACT = "analysis/data_quality_summary.json"
POLICY_SOURCE_REF = "config:quant.lifecycle_policy.records"

GATE_TO_LIFECYCLE_STATUS = {
    "effective": "effective",
    "watchlisted": "watchlisted",
    "rejected": "rejected",
    "insufficient_evidence": "insufficient_evidence",
}
POLICY_ACTION_ORDER = {"retire": 0, "reject": 1, "watchlist": 2, "promote": 3}


def build_strategy_lifecycle_state(
    config: dict[str, Any],
    run: RunContext,
    *,
    now: datetime | str | None = None,
) -> list[str]:
    if not _quant_enabled(config):
        _record_skipped_manifest(run, reason="quant.enabled is false.")
        return []

    created_at = _format_utc(now)
    builder = _StrategyLifecycleBuilder(config, run, created_at=created_at)
    artifact = builder.artifact()
    write_json(run.analysis_dir / "strategy_lifecycle_state.json", artifact)
    _record_manifest(run, artifact)
    return [STRATEGY_LIFECYCLE_STATE_ARTIFACT]


class _StrategyLifecycleBuilder:
    def __init__(self, config: dict[str, Any], run: RunContext, *, created_at: str) -> None:
        self.config = config
        self.run = run
        self.created_at = created_at
        self.coverage: list[dict[str, Any]] = []
        self.warnings: list[str] = []
        self.errors: list[dict[str, Any]] = []
        self.source_artifacts: list[str] = []
        self.quant_runs = self._read_artifact(
            "strategy_run",
            QUANT_STRATEGY_RUNS_ARTIFACT,
            run.analysis_dir / "quant_strategy_runs.json",
            "runs",
        )
        self.evaluations = self._read_artifact(
            "evaluation",
            STRATEGY_EVALUATION_SUMMARY_ARTIFACT,
            run.analysis_dir / "strategy_evaluation_summary.json",
            "records",
        )
        self.experiment = self._read_artifact(
            "experiment",
            STRATEGY_EXPERIMENT_ARTIFACT,
            run.analysis_dir / "strategy_experiment.json",
            "candidates",
        )
        self.gates = self._read_artifact(
            "gate",
            STRATEGY_EFFECTIVENESS_GATES_ARTIFACT,
            run.analysis_dir / "strategy_effectiveness_gates.json",
            "records",
        )
        self.targets = self._read_artifact(
            "outcome_target",
            OUTCOME_TARGETS_ARTIFACT,
            run.analysis_dir / "outcome_targets.json",
            "targets",
            required=False,
        )
        self.outcomes = self._read_artifact(
            "outcome",
            OUTCOME_EVALUATIONS_ARTIFACT,
            run.analysis_dir / "outcome_evaluations.json",
            "evaluations",
            required=False,
        )
        self.regime = self._read_artifact(
            "regime",
            MARKET_REGIME_ASSESSMENT_ARTIFACT,
            run.analysis_dir / "market_regime_assessment.json",
            "records",
            required=False,
        )
        self.risk = self._read_artifact(
            "risk",
            RISK_ASSESSMENT_ARTIFACT,
            run.analysis_dir / "risk_assessment.json",
            "records",
            required=False,
        )
        self.data_quality = self._read_artifact(
            "data_quality",
            DATA_QUALITY_SUMMARY_ARTIFACT,
            run.analysis_dir / "data_quality_summary.json",
            "checks",
            required=False,
        )
        self.policy_records = _policy_records(config)
        self._record_policy_coverage()

    def artifact(self) -> dict[str, Any]:
        records = self._records()
        warnings = _unique_sorted(
            [
                *self.warnings,
                *[
                    warning
                    for record in records
                    for warning in _string_list(record.get("warnings"))
                ],
            ]
        )
        errors = [
            *self.errors,
            *[
                error
                for record in records
                for error in _error_list(record.get("errors"))
            ],
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "strategy_lifecycle_state",
            "run_id": self.run.run_id,
            "created_at": self.created_at,
            "status": _artifact_status(records, coverage=self.coverage, warnings=warnings, errors=errors),
            "records": records,
            "coverage": sorted(self.coverage, key=lambda item: (item["source_layer"], item["source_artifact"])),
            "counts": _counts(records, coverage=self.coverage, warnings=warnings, errors=errors),
            "warnings": warnings,
            "errors": errors,
            "source_artifacts": _unique_sorted(self.source_artifacts),
        }

    def _records(self) -> list[dict[str, Any]]:
        keys = self._strategy_keys()
        records = [
            self._record_for_key(key)
            for key in sorted(keys, key=_strategy_key_sort_key)
        ]
        return records

    def _strategy_keys(self) -> set[tuple[str, str | None, str | None]]:
        keys: set[tuple[str, str | None, str | None]] = set()
        for record in _dict_list(self.evaluations.get("records")):
            keys.add(_record_key(record))
        for record in _dict_list(self.quant_runs.get("runs")):
            keys.add(_record_key(record))
        for gate in _dict_list(self.gates.get("records")):
            key = _record_key(gate)
            has_scoped_key = any(
                item[0] == key[0] and (item[1] is not None or item[2] is not None)
                for item in keys
            )
            if key[1] is None and key[2] is None and has_scoped_key:
                continue
            keys.add(key)
        return {key for key in keys if key[0] != "unknown"}

    def _record_for_key(self, key: tuple[str, str | None, str | None]) -> dict[str, Any]:
        strategy_name, symbol, timeframe = key
        gate = self._matching_gate(key)
        evaluation = self._matching_evaluation(key)
        quant_run = self._matching_quant_run(key)
        experiment_candidate = self._matching_experiment_candidate(strategy_name)
        params = _params_from(gate, evaluation, quant_run, experiment_candidate)
        parameter_digest = _parameter_digest(params)
        strategy_contract_version = _strategy_contract_version(evaluation, quant_run)
        policy_refs = self._matching_policy_refs(
            strategy_name,
            symbol=symbol,
            timeframe=timeframe,
            strategy_contract_version=strategy_contract_version,
            parameter_digest=parameter_digest,
        )
        outcome_feedback = self._outcome_feedback(key)
        base_status = _base_lifecycle_status(gate, evaluation, quant_run)
        degradation = _degradation_state(outcome_feedback, gate, evaluation)
        lifecycle_status = _apply_degradation(base_status, degradation)
        lifecycle_status = _apply_policy_status(lifecycle_status, policy_refs)
        source_artifacts = _unique_sorted(
            [
                *_record_source_artifacts(gate),
                *_record_source_artifacts(evaluation),
                *_record_source_artifacts(quant_run),
                *_record_source_artifacts(experiment_candidate),
                *outcome_feedback["source_artifacts"],
                *([POLICY_SOURCE_REF] if policy_refs else []),
            ]
        )
        warnings = _unique_sorted(
            [
                *_record_warnings(gate),
                *_record_warnings(evaluation),
                *_record_warnings(quant_run),
                *_record_warnings(experiment_candidate),
                *outcome_feedback["warnings"],
            ]
        )
        errors = [
            *_record_errors(gate),
            *_record_errors(evaluation),
            *_record_errors(quant_run),
            *_record_errors(experiment_candidate),
            *outcome_feedback["errors"],
        ]
        source_record_refs = _unique_sorted(
            [
                *_record_refs(gate, ("gate_id", "gate_record_id")),
                *_record_refs(evaluation, ("evaluation_id", "record_id")),
                *_record_refs(quant_run, ("strategy_run_id",)),
                *_record_refs(experiment_candidate, ("strategy_name",)),
                *outcome_feedback["source_record_refs"],
            ]
        )
        return {
            "lifecycle_record_id": _lifecycle_record_id(strategy_name, symbol, timeframe),
            "strategy_name": strategy_name,
            "scope": {"symbol": symbol, "timeframe": timeframe},
            "strategy_contract_version": strategy_contract_version,
            "parameter_version": parameter_digest,
            "parameter_digest": parameter_digest,
            "lifecycle_status": lifecycle_status,
            "health_state": _health_state(lifecycle_status, gate, degradation, policy_refs),
            "degradation": degradation,
            "regime_weakness": _regime_weakness(gate, evaluation),
            "promotion": _promotion_state(policy_refs, lifecycle_status),
            "retirement": _retirement_state(policy_refs),
            "evidence": _evidence(gate, evaluation, quant_run, outcome_feedback, policy_refs),
            "uncertainty": _uncertainty(lifecycle_status, outcome_feedback),
            "warnings": warnings,
            "errors": errors,
            "source_artifacts": source_artifacts,
            "source_record_refs": source_record_refs,
        }

    def _matching_gate(self, key: tuple[str, str | None, str | None]) -> dict[str, Any] | None:
        return _first_matching(_dict_list(self.gates.get("records")), key)

    def _matching_evaluation(self, key: tuple[str, str | None, str | None]) -> dict[str, Any] | None:
        return _first_matching(_dict_list(self.evaluations.get("records")), key)

    def _matching_quant_run(self, key: tuple[str, str | None, str | None]) -> dict[str, Any] | None:
        return _first_matching(_dict_list(self.quant_runs.get("runs")), key)

    def _matching_experiment_candidate(self, strategy_name: str) -> dict[str, Any] | None:
        for candidate in _dict_list(self.experiment.get("candidates")):
            if str(candidate.get("strategy_name") or "") == strategy_name:
                return candidate
        return None

    def _outcome_feedback(self, key: tuple[str, str | None, str | None]) -> dict[str, Any]:
        target_by_id = {
            str(target.get("target_id")): target
            for target in _dict_list(self.targets.get("targets"))
            if target.get("target_kind") == "strategy_gate" and target.get("target_id")
        }
        matches = []
        for evaluation in _dict_list(self.outcomes.get("evaluations")):
            target = target_by_id.get(str(evaluation.get("target_id")))
            if target is None:
                continue
            if _target_matches_key(target, key):
                matches.append((target, evaluation))
        source_artifacts = _unique_sorted(
            [
                OUTCOME_TARGETS_ARTIFACT,
                OUTCOME_EVALUATIONS_ARTIFACT,
                *[
                    artifact
                    for target, evaluation in matches
                    for artifact in [
                        *_string_list(target.get("source_artifacts")),
                        *_string_list(evaluation.get("source_artifacts")),
                    ]
                ],
            ]
            if matches
            else []
        )
        source_record_refs = _unique_sorted(
            [
                ref
                for target, evaluation in matches
                for ref in [
                    _text_or_none(target.get("target_id")),
                    _text_or_none(target.get("source_record_id")),
                    _text_or_none(evaluation.get("outcome_id")),
                ]
                if ref
            ]
        )
        warnings = _unique_sorted(
            [
                warning
                for _, evaluation in matches
                for warning in _string_list(evaluation.get("warnings"))
            ]
        )
        errors = [
            error
            for _, evaluation in matches
            for error in _error_list(evaluation.get("errors"))
        ]
        states = [
            str(evaluation.get("outcome_state") or "unknown")
            for _, evaluation in matches
        ]
        return {
            "records": len(matches),
            "states": states,
            "source_artifacts": source_artifacts,
            "source_record_refs": source_record_refs,
            "warnings": warnings,
            "errors": errors,
        }

    def _matching_policy_refs(
        self,
        strategy_name: str,
        *,
        symbol: str | None,
        timeframe: str | None,
        strategy_contract_version: str,
        parameter_digest: str,
    ) -> list[dict[str, Any]]:
        refs = [
            _policy_ref(record, index=index)
            for index, record in enumerate(self.policy_records)
            if _policy_matches(
                record,
                strategy_name,
                symbol=symbol,
                timeframe=timeframe,
                strategy_contract_version=strategy_contract_version,
                parameter_digest=parameter_digest,
            )
        ]
        return sorted(refs, key=lambda item: (POLICY_ACTION_ORDER.get(str(item.get("action")), 99), item["policy_ref_id"]))

    def _read_artifact(
        self,
        source_layer: str,
        source_artifact: str,
        path: Path,
        records_key: str,
        *,
        required: bool = True,
    ) -> dict[str, Any]:
        data, error = _read_json(path)
        if error is not None:
            status = "missing" if error["type"] == "missing" else "failed"
            self._record_coverage(source_layer, source_artifact, status, error=error["message"])
            if required:
                self.warnings.append(error["message"])
            return {}
        records = _dict_list(data.get(records_key))
        warnings = _string_list(data.get("warnings"))
        errors = _error_list(data.get("errors"))
        self._record_coverage(
            source_layer,
            source_artifact,
            _coverage_status(data),
            records=len(records),
            warnings=len(warnings),
            errors=len(errors),
            artifact_status=_text_or_none(data.get("status")),
        )
        self.source_artifacts.extend([source_artifact, *_string_list(data.get("source_artifacts"))])
        self.warnings.extend(warnings)
        self.errors.extend(errors)
        return data

    def _record_coverage(
        self,
        source_layer: str,
        source_artifact: str,
        status: str,
        *,
        records: int = 0,
        warnings: int = 0,
        errors: int = 0,
        reason: str | None = None,
        error: str | None = None,
        artifact_status: str | None = None,
    ) -> None:
        self.coverage.append(
            {
                "source_layer": source_layer,
                "source_artifact": source_artifact,
                "status": status,
                "records": records,
                "warnings": warnings,
                "errors": errors,
                "reason": reason,
                "error": error,
                "artifact_status": artifact_status,
            }
        )
        self.source_artifacts.append(source_artifact)

    def _record_policy_coverage(self) -> None:
        if self.policy_records:
            self._record_coverage(
                "policy",
                POLICY_SOURCE_REF,
                "used",
                records=len(self.policy_records),
            )
        else:
            self._record_coverage(
                "policy",
                POLICY_SOURCE_REF,
                "skipped",
                reason="quant.lifecycle_policy.records is not configured.",
            )


def _record_key(record: dict[str, Any]) -> tuple[str, str | None, str | None]:
    return (
        str(record.get("strategy_name") or "unknown"),
        _text_or_none(record.get("symbol")),
        _text_or_none(record.get("timeframe")),
    )


def _strategy_key_sort_key(key: tuple[str, str | None, str | None]) -> tuple[str, str, str]:
    return (key[0], key[1] or "", key[2] or "")


def _first_matching(records: list[dict[str, Any]], key: tuple[str, str | None, str | None]) -> dict[str, Any] | None:
    exact = [record for record in records if _record_key(record) == key]
    if exact:
        return sorted(exact, key=lambda item: _text_or_none(item.get("created_at")) or "")[-1]
    strategy_name, symbol, timeframe = key
    same_strategy = [
        record
        for record in records
        if str(record.get("strategy_name") or "") == strategy_name
        and (symbol is None or record.get("symbol") in {None, symbol})
        and (timeframe is None or record.get("timeframe") in {None, timeframe})
    ]
    if same_strategy:
        return sorted(same_strategy, key=lambda item: _text_or_none(item.get("created_at")) or "")[-1]
    return None


def _params_from(*records: dict[str, Any] | None) -> dict[str, Any]:
    for record in records:
        if isinstance(record, dict) and isinstance(record.get("params"), dict):
            return record["params"]
    return {}


def _parameter_digest(params: dict[str, Any]) -> str:
    canonical = json.dumps(params, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"sha256:{digest}"


def _strategy_contract_version(*records: dict[str, Any] | None) -> str:
    for record in records:
        if isinstance(record, dict) and record.get("strategy_version") is not None:
            return str(record["strategy_version"])
        if isinstance(record, dict) and record.get("strategy_contract_version") is not None:
            return str(record["strategy_contract_version"])
    return "unknown"


def _base_lifecycle_status(
    gate: dict[str, Any] | None,
    evaluation: dict[str, Any] | None,
    quant_run: dict[str, Any] | None,
) -> str:
    if isinstance(gate, dict):
        status = str(gate.get("status") or "insufficient_evidence")
        return GATE_TO_LIFECYCLE_STATUS.get(status, "insufficient_evidence")
    if isinstance(evaluation, dict) and evaluation.get("status") == "succeeded":
        return "active_candidate"
    if isinstance(quant_run, dict) and quant_run.get("status") == "succeeded":
        return "active_candidate"
    if any(isinstance(record, dict) and record.get("status") == "failed" for record in (evaluation, quant_run)):
        return "failed"
    return "insufficient_evidence"


def _degradation_state(
    outcome_feedback: dict[str, Any],
    gate: dict[str, Any] | None,
    evaluation: dict[str, Any] | None,
) -> dict[str, Any]:
    states = set(outcome_feedback["states"])
    reasons = []
    source_record_refs = outcome_feedback["source_record_refs"]
    if "not_aligned" in states:
        reasons.append("Prior strategy gate outcome was not aligned with later market movement.")
        return {
            "state": "degraded",
            "reasons": reasons,
            "source_record_refs": source_record_refs,
        }
    weak_reason_codes = _reason_codes(gate)
    if weak_reason_codes & {"unstable_walk_forward", "weak_walk_forward_positive_coverage", "excessive_cost_drag"}:
        reasons.append("Strategy gate contains deterministic degradation warning reasons.")
        return {
            "state": "warning",
            "reasons": reasons,
            "source_record_refs": source_record_refs,
        }
    if states & {"pending", "unresolved", "insufficient_data", "skipped", "failed", "unknown"}:
        reasons.append("Outcome feedback is not strong enough to confirm lifecycle health.")
        return {
            "state": "insufficient_evidence",
            "reasons": reasons,
            "source_record_refs": source_record_refs,
        }
    if isinstance(evaluation, dict):
        overfit = evaluation.get("overfitting_risk") if isinstance(evaluation.get("overfitting_risk"), dict) else {}
        if overfit.get("status") in {"medium", "elevated"}:
            reasons.append("Strategy evaluation reports elevated overfitting risk.")
            return {
                "state": "warning",
                "reasons": reasons,
                "source_record_refs": source_record_refs,
            }
    return {
        "state": "none",
        "reasons": [],
        "source_record_refs": source_record_refs,
    }


def _apply_degradation(base_status: str, degradation: dict[str, Any]) -> str:
    state = str(degradation.get("state") or "none")
    if state == "degraded" and base_status in {"effective", "active_candidate", "watchlisted"}:
        return "degraded"
    if state == "insufficient_evidence" and base_status in {"effective", "active_candidate"}:
        return "insufficient_evidence"
    return base_status


def _apply_policy_status(lifecycle_status: str, policy_refs: list[dict[str, Any]]) -> str:
    actions = {str(item.get("action")) for item in policy_refs}
    if "retire" in actions:
        return "retired"
    if "reject" in actions:
        return "rejected"
    if "watchlist" in actions and lifecycle_status == "effective":
        return "watchlisted"
    return lifecycle_status


def _health_state(
    lifecycle_status: str,
    gate: dict[str, Any] | None,
    degradation: dict[str, Any],
    policy_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    reasons = []
    if isinstance(gate, dict):
        reasons.append(f"strategy_gate_status={gate.get('status')}.")
    if degradation.get("state") not in {None, "none"}:
        reasons.extend(_string_list(degradation.get("reasons")))
    actions = [str(item.get("action")) for item in policy_refs]
    if actions:
        reasons.append(f"explicit_lifecycle_policy_actions={','.join(sorted(set(actions)))}.")
    if lifecycle_status == "effective":
        return {"state": "healthy", "confidence": "medium", "reasons": reasons}
    if lifecycle_status == "degraded":
        return {"state": "degraded", "confidence": "medium", "reasons": reasons}
    if lifecycle_status == "retired":
        return {"state": "retired", "confidence": "high", "reasons": reasons}
    if lifecycle_status == "insufficient_evidence":
        return {"state": "insufficient_evidence", "confidence": "low", "reasons": reasons}
    if lifecycle_status == "failed":
        return {"state": "failed", "confidence": "unknown", "reasons": reasons}
    return {"state": "watch", "confidence": "low", "reasons": reasons}


def _regime_weakness(gate: dict[str, Any] | None, evaluation: dict[str, Any] | None) -> dict[str, Any]:
    reason_codes = _reason_codes(gate)
    regimes = []
    reasons = []
    if "unstable_walk_forward" in reason_codes:
        regimes.append("walk_forward_windows")
        reasons.append("Walk-forward evidence is unstable across evaluation windows.")
    if "weak_walk_forward_positive_coverage" in reason_codes:
        regimes.append("walk_forward_positive_return_windows")
        reasons.append("Walk-forward positive-return coverage is weak.")
    if isinstance(evaluation, dict):
        walk = evaluation.get("walk_forward") if isinstance(evaluation.get("walk_forward"), dict) else {}
        summary = walk.get("summary") if isinstance(walk.get("summary"), dict) else {}
        if summary.get("result_stability") == "unstable":
            regimes.append("walk_forward_result_stability")
            reasons.append("Evaluation walk-forward result stability is unstable.")
    if regimes:
        return {"state": "weak", "regimes": _unique_sorted(regimes), "reasons": _unique_sorted(reasons)}
    return {"state": "unknown", "regimes": [], "reasons": ["No regime-specific lifecycle weakness evidence was available."]}


def _promotion_state(policy_refs: list[dict[str, Any]], lifecycle_status: str) -> dict[str, Any]:
    refs = [item for item in policy_refs if item.get("action") == "promote"]
    if not refs:
        return {"state": "not_requested", "policy_refs": []}
    state = "requested" if lifecycle_status in {"effective", "active_candidate"} else "blocked"
    return {"state": state, "policy_refs": [item["policy_ref_id"] for item in refs]}


def _retirement_state(policy_refs: list[dict[str, Any]]) -> dict[str, Any]:
    refs = [item for item in policy_refs if item.get("action") == "retire"]
    if not refs:
        return {"state": "not_retired", "policy_refs": []}
    return {"state": "explicitly_retired", "policy_refs": [item["policy_ref_id"] for item in refs]}


def _evidence(
    gate: dict[str, Any] | None,
    evaluation: dict[str, Any] | None,
    quant_run: dict[str, Any] | None,
    outcome_feedback: dict[str, Any],
    policy_refs: list[dict[str, Any]],
) -> list[str]:
    items = []
    if isinstance(gate, dict):
        items.append(f"strategy_gate_status={gate.get('status')}.")
        reason_codes = sorted(_reason_codes(gate))
        if reason_codes:
            items.append(f"strategy_gate_reason_codes={','.join(reason_codes)}.")
    if isinstance(evaluation, dict):
        items.append(f"strategy_evaluation_status={evaluation.get('status')}.")
    if isinstance(quant_run, dict):
        items.append(f"quant_strategy_run_status={quant_run.get('status')}.")
    if outcome_feedback["records"]:
        states = ",".join(sorted(set(outcome_feedback["states"])))
        items.append(f"strategy_gate_outcome_feedback_states={states}.")
    actions = sorted({str(item.get("action")) for item in policy_refs})
    if actions:
        items.append(f"explicit_lifecycle_policy_actions={','.join(actions)}.")
    return _unique_sorted(items)


def _uncertainty(lifecycle_status: str, outcome_feedback: dict[str, Any]) -> list[str]:
    uncertainty = [
        "Lifecycle state is deterministic research material, not trading execution or a forecast.",
        "Promotion and retirement require explicit local policy records.",
    ]
    if not outcome_feedback["records"]:
        uncertainty.append("No strategy-gate outcome feedback matched this lifecycle record.")
    if lifecycle_status in {"insufficient_evidence", "active_candidate"}:
        uncertainty.append("Available evidence is not strong enough to classify long-term strategy health.")
    return _unique_sorted(uncertainty)


def _policy_records(config: dict[str, Any]) -> list[dict[str, Any]]:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    policy = quant.get("lifecycle_policy") if isinstance(quant.get("lifecycle_policy"), dict) else {}
    records = policy.get("records") if isinstance(policy.get("records"), list) else []
    return [record for record in records if isinstance(record, dict)]


def _policy_ref(record: dict[str, Any], *, index: int) -> dict[str, Any]:
    action = str(record.get("action") or "unknown")
    strategy_name = str(record.get("strategy_name") or "unknown")
    scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}
    ref_body = {
        "action": action,
        "strategy_name": strategy_name,
        "strategy_contract_version": record.get("strategy_contract_version"),
        "parameter_digest": record.get("parameter_digest"),
        "scope": {
            "symbol": scope.get("symbol"),
            "timeframe": scope.get("timeframe"),
        },
        "created_at": record.get("created_at"),
        "effective_at": record.get("effective_at"),
        "index": index,
    }
    digest = hashlib.sha256(
        json.dumps(ref_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "policy_ref_id": f"lifecycle_policy:{strategy_name}:{action}:{digest}",
        "action": action,
        "strategy_name": strategy_name,
        "strategy_contract_version": record.get("strategy_contract_version"),
        "parameter_digest": record.get("parameter_digest"),
        "scope": ref_body["scope"],
        "created_at": record.get("created_at"),
        "effective_at": record.get("effective_at"),
        "source_ref": POLICY_SOURCE_REF,
    }


def _policy_matches(
    record: dict[str, Any],
    strategy_name: str,
    *,
    symbol: str | None,
    timeframe: str | None,
    strategy_contract_version: str,
    parameter_digest: str,
) -> bool:
    if str(record.get("strategy_name") or "") != strategy_name:
        return False
    if record.get("strategy_contract_version") is not None and str(record["strategy_contract_version"]) != strategy_contract_version:
        return False
    if record.get("parameter_digest") is not None and str(record["parameter_digest"]) != parameter_digest:
        return False
    scope = record.get("scope") if isinstance(record.get("scope"), dict) else {}
    policy_symbol = _text_or_none(scope.get("symbol"))
    policy_timeframe = _text_or_none(scope.get("timeframe"))
    if policy_symbol is not None and policy_symbol != symbol:
        return False
    if policy_timeframe is not None and policy_timeframe != timeframe:
        return False
    return True


def _target_matches_key(target: dict[str, Any], key: tuple[str, str | None, str | None]) -> bool:
    strategy_name, symbol, timeframe = key
    expected = target.get("expected_observation") if isinstance(target.get("expected_observation"), dict) else {}
    if str(expected.get("strategy_name") or "") != strategy_name:
        return False
    target_symbol = _text_or_none(target.get("symbol"))
    target_timeframe = _text_or_none(target.get("timeframe"))
    if symbol is not None and target_symbol != symbol:
        return False
    if timeframe is not None and target_timeframe != timeframe:
        return False
    return True


def _read_json(path: Path) -> tuple[dict[str, Any], dict[str, str] | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, {"type": "missing", "message": f"{path.name} was not found."}
    except JSONDecodeError as exc:
        return {}, {"type": "invalid_json", "message": f"{path.name} is not valid JSON: {exc.msg}."}
    if not isinstance(data, dict):
        return {}, {"type": "invalid_shape", "message": f"{path.name} must contain a JSON object."}
    return data, None


def _coverage_status(data: dict[str, Any]) -> str:
    status = str(data.get("status") or "available").strip().lower()
    if status in {"ok", "succeeded", "available"}:
        return "used"
    if status in {"warning", "partial", "degraded", "stale", "insufficient", "insufficient_evidence"}:
        return "degraded"
    if status in {"failed", "skipped", "unavailable", "missing"}:
        return status
    return "used"


def _artifact_status(
    records: list[dict[str, Any]],
    *,
    coverage: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> str:
    if errors or any(item.get("status") == "failed" for item in coverage):
        return "degraded" if records else "failed"
    if any(item.get("status") == "missing" and item.get("source_layer") in {"gate", "strategy_run", "evaluation"} for item in coverage):
        return "degraded"
    if not records:
        return "skipped"
    if warnings or any(record.get("lifecycle_status") in {"degraded", "insufficient_evidence", "failed"} for record in records):
        return "warning"
    return "ok"


def _counts(
    records: list[dict[str, Any]],
    *,
    coverage: list[dict[str, Any]],
    warnings: list[str],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "records": len(records),
        "coverage_records": len(coverage),
        "by_lifecycle_status": _count_by(records, "lifecycle_status"),
        "effective": sum(1 for record in records if record.get("lifecycle_status") == "effective"),
        "active_candidate": sum(1 for record in records if record.get("lifecycle_status") == "active_candidate"),
        "watchlisted": sum(1 for record in records if record.get("lifecycle_status") == "watchlisted"),
        "rejected": sum(1 for record in records if record.get("lifecycle_status") == "rejected"),
        "degraded": sum(1 for record in records if record.get("lifecycle_status") == "degraded"),
        "retired": sum(1 for record in records if record.get("lifecycle_status") == "retired"),
        "insufficient_evidence": sum(1 for record in records if record.get("lifecycle_status") == "insufficient_evidence"),
        "failed": sum(1 for record in records if record.get("lifecycle_status") == "failed"),
        "source_status_counts": _count_by(coverage, "status"),
        "policy_records": sum(int(item.get("records") or 0) for item in coverage if item.get("source_layer") == "policy"),
        "warnings": len(warnings),
        "errors": len(errors),
    }


def _record_manifest(run: RunContext, artifact: dict[str, Any]) -> None:
    counts = artifact["counts"]
    run.manifest["artifacts"]["strategy_lifecycle_state"] = STRATEGY_LIFECYCLE_STATE_ARTIFACT
    run.manifest["strategy_lifecycle_state"] = {
        "status": artifact["status"],
        "artifact": STRATEGY_LIFECYCLE_STATE_ARTIFACT,
        "records": counts["records"],
        "coverage_records": counts["coverage_records"],
        "lifecycle_status_counts": counts["by_lifecycle_status"],
        "degraded_count": counts["degraded"],
        "retired_count": counts["retired"],
        "policy_records": counts["policy_records"],
        "warnings": counts["warnings"],
        "errors": counts["errors"],
    }
    run.manifest["counts"]["strategy_lifecycle_records"] = counts["records"]
    run.manifest["counts"]["strategy_lifecycle_effective"] = counts["effective"]
    run.manifest["counts"]["strategy_lifecycle_active_candidate"] = counts["active_candidate"]
    run.manifest["counts"]["strategy_lifecycle_watchlisted"] = counts["watchlisted"]
    run.manifest["counts"]["strategy_lifecycle_rejected"] = counts["rejected"]
    run.manifest["counts"]["strategy_lifecycle_degraded"] = counts["degraded"]
    run.manifest["counts"]["strategy_lifecycle_retired"] = counts["retired"]
    run.manifest["counts"]["strategy_lifecycle_insufficient_evidence"] = counts["insufficient_evidence"]
    run.manifest["counts"]["strategy_lifecycle_failed"] = counts["failed"]
    run.manifest["counts"]["strategy_lifecycle_policy_records"] = counts["policy_records"]
    run.manifest["counts"]["strategy_lifecycle_warnings"] = counts["warnings"]
    run.manifest["counts"]["strategy_lifecycle_errors"] = counts["errors"]


def _record_skipped_manifest(run: RunContext, *, reason: str) -> None:
    run.manifest["strategy_lifecycle_state"] = {
        "status": "skipped",
        "reason": reason,
        "artifact": None,
        "records": 0,
        "coverage_records": 0,
        "lifecycle_status_counts": {},
        "degraded_count": 0,
        "retired_count": 0,
        "policy_records": 0,
        "warnings": 0,
        "errors": 0,
    }
    for key in (
        "strategy_lifecycle_records",
        "strategy_lifecycle_effective",
        "strategy_lifecycle_active_candidate",
        "strategy_lifecycle_watchlisted",
        "strategy_lifecycle_rejected",
        "strategy_lifecycle_degraded",
        "strategy_lifecycle_retired",
        "strategy_lifecycle_insufficient_evidence",
        "strategy_lifecycle_failed",
        "strategy_lifecycle_policy_records",
        "strategy_lifecycle_warnings",
        "strategy_lifecycle_errors",
    ):
        run.manifest["counts"][key] = 0


def _lifecycle_record_id(strategy_name: str, symbol: str | None, timeframe: str | None) -> str:
    scope = f"{symbol or 'aggregate'}:{timeframe or 'aggregate'}"
    return f"strategy_lifecycle:{strategy_name}:{scope}"


def _reason_codes(record: dict[str, Any] | None) -> set[str]:
    if not isinstance(record, dict):
        return set()
    return {
        str(reason.get("code"))
        for reason in _dict_list(record.get("reasons"))
        if reason.get("code") is not None
    }


def _record_source_artifacts(record: dict[str, Any] | None) -> list[str]:
    if not isinstance(record, dict):
        return []
    return _string_list(record.get("source_artifacts"))


def _record_warnings(record: dict[str, Any] | None) -> list[str]:
    if not isinstance(record, dict):
        return []
    return _string_list(record.get("warnings"))


def _record_errors(record: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(record, dict):
        return []
    errors = _error_list(record.get("errors"))
    error = record.get("error")
    if isinstance(error, dict):
        errors.append(error)
    return errors


def _record_refs(record: dict[str, Any] | None, fields: tuple[str, ...]) -> list[str]:
    if not isinstance(record, dict):
        return []
    return [
        str(record[field])
        for field in fields
        if field in record and record[field] is not None
    ]


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _quant_enabled(config: dict[str, Any]) -> bool:
    quant = config.get("quant") if isinstance(config.get("quant"), dict) else {}
    return quant.get("enabled") is True


def _format_utc(value: datetime | str | None) -> str:
    if isinstance(value, str):
        parsed = _parse_utc(value)
        return _format_utc_datetime(parsed) if parsed else value
    if isinstance(value, datetime):
        return _format_utc_datetime(value)
    return _format_utc_datetime(datetime.now(UTC))


def _parse_utc(value: str) -> datetime | None:
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _format_utc_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _text_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float)) and not isinstance(item, bool)]


def _error_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unique_sorted(values: list[str]) -> list[str]:
    return sorted({value for value in values if isinstance(value, str) and value})
