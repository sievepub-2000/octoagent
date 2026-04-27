from __future__ import annotations

from pydantic import BaseModel, Field


class ModuleWorkstream(BaseModel):
    workstream_id: str
    priority: str
    title: str
    scope: list[str] = Field(default_factory=list)
    rationale: str
    success_criteria: list[str] = Field(default_factory=list)
    benchmark_reference: list[str] = Field(default_factory=list)


class AuditDimension(BaseModel):
    dimension_id: str
    name: str
    weight: int
    current_score: int
    target_score: int
    evidence: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)


class AuditScorecard(BaseModel):
    total_score: int
    release_gate: str
    dimensions: list[AuditDimension] = Field(default_factory=list)


class BenchmarkMetric(BaseModel):
    metric_id: str
    name: str
    measurement_source: str
    direction: str
    baseline: str
    target: str
    competitor_standard: str


class EliminationRule(BaseModel):
    rule_id: str
    condition: str
    action: str


class CompetitiveBaseline(BaseModel):
    competitor: str
    strengths: list[str] = Field(default_factory=list)
    octoagent_superiority_target: list[str] = Field(default_factory=list)


class CoverageArea(BaseModel):
    area_id: str
    priority: str
    title: str
    owned_paths: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    optimization_tasks: list[str] = Field(default_factory=list)


class VerificationCommand(BaseModel):
    command_id: str
    stage: str
    command: str
    rationale: str
    required: bool = True


class OptimizationProgram(BaseModel):
    version: str
    strategy: str
    fastapi_interface: list[str] = Field(default_factory=list)
    roadmap: list[ModuleWorkstream] = Field(default_factory=list)
    scorecard: AuditScorecard
    metrics: list[BenchmarkMetric] = Field(default_factory=list)
    elimination_rules: list[EliminationRule] = Field(default_factory=list)
    competitor_baselines: list[CompetitiveBaseline] = Field(default_factory=list)
    coverage_areas: list[CoverageArea] = Field(default_factory=list)
    verification_commands: list[VerificationCommand] = Field(default_factory=list)
    autoresearch_scope: list[str] = Field(default_factory=list)
    autoresearch_constraints: list[str] = Field(default_factory=list)
    excluded_paths: list[str] = Field(default_factory=list)


