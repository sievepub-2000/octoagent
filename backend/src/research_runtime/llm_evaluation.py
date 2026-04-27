"""LLM-backed evaluation for research runtime experiments.

When an LLM provider is available, this module can evaluate
trial results using model inference rather than deterministic
scoring formulas.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


async def llm_evaluate_trial(
    *,
    experiment_goal: str,
    trial_description: str,
    candidate_files: list[str],
    success_metric: str,
    invoke_fn: Callable[..., Any] | None = None,
) -> dict[str, float]:
    """Evaluate a research trial using an LLM provider.

    If *invoke_fn* is None or the call fails, falls back to
    deterministic scoring.

    Returns:
        Dictionary with metric_name → score (0.0–1.0).
    """
    if invoke_fn is None:
        return {}

    prompt = (
        f"You are evaluating a research trial.\n"
        f"Goal: {experiment_goal}\n"
        f"Trial: {trial_description}\n"
        f"Files modified: {', '.join(candidate_files[:10])}\n"
        f"Success metric: {success_metric}\n\n"
        f"Rate this trial on a scale of 0.0 to 1.0 for the metric '{success_metric}'.\n"
        f"Respond with ONLY a decimal number between 0.0 and 1.0."
    )

    try:
        response = await invoke_fn(prompt)
        text = str(response).strip()
        # Extract first float-like token
        for token in text.split():
            try:
                score = float(token)
                if 0.0 <= score <= 1.0:
                    return {success_metric: round(score, 3)}
            except ValueError:
                continue
        logger.warning("LLM evaluation returned non-numeric response: %s", text[:100])
        return {}
    except Exception:
        logger.warning("LLM evaluation failed, falling back to deterministic scoring", exc_info=True)
        return {}


def get_llm_invoke_fn():
    """Try to obtain an LLM invoke function from the model router.

    Returns None if no provider is available.
    """
    try:
        from src.model_router import get_model_router_service

        router = get_model_router_service()
        if not hasattr(router, "invoke"):
            return None

        async def _invoke(prompt: str) -> str:
            return await router.invoke(prompt)

        return _invoke
    except Exception:
        return None
