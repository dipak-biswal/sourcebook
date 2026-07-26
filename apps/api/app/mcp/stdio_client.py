"""Minimal MCP stdio JSON-RPC client (Content-Length framing).

Enough to talk to official servers like ``npx -y @drawio/mcp``:
initialize → tools/list → tools/call. Not a full MCP SDK.
"""

from __future__ import annotations

import json
import logging
import os
import select
import subprocess
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class McpStdioError(RuntimeError):
    """Raised when the MCP process or protocol fails."""


class McpStdioClient:
    """
    Short-lived MCP client over a child process stdio transport.

    Usage::

        with McpStdioClient(["npx", "-y", "@drawio/mcp"], timeout=45) as client:
            client.initialize()
            result = client.call_tool("open_drawio_mermaid", {"content": "..."})
    """

    def __init__(
        self,
        command: list[str],
        *,
        timeout: float = 45.0,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> None:
        if not command:
            raise ValueError("command must be non-empty")
        self._command = list(command)
        self._timeout = float(timeout)
        self._env = env
        self._cwd = cwd
        self._proc: subprocess.Popen[bytes] | None = None
        self._stderr_chunks: list[bytes] = []
        self._stderr_thread: threading.Thread | None = None
        self._next_id = 1
        self._lock = threading.Lock()

    def __enter__(self) -> McpStdioClient:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def stderr_text(self) -> str:
        return b"".join(self._stderr_chunks).decode("utf-8", errors="replace")

    def start(self) -> None:
        if self._proc is not None:
            return
        env = os.environ.copy()
        if self._env:
            env.update(self._env)
        # Avoid interactive npx prompts when possible.
        env.setdefault("npm_config_yes", "true")
        env.setdefault("CI", "1")
        try:
            self._proc = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._cwd,
                env=env,
                bufsize=0,
            )
        except FileNotFoundError as e:
            raise McpStdioError(
                f"Failed to start MCP server {self._command[0]!r}: {e}"
            ) from e

        def _drain_stderr() -> None:
            assert self._proc is not None and self._proc.stderr is not None
            try:
                while True:
                    chunk = self._proc.stderr.read(4096)
                    if not chunk:
                        break
                    self._stderr_chunks.append(chunk)
                    # Cap stderr buffer
                    if sum(len(c) for c in self._stderr_chunks) > 200_000:
                        self._stderr_chunks = self._stderr_chunks[-20:]
            except Exception:
                pass

        self._stderr_thread = threading.Thread(
            target=_drain_stderr, name="mcp-stderr", daemon=True
        )
        self._stderr_thread.start()

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        if self._stderr_thread and self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=1.0)

    def _require_proc(self) -> subprocess.Popen[bytes]:
        if self._proc is None:
            raise McpStdioError("MCP client not started")
        if self._proc.poll() is not None:
            raise McpStdioError(
                f"MCP process exited early (code={self._proc.returncode}): "
                f"{self.stderr_text[:400]}"
            )
        return self._proc

    def _write(self, message: dict[str, Any]) -> None:
        proc = self._require_proc()
        assert proc.stdin is not None
        body = json.dumps(message, ensure_ascii=False).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        with self._lock:
            proc.stdin.write(header + body)
            proc.stdin.flush()

    def _read_message(self, *, timeout: float | None = None) -> dict[str, Any]:
        proc = self._require_proc()
        assert proc.stdout is not None
        deadline = time.time() + (self._timeout if timeout is None else timeout)

        def _read_exact(n: int) -> bytes:
            out = b""
            while len(out) < n:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise McpStdioError("timeout reading MCP message body")
                # select for readability
                r, _, _ = select.select([proc.stdout], [], [], min(0.5, remaining))
                if not r:
                    if proc.poll() is not None:
                        raise McpStdioError(
                            f"MCP process died while reading body "
                            f"(code={proc.returncode}): {self.stderr_text[:400]}"
                        )
                    continue
                chunk = proc.stdout.read(n - len(out))
                if not chunk:
                    if proc.poll() is not None:
                        raise McpStdioError(
                            f"MCP EOF mid-body (code={proc.returncode}): "
                            f"{self.stderr_text[:400]}"
                        )
                    continue
                out += chunk
            return out

        # Read headers byte-by-byte until \r\n\r\n
        header_buf = b""
        while not header_buf.endswith(b"\r\n\r\n"):
            remaining = deadline - time.time()
            if remaining <= 0:
                raise McpStdioError(
                    f"timeout reading MCP headers: {header_buf[:120]!r} "
                    f"stderr={self.stderr_text[:300]!r}"
                )
            r, _, _ = select.select([proc.stdout], [], [], min(0.5, remaining))
            if not r:
                if proc.poll() is not None:
                    raise McpStdioError(
                        f"MCP process died during headers "
                        f"(code={proc.returncode}): {self.stderr_text[:400]}"
                    )
                continue
            ch = proc.stdout.read(1)
            if not ch:
                if proc.poll() is not None:
                    raise McpStdioError(
                        f"MCP EOF during headers (code={proc.returncode}): "
                        f"{self.stderr_text[:400]}"
                    )
                continue
            header_buf += ch
            if len(header_buf) > 64_000:
                raise McpStdioError("MCP header too large")

        headers = header_buf.decode("ascii", errors="replace")
        length: int | None = None
        for line in headers.split("\r\n"):
            if line.lower().startswith("content-length:"):
                try:
                    length = int(line.split(":", 1)[1].strip())
                except ValueError as e:
                    raise McpStdioError(f"bad Content-Length: {line!r}") from e
        if length is None or length < 0:
            raise McpStdioError(f"missing Content-Length in headers: {headers!r}")
        if length > 8_000_000:
            raise McpStdioError(f"MCP body too large: {length}")

        body = _read_exact(length)
        try:
            msg = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise McpStdioError(f"invalid MCP JSON: {e}") from e
        if not isinstance(msg, dict):
            raise McpStdioError("MCP message must be a JSON object")
        return msg

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> Any:
        req_id = self._next_id
        self._next_id += 1
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        self._write(message)
        # Skip unrelated notifications until we get our response id.
        deadline = time.time() + (self._timeout if timeout is None else timeout)
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise McpStdioError(f"timeout waiting for response to {method}")
            msg = self._read_message(timeout=remaining)
            if msg.get("id") != req_id:
                # Notification or unrelated — ignore for this client.
                logger.debug("mcp skip message id=%s method=%s", msg.get("id"), msg.get("method"))
                continue
            if "error" in msg and msg["error"] is not None:
                err = msg["error"]
                raise McpStdioError(f"MCP error on {method}: {err}")
            return msg.get("result")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)

    def initialize(
        self,
        *,
        client_name: str = "sourcebook",
        client_version: str = "0.1.0",
        protocol_version: str = "2024-11-05",
    ) -> dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": protocol_version,
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": client_version},
            },
        )
        # Required handshake notification.
        self.notify("notifications/initialized")
        return result if isinstance(result, dict) else {}

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list", {})
        if not isinstance(result, dict):
            return []
        tools = result.get("tools") or []
        return [t for t in tools if isinstance(t, dict)]

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        result = self.request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            timeout=timeout,
        )
        return result if isinstance(result, dict) else {"result": result}


def parse_tool_text_content(result: dict[str, Any]) -> str:
    """Extract concatenated text parts from an MCP tools/call result."""
    parts: list[str] = []
    content = result.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
            elif isinstance(item, str):
                parts.append(item)
    elif isinstance(content, str):
        parts.append(content)
    return "\n".join(parts).strip()


def extract_urls(text: str) -> list[str]:
    """Best-effort URL harvest from tool text output."""
    import re

    if not text:
        return []
    found = re.findall(r"https?://[^\s<>\"']+", text)
    # Strip trailing punctuation common in prose.
    cleaned: list[str] = []
    for u in found:
        cleaned.append(u.rstrip(").,;]}>\""))
    return cleaned
