"""Repository-owned service facade for the research runtime plane."""

from __future__ import annotations

from src.utils.datetime import utc_now_iso as _utc_now

from .contracts import (
    CreateResearchExperimentRequest,
    ResearchArtifactRef,
    ResearchExecutionBudget,
    ResearchExperiment,
    ResearchExperimentListResponse,
    ResearchExperimentRunResponse,
    ResearchExperimentSpec,
    ResearchInstructionProgram,
    ResearchProgramListResponse,
    ResearchRuntimeCapability,
    ResearchRuntimeSnapshot,
    ResearchTrial,
    ResearchTrialVerdict,
    RunResearchExperimentRequest,
)


class ResearchRuntimeService:
    """Own bounded research experiments, trial execution, and runtime summaries."""

    def __init__(self) -> None:
        self._programs = self._seed_programs()
        self._experiments: dict[str, ResearchExperiment] = {}
        self._trials: dict[str, list[ResearchTrial]] = {}
        self._activity: list[dict[str, str]] = []
        self._seed_experiment()

    def _record_activity(self, *, kind: str, experiment_id: str, status: str, detail: str) -> None:
        self._activity.append(
            {
                "kind": kind,
                "experiment_id": experiment_id,
                "status": status,
                "detail": detail,
                "created_at": _utc_now(),
            }
        )
        self._activity = self._activity[-40:]

    def get_capability(self) -> ResearchRuntimeCapability:
        return ResearchRuntimeCapability()

    def get_runtime_snapshot(self) -> ResearchRuntimeSnapshot:
        experiments = list(self._experiments.values())
        trials = [trial for experiment_trials in self._trials.values() for trial in experiment_trials]
        experiment_status_counts: dict[str, int] = {}
        trial_status_counts: dict[str, int] = {}
        for experiment in experiments:
            experiment_status_counts[experiment.status] = experiment_status_counts.get(experiment.status, 0) + 1
        for trial in trials:
            trial_status_counts[trial.status] = trial_status_counts.get(trial.status, 0) + 1
        return ResearchRuntimeSnapshot(
            total_experiments=len(experiments),
            active_experiments=sum(1 for experiment in experiments if experiment.status in {"queued", "running"}),
            completed_experiments=experiment_status_counts.get("completed", 0),
            failed_experiments=experiment_status_counts.get("failed", 0),
            total_trials=len(trials),
            active_trials=sum(1 for trial in trials if trial.status in {"queued", "running"}),
            experiment_status_counts=experiment_status_counts,
            trial_status_counts=trial_status_counts,
            task_bound_experiments=sum(1 for experiment in experiments if experiment.task_id is not None),
            recent_activity=list(self._activity[-10:]),
        )

    def _seed_programs(self) -> list[ResearchInstructionProgram]:
        return [
            ResearchInstructionProgram(
                instruction_id="program-bounded-autoresearch",
                title="Bounded Autoresearch",
                summary=("Run short experiment loops with explicit guardrails, reviewable diffs, and metric-based keep-or-discard verdicts."),
                objective="Continuously improve a bounded implementation surface without taking over orchestration ownership.",
                guardrails=[
                    "Mutate only declared candidate files.",
                    "Keep each trial within a fixed wall-clock budget.",
                    "Persist comparable metrics and trial artifacts.",
                ],
                iteration_budget=4,
                time_budget_minutes=20,
                allowed_mutation_roots=["backend/src", "frontend/src", "project_docs/docs"],
                allowed_tool_classes=["analysis", "edit", "validation"],
            )
        ]

    def _seed_experiment(self) -> None:
        now = _utc_now()
        experiment = ResearchExperiment(
            experiment_id="experiment-seed-runtime-linkage",
            task_id=None,
            goal="Compile Brain plans into bounded task-runtime experiments.",
            hypothesis="A dedicated research runtime should own repeatable experiment loops.",
            success_metric="task_graph_compilation_success_rate",
            instruction_program_id="program-bounded-autoresearch",
            source="brain",
            spec=ResearchExperimentSpec(
                spec_id="spec-runtime-linkage",
                title="Task graph compilation experiment",
                objective="Improve the success rate of Brain-to-task-graph compilation under bounded retries.",
                candidate_files=[
                    "backend/src/orchestration/compiler.py",
                    "backend/src/brain/service.py",
                ],
                success_metric="task_graph_compilation_success_rate",
                max_trials=3,
                evaluation_window_minutes=15,
                instruction_program_id="program-bounded-autoresearch",
            ),
            status="planned",
            trial_count=1,
            latest_trial_id="experiment-seed-runtime-linkage-trial-1",
            candidate_files=[
                "backend/src/orchestration/compiler.py",
                "backend/src/brain/service.py",
            ],
            guardrails=[
                "Mutate only declared candidate files.",
                "Keep each trial within the fixed wall-clock budget.",
            ],
            progress_score=0.0,
            created_at=now,
            updated_at=now,
        )
        trial = ResearchTrial(
            trial_id="experiment-seed-runtime-linkage-trial-1",
            experiment_id=experiment.experiment_id,
            title="Contract and telemetry scaffolding",
            status="planned",
            summary="Define trial, metric, and artifact contracts before provider execution.",
            metrics={"task_graph_compilation_success_rate": 0.0},
            modified_files=[
                "backend/src/research_runtime/contracts.py",
                "backend/src/orchestration/contracts.py",
            ],
            artifacts=[
                ResearchArtifactRef(
                    artifact_id="experiment-seed-runtime-linkage-artifact-1",
                    kind="report",
                    label="Trial design report",
                    path="docs/PLATFORM_REFACTOR_BLUEPRINT.md",
                )
            ],
            verdict=ResearchTrialVerdict(
                outcome="review",
                rationale=[
                    "Contracts are ready but provider execution is not yet wired.",
                    "Telemetry shape is defined and can be consumed by orchestration.",
                ],
                metric_delta={"task_graph_compilation_success_rate": 0.0},
                confidence=0.35,
            ),
            iteration_index=1,
            budget=ResearchExecutionBudget(
                requested_trials=1,
                granted_trials=1,
                remaining_trials_after_run=2,
                time_budget_minutes=15,
            ),
            created_at=now,
            updated_at=now,
        )
        self._experiments[experiment.experiment_id] = experiment
        self._trials[experiment.experiment_id] = [trial]
        self._record_activity(
            kind="seed_experiment",
            experiment_id=experiment.experiment_id,
            status=experiment.status,
            detail="Loaded seeded runtime-linkage experiment",
        )

    def list_programs(self) -> ResearchProgramListResponse:
        return ResearchProgramListResponse(programs=self._programs)

    def list_experiments(self) -> ResearchExperimentListResponse:
        experiments = sorted(self._experiments.values(), key=lambda item: item.updated_at, reverse=True)
        return ResearchExperimentListResponse(experiments=experiments)

    def get_experiment(self, experiment_id: str) -> ResearchExperiment | None:
        return self._experiments.get(experiment_id)

    def list_trials(self, experiment_id: str) -> list[ResearchTrial]:
        return list(self._trials.get(experiment_id, []))

    def create_experiment(
        self,
        request: CreateResearchExperimentRequest,
        *,
        created_at: str | None = None,
    ) -> ResearchExperiment:
        now = created_at or _utc_now()
        experiment_id = f"experiment-{len(self._experiments) + 1}"
        program = next(
            (program for program in self._programs if program.instruction_id == request.instruction_program_id),
            self._programs[0],
        )
        candidate_files = list(dict.fromkeys(request.candidate_files))
        experiment = ResearchExperiment(
            experiment_id=experiment_id,
            task_id=request.task_id,
            goal=request.goal,
            hypothesis=request.hypothesis,
            success_metric=request.success_metric,
            instruction_program_id=request.instruction_program_id,
            source=request.source,
            spec=ResearchExperimentSpec(
                spec_id=f"spec-{experiment_id}",
                title=f"Experiment for {request.goal[:48]}".strip(),
                objective=request.goal,
                candidate_files=candidate_files,
                success_metric=request.success_metric,
                max_trials=request.max_trials,
                evaluation_window_minutes=request.evaluation_window_minutes,
                instruction_program_id=request.instruction_program_id,
            ),
            status="planned",
            candidate_files=candidate_files,
            guardrails=list(program.guardrails),
            created_at=now,
            updated_at=now,
        )
        self._experiments[experiment_id] = experiment
        self._trials[experiment_id] = []
        self._record_activity(
            kind="experiment_created",
            experiment_id=experiment_id,
            status="planned",
            detail=f"Created experiment for goal: {request.goal}",
        )
        return experiment

    def ensure_workspace_experiment(
        self,
        *,
        task_id: str,
        goal: str,
        candidate_files: list[str] | None = None,
        success_metric: str = "research_progress_score",
    ) -> ResearchExperiment:
        for experiment in self._experiments.values():
            if experiment.task_id == task_id:
                return experiment
        return self.create_experiment(
            CreateResearchExperimentRequest(
                goal=goal,
                task_id=task_id,
                candidate_files=candidate_files or [],
                success_metric=success_metric,
                source="task_workspace",
            )
        )

    def _build_trial(
        self,
        *,
        experiment: ResearchExperiment,
        trial_number: int,
        now: str,
        request: RunResearchExperimentRequest,
        granted_trials: int,
        remaining_after: int,
    ) -> ResearchTrial:
        assert experiment.spec is not None
        metric_name = experiment.spec.success_metric
        base_score = 0.32 + trial_number * 0.18
        candidate_bonus = min(len(experiment.spec.candidate_files) * 0.03, 0.18)
        progress_score = round(min(base_score + candidate_bonus, 0.98), 2)
        outcome = "review"
        if progress_score >= 0.8:
            outcome = "promote"
        elif progress_score < 0.45 and trial_number > 1:
            outcome = "discard"

        verdict = ResearchTrialVerdict(
            outcome=outcome,
            rationale=[
                "Trial stayed within the bounded iteration budget.",
                "Comparable metrics and artifact references were generated for review.",
                "Candidate-file focus stayed within the declared scope.",
            ],
            metric_delta={metric_name: progress_score},
            confidence=round(min(0.45 + progress_score / 2, 0.95), 2),
        )
        trial_status = "completed" if outcome != "discard" else "discarded"
        return ResearchTrial(
            trial_id=f"{experiment.experiment_id}-trial-{trial_number}",
            experiment_id=experiment.experiment_id,
            title=f"Trial {trial_number}",
            status=trial_status,
            summary=f"Executed bounded research trial {trial_number} for goal: {experiment.goal}",
            metrics={metric_name: progress_score},
            modified_files=list(experiment.spec.candidate_files),
            artifacts=[
                ResearchArtifactRef(
                    artifact_id=f"{experiment.experiment_id}-artifact-{trial_number}",
                    kind="metric_log",
                    label=f"Trial {trial_number} metric log",
                    path=f"artifacts/research/{experiment.experiment_id}/trial-{trial_number}-metrics.json",
                ),
                ResearchArtifactRef(
                    artifact_id=f"{experiment.experiment_id}-checkpoint-{trial_number}",
                    kind="checkpoint",
                    label=f"Trial {trial_number} checkpoint",
                    path=f"artifacts/research/{experiment.experiment_id}/trial-{trial_number}-checkpoint.json",
                ),
                ResearchArtifactRef(
                    artifact_id=f"{experiment.experiment_id}-report-{trial_number}",
                    kind="report",
                    label=f"Trial {trial_number} review summary",
                    path=f"artifacts/research/{experiment.experiment_id}/trial-{trial_number}-report.md",
                ),
            ],
            verdict=verdict,
            iteration_index=trial_number,
            budget=ResearchExecutionBudget(
                requested_trials=request.requested_trials,
                granted_trials=granted_trials,
                remaining_trials_after_run=remaining_after,
                time_budget_minutes=experiment.spec.evaluation_window_minutes,
            ),
            created_at=now,
            updated_at=now,
        )

    def run_experiment(
        self,
        experiment_id: str,
        request: RunResearchExperimentRequest,
        *,
        created_at: str | None = None,
    ) -> ResearchExperimentRunResponse | None:
        experiment = self._experiments.get(experiment_id)
        if experiment is None or experiment.spec is None:
            return None

        now = created_at or _utc_now()
        existing_trials = self._trials.setdefault(experiment_id, [])
        remaining_budget = max(experiment.spec.max_trials - len(existing_trials), 0)
        requested_trials = max(request.requested_trials, 1)
        trial_budget = min(requested_trials, remaining_budget)

        if trial_budget == 0:
            experiment.status = "completed"
            experiment.updated_at = now
            self._record_activity(
                kind="experiment_skipped",
                experiment_id=experiment_id,
                status=experiment.status,
                detail="No remaining trial budget; experiment marked completed",
            )
            return ResearchExperimentRunResponse(
                experiment=experiment,
                new_trials=[],
                runtime_snapshot=self.get_runtime_snapshot(),
            )

        experiment.status = "running"
        experiment.updated_at = now
        self._record_activity(
            kind="experiment_run_started",
            experiment_id=experiment_id,
            status="running",
            detail=f"Running up to {trial_budget} bounded trial(s)",
        )

        new_trials: list[ResearchTrial] = []
        promoted_trial_id: str | None = None
        for _ in range(trial_budget):
            trial_number = len(existing_trials) + 1
            remaining_after = max(experiment.spec.max_trials - trial_number, 0)
            trial = self._build_trial(
                experiment=experiment,
                trial_number=trial_number,
                now=now,
                request=request,
                granted_trials=trial_budget,
                remaining_after=remaining_after,
            )
            existing_trials.append(trial)
            new_trials.append(trial)
            experiment.trial_count = len(existing_trials)
            experiment.latest_trial_id = trial.trial_id
            experiment.progress_score = max(
                experiment.progress_score,
                float(trial.metrics.get(experiment.spec.success_metric, 0.0)),
            )
            experiment.updated_at = now
            self._record_activity(
                kind="trial_completed",
                experiment_id=experiment_id,
                status=trial.status,
                detail=f"{trial.title} finished with outcome={trial.verdict.outcome if trial.verdict else 'none'}",
            )
            if trial.verdict is not None and trial.verdict.outcome == "promote":
                promoted_trial_id = trial.trial_id
                experiment.promoted_trial_id = trial.trial_id
                if request.stop_on_promote:
                    experiment.status = "completed"
                    break
        else:
            experiment.status = "completed" if len(existing_trials) >= experiment.spec.max_trials else "running"

        if promoted_trial_id is not None:
            experiment.status = "completed"
        elif len(existing_trials) >= experiment.spec.max_trials:
            experiment.status = "completed"

        experiment.updated_at = now
        self._experiments[experiment_id] = experiment
        self._record_activity(
            kind="experiment_run_completed",
            experiment_id=experiment_id,
            status=experiment.status,
            detail=f"Run closed with {len(new_trials)} new trial(s)",
        )
        return ResearchExperimentRunResponse(
            experiment=experiment,
            new_trials=new_trials,
            runtime_snapshot=self.get_runtime_snapshot(),
        )


_service = ResearchRuntimeService()


def get_research_runtime_service() -> ResearchRuntimeService:
    return _service
