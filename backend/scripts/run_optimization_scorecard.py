from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.storage.optimization import OptimizationProgram, get_optimization_program


@dataclass
class CommandPolicy:
    run_tests: bool = True
    run_build: bool = True
    run_smoke: bool = True
    simulate_success: bool = False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _line_count(path: Path) -> int:
    text = _read_text(path)
    if not text:
        return 0
    return text.count("\n") if text.endswith("\n") else text.count("\n") + 1


def _path_exists(repo_root: Path, relative_path: str) -> bool:
    return (repo_root / relative_path).exists()


def _collect_relevant_directories(repo_root: Path, program: OptimizationProgram) -> list[str]:
    relevant: set[str] = set()

    top_level_targets = [
        ".agents",
        ".github",
        ".superdesign",
        ".tools",
        ".vscode",
        "deploy",
        "desktop",
        "docker",
        "docs",
        "plan",
        "project_docs",
        "references",
        "scripts",
        "skills",
    ]
    for item in top_level_targets:
        if (repo_root / item).exists():
            relevant.add(item)

    for child in (repo_root / "backend" / "src").iterdir():
        if child.is_dir():
            relevant.add(str(child.relative_to(repo_root)))
    for child in [repo_root / "backend" / "tests", repo_root / "backend" / "scripts"]:
        if child.exists():
            relevant.add(str(child.relative_to(repo_root)))

    for child in (repo_root / "frontend" / "src").iterdir():
        if child.is_dir():
            relevant.add(str(child.relative_to(repo_root)))
    for child in [repo_root / "frontend" / "public", repo_root / "frontend" / "scripts"]:
        if child.exists():
            relevant.add(str(child.relative_to(repo_root)))

    excluded = set(program.excluded_paths)
    return sorted(path for path in relevant if path not in excluded)


def _is_covered(path: str, declared_paths: set[str], excluded_paths: set[str]) -> bool:
    if path in excluded_paths:
        return True
    for declared in declared_paths:
        if path == declared or path.startswith(f"{declared}/"):
            return True
    return False


def _coverage_summary(repo_root: Path, program: OptimizationProgram) -> dict[str, Any]:
    declared_paths = {owned_path for area in program.coverage_areas for owned_path in area.owned_paths if not owned_path.endswith(".py") and not owned_path.endswith(".js")}
    excluded_paths = set(program.excluded_paths)
    actual_paths = _collect_relevant_directories(repo_root, program)
    uncovered_paths = [path for path in actual_paths if not _is_covered(path, declared_paths, excluded_paths)]
    return {
        "declared_paths": sorted(declared_paths),
        "actual_paths": actual_paths,
        "excluded_paths": sorted(excluded_paths),
        "uncovered_paths": uncovered_paths,
        "coverage_areas": [area.model_dump() for area in program.coverage_areas],
    }


def _should_execute(stage: str, policy: CommandPolicy) -> bool:
    if stage == "test":
        return policy.run_tests
    if stage == "build":
        return policy.run_build
    if stage == "smoke":
        return policy.run_smoke
    return False


