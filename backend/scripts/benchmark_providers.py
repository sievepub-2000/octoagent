"""Provider performance benchmark — compare LangGraph vs OpenAI Agents latency.

Run: backend/.venv/bin/python backend/scripts/benchmark_providers.py

Also tests hybrid execution strategy and per-agent provider override.
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agent_runtime.contracts import AgentExecutionRequest
from src.agent_runtime.manager import AgentRuntimeManager


async def benchmark_provider(manager: AgentRuntimeManager, provider_name: str, prompt: str, rounds: int = 3):
    """Benchmark a single provider with multiple rounds."""
    timings = []
    errors = []
    for i in range(rounds):
        request = AgentExecutionRequest(
            task_id=f"bench-{provider_name}-{i}",
            prompt=prompt,
            model_override=None,
            timeout_seconds=60,
            recursion_limit=25,
            subagent_enabled=False,
            workspace_metadata={},
        )
        start = time.perf_counter()
        try:
            result = await manager.execute(request, preferred_provider=provider_name)
            elapsed = time.perf_counter() - start
            timings.append(elapsed)
            output_len = len(result.output_text or "")
            print(f"  [{provider_name}] round {i+1}: {elapsed:.3f}s, output={output_len} chars, provider={result.provider}")
        except Exception as exc:
            elapsed = time.perf_counter() - start
            errors.append(str(exc))
            print(f"  [{provider_name}] round {i+1}: ERROR after {elapsed:.3f}s — {exc}")
    return timings, errors


async def main():
    manager = AgentRuntimeManager()
    health = manager.provider_health()

    print("=" * 60)
    print("Provider Performance Benchmark")
    print("=" * 60)
    print()

    for name, info in health.items():
        status = "✅ available" if info["available"] else f"❌ {info['detail']}"
        print(f"  {name}: {status}")
    print()

    prompt = "What is 2+2? Answer in one word."
    available_providers = [name for name, info in health.items() if info["available"]]

    results = {}
    for provider in available_providers:
        print(f"\nBenchmarking: {provider}")
        timings, errors = await benchmark_provider(manager, provider, prompt, rounds=3)
        results[provider] = {"timings": timings, "errors": errors}

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for provider, data in results.items():
        timings = data["timings"]
        if timings:
            avg = sum(timings) / len(timings)
            minv = min(timings)
            maxv = max(timings)
            print(f"  {provider}: avg={avg:.3f}s, min={minv:.3f}s, max={maxv:.3f}s ({len(timings)} ok, {len(data['errors'])} err)")
        else:
            print(f"  {provider}: all {len(data['errors'])} rounds failed")

    unavailable = [name for name, info in health.items() if not info["available"]]
    if unavailable:
        print(f"\n  Skipped (unavailable): {', '.join(unavailable)}")

    # Test agent-level provider override (per_agent/hybrid mode)
    print()
    print("=" * 60)
    print("Agent-Level Provider Override Test")
    print("=" * 60)
    for provider in available_providers:
        request = AgentExecutionRequest(
            task_id=f"override-test-{provider}",
            prompt="Say OK",
            model_override=None,
            timeout_seconds=30,
            recursion_limit=10,
            subagent_enabled=False,
            workspace_metadata={},
            agent_runtime_provider_override=provider,
        )
        try:
            result = await manager.execute(request, preferred_provider="langgraph")
            print(f"  Override to {provider} (workspace=langgraph): actual={result.provider} ✅")
        except Exception as exc:
            print(f"  Override to {provider}: ERROR — {exc}")

    print()


if __name__ == "__main__":
    asyncio.run(main())