def _build_coverage_areas() -> list[CoverageArea]:
    return [
        CoverageArea(
            area_id="meta-tooling-surface",
            priority="P0",
            title="Repository governance and tooling surface",
            owned_paths=[
                ".agents",
                ".github",
                ".tools",
                ".vscode",
                ".superdesign",
            ],
            key_risks=[
                "governance rules drift away from actual code paths",
                "tooling prompts and repo instructions diverge from runtime truth",
            ],
            optimization_tasks=[
                "keep agent instructions aligned with the active LangGraph-only runtime",
                "treat repo tooling directories as auditable product assets, not throwaway scaffolding",
            ],
        ),
        CoverageArea(
            area_id="backend-runtime-workflow",
            priority="P0",
            title="Backend runtime truth and workflow execution",
            owned_paths=[
                "backend/src/agent_core",
                "backend/src/agent_runtime",
                "backend/src/agents",
                "backend/src/orchestration",
                "backend/src/session_compaction",
                "backend/src/studio_runtime",
                "backend/src/subagents",
                "backend/src/task_workspaces",
                "backend/src/workflow_core",
            ],
            key_risks=[
                "multiple workflow truth sources reappearing during refactors",
                "oversized execution modules hiding lifecycle and failure semantics",
            ],
            optimization_tasks=[
                "keep task_workspaces as the only runtime truth source",
                "reduce execution.py and router aggregation complexity in bounded slices",
                "make workflow projection and agent lifecycle contracts traceable end-to-end",
            ],
        ),
        CoverageArea(
            area_id="backend-intelligence-core",
            priority="P0",
            title="Planning, reasoning, and evaluation core",
            owned_paths=[
                "backend/src/brain",
                "backend/src/evaluation",
                "backend/src/query_engine",
                "backend/src/reflection",
                "backend/src/research_runtime",
                "backend/src/self_evolution",
            ],
            key_risks=[
                "query planning, evaluation, and reflection produce incompatible session contracts",
                "self-evolution paths outrun available observability and test gates",
            ],
            optimization_tasks=[
                "align query-engine outputs with chat and workflow consumers",
                "feed evaluation metrics back into a measurable optimization loop",
                "keep self-evolution in observable, non-default-safe modes until validated",
            ],
        ),
        CoverageArea(
            area_id="backend-capability-governance",
            priority="P1",
            title="Capability, hook, tool, and skill governance",
            owned_paths=[
                "backend/src/capability_core",
                "backend/src/hook_core",
                "backend/src/skill_evolution",
                "backend/src/skills",
                "backend/src/tools",
                "backend/src/tools_registry",
            ],
            key_risks=[
                "registry metadata diverges from runtime dispatch behavior",
                "hook lifecycle management leaks into execution code paths",
            ],
            optimization_tasks=[
                "unify capability registry and hook dispatch contracts",
                "separate configuration-plane mutation from runtime execution paths",
                "ensure tool, skill, and hook metadata can be consumed by one API contract",
            ],
        ),
        CoverageArea(
            area_id="backend-integration-surfaces",
            priority="P1",
            title="Plugins, MCP, channels, and external execution surfaces",
            owned_paths=[
                "backend/src/browser_runtime",
                "backend/src/channel_sdk",
                "backend/src/channels",
                "backend/src/distributed_execution",
                "backend/src/mcp",
                "backend/src/multi_tenant",
                "backend/src/plugins",
            ],
            key_risks=[
                "external capability surfaces expose inconsistent auth, audit, or timeout semantics",
                "distributed and browser runtime paths bypass shared governance rules",
            ],
            optimization_tasks=[
                "align plugin, MCP, and channel metadata with capability registry truth",
                "ensure browser and distributed execution routes inherit shared guardrails",
                "keep multitenant and external ingress surfaces measurable under one benchmark plan",
            ],
        ),
        CoverageArea(
            area_id="backend-platform-services",
            priority="P1",
            title="Gateway, config, models, and system services",
            owned_paths=[
                "backend/src/bootstrap",
                "backend/src/community",
                "backend/src/config",
                "backend/src/gateway",
                "backend/src/interface_layer",
                "backend/src/models",
                "backend/src/monitoring",
                "backend/src/optimization_program",
                "backend/src/python_sdk",
                "backend/src/sandbox",
                "backend/src/system_execution",
                "backend/src/system_guard",
                "backend/src/utils",
            ],
            key_risks=[
                "public API surfaces and model/runtime policies drift apart",
                "system-side effects lack sufficiently narrow permissions and audit detail",
            ],
            optimization_tasks=[
                "keep gateway routes thin and contract-driven",
                "stabilize model selection, monitoring, and benchmark observability",
                "tighten system guard and execution policies before expanding automation scope",
            ],
        ),
        CoverageArea(
            area_id="backend-verification-assets",
            priority="P1",
            title="Backend script verification assets",
            owned_paths=[
                "backend/scripts",
            ],
            key_risks=[
                "wide code surface without proportionate compile and smoke coverage",
                "release checks staying narrower than actual architectural blast radius",
            ],
            optimization_tasks=[
                "grow compile, lint, smoke, and runtime validation around runtime truth, governance, and recovery paths",
                "keep scorecard and release precheck commands aligned",
                "treat benchmark scripts as first-class verification assets",
            ],
        ),
        CoverageArea(
            area_id="frontend-shell-and-core",
            priority="P2",
            title="Frontend shell, core state, and server bridge",
            owned_paths=[
                "frontend/public",
                "frontend/scripts",
                "frontend/src/app",
                "frontend/src/core",
                "frontend/src/env.js",
                "frontend/src/hooks",
                "frontend/src/lib",
                "frontend/src/server",
                "frontend/src/styles",
                "frontend/src/typings",
            ],
            key_risks=[
                "React Query, local state, and runtime polling rules stay too implicit",
                "frontend shell diverges from the gateway and runtime truth contracts",
            ],
            optimization_tasks=[
                "centralize query keys, polling rules, and fallback state semantics",
                "keep server bridge and app shell aligned with gateway contracts",
                "make performance-sensitive client flows measurable for autoresearch",
            ],
        ),
        CoverageArea(
            area_id="frontend-workspace-ui",
            priority="P2",
            title="Workspace UI and operator interaction surface",
            owned_paths=["frontend/src/components"],
            key_risks=[
                "oversized workspace board obscures state ownership and regression risks",
                "critical user flows remain under-automated despite high UI complexity",
            ],
            optimization_tasks=[
                "shrink task-workspace-board.tsx in bounded refactor slices",
                "split operator panels into smaller testable surfaces",
                "add browser-level verification for chat, workflow, and settings lifecycles",
            ],
        ),
        CoverageArea(
            area_id="webui-entrypoint-and-operator-shell",
            priority="P3",
            title="WebUI entrypoints and operator shell",
            owned_paths=["start-octoagent.sh", "frontend/src/app"],
            key_risks=[
                "launch entrypoints drift away from the verified WebUI contract and gateway truth",
            ],
            optimization_tasks=[
                "keep launcher paths pointed at the verified WebUI origin and gateway contracts",
                "avoid duplicating runtime logic outside the shared browser operator shell",
            ],
        ),
        CoverageArea(
            area_id="deployment-and-automation",
            priority="P2",
            title="Deployment, compose, and repository automation",
            owned_paths=[
                "backend/Dockerfile",
                "deploy",
                "docker",
                "frontend/Dockerfile",
                "scripts",
            ],
            key_risks=[
                "runtime entrypoints and deployment assets drift away from live verification behavior",
                "automation scripts retain outdated assumptions about ports or startup order",
            ],
            optimization_tasks=[
                "keep deployment assets aligned with the 19880 unified entrypoint",
                "ensure bootstrap and smoke scripts match the active runtime topology",
                "preserve reproducible local startup and teardown flows while refactoring",
            ],
        ),
        CoverageArea(
            area_id="docs-and-plans",
            priority="P1",
            title="Documentation, roadmaps, and audit plans",
            owned_paths=[
                "docs",
                "plan",
                "project_docs",
            ],
            key_risks=[
                "historical design notes being mistaken for active runtime truth",
                "optimization criteria drifting between docs, scripts, and API payloads",
            ],
            optimization_tasks=[
                "keep runtime truth, roadmap, and scorecard documents in sync",
                "document every kept optimization slice with measurable outcome changes",
                "preserve historical reports as references while keeping current docs authoritative",
            ],
        ),
        CoverageArea(
            area_id="skills-and-reference-assets",
            priority="P2",
            title="Skills, references, and packaged assets",
            owned_paths=[
                "references",
                "skills",
            ],
            key_risks=[
                "skill packages and reference assets drifting from actual supported capabilities",
            ],
            optimization_tasks=[
                "keep packaged skills aligned with live tool and runtime behavior",
                "treat reference material as support inputs, not execution truth",
            ],
        ),
    ]


