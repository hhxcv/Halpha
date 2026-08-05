from halpha.database.security_contract import (
    LIVE_ACTIVATION_SAFETY_INDEX_PREDICATE,
    live_activation_safety_index_qualified,
)


def _valid_index_row():
    return (
        False,
        True,
        True,
        ["environment_id", "account_ref"],
        LIVE_ACTIVATION_SAFETY_INDEX_PREDICATE,
    )


def test_live_activation_index_requires_exact_keys_and_predicate() -> None:
    assert live_activation_safety_index_qualified(_valid_index_row()) is True

    wrong_keys = list(_valid_index_row())
    wrong_keys[3] = ["environment_id", "instrument_ref"]
    assert live_activation_safety_index_qualified(wrong_keys) is False

    wrong_predicate = list(_valid_index_row())
    wrong_predicate[4] = "lifecycle::text <> 'COMPLETED'::text"
    assert live_activation_safety_index_qualified(wrong_predicate) is False

    not_ready = list(_valid_index_row())
    not_ready[2] = False
    assert live_activation_safety_index_qualified(not_ready) is False
