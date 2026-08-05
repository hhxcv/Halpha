"""Environment-scoped Windows account and scheduled-task names."""

from __future__ import annotations

from dataclasses import dataclass


SHARED_BACKUP_USER = "HalphaBackup"
SHARED_BACKUP_TASK = "Backup"


@dataclass(frozen=True)
class WindowsDeployment:
    namespace: str
    app_user: str
    executor_user: str
    app_task: str
    executor_task: str
    owns_shared_backup: bool = False


DEMO_DEPLOYMENT = WindowsDeployment(
    namespace="BINANCE_DEMO",
    app_user="HalphaAppDemo",
    executor_user="HalphaExecutorDemo",
    app_task="App.BINANCE_DEMO",
    executor_task="Executor.BINANCE_DEMO",
    owns_shared_backup=True,
)
LIVE_COPY_DEPLOYMENT = WindowsDeployment(
    namespace="BINANCE_LIVE_COPY",
    app_user="HalphaAppCopy",
    executor_user="HalphaExecCopy",
    app_task="App.BINANCE_LIVE_COPY",
    executor_task="Executor.BINANCE_LIVE_COPY",
)
LIVE_PERSONAL_DEPLOYMENT = WindowsDeployment(
    namespace="BINANCE_LIVE_PERSONAL",
    app_user="HalphaAppPersonal",
    executor_user="HalphaExecPersonal",
    app_task="App.BINANCE_LIVE_PERSONAL",
    executor_task="Executor.BINANCE_LIVE_PERSONAL",
)
ALL_WINDOWS_DEPLOYMENTS = (
    DEMO_DEPLOYMENT,
    LIVE_COPY_DEPLOYMENT,
    LIVE_PERSONAL_DEPLOYMENT,
)


def windows_deployment(venue_account_type: str) -> WindowsDeployment:
    deployments = {
        "USDM_DEMO": DEMO_DEPLOYMENT,
        "USDM_COPY_LEAD": LIVE_COPY_DEPLOYMENT,
        "USDM_PERSONAL": LIVE_PERSONAL_DEPLOYMENT,
    }
    try:
        return deployments[venue_account_type]
    except KeyError:
        raise ValueError(
            "WINDOWS_DEPLOYMENT_ACCOUNT_TYPE_UNSUPPORTED "
            f"venue_account_type={venue_account_type}"
        ) from None


def peer_windows_deployments(venue_account_type: str) -> tuple[WindowsDeployment, ...]:
    current = windows_deployment(venue_account_type)
    return tuple(
        deployment
        for deployment in ALL_WINDOWS_DEPLOYMENTS
        if deployment is not current
    )
