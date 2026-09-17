#!/usr/bin/env python3
"""Minimal web UI server for Agent2Chain."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import traceback
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from UI.utils.knowledge_level_state import DEFAULT_LEVEL, KNOWLEDGE_LEVEL_STATE_KEY, normalize_level

from agents.BlockchainAgent.agent import (
    SESSION_ID as DEFAULT_SESSION_ID,
    USER_ID,
    close_mcp_toolsets,
    ensure_session,
    root_agent,
    runner,
)
from UI.utils.server_utils import (
    compile_contract_for_deploy,
    load_src_env,
    normalize_ui_get_path,
    read_json_request_body,
    register_deployed_contract,
    run_contract_scan,
    run_agent_request,
    update_wallet_prompt_state,
)
from UI.utils.info_panel import build_request_info_events
from utils.prompts import get_current_level, get_level_label
from agents.BlockchainAgent.plugin.activity_logger_plugin import log_activity

load_src_env(SRC_DIR)

UI_DIR = Path(__file__).resolve().parent
HOST = os.getenv("UI_HOST", "127.0.0.1")
PORT = int(os.getenv("UI_PORT", "8080"))

_CHAT_REQUEST_LOCK = threading.Lock()
_ASYNC_RUNNER_LOCK = threading.Lock()
_ASYNC_RUNNER: asyncio.Runner | None = None


def _get_async_runner() -> asyncio.Runner:
    """Return a process-wide asyncio runner bound to one persistent loop."""
    global _ASYNC_RUNNER
    with _ASYNC_RUNNER_LOCK:
        if _ASYNC_RUNNER is None:
            _ASYNC_RUNNER = asyncio.Runner()
        return _ASYNC_RUNNER


def _close_async_runner() -> None:
    """Close the shared asyncio runner used by UI requests."""
    global _ASYNC_RUNNER
    with _ASYNC_RUNNER_LOCK:
        runner = _ASYNC_RUNNER
        _ASYNC_RUNNER = None
    if runner is not None:
        runner.close()


def _run_async(coro: Any, *, timeout: float | None = None) -> Any:
    runner = _get_async_runner()
    if timeout is not None:
        return runner.run(asyncio.wait_for(coro, timeout=timeout))
    return runner.run(coro)


def _format_exception_trace(exc: Exception) -> str:
    """Return full traceback text, including nested ExceptionGroup details."""
    try:
        return "".join(traceback.TracebackException.from_exception(exc).format())
    except Exception:
        return traceback.format_exc()


def _collect_exception_messages(exc: BaseException) -> list[str]:
    """Collect exception messages from causes, contexts, and ExceptionGroup leaves."""
    collected: list[str] = []
    seen_nodes: set[int] = set()
    seen_messages: set[str] = set()

    def _walk(current: BaseException | None) -> None:
        if current is None:
            return

        node_id = id(current)
        if node_id in seen_nodes:
            return
        seen_nodes.add(node_id)

        message = f"{type(current).__name__}: {current}".strip()
        if message and message not in seen_messages:
            seen_messages.add(message)
            collected.append(message)

        sub_exceptions = getattr(current, "exceptions", None)
        if sub_exceptions:
            for sub in sub_exceptions:
                if isinstance(sub, BaseException):
                    _walk(sub)

        cause = getattr(current, "__cause__", None)
        if isinstance(cause, BaseException):
            _walk(cause)

        context = getattr(current, "__context__", None)
        if isinstance(context, BaseException):
            _walk(context)

    _walk(exc)
    return collected


def _build_detailed_error_message(exc: BaseException) -> tuple[str, list[str]]:
    """Build a compact detailed error and expose root-cause messages."""
    messages = _collect_exception_messages(exc)
    if not messages:
        return str(exc), []
    if len(messages) == 1:
        return messages[0], messages

    max_roots_in_summary = 3
    roots_preview = "; ".join(messages[1 : 1 + max_roots_in_summary])
    remaining = len(messages) - 1 - max_roots_in_summary
    suffix = f"; +{remaining} more" if remaining > 0 else ""
    summary = f"{messages[0]} | root causes: {roots_preview}{suffix}"
    return summary, messages


class UIRequestHandler(SimpleHTTPRequestHandler):
    """Minimal HTTP handler for static assets and JSON endpoints."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # Client closed the connection before receiving the response.
            return

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/knowledge-level":
            self._handle_knowledge_level()
            return

        if self.path.startswith("/reports/"):
            self._handle_report_download()
            return

        self.path = normalize_ui_get_path(self.path)
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/wallet-state":
            self._handle_wallet_state_update()
            return

        if self.path == "/api/deploy-contract":
            self._handle_deploy_contract()
            return

        if self.path == "/api/register-deployed-contract":
            self._handle_register_deployed_contract()
            return

        if self.path == "/api/scan-contract":
            self._handle_scan_contract()
            return

        if self.path != "/api/chat":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Endpoint not found"})
            return

        try:
            body = read_json_request_body(self)

            message = str(body.get("message", "")).strip()
            wallet = body.get("wallet") if isinstance(body.get("wallet"), dict) else None
            request_id = str(uuid4())

            if not message:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "message is required"})
                return

            with _CHAT_REQUEST_LOCK:
                run_result = _run_async(
                    run_agent_request(
                        message,
                        wallet,
                        request_id,
                        runner=runner,
                        ensure_session=ensure_session,
                        user_id=USER_ID,
                        session_id=DEFAULT_SESSION_ID,
                    ),
                    timeout=60,
                )

            response_text = str(run_result.get("reply") or "")
            invocation_id = run_result.get("invocationId")
            info_events = build_request_info_events(
                request_id=request_id,
                invocation_id=str(invocation_id) if invocation_id else None,
            )
            self._send_json(
                HTTPStatus.OK,
                {
                    "reply": response_text,
                    "requestId": request_id,
                    "infoEvents": info_events,
                },
            )
        except TimeoutError:
            log_activity(
                "request_error",
                {
                    "error": "timeout",
                    "endpoint": "/api/chat",
                },
            )
            self._send_json(
                HTTPStatus.GATEWAY_TIMEOUT,
                {"error": "The root agent took too long to respond. Please retry."},
            )
        except Exception as exc:
            error_trace = _format_exception_trace(exc)
            detailed_error, root_causes = _build_detailed_error_message(exc)

            log_activity(
                "request_error",
                {
                    "error": str(exc),
                    "detailed_error": detailed_error,
                    "root_causes": root_causes,
                    "traceback": error_trace,
                    "endpoint": "/api/chat",
                },
            )
            message = str(exc)
            if "Missing Anthropic API Key" in message:
                self._send_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {
                        "error": "Missing ANTHROPIC_API_KEY. Set it in src/.env before using chat.",
                    },
                )
                return
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": detailed_error,
                    "details": root_causes,
                },
            )

    def _handle_scan_contract(self) -> None:
        try:
            body = read_json_request_body(self)

            file_name = str(body.get("fileName", "")).strip()
            source = str(body.get("source", ""))
            contract_name = str(body.get("contractName", "")).strip() or None

            if not file_name or not file_name.lower().endswith(".sol"):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "fileName must be a .sol file"})
                return
            if not source.strip():
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "source is required"})
                return

            result = _run_async(
                run_contract_scan(file_name=file_name, source=source, contract_name=contract_name),
                timeout=130,
            )
            if result.get("error"):
                self._send_json(HTTPStatus.BAD_GATEWAY, result)
                return

            log_activity(
                "scan_contract_completed",
                {
                    "fileName": file_name,
                    "contractName": contract_name,
                    "reportFileName": result.get("reportFileName"),
                    "source": result.get("source"),
                },
            )
            self._send_json(HTTPStatus.OK, result)
        except Exception as exc:
            log_activity(
                "scan_contract_error",
                {
                    "error": str(exc),
                    "endpoint": "/api/scan-contract",
                },
            )
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def _handle_report_download(self) -> None:
        reports_dir = (SRC_DIR.parent / ".reports").resolve()
        relative = unquote(self.path[len("/reports/") :])
        target = (reports_dir / relative).resolve()

        if reports_dir not in target.parents and target != reports_dir:
            self.send_error(HTTPStatus.FORBIDDEN, "Invalid report path")
            return
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Report not found")
            return

        try:
            data = target.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return

    def _handle_wallet_state_update(self) -> None:
        try:
            body = read_json_request_body(self)
            wallet = body.get("wallet") if isinstance(body.get("wallet"), dict) else {}
            update_wallet_prompt_state(wallet, root_agent)
            self._send_json(HTTPStatus.OK, {"ok": True, "updated": True})
        except Exception as exc:  # pragma: no cover - best effort API guard
            log_activity(
                "wallet_state_error",
                {
                    "error": str(exc),
                    "endpoint": "/api/wallet-state",
                },
            )
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def _handle_knowledge_level(self) -> None:
        try:
            session = _run_async(
                ensure_session(user_id=USER_ID, session_id=DEFAULT_SESSION_ID),
                timeout=10,
            )
            level = normalize_level(session.state.get(KNOWLEDGE_LEVEL_STATE_KEY))
            if level == DEFAULT_LEVEL:
                level = normalize_level(get_current_level())

            self._send_json(
                HTTPStatus.OK,
                {
                    "level": level,
                    "label": get_level_label(level),
                },
            )
        except Exception as exc:
            log_activity(
                "knowledge_level_error",
                {
                    "error": str(exc),
                    "endpoint": "/api/knowledge-level",
                },
            )
            self._send_json(
                HTTPStatus.OK,
                {
                    "level": DEFAULT_LEVEL,
                    "label": get_level_label(DEFAULT_LEVEL),
                    "error": str(exc),
                },
            )

    def _handle_deploy_contract(self) -> None:
        try:
            body = read_json_request_body(self)

            file_name = str(body.get("fileName", "")).strip()
            source = str(body.get("source", ""))
            contract_name = body.get("contractName")
            network_name = body.get("networkName")

            if not file_name or not file_name.lower().endswith(".sol"):
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "fileName must be a .sol file"})
                return
            if not source.strip():
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "source is required"})
                return

            deploy_payload = compile_contract_for_deploy(
                file_name=file_name,
                source=source,
                requested_contract_name=str(contract_name).strip() if contract_name else None,
                network_name=str(network_name).strip() if network_name else None,
            )

            log_activity(
                "deploy_contract_prepared",
                {
                    "fileName": file_name,
                    "contractName": deploy_payload["deployData"].get("contractName"),
                    "networkName": deploy_payload["deployData"].get("networkName"),
                    "chainId": deploy_payload["deployData"].get("chainId"),
                },
            )
            self._send_json(HTTPStatus.OK, deploy_payload)
        except Exception as exc:
            log_activity(
                "deploy_contract_error",
                {
                    "error": str(exc),
                    "endpoint": "/api/deploy-contract",
                },
            )
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def _handle_register_deployed_contract(self) -> None:
        try:
            body = read_json_request_body(self)
            payload = register_deployed_contract(body, SRC_DIR)
            self._send_json(HTTPStatus.OK, payload)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:
            log_activity(
                "register_deployed_contract_error",
                {
                    "error": str(exc),
                    "endpoint": "/api/register-deployed-contract",
                },
            )
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})


def main() -> None:
    project_root = SRC_DIR.parent
    expected_python = project_root / ".venv" / "Scripts" / "python.exe"
    if not expected_python.exists():
        expected_python = project_root / ".venv" / "bin" / "python"

    if expected_python.exists():
        current_python = Path(sys.executable).resolve()
        if current_python != expected_python.resolve():
            raise RuntimeError(
                "UI server must run with project virtualenv interpreter. "
                f"Current: {current_python} | Expected: {expected_python.resolve()}"
            )

    server = HTTPServer((HOST, PORT), UIRequestHandler)
    print(f"BlockchainAgentADK UI available at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _close_async_runner()
        close_mcp_toolsets()


if __name__ == "__main__":
    main()