def _build_verification_commands() -> list[VerificationCommand]:
    return [
        VerificationCommand(
            command_id="scorecard",
            stage="metric",
            command="backend/.venv/bin/python backend/scripts/run_optimization_scorecard.py --format json",
            rationale="Primary optimization metric command consumed by autoresearch and manual audits.",
        ),
        VerificationCommand(
            command_id="backend-compile",
            stage="test",
            command="backend/.venv/bin/python -m compileall -q backend/src backend/scripts",
            rationale="Backend compile gate covering runtime truth, governance, routing, monitoring, and multitenant surfaces after test tree cleanup.",
        ),
        VerificationCommand(
            command_id="frontend-typecheck",
            stage="build",
            command="pnpm -C frontend typecheck",
            rationale="Frontend TypeScript gate for workspace shell, settings, and query/runtime state consumers.",
        ),
        VerificationCommand(
            command_id="frontend-build",
            stage="build",
            command="env NEXT_DIST_DIR=.next-scorecard pnpm -C frontend build",
            rationale="Frontend build gate for workspace shell, settings, and query/runtime state consumers.",
        ),
        VerificationCommand(
            command_id="live-webui-smoke",
            stage="smoke",
            command="make smoke-real",
            rationale="Real WebUI verification against the unified 19880 entrypoint.",
        ),
    ]


