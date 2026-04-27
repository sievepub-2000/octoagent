"""Unified service facade for the Brain Core skeleton."""

from __future__ import annotations

import logging
from typing import Any

from .builder_actions import BrainBuilderActionModelBuilder
from .contracts import BrainModelRecommendation, BrainModuleReport, BrainResponse, BrainTaskContext
from .evidence import BrainEvidenceRouter
from .execution_contracts import BrainExecutionContractBuilder
from .memory_reasoner import BrainMemoryReasoner
from .model_router import BrainModelRouter
from .modules import BrainModuleRegistry
from .planner import BrainPlanner
from .policy import BrainPolicy
from .quant import BrainQuantEngine
from .research import BrainResearcher
from .strategy_graph import StrategyGraphValidator
from .strategy_pack import BrainStrategyPack

logger = logging.getLogger(__name__)


class BrainCoreService:
    """Coordinate planner, research, quant, and policy modules."""

    def __init__(self):
        self.planner = BrainPlanner()
        self.policy = BrainPolicy()
        self.model_router = BrainModelRouter()
        self.validator = StrategyGraphValidator()
        self.contracts = BrainExecutionContractBuilder()
        self.builder_actions = BrainBuilderActionModelBuilder()
        self.strategy_pack = BrainStrategyPack()
        self.modules = BrainModuleRegistry(
            [
                BrainResearcher(),
                BrainEvidenceRouter(),
                BrainMemoryReasoner(),
                BrainQuantEngine(),
            ]
        )

    def describe_modules(self):
        return self.modules.list_descriptors()

    def run(self, context: BrainTaskContext) -> BrainResponse:
        plan = self.planner.build_plan(context)
        strategy_graph = self.planner.build_strategy_graph(context)
        strategy_validation = self.validator.validate(strategy_graph)
        module_reports: list[BrainModuleReport] = []
        for module in self.modules.iter_supported(context):
            module_analysis = module.analyze(context)
            module_reports.append(
                BrainModuleReport(
                    name=module.name,
                    findings=module_analysis.findings,
                    risks=module_analysis.risks,
                    confidence=module_analysis.confidence,
                )
            )

        summary = self.strategy_pack.merge(module_reports)
        analysis = summary.merged_analysis
        if strategy_validation.warnings:
            analysis.findings.extend(
                [f"Fusion warning: {warning}" for warning in strategy_validation.warnings]
            )
        if strategy_validation.errors:
            analysis.risks.extend(
                [f"Fusion error: {error}" for error in strategy_validation.errors]
            )
        decision = self.policy.decide(context, analysis)
        model_rec = self.model_router.route(context, analysis, decision)
        execution_contract = self.contracts.build(context, analysis, decision)
        builder_action_model = self.builder_actions.build(
            context,
            analysis,
            decision,
            execution_contract,
        )
        return BrainResponse(
            plan=plan,
            analysis=analysis,
            module_reports=module_reports,
            decision=decision,
            execution_contract=execution_contract,
            builder_action_model=builder_action_model,
            strategy_graph=strategy_graph,
            strategy_validation=strategy_validation,
            model_recommendation=BrainModelRecommendation(
                tier=model_rec.tier,
                reason=model_rec.reason,
                suggested_capabilities=model_rec.suggested_capabilities,
                fallback_tier=model_rec.fallback_tier,
            ),
        )

    async def execute_plan(
        self,
        context: BrainTaskContext,
        *,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        """Run the brain planning pipeline and dispatch execution to the task workspace.

        If *task_id* is provided, the plan is executed through the
        TaskWorkspaceExecutionController so decisions translate into
        real agent actions.
        """
        brain_response = self.run(context)

        execution_summary: dict[str, Any] = {
            "plan_steps": len(brain_response.plan.steps) if brain_response.plan else 0,
            "decision": brain_response.decision.action if brain_response.decision else "none",
            "module_reports": len(brain_response.module_reports),
            "strategy_valid": (
                not brain_response.strategy_validation.errors
                if brain_response.strategy_validation
                else True
            ),
        }

        # Dispatch execution via TaskWorkspace if task_id is available
        if task_id is not None:
            try:
                from src.workflow_core import (
                    TaskWorkflowModule,
                    get_workflow_core_service,
                    safe_auto_execute_workspace,
                )

                ws_service = get_workflow_core_service()
                workspace = ws_service.get_workspace(task_id) if hasattr(ws_service, "get_workspace") else None
                if workspace is not None:

                    def _merge_workspace_metadata(_task_id: str, **metadata):
                        if hasattr(ws_service, "merge_workspace_metadata"):
                            return ws_service.merge_workspace_metadata(_task_id, **metadata)
                        return None

                    await safe_auto_execute_workspace(
                        workspace,
                        merge_workspace_metadata=_merge_workspace_metadata,
                        workflow_module_factory=TaskWorkflowModule,
                    )
                    execution_summary["execution_dispatched"] = True
                else:
                    execution_summary["execution_dispatched"] = False
                    execution_summary["reason"] = "workspace_not_found"
            except Exception:
                logger.warning("Brain execute_plan: task workspace execution failed", exc_info=True)
                execution_summary["execution_dispatched"] = False
                execution_summary["reason"] = "execution_error"

            # Publish completion through AgentCore so runtime-facing hook emission stays centralized.
            try:
                from src.agent_core import get_agent_core_service

                get_agent_core_service().dispatch_execution_completed_event(
                    task_id,
                    source="brain_core",
                    payload={
                        "plan_steps": execution_summary["plan_steps"],
                        "decision": execution_summary["decision"],
                    },
                )
            except Exception:
                logger.warning("Brain execute_plan: failed to dispatch hook event", exc_info=True)

        return execution_summary
