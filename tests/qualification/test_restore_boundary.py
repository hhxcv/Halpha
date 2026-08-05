from pathlib import Path

from halpha.database.record_families import CURRENT_PRODUCT_SCHEMA_REVISION
from halpha.database.schema_version import CURRENT_SCHEMA_REVISION
from tools.qualification import verify_database_boundary
from tools.qualification import verify_restore_boundary


def test_database_qualifiers_share_one_current_schema_revision() -> None:
    assert CURRENT_PRODUCT_SCHEMA_REVISION == CURRENT_SCHEMA_REVISION
    assert verify_database_boundary.HEAD == CURRENT_PRODUCT_SCHEMA_REVISION


def test_restore_target_uses_uuid_sized_identity() -> None:
    first = verify_restore_boundary._restore_target_database_name()
    second = verify_restore_boundary._restore_target_database_name()

    assert first.startswith("halpha_restore_")
    assert len(first) == len("halpha_restore_") + 32
    assert first != second


def test_restore_qualification_covers_all_contexts_and_nonempty_sources() -> None:
    source = Path(verify_restore_boundary.__file__).read_text(
        encoding="utf-8"
    )

    assert verify_restore_boundary.ENVIRONMENTS == (
        "demo",
        "live_copy",
        "live_personal",
    )
    assert "source_and_restored_record_counts_match" in source
    assert "source_and_restored_content_match" in source
    assert "source_record_counts_before" in source
    assert "source_record_counts_after" in source
    assert "source_table_snapshots_before" in source
    assert "source_table_snapshots_after" in source
    assert "fresh_baseline_has_no_product_records" not in source
    assert "all_peer_environment_roles_rejected" in source


def test_restore_qualification_stops_a_running_task_before_deletion() -> None:
    class RunningTask:
        State = verify_restore_boundary.TASK_STATE_RUNNING

        def Stop(self, flags: int) -> None:
            assert flags == 0
            self.State = verify_restore_boundary.TASK_STATE_READY

    task = RunningTask()
    verify_restore_boundary._stop_task_before_delete(task)

    assert task.State == verify_restore_boundary.TASK_STATE_READY
