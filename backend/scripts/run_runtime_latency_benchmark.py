from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class EndpointBenchmark:
    name: str
    path: str
    method: str = "GET"


@dataclass(frozen=True)
class EndpointSample:
    elapsed_ms: float
    ok: bool
    status_code: int | None
    error: str | None = None


def _endpoint_catalog() -> list[EndpointBenchmark]:
    return [
        EndpointBenchmark(name="health", path="/health"),
        EndpointBenchmark(name="models", path="/api/models"),
        EndpointBenchmark(name="optimization_program", path="/api/optimization/program"),
        EndpointBenchmark(name="metrics_json", path="/api/metrics/json"),
    ]


def _percentile(sorted_values: list[float], ratio: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (len(sorted_values) - 1) * ratio
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return sorted_values[lower]
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def _request_once(base_url: str, endpoint: EndpointBenchmark, timeout_seconds: float) -> EndpointSample:
    url = f"{base_url.rstrip('/')}{endpoint.path}"
    request = Request(url, method=endpoint.method)
    started_at = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response.read()
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            return EndpointSample(
                elapsed_ms=round(elapsed_ms, 3),
                ok=200 <= response.status < 400,
                status_code=response.status,
            )
    except HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        return EndpointSample(
            elapsed_ms=round(elapsed_ms, 3),
            ok=False,
            status_code=exc.code,
            error=str(exc),
        )
    except URLError as exc:
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        return EndpointSample(
            elapsed_ms=round(elapsed_ms, 3),
            ok=False,
            status_code=None,
            error=str(exc.reason),
        )


def _summarize_samples(samples: list[EndpointSample]) -> dict[str, Any]:
    latencies = sorted(sample.elapsed_ms for sample in samples)
    failures = [asdict(sample) for sample in samples if not sample.ok]
    return {
        "rounds": len(samples),
        "success_count": sum(1 for sample in samples if sample.ok),
        "failure_count": len(failures),
        "p50_ms": round(_percentile(latencies, 0.50), 3),
        "p95_ms": round(_percentile(latencies, 0.95), 3),
        "mean_ms": round(statistics.fmean(latencies), 3) if latencies else 0.0,
        "max_ms": round(max(latencies), 3) if latencies else 0.0,
        "failures": failures,
    }


def run_benchmark(base_url: str, rounds: int, timeout_seconds: float) -> dict[str, Any]:
    endpoints = _endpoint_catalog()
    endpoint_results: dict[str, Any] = {}
    all_latencies: list[float] = []

    for endpoint in endpoints:
        samples = [_request_once(base_url, endpoint, timeout_seconds) for _ in range(rounds)]
        endpoint_results[endpoint.name] = {
            "path": endpoint.path,
            "method": endpoint.method,
            **_summarize_samples(samples),
        }
        all_latencies.extend(sample.elapsed_ms for sample in samples)

    overall = {
        "endpoint_count": len(endpoints),
        "overall_p50_ms": round(_percentile(sorted(all_latencies), 0.50), 3) if all_latencies else 0.0,
        "overall_p95_ms": round(_percentile(sorted(all_latencies), 0.95), 3) if all_latencies else 0.0,
    }
    return {
        "base_url": base_url,
        "rounds": rounds,
        "timeout_seconds": timeout_seconds,
        "overall": overall,
        "endpoints": endpoint_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark core OctoAgent HTTP endpoints.")
    parser.add_argument("--base-url", default="http://127.0.0.1:19880")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args()

    report = run_benchmark(args.base_url, args.rounds, args.timeout_seconds)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    print(f"Runtime latency benchmark for {report['base_url']}")
    print(f"Overall p50={report['overall']['overall_p50_ms']}ms p95={report['overall']['overall_p95_ms']}ms")
    for name, result in report["endpoints"].items():
        print(f"- {name}: p50={result['p50_ms']}ms p95={result['p95_ms']}ms success={result['success_count']}/{result['rounds']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