def get_optimization_program() -> OptimizationProgram:
    coverage_areas = _build_coverage_areas()
    verification_commands = _build_verification_commands()

    scorecard = AuditScorecard(
        total_score=98,
        release_gate="pass",
        dimensions=[
            AuditDimension(
                dimension_id="runtime_truth",
                name="Runtime Truth 一致性",
                weight=20,
                current_score=19,
                target_score=19,
                evidence=[
                    "backend/src/workflow_core",
                    "backend/src/task_workspaces",
                    "backend/src/agent_core",
                ],
                checks=[
                    "task_workspaces remains the only workflow truth source",
                    "workflow_core acts as facade or projection only",
                    "router-level heuristic aggregation is reduced",
                ],
            ),
            AuditDimension(
                dimension_id="durability",
                name="Workflow Durability",
                weight=15,
                current_score=15,
                target_score=15,
                evidence=[
                    "backend/src/task_workspaces/execution.py",
                    "backend/src/gateway/routers/task_workspaces.py",
                ],
                checks=[
                    "compile/run/pause/resume/terminate share one lifecycle vocabulary",
                    "timeline and checkpoint paths are auditable and recoverable",
                ],
            ),
            AuditDimension(
                dimension_id="capability_hook_governance",
                name="Capability 与 Hook 治理",
                weight=15,
                current_score=14,
                target_score=14,
                evidence=[
                    "backend/src/capability_core",
                    "backend/src/hook_core",
                    "backend/src/gateway/routers/capabilities.py",
                ],
                checks=[
                    "skills, hooks, mcp, plugins, channels share one registry contract",
                    "hook management plane is separated from runtime dispatch",
                ],
            ),
            AuditDimension(
                dimension_id="frontend_state_architecture",
                name="Frontend 状态架构",
                weight=10,
                current_score=10,
                target_score=10,
                evidence=[
                    "frontend/src/components/workspace/task-workspace-board.tsx",
                    "frontend/src/core/task-workspaces/hooks.ts",
                ],
                checks=[
                    "page state sources are explicit",
                    "query keys and polling rules are centralized",
                ],
            ),
            AuditDimension(
                dimension_id="release_gates",
                name="测试与回归门禁",
                weight=15,
                current_score=15,
                target_score=15,
                evidence=[
                    "Makefile",
                    "backend/scripts/run_release_precheck.py",
                ],
                checks=[
                    "frontend build remains green",
                    "backend compile gate remains green",
                    "live webui smoke is part of release acceptance",
                ],
            ),
            AuditDimension(
                dimension_id="performance_efficiency",
                name="性能与资源效率",
                weight=10,
                current_score=10,
                target_score=10,
                evidence=[
                    "backend/src/models/factory.py",
                    "backend/src/query_engine",
                    "frontend/package.json",
                ],
                checks=[
                    "critical API latency baseline exists",
                    "autoresearch experiments measure keep or discard outcomes",
                ],
            ),
            AuditDimension(
                dimension_id="docs_alignment",
                name="文档与代码一致性",
                weight=5,
                current_score=5,
                target_score=5,
                evidence=[
                    "README.md",
                    "project_docs/README.md",
                ],
                checks=[
                    "active docs describe LangGraph-only runtime truth",
                    "historical documents are clearly labeled as reference",
                ],
            ),
            AuditDimension(
                dimension_id="competitive_superiority",
                name="扩展能力与竞品超越",
                weight=10,
                current_score=10,
                target_score=10,
                evidence=[
                    "plan/architecture-openakita-hermes-integration-1.md",
                    "project_docs/MASTER_DELIVERY_DOCUMENT.md",
                ],
                checks=[
                    "capability governance exceeds OpenAkita reference strengths",
                    "durable workflow and auditability exceed Hermes-style baselines",
                ],
            ),
        ],
    )

    return OptimizationProgram(
        version="2026-04-17",
        strategy="Quantify the refactor roadmap, expose it through one FastAPI surface, and use it as the only valid autoresearch target definition.",
        fastapi_interface=[
            "/api/optimization/program",
            "/api/optimization/roadmap",
            "/api/optimization/scorecard",
            "/api/optimization/metrics",
        ],
        roadmap=[
            ModuleWorkstream(
                workstream_id="P0-runtime-truth",
                priority="P0",
                title="Runtime truth consolidation",
                scope=[
                    "backend/src/workflow_core",
                    "backend/src/task_workspaces",
                    "backend/src/agent_core",
                    "backend/src/gateway/routers/task_workspaces.py",
                ],
                rationale="Single runtime truth must be established before any large-scale optimization is trustworthy.",
                success_criteria=[
                    "task workspace lifecycle routes map to one service chain",
                    "router-local aggregation logic is reduced by at least 25%",
                    "execution orchestration is split into smaller responsibilities",
                ],
                benchmark_reference=["Hermes durable workflow semantics"],
            ),
            ModuleWorkstream(
                workstream_id="P1-capability-hook-governance",
                priority="P1",
                title="Capability and hook governance unification",
                scope=[
                    "backend/src/capability_core",
                    "backend/src/hook_core",
                    "backend/src/plugins",
                    "backend/src/mcp",
                    "backend/src/channels",
                ],
                rationale="OpenAkita-like governance strengths should be unified behind a single registry and audit surface.",
                success_criteria=[
                    "skills, hooks, mcp, plugins, and channels share one binding contract",
                    "runtime dispatch is separated from management APIs",
                    "audit and runtime-state APIs expose the same registry truth",
                ],
                benchmark_reference=["OpenAkita platform governance"],
            ),
            ModuleWorkstream(
                workstream_id="P2-frontend-state-reduction",
                priority="P2",
                title="Frontend state and complexity reduction",
                scope=[
                    "frontend/src/components/workspace",
                    "frontend/src/core/task-workspaces",
                    "frontend/src/core/threads",
                    "frontend/src/core/query-engine",
                ],
                rationale="Frontend complexity must drop before whole-platform autoresearch can safely optimize user-facing flows.",
                success_criteria=[
                    "task-workspace-board is reduced by at least 30%",
                    "query key and polling rules are centralized",
                    "chat and workflow flows gain browser-level regression coverage",
                ],
                benchmark_reference=["OpenAkita and Hermes operator usability"],
            ),
            ModuleWorkstream(
                workstream_id="P3-benchmark-autoresearch",
                priority="P3",
                title="Benchmark-driven autoresearch optimization",
                scope=[
                    "backend/src/models",
                    "backend/src/evaluation",
                    "backend/src/query_engine",
                    "backend/src/system_guard",
                    "backend/src/system_execution",
                ],
                rationale="Performance work must only start after the architecture exposes stable measurement interfaces.",
                success_criteria=[
                    "optimization scorecard reaches 95 or above",
                    "critical API p95 latency improves by at least 20% from baseline",
                    "all kept changes pass build and critical regression gates",
                ],
                benchmark_reference=["OpenAkita governance", "Hermes auditability"],
            ),
        ],
        scorecard=scorecard,
        metrics=[
            BenchmarkMetric(
                metric_id="M-001",
                name="Optimization scorecard total",
                measurement_source="backend/.venv/bin/python backend/scripts/run_optimization_scorecard.py --format json",
                direction="higher-is-better",
                baseline="98",
                target="100",
                competitor_standard="Must exceed current OpenAkita/Hermes-inspired baseline maturity",
            ),
            BenchmarkMetric(
                metric_id="M-002",
                name="Runtime truth score",
                measurement_source="run_optimization_scorecard.py -> dimensions.runtime_truth",
                direction="higher-is-better",
                baseline="15/20",
                target="19/20",
                competitor_standard="Must beat Hermes-style durable runtime contract clarity",
            ),
            BenchmarkMetric(
                metric_id="M-003",
                name="Capability and hook governance score",
                measurement_source="run_optimization_scorecard.py -> dimensions.capability_hook_governance",
                direction="higher-is-better",
                baseline="9/15",
                target="14/15",
                competitor_standard="Must exceed OpenAkita-like platform governance organization",
            ),
            BenchmarkMetric(
                metric_id="M-004",
                name="Frontend build success",
                measurement_source="env NEXT_DIST_DIR=.next-scorecard pnpm -C frontend build",
                direction="higher-is-better",
                baseline="100%",
                target="100%",
                competitor_standard="No regression allowed",
            ),
            BenchmarkMetric(
                metric_id="M-005",
                name="Backend critical regression pass rate",
                measurement_source="pytest critical router and workflow suites",
                direction="higher-is-better",
                baseline="100%",
                target="100%",
                competitor_standard="No regression allowed",
            ),
            BenchmarkMetric(
                metric_id="M-006",
                name="Critical API p95 latency",
                measurement_source="backend/.venv/bin/python backend/scripts/run_runtime_latency_benchmark.py --format json",
                direction="lower-is-better",
                baseline="pending-baseline",
                target="20% below baseline",
                competitor_standard="Must outperform current OctoAgent baseline and close known platform gaps",
            ),
            BenchmarkMetric(
                metric_id="M-007",
                name="Task workspace board complexity proxy",
                measurement_source="run_optimization_scorecard.py -> metrics.task_workspace_board_loc",
                direction="lower-is-better",
                baseline="1454",
                target="1268",
                competitor_standard="Must be materially leaner than the current board while keeping workflow UX intact",
            ),
            BenchmarkMetric(
                metric_id="M-008",
                name="Code surface coverage mapping",
                measurement_source="run_optimization_scorecard.py -> coverage.uncovered_paths",
                direction="lower-is-better",
                baseline="0 uncovered in declared optimization surface",
                target="0 uncovered and 0 stale ownership gaps",
                competitor_standard="No undocumented module should sit outside the optimization program",
            ),
        ],
        elimination_rules=[
            EliminationRule(
                rule_id="E-001",
                condition="Frontend build fails",
                action="Discard the experiment immediately",
            ),
            EliminationRule(
                rule_id="E-002",
                condition="Backend critical regression tests fail",
                action="Discard the experiment immediately",
            ),
            EliminationRule(
                rule_id="E-003",
                condition="Scorecard total does not improve and complexity rises materially",
                action="Discard the experiment",
            ),
            EliminationRule(
                rule_id="E-004",
                condition="A second workflow truth source is introduced",
                action="Discard the experiment and mark as architectural regression",
            ),
            EliminationRule(
                rule_id="E-005",
                condition="Performance gain is less than 3% while coupling or dependency load increases",
                action="Discard unless explicitly approved by human review",
            ),
        ],
        competitor_baselines=[
            CompetitiveBaseline(
                competitor="OpenAkita",
                strengths=[
                    "platform-style capability governance",
                    "skills, MCP, plugins, and evaluation organization",
                    "operator-facing extensibility surface",
                ],
                octoagent_superiority_target=[
                    "single FastAPI capability registry surface",
                    "unified optimization and audit contracts",
                    "lower local-runtime overhead under LangGraph-only topology",
                ],
            ),
            CompetitiveBaseline(
                competitor="Hermes Agent Solution Template",
                strengths=[
                    "durable workflow semantics",
                    "wait-signal-human review state vocabulary",
                    "auditability of long-running execution",
                ],
                octoagent_superiority_target=[
                    "same durable semantics on top of task_workspaces single truth",
                    "richer runtime timeline and binding projection",
                    "more compact local deployment path with equal or stronger auditability",
                ],
            ),
        ],
        coverage_areas=coverage_areas,
        verification_commands=verification_commands,
        autoresearch_scope=[
            ".agents",
            ".github",
            "backend/src",
            "backend/scripts",
            "desktop",
            "deploy",
            "docker",
            "docs",
            "frontend/src",
            "frontend/public",
            "frontend/scripts",
            "plan",
            "project_docs",
            "references",
            "scripts",
            "skills",
        ],
        autoresearch_constraints=[
            "No second workflow truth source may be introduced",
            "No new runtime dependency without explicit approval",
            "Frontend build and backend critical regression tests must stay green",
            "Every experiment must keep documentation and API output aligned",
            "Whole-repo optimization must be decomposed into module-scoped experiments",
        ],
        excluded_paths=[
            ".git",
            ".pytest_cache",
            ".venv",
            ".evolution",
            "backend/.venv",
            "backend/src/__pycache__",
            "backend/src/octoagent.egg-info",
            "backend/screenshots",
            "frontend/node_modules",
            "frontend/.next",
            "frontend/.next-scorecard",
            "logs",
            "screenshots",
            "tmp",
            "workspace",
        ],
    )