import pytest

from tools.qualification import verify_windows_runtime as runtime


@pytest.mark.parametrize(
    ("read_only", "continuous", "expected"),
    (
        (False, False, (True, "PERSISTENT_TRADING_TASK")),
        (True, True, (True, "PERSISTENT_ACCOUNT_OBSERVER")),
        (True, False, (False, "EXPLICIT_OBSERVATION_SESSION_ONLY")),
    ),
)
def test_executor_runtime_policy_matches_account_observation_mode(
    read_only: bool,
    continuous: bool,
    expected: tuple[bool, str],
) -> None:
    assert runtime._executor_runtime_policy(
        read_only=read_only,
        continuous_account_observation=continuous,
    ) == expected


def test_profile_unload_accepts_only_already_invalid_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime.win32profile,
        "UnloadUserProfile",
        lambda _token, _profile: (_ for _ in ()).throw(
            runtime.pywintypes.error(
                runtime.winerror.ERROR_INVALID_HANDLE,
                "UnloadUserProfile",
                "invalid handle",
            )
        ),
    )

    runtime._unload_task_identity_profile(
        object(),
        object(),
        username="HalphaAppDemo",
    )


def test_profile_unload_rejects_other_cleanup_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runtime.win32profile,
        "UnloadUserProfile",
        lambda _token, _profile: (_ for _ in ()).throw(
            runtime.pywintypes.error(
                runtime.winerror.ERROR_ACCESS_DENIED,
                "UnloadUserProfile",
                "access denied",
            )
        ),
    )

    with pytest.raises(
        runtime.WindowsQualificationError,
        match=(
            "TASK_IDENTITY_PROFILE_UNLOAD_FAILED "
            "user=HalphaAppDemo code=5"
        ),
    ):
        runtime._unload_task_identity_profile(
            object(),
            object(),
            username="HalphaAppDemo",
        )
