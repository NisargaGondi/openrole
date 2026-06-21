"""IPC client for the local Handshake MCP daemon (Unix socket)."""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Any

DAEMON_DIR = Path.home() / ".openrole" / "handshake"
SOCKET_PATH = DAEMON_DIR / "daemon.sock"
PID_PATH = DAEMON_DIR / "daemon.pid"
MANAGED_BY_PATH = DAEMON_DIR / "managed_by.pid"


class HandshakeDaemonUnavailable(RuntimeError):
    """Daemon socket not reachable — caller may fall back to one-shot MCP."""


class HandshakeDaemonError(RuntimeError):
    """Daemon rejected the request."""


def daemon_mode() -> str:
    return os.environ.get("HANDSHAKE_DAEMON", "auto").strip().lower()


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
    owner = _managed_by_pid()
    if owner is None or owner != os.getpid():
        return
    try:
        _request({"cmd": "shutdown"}, timeout_s=5.0)
    except HandshakeDaemonUnavailable:
        from openrole.scrapers.handshake_daemon import stop_daemon

        stop_daemon()
    deadline = time.monotonic() + 20.0
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
    except HandshakeDaemonUnavailable:
        return False


def ping_daemon(*, timeout_s: float = 3.0) -> dict[str, Any]:
    return _request({"cmd": "ping"}, timeout_s=timeout_s)


def daemon_call_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    timeout_s: float = 130.0,
) -> dict[str, Any]:
    payload = _request(
        {"cmd": "call_tool", "tool": tool_name, "arguments": arguments},
        timeout_s=timeout_s,
    )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise HandshakeDaemonError("Daemon returned invalid call_tool payload")
    return result


def _request(body: dict[str, Any], *, timeout_s: float) -> dict[str, Any]:
    if not SOCKET_PATH.exists():
        raise HandshakeDaemonUnavailable(f"No daemon socket at {SOCKET_PATH}")

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
            raise HandshakeDaemonUnavailable("Handshake daemon closed connection")
        payload = json.loads(raw)
    except (FileNotFoundError, ConnectionRefusedError, TimeoutError, OSError) as exc:
        raise HandshakeDaemonUnavailable(str(exc)) from exc
    finally:
        sock.close()

    if not payload.get("ok"):
        raise HandshakeDaemonError(str(payload.get("error") or "Daemon request failed"))
    return payload
