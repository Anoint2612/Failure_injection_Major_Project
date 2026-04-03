#!/usr/bin/env python3
"""Telemetry exporter for Prometheus.

Fetches the last 2 minutes of selected metrics for the `auth` and `data`
services and stores the raw Prometheus response JSON in
`experiments/logs/telemetry_<timestamp>.json`.

The script tolerates temporary Prometheus outages – any query error
records an error entry and the script continues processing the remaining
metrics.
"""

import os
import json
import time
import datetime
from typing import Dict, Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
# Store logs under the repository root in ``experiments/logs``
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "experiments", "logs")

# List of metric names to query.
METRICS = [
    "http_requests_total",
    "container_cpu_usage_seconds_total",
    "request_latency_seconds",
]


# ---------------------------------------------------------------------------
# Helper – fetch a range query from Prometheus
# ---------------------------------------------------------------------------
def _fetch_range(
    metric: str, start: float, end: float, step: int = 15
) -> Dict[str, Any]:
    """Query Prometheus for ``metric`` over ``[start, end]``.

    The query filters on the instance label so that only the ``auth`` and
    ``data`` services (exposed as ``auth:8000`` and ``data:8000``) are
    considered. If Prometheus cannot be reached, an ``error`` field is
    returned and ``result`` is an empty list.
    """
    # The instance label contains the target address (e.g. ``auth:8000``).
    query = f'{metric}{{instance=~"(auth|data):.*"}}'
    params = {
        "query": query,
        "start": start,
        "end": end,
        "step": step,
    }
    try:
        # Import requests lazily – it may not be installed in a minimal env.
        import requests

        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range", params=params, timeout=5
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # Broad to catch import errors and request failures.
        # Return a structure compatible with Prometheus API for downstream code.
        return {
            "status": "error",
            "error": str(exc),
            "data": {"result": []},
        }


# ---------------------------------------------------------------------------
# Main execution flow
# ---------------------------------------------------------------------------
def main() -> None:
    # Determine the time window – last 2 minutes.
    end_ts = time.time()
    start_ts = end_ts - 120  # 120 seconds = 2 minutes

    telemetry: Dict[str, Any] = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "window_seconds": 120,
        "metrics": {},
    }

    for metric in METRICS:
        telemetry["metrics"][metric] = _fetch_range(metric, start_ts, end_ts)

    # Ensure the output directory exists.
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(OUTPUT_DIR, f"telemetry_{timestamp}.json")
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(telemetry, fp, indent=2)
    print(f"Telemetry saved to {out_path}")


if __name__ == "__main__":
    main()
