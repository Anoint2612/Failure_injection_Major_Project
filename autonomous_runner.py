#!/usr/bin/env python3
"""autonomous_runner.py – Master Switch for the framework.

Workflow:
1. Executes ``scenario_generator.py`` to obtain an AI‑suggested experiment
   configuration (JSON).
2. Loads the newest JSON file produced under ``experiments/scenarios``.
3. Sends a fault‑injection request to the FastAPI ``controller`` (``/inject/stop``).
4. Waits for the experiment duration defined in the JSON.
5. Calls the rollback endpoint (``/rollback/start``) to restore services.
6. Runs ``telemetry_exporter.py`` to collect Prometheus data.
7. Runs ``gemini_analyzer.py`` to produce an AI‑driven analysis report.

The script assumes the scenario JSON contains at least the following keys:
```
{
  "services": ["auth", "data"],   # services to stop (fault injection)
  "duration": 30                    # experiment length in seconds
}
```
Additional keys can be added later; they are ignored by this runner.

All network calls are wrapped in ``try/except`` blocks – failures are printed
but do not abort the overall flow unless they are critical (e.g., missing
scenario file). Environment variables:
- ``CONTROLLER_URL`` – Base URL of the controller (default ``http://localhost:8080``)
- ``PYTHONPATH`` is not required as the scripts live in the repository root.
"""

import os
import sys
import json
import time
import subprocess
import glob
import datetime
from typing import Dict, Any, List

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SCENARIO_DIR = os.path.join(BASE_DIR, "experiments", "scenarios")
SCENARIO_GENERATOR = os.path.join(BASE_DIR, "scenario_generator.py")
TELEMETRY_EXPORTER = os.path.join(BASE_DIR, "telemetry_exporter.py")
GEMINI_ANALYZER = os.path.join(BASE_DIR, "gemini_analyzer.py")

# Controller endpoint – can be overridden via env var.
CONTROLLER_URL = os.getenv("CONTROLLER_URL", "http://localhost:8080")

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def run_subprocess(script_path: str) -> subprocess.CompletedProcess:
    """Execute a Python script with ``python3`` and return the result.

    ``script_path`` must be an absolute path. Errors are not raised – the caller
    can inspect ``returncode`` and ``stdout``/``stderr``.
    """
    return subprocess.run(
        ["python3", script_path],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
    )


def generate_scenario() -> str:
    """Run ``scenario_generator.py`` and return the path of the JSON file it created.

    The generator prints the absolute path of the saved file; we parse that
    output. As a fallback, we select the newest ``*.json`` file in
    ``SCENARIO_DIR``.
    """
    result = run_subprocess(SCENARIO_GENERATOR)
    if result.returncode != 0:
        sys.stderr.write(f"scenario_generator failed: {result.stderr}\n")
        sys.exit(1)
    # Look for a line containing the path.
    for line in result.stdout.splitlines():
        if "Scenario JSON saved to" in line:
            # Format: "Scenario JSON saved to /path/to/file.json"
            parts = line.split("saved to", 1)[1].strip()
            return parts
    # Fallback – pick the newest JSON in the scenario directory.
    pattern = os.path.join(SCENARIO_DIR, "*.json")
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(f"No scenario JSON files found in {SCENARIO_DIR}")
    return max(files, key=os.path.getmtime)


def load_json(file_path: str) -> Dict[str, Any]:
    """Read a JSON file and return its content as a dictionary."""
    with open(file_path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def post_to_controller(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """POST ``payload`` to ``CONTROLLER_URL`` + ``endpoint`` and return JSON response.

    Any HTTP error is printed and returns an empty dict.
    """
    url = f"{CONTROLLER_URL}{endpoint}"
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        sys.stderr.write(f"Error calling {url}: {exc}\n")
        return {}


def wait_for_duration(seconds: int) -> None:
    """Simple sleep wrapper that prints a countdown for visibility."""
    if seconds <= 0:
        return
    print(f"Waiting {seconds}s for experiment to run…")
    # Sleep in 1‑second increments to allow early interruption via KeyboardInterrupt.
    for remaining in range(seconds, 0, -1):
        time.sleep(1)
        if remaining % 10 == 0 or remaining <= 5:
            print(f"{remaining}s remaining…")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def main() -> None:
    # 1. Generate a new scenario.
    print("Generating AI‑suggested scenario…")
    try:
        scenario_path = generate_scenario()
    except Exception as exc:
        sys.stderr.write(f"Failed to obtain scenario: {exc}\n")
        sys.exit(1)
    print(f"Scenario file: {scenario_path}")

    # 2. Load the scenario JSON.
    try:
        scenario = load_json(scenario_path)
    except Exception as exc:
        sys.stderr.write(f"Could not read scenario JSON: {exc}\n")
        sys.exit(1)

    # Expected keys.
    services: List[str] = scenario.get("services", [])
    duration: int = scenario.get("duration", 30)
    if not services:
        sys.stderr.write("Scenario does not specify any services to inject. Exiting.\n")
        sys.exit(1)

    print(f"Injecting fault into services: {services}")
    # 3. Send injection request to controller.
    inject_response = post_to_controller("/inject/stop", {"services": services})
    print("Injection response:", inject_response)

    # 4. Wait for the experiment duration.
    wait_for_duration(duration)

    # 5. Rollback – start the services again.
    print("Rolling back – restarting services…")
    rollback_response = post_to_controller("/rollback/start", {"services": services})
    print("Rollback response:", rollback_response)

    # 6. Run telemetry exporter.
    print("Collecting telemetry…")
    tel_result = run_subprocess(TELEMETRY_EXPORTER)
    if tel_result.returncode != 0:
        sys.stderr.write(f"telemetry_exporter failed: {tel_result.stderr}\n")
    else:
        print(tel_result.stdout.strip())

    # 7. Run Gemini analyzer on the newly exported telemetry.
    print("Running AI analysis on telemetry…")
    gem_result = run_subprocess(GEMINI_ANALYZER)
    if gem_result.returncode != 0:
        sys.stderr.write(f"gemini_analyzer failed: {gem_result.stderr}\n")
    else:
        print(gem_result.stdout.strip())

    print("Autonomous run completed.")


if __name__ == "__main__":
    main()
