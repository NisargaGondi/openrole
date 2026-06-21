"""Local Handshake MCP daemon — one browser session for scout / ingest."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import time
from typing import Any

from openrole.scrapers.handshake_ipc import DAEMON_DIR, PID_PATH, SOCKET_PATH


def _idle_timeout_s() -> float:
    raw = os.environ.get("HANDSHAKE_DAEMON_IDLE_TIMEOUT_S", "1800").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 1800.0
    return max(0.0, value)


def _handshake_headless() -> bool:
    from openrole.scrapers.browser_headless import scrape_headless_enabled

    return scrape_headless_enabled("OPENROLE_HANDSHAKE_HEADLESS", default=False)


class HandshakeDaemon:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_activity = time.monotonic()
        self._call_count = 0
        self._started_at = time.monotonic()
        self._shutting_down = False
        self._read_stream = None
        self._write_stream = None
        self._session = None
        self._stdio_ctx = None
        self._session_ctx = None

    def touch(self) -> None:
        self._last_activity = time.monotonic()

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_activity

    async def start_mcp(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        from openrole.scrapers.handshake_client import _handshake_mcp_argv

        server_params = StdioServerParameters(
            command=sys.executable,
            args=_handshake_mcp_argv(headless=_handshake_headless()),
            env=None,
        )
        self._stdio_ctx = stdio_client(server_params)
        self._read_stream, self._write_stream = await self._stdio_ctx.__aenter__()
        self._session_ctx = ClientSession(self._read_stream, self._write_stream)
        self._session = await self._session_ctx.__aenter__()
        await self._session.initialize()

    async def close(self) -> None:
        if self._session_ctx is not None:
            await self._session_ctx.__aexit__(None, None, None)
            self._session_ctx = None
            self._session = None
        if self._stdio_ctx is not None:
            await self._stdio_ctx.__aexit__(None, None, None)
            self._stdio_ctx = None

    async def handle(self, body: dict[str, Any]) -> dict[str, Any]:
        cmd = str(body.get("cmd") or "").strip().lower()
        if cmd == "ping":
            return {
                "ok": True,
                "cmd": "ping",
                "uptime_s": round(time.monotonic() - self._started_at, 1),
                "idle_s": round(self.idle_seconds, 1),
                "calls": self._call_count,
                "headless": _handshake_headless(),
            }
        if cmd == "status":
            return {
                "ok": True,
                "idle_s": round(self.idle_seconds, 1),
                "calls": self._call_count,
                "headless": _handshake_headless(),
            }
        if cmd == "shutdown":
            self._shutting_down = True
            return {"ok": True, "message": "shutting down"}
        if cmd == "call_tool":
            tool = str(body.get("tool") or "").strip()
            arguments = body.get("arguments")
            if not tool:
                return {"ok": False, "error": "tool name required"}
            if not isinstance(arguments, dict):
                arguments = {}
            async with self._lock:
                self.touch()
                result = await self._call_tool(tool, arguments)
                self._call_count += 1
            return {"ok": True, "result": result}
        return {"ok": False, "error": f"unknown cmd: {cmd}"}

    async def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from openrole.scrapers.handshake_client import (
            HandshakeMCPError,
            _content_to_dict,
            _format_mcp_error,
        )

        if self._session is None:
            raise HandshakeMCPError("Handshake MCP session not started")
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(tool_name, arguments),
                timeout=120.0,
            )
        except asyncio.TimeoutError as exc:
            raise HandshakeMCPError(f"Handshake tool {tool_name} timed out") from exc
        if result.isError:
            raise HandshakeMCPError(
                f"Handshake tool {tool_name} failed: {_format_mcp_error(result.content)}"
            )
        return _content_to_dict(result.content)

    async def idle_watchdog(self, timeout_s: float) -> None:
        if timeout_s <= 0:
            return
        while not self._shutting_down:
            await asyncio.sleep(30.0)
            if self._shutting_down:
                break
            if self.idle_seconds >= timeout_s:
                print(
                    f"Handshake daemon idle for {int(self.idle_seconds)}s — shutting down "
                    f"(set HANDSHAKE_DAEMON_IDLE_TIMEOUT_S=0 to disable)",
                    flush=True,
                )
                self._shutting_down = True
                break


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    daemon: HandshakeDaemon,
) -> None:
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=300.0)
        if not line:
            return
        body = json.loads(line.decode("utf-8"))
        try:
            result = await daemon.handle(body)
        except Exception as exc:
            result = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
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

    daemon = HandshakeDaemon()
    loop = asyncio.get_running_loop()

    def _signal_stop(*_args: Any) -> None:
        daemon._shutting_down = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _signal_stop())

    print("Starting Handshake MCP session…", flush=True)
    await daemon.start_mcp()
    headless = _handshake_headless()
    print(
        f"Handshake daemon ready ({'headless' if headless else 'visible window'}) — "
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
        print("Handshake daemon stopped.", flush=True)
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
            print(f"Sent SIGTERM to Handshake daemon (pid {pid})")
            return 0
        except OSError as exc:
            print(f"Could not stop daemon pid {pid}: {exc}")
    if SOCKET_PATH.exists():
        try:
            from openrole.scrapers.handshake_ipc import _request

            _request({"cmd": "shutdown"}, timeout_s=5.0)
            print("Handshake daemon shutdown requested")
            return 0
        except Exception as exc:
            print(f"Shutdown via socket failed: {exc}")
    print("Handshake daemon is not running")
    return 1


def status_daemon() -> int:
    from openrole.scrapers.handshake_ipc import daemon_running, ping_daemon

    if not daemon_running():
        print("Handshake daemon: not running")
        print("  Start: bash scripts/run_handshake_daemon.sh")
        return 1
    info = ping_daemon()
    print("Handshake daemon: running")
    print(f"  PID: {PID_PATH.read_text().strip() if PID_PATH.is_file() else '?'}")
    print(f"  Socket: {SOCKET_PATH}")
    print(f"  Headless: {info.get('headless')}")
    print(f"  Calls served: {info.get('calls')}")
    print(f"  Idle: {info.get('idle_s')}s")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Handshake persistent MCP daemon")
    parser.add_argument(
        "action",
        nargs="?",
        default="run",
        choices=("run", "start", "stop", "status"),
    )
    args = parser.parse_args(argv)
    if args.action == "stop":
        return stop_daemon()
    if args.action == "status":
        return status_daemon()
    return asyncio.run(run_daemon())


if __name__ == "__main__":
    raise SystemExit(main())
