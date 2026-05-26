"""Summarize chat regression trend JSONL into operator-readable reports."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@dataclass
class ChatRegressionTrendSummary:
    ok: bool
    source_path: str
    record_count: int
    first_recorded_at: str | None = None
    last_recorded_at: str | None = None
    min_render_ms: int = 0
    avg_render_ms: float = 0.0
    p95_render_ms: int = 0
    max_render_ms: int = 0
    min_message_count: int = 0
    max_message_count: int = 0
    stable_record_count: int = 0
    critical_browser_error_count: int = 0
    thresholds: dict[str, int] = field(default_factory=dict)
    threshold_breaches: list[str] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Invalid JSONL at {path}:{line_number}: record must be an object")
        records.append(payload)
    return records


def _percentile_95(values: list[int]) -> int:
    if not values:
        return 0
    if len(values) == 1:
        return values[0]
    return int(statistics.quantiles(values, n=100, method="inclusive")[94])


def summarize_trends(path: Path, *, max_render_ms: int = 5000, min_message_count: int = 520) -> ChatRegressionTrendSummary:
    records = _load_records(path)
    render_values = [int(item.get("long_scroll_render_ms") or 0) for item in records]
    message_counts = [int(item.get("long_scroll_message_count") or 0) for item in records]
    stable_count = sum(1 for item in records if bool(item.get("long_scroll_stable")))
    critical_errors = sum(int(item.get("critical_browser_error_count") or 0) for item in records)
    breaches: list[str] = []
    if not records:
        breaches.append("no_trend_records")
    if render_values and max(render_values) > max_render_ms:
        breaches.append(f"render_ms exceeded threshold: max={max(render_values)} threshold={max_render_ms}")
    if message_counts and min(message_counts) < min_message_count:
        breaches.append(f"message_count below threshold: min={min(message_counts)} threshold={min_message_count}")
    if stable_count != len(records):
        breaches.append(f"unstable_records detected: stable={stable_count} total={len(records)}")
    if critical_errors:
        breaches.append(f"critical_browser_errors detected: count={critical_errors}")
    timestamps = [str(item.get("recorded_at")) for item in records if item.get("recorded_at")]
    return ChatRegressionTrendSummary(
        ok=not breaches,
        source_path=str(path),
        record_count=len(records),
        first_recorded_at=timestamps[0] if timestamps else None,
        last_recorded_at=timestamps[-1] if timestamps else None,
        min_render_ms=min(render_values) if render_values else 0,
        avg_render_ms=round(sum(render_values) / len(render_values), 2) if render_values else 0.0,
        p95_render_ms=_percentile_95(render_values),
        max_render_ms=max(render_values) if render_values else 0,
        min_message_count=min(message_counts) if message_counts else 0,
        max_message_count=max(message_counts) if message_counts else 0,
        stable_record_count=stable_count,
        critical_browser_error_count=critical_errors,
        thresholds={"max_render_ms": max_render_ms, "min_message_count": min_message_count},
        threshold_breaches=breaches,
    )


def write_markdown_report(path: Path, summary: ChatRegressionTrendSummary) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    status = "OK" if summary.ok else "FAIL"
    breaches = "\n".join(f"- {item}" for item in summary.threshold_breaches) or "No threshold breaches."
    content = f"""# Chat Regression Trend Report

Generated at: {summary.generated_at}

Source: `{summary.source_path}`

Overall status: **{status}**

| Metric | Threshold | Observed | Status |
| --- | ---: | ---: | --- |
| Max render ms | {summary.thresholds["max_render_ms"]} | {summary.max_render_ms} | {"OK" if summary.max_render_ms <= summary.thresholds["max_render_ms"] and summary.record_count else "FAIL"} |
| Min message count | {summary.thresholds["min_message_count"]} | {summary.min_message_count} | {"OK" if summary.min_message_count >= summary.thresholds["min_message_count"] and summary.record_count else "FAIL"} |
| Stable records | {summary.record_count} | {summary.stable_record_count} | {"OK" if summary.stable_record_count == summary.record_count and summary.record_count else "FAIL"} |
| Critical browser errors | 0 | {summary.critical_browser_error_count} | {"OK" if summary.critical_browser_error_count == 0 else "FAIL"} |

## Window

- First record: {summary.first_recorded_at or "-"}
- Last record: {summary.last_recorded_at or "-"}
- Records: {summary.record_count}
- Average render: {summary.avg_render_ms} ms
- P95 render: {summary.p95_render_ms} ms

## Threshold Breaches

{breaches}
"""
    path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(BACKEND_ROOT / "reports" / "chat-regression-trends.jsonl"))
    parser.add_argument("--json-output", default=str(BACKEND_ROOT / "reports" / "chat-regression-trends-summary.json"))
    parser.add_argument("--markdown-output", default=str(BACKEND_ROOT / "reports" / "chat-regression-trends.md"))
    parser.add_argument("--max-render-ms", type=int, default=5000)
    parser.add_argument("--min-message-count", type=int, default=520)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summary = summarize_trends(
        Path(args.input),
        max_render_ms=max(1, args.max_render_ms),
        min_message_count=max(1, args.min_message_count),
    )
    json_output = Path(args.json_output)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(asdict(summary), ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(Path(args.markdown_output), summary)
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2 if args.json else None))
    return 0 if summary.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
