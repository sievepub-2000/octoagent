"""Task workflow archive manager.

Creates a durable per-task archive under ``workflow/taskwork/`` with a clear,
human-readable layout:

- ``PROJECT_OVERVIEW.md``: task summary and project-level context
- ``WORKFLOW_CONFIG.md``: workflow cards, edges, and runtime config
- ``RUN_LOG.md``: execution log, checkpoints, and final result notes
- ``artifacts/``: copied output files when available
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config.paths import get_paths

_INVALID_TASK_DIR_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff._-]+")
_MULTI_DASH_RE = re.compile(r"-{2,}")
_WORKFLOW_STATE_FILE = "task-workflow-state.json"
CANONICAL_PROJECT_DOC = "01_PROJECT.md"
CANONICAL_SETTINGS_DOC = "02_WORKFLOW_SETTINGS.md"
CANONICAL_RESULT_DOC = "03_RESULT.md"
LEGACY_PROJECT_DOC = "PROJECT_OVERVIEW.md"
LEGACY_SETTINGS_DOC = "WORKFLOW_CONFIG.md"
LEGACY_RESULT_DOC = "RESULT.md"
RUN_LOG_DOC = "RUN_LOG.md"


def _slugify(value: str) -> str:
    normalized = value.strip().lower().replace("/", "-").replace("\\", "-")
    slug = _INVALID_TASK_DIR_RE.sub("-", normalized)
    slug = _MULTI_DASH_RE.sub("-", slug).strip("-._")
    return slug or "task"


class WorkflowFileManager:
    """Persist per-task archives and lightweight workflow projections."""

    def __init__(self, base_dir: Path | None = None) -> None:
        if base_dir is not None:
            self._root = Path(base_dir)
        else:
            paths = get_paths()
            self._root = paths.workflow_tasks_dir
        self._state_dir = self._root / "_state"
        self._index_path = self._state_dir / "directories.json"

    def create_workflow_dir(
        self,
        workflow_id: str,
        *,
        name: str,
        goal: str,
        mode: str,
        agent_runtime_provider: str,
        summary: str,
        main_agent: str,
        sub_agents: list[str],
        agents: list[dict[str, Any]],
        cards: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        status: str,
    ) -> None:
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        archive_dir = self._root / f"task-{_slugify(name or workflow_id)}-{timestamp}"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "artifacts").mkdir(exist_ok=True)
        self._write_index_entry(workflow_id, archive_dir.name)
        self.update_task_file(
            workflow_id,
            name=name,
            goal=goal,
            mode=mode,
            agent_runtime_provider=agent_runtime_provider,
            summary=summary,
            main_agent=main_agent,
            sub_agents=sub_agents,
        )
        self.update_workflow_file(
            workflow_id,
            name=name,
            goal=goal,
            mode=mode,
            agent_runtime_provider=agent_runtime_provider,
            agents=agents,
            cards=cards,
            edges=edges,
            status=status,
        )
        self.append_run_log(
            workflow_id,
            title="Archive initialized",
            details=[
                f"Task ID: `{workflow_id}`",
                f"Status: `{status}`",
                f"Main agent: `{main_agent or 'n/a'}`",
            ],
        )

    def get_dir_path(self, workflow_id: str) -> str | None:
        archive_dir = self._resolve_archive_dir(workflow_id)
        return str(archive_dir) if archive_dir is not None else None

    def document_paths(self, workflow_id: str) -> dict[str, str]:
        self._require_archive_dir(workflow_id)
        return {
            "project": CANONICAL_PROJECT_DOC,
            "settings": CANONICAL_SETTINGS_DOC,
            "result": CANONICAL_RESULT_DOC,
            "run_log": RUN_LOG_DOC,
        }

    def delete_workflow_dir(self, workflow_id: str) -> None:
        archive_dir = self._resolve_archive_dir(workflow_id)
        if archive_dir is not None:
            shutil.rmtree(archive_dir, ignore_errors=True)
        index = self._read_index()
        if workflow_id in index:
            del index[workflow_id]
            self._write_index(index)

    def update_task_file(
        self,
        task_id: str,
        *,
        name: str,
        goal: str,
        mode: str,
        agent_runtime_provider: str,
        summary: str,
        main_agent: str,
        sub_agents: list[str],
    ) -> None:
        archive_dir = self._require_archive_dir(task_id)
        payload = {
            "task_id": task_id,
            "name": name,
            "goal": goal,
            "mode": mode,
            "agent_runtime_provider": agent_runtime_provider,
            "summary": summary,
            "main_agent": main_agent,
            "sub_agents": sub_agents,
        }
        self._write_json(archive_dir / "task.json", payload)
        overview = [
            f"# {name or task_id}",
            "",
            "## Project Name",
            "",
            name or task_id,
            "",
            "## Project Content",
            "",
            goal or summary or "_No project content provided._",
            "",
            "## Execution Context",
            "",
            f"- Task ID: `{task_id}`",
            f"- Mode: `{mode}`",
            f"- Runtime provider: `{agent_runtime_provider}`",
            f"- Main agent: `{main_agent or 'n/a'}`",
            f"- Sub agents: {', '.join(sub_agents) if sub_agents else 'none'}",
            "",
            "## Summary",
            "",
            summary or "_No summary provided._",
        ]
        content = "\n".join(overview) + "\n"
        (archive_dir / CANONICAL_PROJECT_DOC).write_text(content, encoding="utf-8")
        (archive_dir / LEGACY_PROJECT_DOC).write_text(content, encoding="utf-8")

    def update_workflow_file(
        self,
        task_id: str,
        *,
        name: str,
        goal: str,
        mode: str,
        agent_runtime_provider: str,
        agents: list[dict[str, Any]],
        cards: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        status: str | None = None,
    ) -> None:
        archive_dir = self._require_archive_dir(task_id)
        payload = {
            "task_id": task_id,
            "name": name,
            "mode": mode,
            "agent_runtime_provider": agent_runtime_provider,
            "status": status,
            "agents": agents,
            "cards": cards,
            "edges": edges,
        }
        self._write_json(archive_dir / "workflow.json", payload)
        run_log_snapshot = self.read_run_log(task_id) or "# Workflow Run Log\n\n_Results pending._\n"
        card_by_agent_id = {
            str(card.get("linked_agent_id")): card
            for card in cards
            if isinstance(card, dict) and card.get("linked_agent_id")
        }
        lines = [
            "# Workflow Settings",
            "",
            f"- Task ID: `{task_id}`",
            f"- Name: `{name or task_id}`",
            f"- Mode: `{mode}`",
            f"- Runtime provider: `{agent_runtime_provider}`",
        ]
        if status is not None:
            lines.append(f"- Status: `{status}`")
        if goal:
            lines.append(f"- Goal: {goal}")
        lines.extend(
            [
                "",
                "## Agent Directory",
                "",
            ]
        )
        if agents:
            for agent in agents:
                linked_card = card_by_agent_id.get(str(agent.get("agent_id")), {})
                card_config = linked_card.get("config") if isinstance(linked_card, dict) else {}
                if not isinstance(card_config, dict):
                    card_config = {}
                lines.extend(
                    [
                        f"### {agent.get('name') or agent.get('agent_id')}",
                        "",
                        f"- Agent ID: `{agent.get('agent_id', 'n/a')}`",
                        f"- Role: `{agent.get('role', 'n/a')}`",
                        f"- Model: `{agent.get('model_name') or 'default'}`",
                        f"- Branch task: {agent.get('task_scope') or card_config.get('branch_task') or 'n/a'}",
                        f"- Bound card: `{linked_card.get('card_id', 'n/a')}`",
                        f"- Document: `{card_config.get('document_path', CANONICAL_SETTINGS_DOC)}`",
                        "",
                        "#### Prompt Preview",
                        "",
                        str(card_config.get("prompt_preview") or "_No prompt preview available._"),
                        "",
                    ]
                )
        else:
            lines.extend(["_No agents configured._", ""])
        lines.extend(
            [
                "## Workflow Graph JSON",
                "",
                "### Agents",
                "",
                "```json",
                json.dumps(agents, ensure_ascii=False, indent=2),
                "```",
                "",
                "## Cards",
                "",
                "```json",
                json.dumps(cards, ensure_ascii=False, indent=2),
                "```",
                "",
                "## Edges",
                "",
                "```json",
                json.dumps(edges, ensure_ascii=False, indent=2),
                "```",
                "",
                "## System Operation Log",
                "",
                run_log_snapshot,
            ]
        )
        content = "\n".join(lines) + "\n"
        (archive_dir / CANONICAL_SETTINGS_DOC).write_text(content, encoding="utf-8")
        (archive_dir / LEGACY_SETTINGS_DOC).write_text(content, encoding="utf-8")

    def append_run_log(self, task_id: str, *, title: str, details: list[str] | None = None) -> None:
        archive_dir = self._require_archive_dir(task_id)
        log_path = archive_dir / RUN_LOG_DOC
        if not log_path.exists():
            log_path.write_text("# Workflow Run Log\n\n## Final Results\n\n_Results pending._\n", encoding="utf-8")
        timestamp = datetime.now(UTC).isoformat()
        section = [f"\n## {timestamp} - {title}\n"]
        if details:
            section.extend([f"- {detail}" for detail in details])
            section.append("")
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(section))

    def record_artifact(
        self,
        task_id: str,
        *,
        source_path: str | Path,
        description: str | None = None,
    ) -> str:
        archive_dir = self._require_archive_dir(task_id)
        artifacts_dir = archive_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        source = Path(source_path)
        target = artifacts_dir / source.name
        if source.resolve() != target.resolve():
            shutil.copy2(source, target)
        relative = target.relative_to(archive_dir)
        self.append_run_log(
            task_id,
            title="Artifact recorded",
            details=[
                f"{description or source.name}: [{relative.as_posix()}]({relative.as_posix()})",
            ],
        )
        return str(target)

    def read_result(self, task_id: str) -> str | None:
        """Read the 03_RESULT.md document for a task."""
        archive_dir = self._resolve_archive_dir(task_id)
        if archive_dir is None:
            return None
        for name in (CANONICAL_RESULT_DOC, LEGACY_RESULT_DOC):
            path = archive_dir / name
            if path.exists():
                return path.read_text(encoding="utf-8")
        return None

    def read_result_payload(self, task_id: str) -> dict[str, Any]:
        """Read the best available result payload for a task.

        Priority order:
        1. Canonical or legacy result document.
        2. Final Results section extracted from RUN_LOG.md.
        """
        archive_dir = self._resolve_archive_dir(task_id)
        empty_payload = {
            "content": "",
            "has_result": False,
            "source_path": None,
            "source_label": None,
            "available_sources": [],
        }
        if archive_dir is None:
            return empty_payload

        available_sources = [
            name
            for name in (CANONICAL_RESULT_DOC, LEGACY_RESULT_DOC, RUN_LOG_DOC)
            if (archive_dir / name).exists()
        ]

        for name in (CANONICAL_RESULT_DOC, LEGACY_RESULT_DOC):
            path = archive_dir / name
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            if content.strip():
                return {
                    "content": content,
                    "has_result": True,
                    "source_path": name,
                    "source_label": name,
                    "available_sources": available_sources,
                }

        run_log = self.read_run_log(task_id)
        extracted = self._extract_final_results_section(run_log)
        if extracted:
            return {
                "content": extracted,
                "has_result": True,
                "source_path": RUN_LOG_DOC,
                "source_label": f"{RUN_LOG_DOC}#final-results",
                "available_sources": available_sources,
            }

        return {
            **empty_payload,
            "available_sources": available_sources,
        }

    def read_run_log(self, task_id: str) -> str | None:
        archive_dir = self._resolve_archive_dir(task_id)
        if archive_dir is None:
            return None
        log_path = archive_dir / RUN_LOG_DOC
        if not log_path.exists():
            return None
        return log_path.read_text(encoding="utf-8")

    def _extract_final_results_section(self, content: str | None) -> str | None:
        if not content or "## Final Results" not in content:
            return None
        marker = "## Final Results\n"
        start = content.index(marker) + len(marker)
        next_section = content.find("\n## ", start)
        if next_section == -1:
            next_section = len(content)
        section = content[start:next_section].strip()
        if not section or section == "_Results pending._":
            return None
        return f"## Final Results\n\n{section}\n"

    def resolve_artifact_path(self, task_id: str, relative_path: str) -> Path | None:
        archive_dir = self._resolve_archive_dir(task_id)
        if archive_dir is None:
            return None
        candidate = (archive_dir / relative_path).resolve()
        try:
            candidate.relative_to(archive_dir.resolve())
        except ValueError:
            return None
        if not candidate.exists() or not candidate.is_file():
            return None
        return candidate

    def sync_task_attachments(self, task_id: str) -> list[dict[str, str]]:
        archive_dir = self._require_archive_dir(task_id)
        artifacts_dir = archive_dir / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        artifacts: list[dict[str, str]] = []
        for item in sorted(artifacts_dir.iterdir()):
            if not item.is_file():
                continue
            relative_path = item.relative_to(archive_dir).as_posix()
            artifacts.append({"name": item.name, "path": relative_path})
        return artifacts

    def write_agent_conversation(
        self,
        task_id: str,
        *,
        agent_id: str,
        agent_name: str | None,
        messages: list[dict[str, Any]],
    ) -> dict[str, str]:
        archive_dir = self._require_archive_dir(task_id)
        conversations_dir = archive_dir / "agent_conversations"
        conversations_dir.mkdir(exist_ok=True)
        json_path = conversations_dir / f"{agent_id}.json"
        markdown_path = conversations_dir / f"{agent_id}.md"
        payload = {
            "task_id": task_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "message_count": len(messages),
            "messages": messages,
        }
        self._write_json(json_path, payload)

        markdown_lines = [
            f"# {agent_name or agent_id} Conversation",
            "",
            f"- Task ID: `{task_id}`",
            f"- Agent ID: `{agent_id}`",
            f"- Message count: `{len(messages)}`",
            "",
            "## Messages",
            "",
        ]
        if messages:
          for message in messages:
            role = str(message.get("role") or "unknown")
            created_at = str(message.get("created_at") or "")
            content = str(message.get("content") or "").strip() or "_No content._"
            markdown_lines.extend(
                [
                    f"### {role.upper()}" + (f" · {created_at}" if created_at else ""),
                    "",
                    content,
                    "",
                ]
            )
        else:
            markdown_lines.append("_No messages recorded yet._")
        markdown_path.write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")
        return {
            "json": json_path.relative_to(archive_dir).as_posix(),
            "markdown": markdown_path.relative_to(archive_dir).as_posix(),
        }

    def read_agent_conversation(self, task_id: str, agent_id: str) -> list[dict[str, Any]] | None:
        archive_dir = self._resolve_archive_dir(task_id)
        if archive_dir is None:
            return None
        json_path = archive_dir / "agent_conversations" / f"{agent_id}.json"
        if not json_path.exists():
            return None
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        messages = payload.get("messages") if isinstance(payload, dict) else None
        if not isinstance(messages, list):
            return None
        return [message for message in messages if isinstance(message, dict)]

    def write_workflow_state(self, task_id: str, payload: dict[str, Any]) -> None:
        archive_dir = self._require_archive_dir(task_id)
        self._write_json(archive_dir / _WORKFLOW_STATE_FILE, payload)

    def read_workflow_state(self, task_id: str) -> dict[str, Any] | None:
        archive_dir = self._resolve_archive_dir(task_id)
        if archive_dir is None:
            return None
        state_path = archive_dir / _WORKFLOW_STATE_FILE
        if not state_path.exists():
            return None
        try:
            payload = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def update_result_file(
        self,
        task_id: str,
        *,
        name: str,
        status: str,
        output: str,
        transcripts: str,
        artifacts: list[dict[str, str]] | None,
        failure_reason: str | None,
    ) -> None:
        archive_dir = self._require_archive_dir(task_id)
        result_lines = [
            f"# {name or task_id} Result",
            "",
            f"- Task ID: `{task_id}`",
            f"- Status: `{status}`",
        ]
        if failure_reason:
            result_lines.append(f"- Failure reason: {failure_reason}")
        result_lines.extend([
            "",
            "## Output",
            "",
            output or "_No output recorded._",
            "",
        ])
        if artifacts:
            result_lines.extend(["## Artifacts", ""])
            result_lines.extend(
                [
                    f"- [{artifact.get('path', artifact.get('name', 'artifact'))}]({artifact.get('path', artifact.get('name', 'artifact'))})"
                    for artifact in artifacts
                ]
            )
            result_lines.append("")
        result_lines.extend([
            "## Transcripts",
            "",
            transcripts or "_No transcripts captured._",
            "",
        ])
        content = "\n".join(result_lines)
        (archive_dir / CANONICAL_RESULT_DOC).write_text(content, encoding="utf-8")
        (archive_dir / LEGACY_RESULT_DOC).write_text(content, encoding="utf-8")
        self._write_final_results_section(
            task_id,
            status=status,
            output=output,
            failure_reason=failure_reason,
            artifacts=artifacts or [],
        )

    def _write_final_results_section(
        self,
        task_id: str,
        *,
        status: str,
        output: str,
        failure_reason: str | None,
        artifacts: list[dict[str, str]],
    ) -> None:
        archive_dir = self._require_archive_dir(task_id)
        log_path = archive_dir / "RUN_LOG.md"
        if not log_path.exists():
            log_path.write_text("# Workflow Run Log\n\n## Final Results\n\n_Results pending._\n", encoding="utf-8")
        content = log_path.read_text(encoding="utf-8")
        marker = "## Final Results\n"
        if marker not in content:
            content = f"# Workflow Run Log\n\n## Final Results\n\n_Results pending._\n\n{content}"
        start = content.index(marker) + len(marker)
        next_section = content.find("\n## ", start)
        if next_section == -1:
            next_section = len(content)
        final_lines = [f"- Status: `{status}`", ""]
        if failure_reason:
            final_lines.extend(["### Failure reason", "", failure_reason, ""])
        final_lines.extend(["### Output", "", output or "_No output recorded._", ""])
        if artifacts:
            final_lines.extend(["### Artifacts", ""])
            final_lines.extend(
                [
                    f"- [{artifact.get('path', artifact.get('name', 'artifact'))}]({artifact.get('path', artifact.get('name', 'artifact'))})"
                    for artifact in artifacts
                ]
            )
            final_lines.append("")
        updated = content[:start] + "\n" + "\n".join(final_lines) + content[next_section:]
        log_path.write_text(updated, encoding="utf-8")

    def _require_archive_dir(self, workflow_id: str) -> Path:
        archive_dir = self._resolve_archive_dir(workflow_id)
        if archive_dir is not None:
            return archive_dir
        fallback_dir = self._root / workflow_id
        fallback_dir.mkdir(parents=True, exist_ok=True)
        self._write_index_entry(workflow_id, fallback_dir.name)
        return fallback_dir

    def _resolve_archive_dir(self, workflow_id: str) -> Path | None:
        folder_name = self._read_index().get(workflow_id)
        if not folder_name:
            return None
        candidate = self._root / folder_name
        return candidate if candidate.exists() else None

    def _read_index(self) -> dict[str, str]:
        return self._read_index_from(self._state_dir, self._index_path)

    def _read_index_from(self, state_dir: Path, index_path: Path) -> dict[str, str]:
        state_dir.mkdir(parents=True, exist_ok=True)
        if not index_path.exists():
            return {}
        try:
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(value) for key, value in payload.items()}

    def _write_index(self, payload: dict[str, str]) -> None:
        self._write_index_to(self._state_dir, self._index_path, payload)

    def _write_index_to(self, state_dir: Path, index_path: Path, payload: dict[str, str]) -> None:
        state_dir.mkdir(parents=True, exist_ok=True)
        index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_index_entry(self, workflow_id: str, folder_name: str) -> None:
        index = self._read_index()
        index[workflow_id] = folder_name
        self._write_index(index)

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
