"""Start browser/MCP daemons only for the pipeline step that needs them, then tear down."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from contextlib import contextmanager
from collections.abc import Iterator
from typing import Literal

DaemonName = Literal["careershift", "handshake"]

_STARTUP_WAIT_S = 90.0
_POLL_INTERVAL_S = 0.4


def on_demand_enabled() -> bool:
    raw = os.environ.get("BROWSER_DAEMON_ON_DEMAND", "true").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _spawn_careershift_daemon() -> None:
    from openrole.scrapers.careershift_ipc import DAEMON_DIR

    DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("CAREERSHIFT_DAEMON_IDLE_TIMEOUT_S", "0")
    subprocess.Popen(
        [sys.executable, "-m", "openrole.scrapers.careershift_daemon", "run"],
        cwd=str(_repo_root()),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _spawn_handshake_daemon() -> None:
    from openrole.scrapers.handshake_ipc import DAEMON_DIR

    DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("HANDSHAKE_DAEMON_IDLE_TIMEOUT_S", "0")
    env.setdefault("OPENROLE_HANDSHAKE_HEADLESS", "false")
    subprocess.Popen(
        [sys.executable, "-m", "openrole.scrapers.handshake_daemon", "run"],
        cwd=str(_repo_root()),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _repo_root() -> os.PathLike[str]:
    from pathlib import Path

    return Path(__file__).resolve().parents[3]


def _wait_until_running(name: DaemonName, *, deadline: float) -> None:
    while time.monotonic() < deadline:
        if name == "careershift":
            from openrole.scrapers.careershift_ipc import daemon_running

            if daemon_running():
                return
        elif name == "handshake":
            from openrole.scrapers.handshake_ipc import daemon_running

            if daemon_running():
                return
        time.sleep(_POLL_INTERVAL_S)
    label = "CareerShift" if name == "careershift" else "Handshake"
    raise RuntimeError(f"{label} daemon did not become ready within {_STARTUP_WAIT_S:.0f}s")


def _should_manage(name: DaemonName) -> bool:
    if not on_demand_enabled():
        return False
    if name == "careershift":
        from openrole.scrapers.careershift_ipc import prefer_daemon

        return prefer_daemon()
    from openrole.scrapers.handshake_ipc import prefer_daemon

    return prefer_daemon()


def ensure_daemon(name: DaemonName) -> bool:
    """Start daemon if needed. Returns True when this call spawned it."""
    if not _should_manage(name):
        return False

    if name == "careershift":
        from openrole.scrapers.careershift_ipc import daemon_running, mark_managed_by

        if daemon_running():
            return False
        mark_managed_by(os.getpid())
        _spawn_careershift_daemon()
    else:
        from openrole.scrapers.handshake_ipc import daemon_running, mark_managed_by

        if daemon_running():
            return False
        mark_managed_by(os.getpid())
        _spawn_handshake_daemon()

    _wait_until_running(name, deadline=time.monotonic() + _STARTUP_WAIT_S)
    return True


def stop_daemon_if_managed(name: DaemonName) -> None:
    """Shut down daemon only if we marked it for on-demand lifecycle."""
    if not on_demand_enabled():
        return
    if name == "careershift":
        from openrole.scrapers.careershift_ipc import clear_managed_by, stop_managed_daemon

        stop_managed_daemon()
        clear_managed_by()
    else:
        from openrole.scrapers.handshake_ipc import clear_managed_by, stop_managed_daemon

        stop_managed_daemon()
        clear_managed_by()


@contextmanager
def managed_daemons(*names: DaemonName) -> Iterator[None]:
    """Ensure daemons for `names` are up for the block; stop any we started."""
    started: list[DaemonName] = []
    try:
        for name in names:
            if ensure_daemon(name):
                started.append(name)
        yield
    finally:
        for name in reversed(started):
            stop_daemon_if_managed(name)
