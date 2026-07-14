from __future__ import annotations

import asyncio

from src.harness.deep_agent import DeepAgentConfig, DeepAgentExecutor, TaskPlan
from src.harness.work_bus_redis import WorkBusRedis


def test_work_bus_falls_back_to_in_process_pubsub(monkeypatch):
    monkeypatch.setenv("OCTO_WORK_BUS_REDIS", "0")
    monkeypatch.setattr("src.harness.work_bus_redis._resolve_postgres_dsn", lambda: None)

    async def scenario() -> None:
        bus = WorkBusRedis()
        subscriber = bus.subscribe("thread-a")
        next_event = asyncio.create_task(subscriber.__anext__())
        await asyncio.sleep(0)
        await bus.publish_step_event(
            thread_id="thread-a",
            plan_id="plan-a",
            kind="step_completed",
            step_id="step-a",
            status="completed",
            title="Collect inputs",
        )
        event = await asyncio.wait_for(next_event, timeout=1)
        await subscriber.aclose()

        assert event["thread_id"] == "thread-a"
        assert event["kind"] == "step_completed"
        assert event["sequence"] == 1
        snapshot = await bus.get_active_steps("thread-a")
        assert [item["event_id"] for item in snapshot] == [event["event_id"]]

    asyncio.run(scenario())


def test_deep_agent_solidifies_completed_multistep_plan(tmp_path):
    def tool_executor(tool_name: str, tool_args: dict) -> str:
        return f"ok:{tool_name}:{tool_args.get('index')}"

    config = DeepAgentConfig(
        enable_work_bus=False,
        solidification_output_dir=str(tmp_path),
        solidification_min_steps=4,
    )
    agent = DeepAgentExecutor(config=config, tool_executor=tool_executor)
    plan = TaskPlan(goal="Prepare weekly operations report")
    for index in range(4):
        plan.add_step(
            f"Step {index + 1}",
            tool_name="noop",
            tool_args={"index": index},
        )

    result = agent.execute_plan(plan)

    assert result.status == "completed"
    skill_path = result.metadata.get("solidified_skill_path")
    assert skill_path is not None
    content = tmp_path.joinpath(skill_path.split(str(tmp_path), 1)[1].lstrip("/")).read_text(encoding="utf-8")
    assert "name: deep-agent-prepare-weekly-operations-report" in content
    assert "Captured from a successful DeepAgent workflow." in content


def test_deep_agent_async_execution_publishes_work_bus_events(monkeypatch):
    monkeypatch.setenv("OCTO_WORK_BUS_REDIS", "0")
    monkeypatch.setattr("src.harness.work_bus_redis._resolve_postgres_dsn", lambda: None)

    import src.harness.work_bus_redis as work_bus_module

    bus = WorkBusRedis()
    monkeypatch.setattr(work_bus_module, "_work_bus", bus)

    async def tool_executor(tool_name: str, tool_args: dict) -> str:
        return f"done:{tool_name}:{tool_args['value']}"

    async def scenario() -> None:
        agent = DeepAgentExecutor(
            config=DeepAgentConfig(enable_skill_solidification=False),
            async_tool_executor=tool_executor,
        )
        plan = TaskPlan(goal="Inspect pipeline", metadata={"thread_id": "thread-b"})
        plan.add_step("Check first stage", tool_name="check", tool_args={"value": 1})
        plan.add_step("Check second stage", tool_name="check", tool_args={"value": 2})

        await agent.aexecute_plan(plan)
        events = await bus.get_active_steps("thread-b")

        kinds = [event["kind"] for event in events]
        assert kinds[0] == "plan_started"
        assert kinds[-1] == "plan_completed"
        assert kinds.count("step_started") == 2
        assert kinds.count("step_completed") == 2
        assert events[-1]["status"] == "completed"

    asyncio.run(scenario())
