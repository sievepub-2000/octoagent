from __future__ import annotations

from src.agents.resource_profile import _TIER_DEFAULTS


def test_recursion_defaults_support_deep_research() -> None:
    """Each hardware tier must supply enough super-steps for realistic deep-research runs.

    Anti-loop protection comes from ProgressStallMiddleware / ToolBudgetMiddleware,
    not from a low recursion_limit.  At ~18 super-steps per visible tool round:
      tiny   2_000  -> ~111 tool rounds  (minimal hardware, still reasonable)
      small  5_000  -> ~277 tool rounds
      medium 10_000 -> ~555 tool rounds
      large  20_000 -> ~1111 tool rounds  (was 400 -> caused GraphRecursionError at step 22)
    """
    assert _TIER_DEFAULTS["tiny"]["recursion_default"] >= 1_000
    assert _TIER_DEFAULTS["small"]["recursion_default"] >= 3_000
    assert _TIER_DEFAULTS["medium"]["recursion_default"] >= 8_000
    assert _TIER_DEFAULTS["large"]["recursion_default"] >= 15_000
    assert _TIER_DEFAULTS["large"]["workspace_recursion_default"] >= 40_000
