"""IPC client for the local CareerShift browser daemon (Unix socket)."""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Any

DAEMON_DIR = Path.home() / ".openrole" / "careershift"
SOCKET_PATH = DAEMON_DIR / "daemon.sock"
PID_PATH = DAEMON_DIR / "daemon.pid"
MANAGED_BY_PATH = DAEMON_DIR / "managed_by.pid"


class CareerShiftDaemonUnavailable(RuntimeError):
    """Daemon socket not reachable — caller may fall back to one-shot browser."""


class CareerShiftDaemonError(RuntimeError):
    """Daemon rejected the request."""


def daemon_mode() -> str:
    """auto | always | off — whether pipeline calls prefer the daemon."""
    return os.environ.get("CAREERSHIFT_DAEMON", "auto").strip().lower()


def prefer_daemon() -> bool:
    mode = daemon_mode()
    return mode in ("auto", "always", "true", "1", "yes", "on")


def require_daemon() -> bool:
    return daemon_mode() in ("always", "require", "required")


def mark_managed_by(pid: int) -> None:
    DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    MANAGED_BY_PATH.write_text(str(pid), encoding="utf-8")


def clear_managed_by() -> None:
    if MANAGED_BY_PATH.is_file():
        MANAGED_BY_PATH.unlink(missing_ok=True)


def _managed_by_pid() -> int | None:
    if not MANAGED_BY_PATH.is_file():
        return None
    try:
        return int(MANAGED_BY_PATH.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def stop_managed_daemon() -> None:
    """Request shutdown only when this process owns the on-demand daemon."""
    owner = _managed_by_pid()
    if owner is None or owner != os.getpid():
        return
    try:
        _request({"cmd": "shutdown"}, timeout_s=5.0)
    except CareerShiftDaemonUnavailable:
        from openrole.scrapers.careershift_daemon import stop_daemon

        stop_daemon()
    # Give the daemon a moment to exit
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if not daemon_running():
            break
        time.sleep(0.2)


def daemon_pid() -> int | None:
    if not PID_PATH.is_file():
        return None
    try:
        raw = PID_PATH.read_text(encoding="utf-8").strip()
        pid = int(raw)
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def daemon_running() -> bool:
    if not SOCKET_PATH.exists():
        return daemon_pid() is not None
    try:
        ping_daemon(timeout_s=2.0)
        return True
    except CareerShiftDaemonUnavailable:
        return False


def ping_daemon(*, timeout_s: float = 3.0) -> dict[str, Any]:
    return _request({"cmd": "ping"}, timeout_s=timeout_s)


def daemon_search_batch(queries: list[dict[str, Any]], *, timeout_s: float | None = None) -> list[dict[str, Any]]:
    if timeout_s is None:
        from openrole.scrapers.careershift_client import _batch_timeout_s

        timeout_s = _batch_timeout_s() + 30.0
    payload = _request({"cmd": "search_batch", "queries": queries}, timeout_s=timeout_s)
    results = payload.get("results")
    if not isinstance(results, list):
        raise CareerShiftDaemonError("Daemon returned invalid search_batch payload")
    return results


def _request(body: dict[str, Any], *, timeout_s: float) -> dict[str, Any]:
    if not SOCKET_PATH.exists():
        raise CareerShiftDaemonUnavailable(f"No daemon socket at {SOCKET_PATH}")

    data = (json.dumps(body, ensure_ascii=False) + "\n").encode("utf-8")
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout_s

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(max(0.5, deadline - time.monotonic()))
        sock.connect(str(SOCKET_PATH))
        sock.sendall(data)
        sock.setblocking(False)
        while time.monotonic() < deadline:
            try:
                part = sock.recv(65536)
                if not part:
                    break
                chunks.append(part)
                if b"\n" in part:
                    break
            except BlockingIOError:
                time.sleep(0.05)
        raw = b"".join(chunks).split(b"\n", 1)[0].decode("utf-8")
        if not raw:
            raise CareerShiftDaemonUnavailable("CareerShift daemon closed connection")
        payload = json.loads(raw)
    except (FileNotFoundError, ConnectionRefusedError, TimeoutError, OSError) as exc:
        raise CareerShiftDaemonUnavailable(str(exc)) from exc
    finally:
        sock.close()

    if not payload.get("ok"):
        raise CareerShiftDaemonError(str(payload.get("error") or "Daemon request failed"))
    return payload
