"""Parallel execution engine for independent tool calls.

Provides concurrent execution of READ/QUERY tools, serial execution of WRITE
tools, and conditional parallelization of EXEC tools based on path analysis.
Includes retry with exponential backoff, fuzzy parameter repair, and recovery
injection before retries.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .tool_dependency import (
    ExecutionLayer,
    ToolCallRef,
    ToolCategory,
    analyze_tool_calls,
    classify_tool,
)

logger = logging.getLogger(__name__)


_MAX_CONCURRENT_WORKERS = int(os.getenv("OCTOAGENT_MAX_WORKERS", "8"))
_PER_TOOL_TIMEOUT = float(os.getenv("OCTOAGENT_PER_TOOL_TIMEOUT", "30"))
_TOTAL_BATCH_TIMEOUT = float(os.getenv("OCTOAGENT_TOTAL_BATCH_TIMEOUT", "120"))
_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5


@dataclass
class CallResult:
    index: int
    tool_name: str
    args: dict[str, Any]
    result: Any | None
    error: str | None
    attempts: int = 1
    duration_ms: float = 0.0
    repaired: bool = False
    recovery_injected: bool = False


@dataclass
class ParallelExecutorConfig:
    max_workers: int = _MAX_CONCURRENT_WORKERS
    per_tool_timeout: float = _PER_TOOL_TIMEOUT
    total_batch_timeout: float = _TOTAL_BATCH_TIMEOUT
    max_retries: int = _MAX_RETRIES
    backoff_base: float = _BACKOFF_BASE


_FILE_PATH_LOCKS: dict[str, asyncio.Lock] = {}
_LOCKS_MUTEX: asyncio.Lock | None = None


def _get_file_lock(path: str) -> asyncio.Lock:
    global _LOCKS_MUTEX
    if _LOCKS_MUTEX is None:
        _LOCKS_MUTEX = asyncio.Lock()
    normalized = path.replace("\\", "/").rstrip("/")
    if normalized not in _FILE_PATH_LOCKS:
        lock = getattr(asyncio, "Lock", None)
        if lock is not None:
            _FILE_PATH_LOCKS[normalized] = lock()
        else:
            _FILE_PATH_LOCKS[normalized] = asyncio.Lock()
    return _FILE_PATH_LOCKS[normalized]


_ERROR_PARAM_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'["\']([^"\']*?)["\']', re.IGNORECASE), "param_value"),
    (re.compile(r"path[s]?[\s:=]+['\"]?([^\s'\"]+)", re.IGNORECASE), "path_value"),
    (re.compile(r"file[\s:=]+['\"]?([^\s'\"]+)", re.IGNORECASE), "file_value"),
    (re.compile(r"url[\s:=]+['\"]?([^\s'\"]+)", re.IGNORECASE), "url_value"),
]


def _extract_error_params(error_msg: str) -> dict[str, str]:
    params: dict[str, str] = {}
    for pattern, key in _ERROR_PARAM_PATTERNS:
        match = pattern.search(error_msg)
        if match and key not in params:
            params[key] = match.group(1).strip()
    return params


def _fuzzy_repair_args(tool_name: str, args: dict[str, Any], error_msg: str) -> tuple[dict[str, Any], bool]:
    repaired_args = dict(args)
    repaired = False
    error_lower = error_msg.lower()

    if "not found" in error_lower or "does not exist" in error_lower or "no such file" in error_lower:
        for key, value in list(repaired_args.items()):
            if isinstance(value, str):
                stripped = value.strip().strip("'\"")
                if "/" in stripped or "\\" in stripped:
                    alt_value = stripped.replace(" ", "\\ ").replace("(", "\\(").replace(")", "\\)")
                    if alt_value != stripped and alt_value not in repaired_args.values():
                        repaired_args[key] = alt_value
                        repaired = True

    if "permission" in error_lower or "access denied" in error_lower:
        for key, value in list(repaired_args.items()):
            if isinstance(value, str) and ("sudo" not in value.lower()[:20]):
                if key == "command":
                    repaired_args[key] = f"sudo {value}"
                    repaired = True

    if "timeout" in error_lower or "timed out" in error_lower:
        for key, value in list(repaired_args.items()):
            if isinstance(value, str) and ("--timeout" not in value):
                if "--max-time" not in value and "-m" not in value:
                    repaired_args[key] = f"{value} --max-time 60"
                    repaired = True

    return repaired_args, repaired


_DIAGNOSTIC_TOOLS: dict[str, str] = {
    "file_write": "ls -la",
    "code_edit": "pwd",
    "create_file": "ls -la $(dirname ",
    "update_file": "cat ",
    "shell_exec": "echo 'diagnostic context'",
    "run_command": "echo 'diagnostic context'",
    "file_read": "ls -la ",
    "grep": "find . -name ",
}


def _build_recovery_call(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    diag_cmd = _DIAGNOSTIC_TOOLS.get(tool_name, "echo 'diagnostic'")
    recovery_args: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str) and len(value) > 50:
            recovery_args[key] = value[:50] + "..."
        else:
            recovery_args[key] = value
    if tool_name in ("file_write", "code_edit", "create_file"):
        for key, value in list(recovery_args.items()):
            if isinstance(value, str) and ("/" in value or "\\" in value):
                dirname_match = re.search(r"(.*/)[^/]+$", value)
                if dirname_match:
                    recovery_args["diagnostic_path"] = f"{dirname_match.group(1)}"
    return {
        "tool": "shell_exec",
        "args": {"command": diag_cmd},
        "_recovery_injected": True,
    }


class ParallelExecutor:
    """Execute independent tool calls concurrently with safety guards."""

    def __init__(self, config: ParallelExecutorConfig | None = None):
        self._config = config or ParallelExecutorConfig()
        self._semaphore: asyncio.Semaphore | None = None

    @property
    def max_workers(self) -> int:
        return self._config.max_workers

    async def _ensure_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._config.max_workers)
        return self._semaphore

    def analyze_dependencies(self, tool_calls: list[dict[str, Any]]) -> list[ExecutionLayer]:
        return analyze_tool_calls(tool_calls)

    async def execute_batch(
        self,
        tool_calls: list[dict[str, Any]],
        executor_fn: Callable[[dict[str, Any]], Any],
    ) -> list[CallResult]:
        if not tool_calls:
            return []

        layers = self.analyze_dependencies(tool_calls)
        results: list[CallResult | None] = [None] * len(tool_calls)
        start_time = time.monotonic()

        for layer in layers:
            elapsed = time.monotonic() - start_time
            if elapsed >= self._config.total_batch_timeout:
                for i, call in enumerate(tool_calls):
                    if results[i] is None:
                        results[i] = CallResult(
                            index=i,
                            tool_name=str(call.get("tool", call.get("name", ""))),
                            args=dict(call.get("args", call.get("parameters", {})) or {}),
                            result=None,
                            error=f"Batch timeout exceeded ({self._config.total_batch_timeout}s)",
                        )
                break

            serial_calls = [c for c in layer.calls if c.category == classify_tool(c.tool_name) and c.category.value == "write"]
            parallel_candidates = [c for c in layer.calls if c.category != ToolCategory.WRITE]

            if serial_calls:
                for call_ref in serial_calls:
                    result = await self._execute_with_retry(call_ref, executor_fn, start_time)
                    results[call_ref.index] = result

            if parallel_candidates:
                layer_results = await self._execute_parallel_group(parallel_candidates, executor_fn, start_time)
                for i, result in enumerate(layer_results):
                    if result is not None:
                        results[parallel_candidates[i].index] = result

        return [r for r in results if r is not None]

    async def _execute_with_retry(
        self,
        call_ref: ToolCallRef,
        executor_fn: Callable[[dict[str, Any]], Any],
        batch_start_time: float,
    ) -> CallResult:
        attempts = 0
        last_error: str | None = None
        current_args = dict(call_ref.args)

        for attempt in range(1, self._config.max_retries + 1):
            attempts = attempt
            elapsed = time.monotonic() - batch_start_time
            if elapsed >= self._config.total_batch_timeout:
                return CallResult(
                    index=call_ref.index,
                    tool_name=call_ref.tool_name,
                    args=current_args,
                    result=None,
                    error=f"Batch timeout exceeded ({self._config.total_batch_timeout}s)",
                    attempts=attempts,
                )

            call_dict = {"tool": call_ref.tool_name, "args": current_args}
            attempt_start = time.monotonic()

            try:
                result = await asyncio.wait_for(
                    executor_fn(call_dict),
                    timeout=self._config.per_tool_timeout,
                )
                duration_ms = (time.monotonic() - attempt_start) * 1000
                return CallResult(
                    index=call_ref.index,
                    tool_name=call_ref.tool_name,
                    args=current_args,
                    result=result,
                    error=None,
                    attempts=attempts,
                    duration_ms=duration_ms,
                )
            except TimeoutError:
                last_error = f"Tool '{call_ref.tool_name}' timed out after {self._config.per_tool_timeout}s"
                logger.warning(last_error)
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.debug(f"Tool call failed (attempt {attempt}): {last_error}")

            if attempt < self._config.max_retries:
                backoff = self._config.backoff_base * (2 ** (attempt - 1))
                await asyncio.sleep(min(backoff, 5.0))

            if last_error and "timed out" not in last_error.lower():
                current_args, was_repaired = _fuzzy_repair_args(call_ref.tool_name, current_args, last_error)
                if was_repaired:
                    logger.info(f"Fuzzy repair applied to '{call_ref.tool_name}': adjusted args based on error: {last_error[:200]}")

            if last_error and attempt < self._config.max_retries - 1:
                recovery_call = _build_recovery_call(call_ref.tool_name, current_args)
                try:
                    await asyncio.wait_for(
                        executor_fn(recovery_call),
                        timeout=self._config.per_tool_timeout,
                    )
                except Exception as rec_exc:
                    logger.debug(f"Recovery diagnostic failed: {rec_exc}")

        return CallResult(
            index=call_ref.index,
            tool_name=call_ref.tool_name,
            args=current_args,
            result=None,
            error=last_error or "Unknown failure",
            attempts=attempts,
            repaired=True if last_error and "timed out" not in (last_error or "").lower() else False,
        )

    async def _execute_parallel_group(
        self,
        call_refs: list[ToolCallRef],
        executor_fn: Callable[[dict[str, Any]], Any],
        batch_start_time: float,
    ) -> list[CallResult | None]:
        semaphore = await self._ensure_semaphore()
        results: list[CallResult | None] = [None] * len(call_refs)

        path_locks: dict[str, asyncio.Lock] = {}
        for ref in call_refs:
            if ref.category == ToolCategory.WRITE:
                for p in ref.paths:
                    lock = _get_file_lock(p)
                    path_locks[p] = lock

        async def _run_with_lock(ref_idx: int, ref: ToolCallRef) -> CallResult | None:
            relevant_locks: list[asyncio.Lock] = []
            if ref.category == ToolCategory.WRITE:
                for p in ref.paths:
                    if p in path_locks:
                        relevant_locks.append(path_locks[p])

            async with semaphore:
                if relevant_locks:
                    async with asyncio.TaskGroup() as tg:
                        for lock in relevant_locks:
                            tg.create_task(lock.acquire())
                try:
                    result = await self._execute_with_retry(ref, executor_fn, batch_start_time)
                    return result
                finally:
                    if relevant_locks:
                        for lock in relevant_locks:
                            lock.release()

        tasks = [_run_with_lock(i, ref) for i, ref in enumerate(call_refs)]
        completed_results = await asyncio.gather(*tasks)

        for i, result in enumerate(completed_results):
            if result is not None:
                results[i] = result

        return results

    def handle_failure(self, call_result: CallResult) -> dict[str, Any]:
        if call_result.error is None:
            return {"action": "none", "reason": "no_error"}

        error_lower = (call_result.error or "").lower()
        if any(marker in error_lower for marker in ("timed out", "timeout")):
            return {
                "action": "retry_with_timeout_increase",
                "error": call_result.error,
                "attempts": call_result.attempts,
                "suggestion": "increase per-tool timeout or simplify command",
            }

        if any(marker in error_lower for marker in ("not found", "does not exist", "no such")):
            return {
                "action": "retry_with_path_check",
                "error": call_result.error,
                "attempts": call_result.attempts,
                "suggestion": "verify path exists before retrying",
            }

        if any(marker in error_lower for marker in ("permission", "access denied", "forbidden")):
            return {
                "action": "retry_with_sudo",
                "error": call_result.error,
                "attempts": call_result.attempts,
                "suggestion": "try with elevated permissions or different approach",
            }

        if call_result.repaired:
            return {
                "action": "retry_repaired",
                "error": call_result.error,
                "attempts": call_result.attempts,
                "suggestion": "retried with fuzzy-repaired parameters",
            }

        return {
            "action": "mark_failed",
            "error": call_result.error,
            "attempts": call_result.attempts,
            "suggestion": "no recovery strategy matched; mark as failed",
        }


__all__ = [
    "CallResult",
    "ParallelExecutor",
    "ParallelExecutorConfig",
]