def _run_command(command: str, repo_root: Path, timeout: int = 900) -> dict[str, Any]:
    started_at = time.time()
    completed = subprocess.run(
        shlex.split(command),
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "passed": completed.returncode == 0,
        "duration_seconds": round(time.time() - started_at, 3),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def _verification_results(repo_root: Path, program: OptimizationProgram, policy: CommandPolicy) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for verification in program.verification_commands:
        if verification.command_id == "scorecard":
            continue
        execute = _should_execute(verification.stage, policy)
        if policy.simulate_success:
            results[verification.command_id] = {
                "command": verification.command,
                "stage": verification.stage,
                "executed": False,
                "simulated": True,
                "passed": True,
                "returncode": 0,
                "duration_seconds": 0.0,
                "stdout_tail": "",
                "stderr_tail": "",
            }
            continue
        if not execute:
            results[verification.command_id] = {
                "command": verification.command,
                "stage": verification.stage,
                "executed": False,
                "simulated": False,
                "passed": False,
                "returncode": None,
                "duration_seconds": 0.0,
                "stdout_tail": "",
                "stderr_tail": "",
            }
            continue
        command_result = _run_command(verification.command, repo_root)
        results[verification.command_id] = {
            **command_result,
            "stage": verification.stage,
            "executed": True,
            "simulated": False,
        }
    return results


def _runtime_latency_benchmark_result(repo_root: Path, policy: CommandPolicy) -> dict[str, Any]:
    command = [
        sys.executable,
        "backend/scripts/run_runtime_latency_benchmark.py",
        "--base-url",
        "http://127.0.0.1:19880",
        "--rounds",
        "5",
        "--format",
        "json",
    ]
    command_text = shlex.join(command)

    if policy.simulate_success:
        return {
            "command": command_text,
            "stage": "smoke",
            "executed": False,
            "simulated": True,
            "passed": True,
            "returncode": 0,
            "duration_seconds": 0.0,
            "stdout_tail": "",
            "stderr_tail": "",
            "report": None,
        }

    if not policy.run_smoke:
        return {
            "command": command_text,
            "stage": "smoke",
            "executed": False,
            "simulated": False,
            "passed": False,
            "returncode": None,
            "duration_seconds": 0.0,
            "stdout_tail": "",
            "stderr_tail": "",
            "report": None,
        }

    started_at = time.time()
    completed = subprocess.run(
        command,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    report: dict[str, Any] | None = None
    if completed.returncode == 0:
        try:
            report = json.loads(completed.stdout)
        except json.JSONDecodeError:
            report = None

    return {
        "command": command_text,
        "stage": "smoke",
        "executed": True,
        "simulated": False,
        "passed": completed.returncode == 0 and report is not None,
        "returncode": completed.returncode,
        "duration_seconds": round(time.time() - started_at, 3),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "report": report,
    }


def _runtime_latency_metric(verification_results: dict[str, dict[str, Any]]) -> float | None:
    benchmark_result = verification_results.get("runtime-latency-benchmark", {})
    if not benchmark_result or benchmark_result.get("simulated"):
        return None

    report = benchmark_result.get("report")
    if not isinstance(report, dict):
        return None

    overall = report.get("overall")
    if not isinstance(overall, dict):
        return None

    metric_value = overall.get("overall_p95_ms")
    if isinstance(metric_value, (int, float)):
        return round(float(metric_value), 3)
    return None


def _runtime_truth_score(repo_root: Path) -> tuple[int, list[dict[str, Any]]]:
    execution_path = repo_root / "backend" / "src" / "task_workspaces" / "execution.py"
    router_path = repo_root / "backend" / "src" / "gateway" / "routers" / "task_workspaces.py"
    workflow_service_path = repo_root / "backend" / "src" / "workflow_core" / "service.py"
    execution_text = _read_text(execution_path)
    workflow_service_text = _read_text(workflow_service_path)
    execution_loc = _line_count(execution_path)
    router_loc = _line_count(router_path)

    checks: list[dict[str, Any]] = []
    score = 0

    core_paths_ready = all(
        _path_exists(repo_root, relative)
        for relative in [
            "backend/src/workflow_core",
            "backend/src/task_workspaces",
            "backend/src/agent_core",
        ]
    )
    checks.append(
        {
            "check": "runtime core directories exist",
            "passed": core_paths_ready,
            "points_awarded": 4 if core_paths_ready else 0,
            "points_available": 4,
        }
    )
    score += 4 if core_paths_ready else 0

    controller_contract_ready = (
        "TaskWorkspaceExecutionController" in execution_text and "TaskWorkspaceMessageExecutor" in execution_text and "TaskWorkspaceExecutionController" in workflow_service_text and "TaskWorkspaceMessageExecutor" in workflow_service_text
    )
    checks.append(
        {
            "check": "workflow and task workspace execution controllers are shared",
            "passed": controller_contract_ready,
            "points_awarded": 5 if controller_contract_ready else 0,
            "points_available": 5,
        }
    )
    score += 5 if controller_contract_ready else 0

    execution_points = 0
    if execution_loc <= 750:
        execution_points = 6
    elif execution_loc <= 850:
        execution_points = 5
    elif execution_loc <= 950:
        execution_points = 4
    elif execution_loc <= 1000:
        execution_points = 3
    elif execution_loc <= 1150:
        execution_points = 2
    checks.append(
        {
            "check": "task workspace execution module size",
            "passed": execution_points > 0,
            "points_awarded": execution_points,
            "points_available": 6,
            "evidence": {"line_count": execution_loc},
        }
    )
    score += execution_points

    router_points = 0
    if router_loc <= 450:
        router_points = 5
    elif router_loc <= 550:
        router_points = 4
    elif router_loc <= 650:
        router_points = 3
    elif router_loc <= 800:
        router_points = 2
    elif router_loc <= 1000:
        router_points = 1
    checks.append(
        {
            "check": "task workspace router aggregation size",
            "passed": router_points > 0,
            "points_awarded": router_points,
            "points_available": 5,
            "evidence": {"line_count": router_loc},
        }
    )
    score += router_points
    return score, checks


def _durability_score(repo_root: Path, verification_results: dict[str, dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    score = 0

    execution_modules = all(
        _path_exists(repo_root, relative)
        for relative in [
            "backend/src/task_workspaces/execution.py",
            "backend/src/task_workspaces/runtime_state.py",
            "backend/src/studio_runtime/builder.py",
        ]
    )
    score += 5 if execution_modules else 0
    checks.append(
        {
            "check": "task workspace execution and lifecycle modules exist",
            "passed": execution_modules,
            "points_awarded": 5 if execution_modules else 0,
            "points_available": 5,
        }
    )

    store_modules = all(
        _path_exists(repo_root, relative)
        for relative in [
            "backend/src/workflow_core/store.py",
            "backend/src/workflow_core/lifecycle.py",
        ]
    )
    score += 3 if store_modules else 0
    checks.append(
        {
            "check": "workflow store and lifecycle modules exist",
            "passed": store_modules,
            "points_awarded": 3 if store_modules else 0,
            "points_available": 3,
        }
    )

    smoke_result = verification_results.get("live-webui-smoke", {})
    smoke_passed = bool(smoke_result.get("passed"))
    score += 3 if smoke_passed else 0
    checks.append(
        {
            "check": "live WebUI smoke passes",
            "passed": smoke_passed,
            "points_awarded": 3 if smoke_passed else 0,
            "points_available": 3,
        }
    )

    recovery_modules = all(
        _path_exists(repo_root, relative)
        for relative in [
            "backend/src/agents/middlewares/session_compaction_middleware.py",
            "backend/src/agents/checkpointer",
        ]
    )
    score += 4 if recovery_modules else 0
    checks.append(
        {
            "check": "durability and recovery implementation modules exist",
            "passed": recovery_modules,
            "points_awarded": 4 if recovery_modules else 0,
            "points_available": 4,
        }
    )
    return score, checks


def _capability_governance_score(repo_root: Path) -> tuple[int, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    score = 0

    core_dirs = all(_path_exists(repo_root, relative) for relative in ["backend/src/capability_core", "backend/src/hook_core"])
    score += 3 if core_dirs else 0
    checks.append(
        {
            "check": "capability_core and hook_core exist",
            "passed": core_dirs,
            "points_awarded": 3 if core_dirs else 0,
            "points_available": 3,
        }
    )

    integration_dirs = all(
        _path_exists(repo_root, relative)
        for relative in [
            "backend/src/plugins",
            "backend/src/mcp",
            "backend/src/channels",
            "backend/src/tools_registry",
        ]
    )
    score += 2 if integration_dirs else 0
    checks.append(
        {
            "check": "plugins, mcp, channels, and tools_registry exist",
            "passed": integration_dirs,
            "points_awarded": 2 if integration_dirs else 0,
            "points_available": 2,
        }
    )

    capability_impl = all(
        _path_exists(repo_root, relative)
        for relative in [
            "backend/src/capability_core/service.py",
            "backend/src/gateway/routers/capabilities.py",
            "backend/src/hook_core/service.py",
            "backend/src/capability_core/registry.py",
        ]
    )
    score += 9 if capability_impl else 0
    checks.append(
        {
            "check": "capability, hook, registry, and router implementations exist",
            "passed": capability_impl,
            "points_awarded": 9 if capability_impl else 0,
            "points_available": 9,
        }
    )
    return score, checks


def _frontend_state_score(repo_root: Path, verification_results: dict[str, dict[str, Any]]) -> tuple[int, list[dict[str, Any]], int]:
    checks: list[dict[str, Any]] = []
    score = 0
    board_path = repo_root / "frontend" / "src" / "components" / "workspace" / "task-workspace-board.tsx"
    board_loc = _line_count(board_path)

    board_points = 0
    if board_loc <= 1500:
        board_points = 4
    elif board_loc <= 1850:
        board_points = 2
    elif board_loc <= 2200:
        board_points = 1
    score += board_points
    checks.append(
        {
            "check": "task workspace board complexity threshold",
            "passed": board_points > 0,
            "points_awarded": board_points,
            "points_available": 4,
            "evidence": {"line_count": board_loc},
        }
    )

    core_contract_paths = all(
        _path_exists(repo_root, relative)
        for relative in [
            "frontend/src/core/task-workspaces",
            "frontend/src/core",
            "frontend/src/hooks",
        ]
    )
    score += 2 if core_contract_paths else 0
    checks.append(
        {
            "check": "frontend core state directories exist",
            "passed": core_contract_paths,
            "points_awarded": 2 if core_contract_paths else 0,
            "points_available": 2,
        }
    )

    build_result = verification_results.get("frontend-build", {})
    build_passed = bool(build_result.get("passed"))
    score += 2 if build_passed else 0
    checks.append(
        {
            "check": "frontend build passes",
            "passed": build_passed,
            "points_awarded": 2 if build_passed else 0,
            "points_available": 2,
        }
    )

    workspace_routes = _path_exists(repo_root, "frontend/src/app/workspace")
    score += 2 if workspace_routes else 0
    checks.append(
        {
            "check": "workspace routes exist",
            "passed": workspace_routes,
            "points_awarded": 2 if workspace_routes else 0,
            "points_available": 2,
        }
    )
    return score, checks, board_loc


def _test_release_gate_score(repo_root: Path, verification_results: dict[str, dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    score = 0

    compile_passed = bool(verification_results.get("backend-compile", {}).get("passed"))
    score += 5 if compile_passed else 0
    checks.append(
        {
            "check": "backend compile gate passes",
            "passed": compile_passed,
            "points_awarded": 5 if compile_passed else 0,
            "points_available": 5,
        }
    )

    build_passed = bool(verification_results.get("frontend-build", {}).get("passed"))
    score += 5 if build_passed else 0
    checks.append(
        {
            "check": "frontend build gate passes",
            "passed": build_passed,
            "points_awarded": 5 if build_passed else 0,
            "points_available": 5,
        }
    )

    smoke_passed = bool(verification_results.get("live-webui-smoke", {}).get("passed"))
    score += 1 if smoke_passed else 0
    checks.append(
        {
            "check": "real WebUI smoke passes",
            "passed": smoke_passed,
            "points_awarded": 1 if smoke_passed else 0,
            "points_available": 1,
        }
    )

    typecheck_passed = bool(verification_results.get("frontend-typecheck", {}).get("passed"))
    score += 4 if typecheck_passed else 0
    checks.append(
        {
            "check": "frontend typecheck gate passes",
            "passed": typecheck_passed,
            "points_awarded": 4 if typecheck_passed else 0,
            "points_available": 4,
        }
    )
    return score, checks


def _performance_score(repo_root: Path) -> tuple[int, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    score = 0

    evaluation_metrics = _path_exists(repo_root, "backend/src/evaluation/metrics.py")
    score += 2 if evaluation_metrics else 0
    checks.append(
        {
            "check": "evaluation metrics module exists",
            "passed": evaluation_metrics,
            "points_awarded": 2 if evaluation_metrics else 0,
            "points_available": 2,
        }
    )

    provider_benchmark = _path_exists(repo_root, "backend/scripts/benchmark_providers.py")
    score += 1 if provider_benchmark else 0
    checks.append(
        {
            "check": "provider benchmark script exists",
            "passed": provider_benchmark,
            "points_awarded": 1 if provider_benchmark else 0,
            "points_available": 1,
        }
    )

    metrics_router = _path_exists(repo_root, "backend/src/gateway/routers/metrics.py")
    score += 1 if metrics_router else 0
    checks.append(
        {
            "check": "metrics router exists",
            "passed": metrics_router,
            "points_awarded": 1 if metrics_router else 0,
            "points_available": 1,
        }
    )

    monitoring_registry = _path_exists(repo_root, "backend/src/monitoring/__init__.py")
    score += 1 if monitoring_registry else 0
    checks.append(
        {
            "check": "monitoring registry exists",
            "passed": monitoring_registry,
            "points_awarded": 1 if monitoring_registry else 0,
            "points_available": 1,
        }
    )

    runtime_latency_benchmark = _path_exists(repo_root, "backend/scripts/run_runtime_latency_benchmark.py")
    score += 5 if runtime_latency_benchmark else 0
    checks.append(
        {
            "check": "runtime latency benchmark exists",
            "passed": runtime_latency_benchmark,
            "points_awarded": 5 if runtime_latency_benchmark else 0,
            "points_available": 5,
        }
    )
    return score, checks


def _docs_alignment_score(repo_root: Path) -> tuple[int, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    score = 0

    readme_text = _read_text(repo_root / "README.md")
    readme_aligned = "LangGraph-only" in readme_text and "19880" in readme_text
    score += 2 if readme_aligned else 0
    checks.append(
        {
            "check": "root README reflects LangGraph-only and 19880 entrypoint",
            "passed": readme_aligned,
            "points_awarded": 2 if readme_aligned else 0,
            "points_available": 2,
        }
    )

    project_docs_text = _read_text(repo_root / "project_docs" / "README.md")
    project_docs_aligned = "AUTORESEARCH_OPTIMIZATION_PROGRAM" in project_docs_text
    score += 1 if project_docs_aligned else 0
    checks.append(
        {
            "check": "project docs index links the optimization program",
            "passed": project_docs_aligned,
            "points_awarded": 1 if project_docs_aligned else 0,
            "points_available": 1,
        }
    )

    execution_doc_exists = _path_exists(repo_root, "project_docs/docs/OPTIMIZATION_SCORECARD_EXECUTION.md")
    score += 2 if execution_doc_exists else 0
    checks.append(
        {
            "check": "scorecard execution document exists",
            "passed": execution_doc_exists,
            "points_awarded": 2 if execution_doc_exists else 0,
            "points_available": 2,
        }
    )
    return score, checks


def _competitive_score(program: OptimizationProgram, repo_root: Path) -> tuple[int, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    score = 0

    openakita_present = any(item.competitor == "OpenAkita" for item in program.competitor_baselines)
    score += 2 if openakita_present else 0
    checks.append(
        {
            "check": "OpenAkita baseline is represented",
            "passed": openakita_present,
            "points_awarded": 2 if openakita_present else 0,
            "points_available": 2,
        }
    )

    hermes_present = any(item.competitor.startswith("Hermes") for item in program.competitor_baselines)
    score += 2 if hermes_present else 0
    checks.append(
        {
            "check": "Hermes baseline is represented",
            "passed": hermes_present,
            "points_awarded": 2 if hermes_present else 0,
            "points_available": 2,
        }
    )

    elimination_rules_ready = len(program.elimination_rules) >= 5
    score += 2 if elimination_rules_ready else 0
    checks.append(
        {
            "check": "elimination policy has at least five rules",
            "passed": elimination_rules_ready,
            "points_awarded": 2 if elimination_rules_ready else 0,
            "points_available": 2,
        }
    )

    validation_matrix_exists = _path_exists(repo_root, "project_docs/docs/COMPETITIVE_VALIDATION_MATRIX.md")
    score += 2 if validation_matrix_exists else 0
    checks.append(
        {
            "check": "competitive validation matrix exists",
            "passed": validation_matrix_exists,
            "points_awarded": 2 if validation_matrix_exists else 0,
            "points_available": 2,
        }
    )

    latency_benchmark_exists = _path_exists(repo_root, "backend/scripts/run_runtime_latency_benchmark.py")
    score += 2 if latency_benchmark_exists else 0
    checks.append(
        {
            "check": "competitive latency benchmark exists",
            "passed": latency_benchmark_exists,
            "points_awarded": 2 if latency_benchmark_exists else 0,
            "points_available": 2,
        }
    )
    return score, checks


def evaluate_scorecard(repo_root: Path | None = None, policy: CommandPolicy | None = None) -> dict[str, Any]:
    repo_root = repo_root or _repo_root()
    policy = policy or CommandPolicy()
    program = get_optimization_program()
    coverage = _coverage_summary(repo_root, program)
    verification_results = _verification_results(repo_root, program, policy)
    verification_results["runtime-latency-benchmark"] = _runtime_latency_benchmark_result(repo_root, policy)

    runtime_score, runtime_checks = _runtime_truth_score(repo_root)
    durability_score, durability_checks = _durability_score(repo_root, verification_results)
    capability_score, capability_checks = _capability_governance_score(repo_root)
    frontend_score, frontend_checks, board_loc = _frontend_state_score(repo_root, verification_results)
    release_score, release_checks = _test_release_gate_score(repo_root, verification_results)
    performance_score, performance_checks = _performance_score(repo_root)
    docs_score, docs_checks = _docs_alignment_score(repo_root)
    competitive_score, competitive_checks = _competitive_score(program, repo_root)

    score_map = {
        "runtime_truth": (runtime_score, runtime_checks),
        "durability": (durability_score, durability_checks),
        "capability_hook_governance": (capability_score, capability_checks),
        "frontend_state_architecture": (frontend_score, frontend_checks),
        "test_release_gates": (release_score, release_checks),
        "performance_efficiency": (performance_score, performance_checks),
        "docs_alignment": (docs_score, docs_checks),
        "competitive_superiority": (competitive_score, competitive_checks),
    }

    dimensions: list[dict[str, Any]] = []
    for dimension in program.scorecard.dimensions:
        score, checks = score_map[dimension.dimension_id]
        dimensions.append(
            {
                **dimension.model_dump(),
                "current_score": score,
                "checks": checks,
            }
        )

    total_score = sum(item["current_score"] for item in dimensions)
    release_gate = "pass" if total_score >= 70 and not coverage["uncovered_paths"] else program.scorecard.release_gate
    metric_values = {
        "M-001": total_score,
        "M-002": runtime_score,
        "M-003": capability_score,
        "M-004": 100 if verification_results.get("frontend-build", {}).get("passed") else 0,
        "M-005": 100 if verification_results.get("backend-critical-regression", {}).get("passed") else 0,
        "M-006": _runtime_latency_metric(verification_results),
        "M-007": board_loc,
        "M-008": len(coverage["uncovered_paths"]),
    }

    return {
        "repo_root": str(repo_root),
        "strategy": program.strategy,
        "baseline_total": program.scorecard.total_score,
        "baseline_aligned": total_score == program.scorecard.total_score,
        "release_gate": release_gate,
        "total_score": total_score,
        "dimensions": dimensions,
        "metrics": metric_values,
        "coverage": coverage,
        "verification_commands": verification_results,
        "autoresearch_scope": program.autoresearch_scope,
        "autoresearch_constraints": program.autoresearch_constraints,
        "excluded_paths": program.excluded_paths,
        "coverage_areas": [area.model_dump() for area in program.coverage_areas],
    }


def _format_text(report: dict[str, Any]) -> str:
    lines = [
        f"Optimization scorecard total: {report['total_score']}",
        f"Release gate: {report['release_gate']}",
        f"Baseline aligned: {report['baseline_aligned']}",
        "",
        "Dimensions:",
    ]
    for dimension in report["dimensions"]:
        lines.append(f"- {dimension['dimension_id']}: {dimension['current_score']}/{dimension['weight']} (target {dimension['target_score']})")
    lines.extend(
        [
            "",
            f"Uncovered paths: {len(report['coverage']['uncovered_paths'])}",
        ]
    )
    for path in report["coverage"]["uncovered_paths"]:
        lines.append(f"  - {path}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the OctoAgent optimization scorecard.")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--skip-smoke", action="store_true")
    parser.add_argument("--simulate-command-success", action="store_true")
    args = parser.parse_args()

    report = evaluate_scorecard(
        policy=CommandPolicy(
            run_tests=not args.skip_tests,
            run_build=not args.skip_build,
            run_smoke=not args.skip_smoke,
            simulate_success=args.simulate_command_success,
        )
    )

    try:
        if args.format == "json":
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print(_format_text(report))
    except BrokenPipeError:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
