"""Execution routing helpers for query engine turns."""

from __future__ import annotations

from urllib.parse import quote_plus

from src.browser_runtime import BrowserActionContract, BrowserSessionRequest
from src.research_runtime import RunResearchExperimentRequest
from src.runtime_governance import get_runtime_worker_isolation
from src.system_execution import SystemExecutionPlanRequest, SystemExecutionStepExecutionRequest

from .contracts import QueryClientCommand

_TASK_GOAL_PROMPT_MARKERS = (
    "原始任务目标：",
    "任务目标：",
    "总任务：",
    "负责核查以下任务是否真正完成：",
)

_TASK_PROMPT_SECTION_MARKERS = (
    "执行成员：",
    "协调者要求：",
    "其他已完成 worker 输出：",
    "待核查 worker 输出：",
    "协调计划：",
    "worker 输出：",
    "review 结论：",
)


class QueryTurnExecutor:
    """Select runtime targets and execute bounded query turns."""

    def __init__(self, make_id, *, get_browser_runtime_service_fn, get_research_runtime_service_fn, get_system_execution_service_fn):
        self._make_id = make_id
        self._get_browser_runtime_service = get_browser_runtime_service_fn
        self._get_research_runtime_service = get_research_runtime_service_fn
        self._get_system_execution_service = get_system_execution_service_fn

    def extract_signal_message(self, message: str) -> str:
        candidate = message.strip()
        for marker in _TASK_GOAL_PROMPT_MARKERS:
            if marker not in candidate:
                continue
            tail = candidate.rsplit(marker, 1)[-1]
            lowered = tail.lower()
            cut_positions = [
                lowered.find(section_marker)
                for section_marker in _TASK_PROMPT_SECTION_MARKERS
                if lowered.find(section_marker) >= 0
            ]
            if cut_positions:
                tail = tail[: min(cut_positions)]
            return tail.strip()
        return candidate

    def select_execution_target(self, message: str, client_command: QueryClientCommand | None = None) -> str:
        if client_command is not None:
            return client_command.execution_target
        signal_message = self.extract_signal_message(message)
        lowered = signal_message.lower()
        if any(token in lowered for token in ["research", "experiment", "trial", "hypothesis", "metric"]):
            return "research_runtime"
        if any(token in lowered for token in ["http://", "https://", "browser", "web", "page", "url", "snapshot", "weather", "forecast", "temperature", "latest", "search", "lookup", "news", "天气", "查询"]):
            return "browser_runtime"
        if any(marker in lowered for marker in ["run:", "command:", "shell:", "cli:", "workspace cli:", "system cli:"]):
            return "system_execution"
        if signal_message.strip().startswith(("pwd", "ls", "rg ", "cat ", "find ", "git status", "git diff --stat")):
            return "system_execution"
        if self.extract_requested_path(signal_message):
            return "system_execution"
        if any(token in lowered for token in ["system", "desktop", "file", "folder", "command", "shell", "terminal", "app"]):
            return "system_execution"
        return "repo_read"

    def resolve_client_command(
        self,
        message: str,
        *,
        permission_mode: str = "workspace",
    ) -> QueryClientCommand:
        signal_message = self.extract_signal_message(message)
        target = self.select_execution_target(signal_message)
        command_text = self.extract_shell_command(signal_message)
        requested_path = self.extract_requested_path(signal_message)
        requested_app = self.extract_requested_app(signal_message)
        requested_url = self.extract_url(signal_message) if target == "browser_runtime" else None
        cli_scope = self.extract_cli_scope(signal_message)
        notes: list[str] = []

        if target == "research_runtime":
            intent = "research"
        elif target == "browser_runtime":
            intent = "browser"
        elif target == "system_execution":
            if cli_scope == "system":
                intent = "system_cli"
            elif cli_scope == "workspace" or command_text:
                intent = "workspace_cli"
            elif requested_path:
                intent = "filesystem"
            else:
                intent = "desktop"
        elif target == "repo_read":
            intent = "repo_read"
        else:
            intent = "conversation"

        if intent == "system_cli" and permission_mode not in {"system", "yolo"}:
            notes.append("System CLI currently exceeds the active permission mode and may be blocked server-side.")
        if target == "repo_read":
            notes.append("No side-effect target detected; defaulting to read-oriented repository reasoning.")

        return QueryClientCommand(
            operation_id=self._make_id("client-op", f"{intent}-{abs(hash(signal_message)) % 1000000}"),
            source="client",
            intent=intent,
            execution_target=target,
            command_text=command_text,
            cli_scope=cli_scope,
            requested_url=requested_url,
            requested_path=requested_path,
            requested_app=requested_app,
            notes=notes,
        )

    def approval_required(self, session, target: str, message: str) -> bool:
        permission_mode = str(session.metadata.get("permission_mode") or "workspace")
        if permission_mode == "yolo":
            return False
        if permission_mode == "system" and target in {"repo_read", "browser_runtime", "system_execution"}:
            return False
        if permission_mode == "workspace" and target in {"repo_read", "system_execution"}:
            return False
        if target == "browser_runtime" and not self.browser_actions_need_approval(message):
            return False
        tool_id = {
            "browser_runtime": "browser-runtime",
            "system_execution": "system-execution",
            "repo_read": "repo-read",
        }.get(target)
        if tool_id is None:
            return False
        tool = next((item for item in session.available_tools if item.tool_id == tool_id), None)
        return bool(tool and tool.requires_approval)

    def execute_browser_target(self, session, message: str, *, created_at: str, client_command: QueryClientCommand | None = None):
        target = client_command.requested_url if client_command is not None and client_command.requested_url else self.browser_query_url(message)
        actions = self.browser_actions_from_message(message)
        allowed_domains: list[str] = []
        if "://" in target:
            domain = target.split("://", 1)[1].split("/", 1)[0]
            if domain:
                allowed_domains.append(domain)
        with get_runtime_worker_isolation().slot("browser"):
            browser_service = self._get_browser_runtime_service()
            browser_session = browser_service.create_session(
                BrowserSessionRequest(
                    target=target,
                    allowed_domains=allowed_domains,
                    actions=actions,
                    requires_approval=False,
                    policy_label="safe_read",
                ),
                created_at=created_at,
            )
            latest_result = None
            tool_calls = 0
            while True:
                current_result = browser_service.execute_next_action(
                    browser_session.session_id,
                    request=type("Req", (), {"note": message if tool_calls == 0 else "Continue browser action chain."})(),
                    executed_at=created_at,
                )
                tool_calls += 1
                latest_result = current_result
                if current_result is None or current_result.remaining_actions == 0 or current_result.status == "blocked":
                    break
                if tool_calls >= max(2, len(actions)):
                    break
            detail = latest_result.detail if latest_result is not None else "Browser runtime did not return an execution result."
            status = latest_result.status if latest_result is not None else "blocked"
        browser_state = browser_service.get_session(browser_session.session_id)
        if browser_state is not None:
            state_detail = []
            if browser_state.current_url:
                state_detail.append(f"url={browser_state.current_url}")
            if browser_state.latest_snapshot_summary:
                state_detail.append(browser_state.latest_snapshot_summary)
            if getattr(browser_state, "form_state", None):
                state_detail.append(f"form_state={browser_state.form_state}")
            if getattr(browser_state, "available_targets", None):
                state_detail.append(f"targets={len(browser_state.available_targets)}")
            if getattr(browser_state, "available_inputs", None):
                state_detail.append(f"inputs={len(browser_state.available_inputs)}")
            if getattr(browser_state, "recovery_available", False):
                state_detail.append("recovery_available=true")
            if getattr(browser_state, "last_failure_detail", None):
                state_detail.append(f"last_failure={browser_state.last_failure_detail}")
            if state_detail:
                detail = f"{detail} Browser state: {'; '.join(state_detail)}."
        session.metadata["last_browser_session_id"] = browser_session.session_id
        return "browser_runtime", detail, tool_calls, status, browser_session.session_id, latest_result.action_id if latest_result is not None else None

    def execute_research_target(self, session, message: str, *, created_at: str):
        experiment_id = str(session.metadata.get("research_experiment_id") or "").strip()
        if not experiment_id:
            return "research_runtime", "No research experiment is attached to the current workspace session.", 0, "blocked", None, None
        requested_trials = self.extract_requested_trial_count(message)
        with get_runtime_worker_isolation().slot("research"):
            response = self._get_research_runtime_service().run_experiment(
                experiment_id,
                RunResearchExperimentRequest(requested_trials=requested_trials),
                created_at=created_at,
            )
        if response is None:
            return "research_runtime", f"Research experiment '{experiment_id}' is not available.", 0, "blocked", experiment_id, None
        latest_trial = response.new_trials[-1] if response.new_trials else None
        summary_parts = [
            f"Research experiment {experiment_id} status={response.experiment.status}.",
            f"new_trials={len(response.new_trials)}",
            f"trial_count={response.experiment.trial_count}",
        ]
        if latest_trial is not None:
            summary_parts.append(f"latest_trial={latest_trial.trial_id}")
            if latest_trial.verdict is not None:
                summary_parts.append(f"verdict={latest_trial.verdict.outcome}")
        session.metadata["last_research_experiment_id"] = experiment_id
        return "research_runtime", " ".join(summary_parts), max(1, len(response.new_trials)), "completed", experiment_id, latest_trial.trial_id if latest_trial is not None else None

    def execute_system_target(self, session, message: str, *, allow_side_effects: bool, client_command: QueryClientCommand | None = None):
        requested_command = client_command.command_text if client_command is not None else self.extract_shell_command(message)
        requested_path = client_command.requested_path if client_command is not None else self.extract_requested_path(message)
        requested_app = client_command.requested_app if client_command is not None else self.extract_requested_app(message)
        permission_mode = str(session.metadata.get("permission_mode") or "workspace")
        cli_scope = client_command.cli_scope if client_command is not None else self.extract_cli_scope(message)
        if cli_scope == "system":
            if permission_mode not in {"system", "yolo"}:
                return "system_execution", "System-level CLI requires system or yolo permission mode.", 0, "blocked", None, None
            target = "system_cli"
        elif cli_scope == "workspace" or requested_command:
            target = "workspace_cli"
        elif requested_path or any(token in message.lower() for token in ["file", "folder", "path"]):
            target = "filesystem"
        else:
            target = "desktop"
        dry_run = not (allow_side_effects and (requested_command or requested_path or requested_app))
        with get_runtime_worker_isolation().slot("system"):
            system_service = self._get_system_execution_service()
            system_session = system_service.create_session(
                SystemExecutionPlanRequest(
                    goal=message,
                    target=target,
                    require_approval=False,
                    allowed_apps=[requested_app] if requested_app else [],
                    requested_paths=[requested_path] if requested_path else [],
                    requested_commands=[requested_command] if requested_command else [],
                ),
                dry_run=dry_run,
            )
            result = None
            tool_calls = 0
            details: list[str] = []
            max_steps = 4 if requested_command and not dry_run else 1
            for _ in range(max_steps):
                result = system_service.execute_next_step(
                    system_session.session_id,
                    SystemExecutionStepExecutionRequest(note=message),
                )
                tool_calls += 1
                if result is None:
                    break
                details.append(result.detail)
                current_session = system_service.get_session(system_session.session_id) if getattr(system_service, "get_session", None) else None
                if current_session is None or current_session.last_command is not None or result.status == "blocked" or result.remaining_steps == 0:
                    break
        session.metadata["last_system_session_id"] = system_session.session_id
        if result is None:
            return "system_execution", "System execution did not return an execution result.", tool_calls or 1, "blocked", system_session.session_id, None
        return "system_execution", (" ".join(details).strip() or result.detail), tool_calls, result.status, system_session.session_id, result.step_id

    def execute_read_target(self, session, message: str, client_command: QueryClientCommand | None = None):
        analysis = session.task_analysis.summary if session.task_analysis is not None else session.current_goal
        detail = (
            f"Read-oriented turn executed against repository context. "
            f"Current guidance: {analysis} "
            f"Primary goal: {session.current_goal}. "
            f"Request: {message}"
        )
        if client_command is not None and client_command.notes:
            detail = f"{detail} Client notes: {' '.join(client_command.notes)}"
        return "repo_read", detail, 0, "completed", None, None

    def browser_actions_from_message(self, message: str) -> list[BrowserActionContract]:
        actions: list[BrowserActionContract] = [
            BrowserActionContract(
                action_id=self._make_id("browser-action", "open"),
                kind="open",
                target=self.browser_query_url(message),
                requires_approval=False,
            )
        ]
        fill_instruction = self.extract_browser_fill(message)
        if fill_instruction is not None:
            field_name, value = fill_instruction
            actions.append(BrowserActionContract(action_id=self._make_id("browser-action", "fill"), kind="fill", target=field_name, value=value, requires_approval=False))
        click_target = self.extract_browser_click(message)
        if click_target is not None:
            actions.append(BrowserActionContract(action_id=self._make_id("browser-action", "click"), kind="click", target=click_target, requires_approval=False))
        wait_target = self.extract_browser_wait(message)
        if wait_target is not None:
            actions.append(BrowserActionContract(action_id=self._make_id("browser-action", "wait"), kind="wait", value=wait_target, requires_approval=False))
        actions.append(BrowserActionContract(action_id=self._make_id("browser-action", "snapshot"), kind="snapshot", requires_approval=False))
        return actions

    def browser_query_url(self, message: str) -> str:
        explicit = self.extract_url(message)
        if explicit is not None:
            return explicit
        return f"https://duckduckgo.com/?q={quote_plus(message.strip() or 'octoagent')}"

    def browser_actions_need_approval(self, message: str) -> bool:
        lowered = message.lower()
        return any(token in lowered for token in [" click ", "fill ", "submit", "login", "purchase", "delete", "confirm"])

    def extract_requested_trial_count(self, message: str) -> int:
        lowered = message.lower()
        for marker in ["run ", "execute ", "start "]:
            if marker in lowered and " trial" in lowered:
                start = lowered.index(marker) + len(marker)
                for candidate in message[start:].split():
                    if candidate.isdigit():
                        return max(1, min(int(candidate), 3))
        if "two trial" in lowered:
            return 2
        if "three trial" in lowered:
            return 3
        return 1

    def extract_browser_fill(self, message: str):
        lowered = message.lower()
        marker = "fill "
        if marker not in lowered or " with " not in lowered:
            return None
        start = lowered.index(marker) + len(marker)
        middle = lowered.index(" with ", start)
        field_name = message[start:middle].strip().strip("\"'")
        value_start = middle + len(" with ")
        value_end = len(message)
        for delimiter in [" click ", " wait for ", " wait ", " snapshot"]:
            next_index = lowered.find(delimiter, value_start)
            if next_index != -1:
                value_end = min(value_end, next_index)
        value = message[value_start:value_end].strip().strip("\"'")
        return (field_name, value) if field_name and value else None

    def extract_browser_click(self, message: str):
        lowered = message.lower()
        marker = "click "
        if marker not in lowered:
            return None
        start = lowered.index(marker) + len(marker)
        end = len(message)
        for delimiter in [" wait for ", " wait ", " snapshot"]:
            next_index = lowered.find(delimiter, start)
            if next_index != -1:
                end = min(end, next_index)
        target = message[start:end].strip().strip("\"'")
        return target or None

    def extract_browser_wait(self, message: str):
        lowered = message.lower()
        for marker in ["wait for ", "wait "]:
            if marker in lowered:
                start = lowered.index(marker) + len(marker)
                target = message[start:].strip().strip("\"'")
                return target or None
        return None

    def extract_shell_command(self, message: str):
        lowered = message.lower()
        for marker in ["workspace cli:", "system cli:", "cli:", "run:", "command:", "shell:"]:
            if marker in lowered:
                index = lowered.index(marker) + len(marker)
                command = message[index:].strip()
                return command or None
        stripped = message.strip()
        return stripped if stripped.startswith(("pwd", "ls", "rg ", "cat ", "find ", "git status", "git diff --stat")) else None

    def extract_cli_scope(self, message: str):
        lowered = message.strip().lower()
        if lowered.startswith("system cli:"):
            return "system"
        if lowered.startswith("workspace cli:") or lowered.startswith("cli:"):
            return "workspace"
        return None

    def extract_requested_path(self, message: str):
        stripped = message.strip()
        lowered = stripped.lower()
        for prefix in ["open file ", "open folder ", "open path ", "open "]:
            if lowered.startswith(prefix):
                candidate = stripped[len(prefix):].strip().strip("\"'")
                return candidate or None
        return None

    def extract_requested_app(self, message: str):
        stripped = message.strip()
        lowered = stripped.lower()
        for prefix in ["launch app ", "open app ", "launch "]:
            if lowered.startswith(prefix):
                candidate = stripped[len(prefix):].strip().strip("\"'")
                return candidate or None
        return None

    def extract_url(self, message: str):
        for token in message.split():
            if token.startswith(("http://", "https://")):
                return token.strip().strip("\"',)")
        return None
