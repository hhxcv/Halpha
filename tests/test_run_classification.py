from __future__ import annotations

from halpha.runtime.run_classification import normalize_run_trigger


def test_run_trigger_metadata_drops_private_or_path_like_values() -> None:
    trigger = normalize_run_trigger(
        {
            "source": "Dashboard",
            "intent": "run_no_codex",
            "job_id": "20260620T000000Z_deadbeef",
            "schedule_id": "https://private.example/schedule",
            "parent_run_id": "runs/20260620T000000Z",
            "source_keys": ["text", "http://private.example/feed", "macro_calendar"],
        },
        default_source="CLI",
        default_intent="run",
    )

    assert trigger == {
        "source": "Dashboard",
        "intent": "run_no_codex",
        "job_id": "20260620T000000Z_deadbeef",
        "source_keys": ["text", "macro_calendar"],
    }
