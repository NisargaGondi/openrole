"""Local CareerShift browser daemon — keeps one Chromium window alive for fast searches."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from openrole.scrapers.careershift_ipc import DAEMON_DIR, PID_PATH, SOCKET_PATH
from openrole.scrapers.careershift_session import CareerShiftBrowserSession


def _daemon_headless() -> bool:
    raw = os.environ.get("OPENROLE_CAREERSHIFT_DAEMON_HEADLESS", "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _idle_timeout_s() -> float:
    raw = os.environ.get("CAREERSHIFT_DAEMON_IDLE_TIMEOUT_S", "1800").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 1800.0
    return max(0.0, value)


class CareerShiftDaemon:
    def __init__(self) -> None:
        self._session = CareerShiftBrowserSession()
        self._lock = asyncio.Lock()
        self._last_activity = time.monotonic()
        self._search_count = 0
        self._started_at = time.monotonic()
        self._shutting_down = False

    async def start_browser(self) -> None:
        await self._session.start(headless=_daemon_headless())

    async def close(self) -> None:
        await self._session.close()

    def touch(self) -> None:
        self._last_activity = time.monotonic()

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_activity

    async def handle(self, body: dict[str, Any]) -> dict[str, Any]:
        cmd = str(body.get("cmd") or "").strip().lower()
        if cmd == "ping":
            return {
                "ok": True,
                "cmd": "ping",
                "uptime_s": round(time.monotonic() - self._started_at, 1),
                "idle_s": round(self.idle_seconds, 1),
                "searches": self._search_count,
                "logged_in": await self._session.session_ok(),
                "headless": _daemon_headless(),
            }
        if cmd == "status":
            return {
                "ok": True,
                "logged_in": await self._session.session_ok(),
                "headless": _daemon_headless(),
                "idle_s": round(self.idle_seconds, 1),
                "searches": self._search_count,
            }
        if cmd == "shutdown":
            self._shutting_down = True
            return {"ok": True, "message": "shutting down"}
        if cmd == "search_batch":
            queries = body.get("queries")
            if not isinstance(queries, list):
                return {"ok": False, "error": "queries must be a list"}
            async with self._lock:
                self.touch()
                results = await self._session.search_batch(queries)
                self._search_count += 1
            return {"ok": True, "results": results, "count": len(results)}
        return {"ok": False, "error": f"unknown cmd: {cmd}"}

    async def idle_watchdog(self, timeout_s: float) -> None:
        if timeout_s <= 0:
            return
        while not self._shutting_down:
            await asyncio.sleep(30.0)
            if self._shutting_down:
                break
            if self.idle_seconds >= timeout_s:
                print(
                    f"CareerShift daemon idle for {int(self.idle_seconds)}s — shutting down "
                    f"(set CAREERSHIFT_DAEMON_IDLE_TIMEOUT_S=0 to disable)",
                    flush=True,
                )
                self._shutting_down = True
                break


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    daemon: CareerShiftDaemon,
) -> None:
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=300.0)
        if not line:
            return
        body = json.loads(line.decode("utf-8"))
        result = await daemon.handle(body)
        writer.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
        await writer.drain()
    except Exception as exc:
        err = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        writer.write((json.dumps(err) + "\n").encode("utf-8"))
        await writer.drain()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def run_daemon() -> int:
    DAEMON_DIR.mkdir(parents=True, exist_ok=True)
    if SOCKET_PATH.exists():
        SOCKET_PATH.unlink()

    daemon = CareerShiftDaemon()
    loop = asyncio.get_running_loop()

    def _signal_stop(*_args: Any) -> None:
        daemon._shutting_down = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _signal_stop())

    print("Starting CareerShift browser…", flush=True)
    await daemon.start_browser()
    headless = _daemon_headless()
    print(
        f"CareerShift daemon ready ({'headless' if headless else 'visible window'}) — "
        f"socket {SOCKET_PATH}",
        flush=True,
    )

    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    idle_task = asyncio.create_task(daemon.idle_watchdog(_idle_timeout_s()))

    server = await asyncio.start_unix_server(
        lambda r, w: _handle_client(r, w, daemon),
        path=str(SOCKET_PATH),
    )

    try:
        async with server:
            serve_task = asyncio.create_task(server.serve_forever())
            while not daemon._shutting_down:
                await asyncio.sleep(0.25)
            serve_task.cancel()
            try:
                await serve_task
            except asyncio.CancelledError:
                pass
    finally:
        idle_task.cancel()
        try:
            await idle_task
        except asyncio.CancelledError:
            pass
        await daemon.close()
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
        if PID_PATH.exists():
            PID_PATH.unlink()
        print("CareerShift daemon stopped.", flush=True)
    return 0


def stop_daemon() -> int:
    pid = None
    if PID_PATH.is_file():
        try:
            pid = int(PID_PATH.read_text(encoding="utf-8").strip())
        except ValueError:
            pid = None
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to CareerShift daemon (pid {pid})")
            return 0
        except OSError as exc:
            print(f"Could not stop daemon pid {pid}: {exc}")
    if SOCKET_PATH.exists():
        try:
            from openrole.scrapers.careershift_ipc import _request

            _request({"cmd": "shutdown"}, timeout_s=5.0)
            print("CareerShift daemon shutdown requested")
            return 0
        except Exception as exc:
            print(f"Shutdown via socket failed: {exc}")
    print("CareerShift daemon is not running")
    return 1


def status_daemon() -> int:
    from openrole.scrapers.careershift_ipc import daemon_running, ping_daemon

    if not daemon_running():
        print("CareerShift daemon: not running")
        print(f"  Start: bash scripts/run_careershift_daemon.sh")
        return 1
    info = ping_daemon()
    print("CareerShift daemon: running")
    print(f"  PID: {PID_PATH.read_text().strip() if PID_PATH.is_file() else '?'}")
    print(f"  Socket: {SOCKET_PATH}")
    print(f"  Logged in: {info.get('logged_in')}")
    print(f"  Headless: {info.get('headless')}")
    print(f"  Searches served: {info.get('searches')}")
    print(f"  Idle: {info.get('idle_s')}s")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CareerShift persistent browser daemon")
    parser.add_argument(
        "action",
        nargs="?",
        default="run",
        choices=("run", "start", "stop", "status"),
        help="run/start = launch daemon; stop/status = control",
    )
    args = parser.parse_args(argv)
    action = args.action
    if action == "stop":
        return stop_daemon()
    if action == "status":
        return status_daemon()
    return asyncio.run(run_daemon())


if __name__ == "__main__":
    raise SystemExit(main())
