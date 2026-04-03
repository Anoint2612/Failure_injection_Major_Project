#!/usr/bin/env python3
"""gemini_analyzer.py – AI‑Powered SRE analysis of recent telemetry.

The script:
1. Finds the most recent JSON file under ``experiments/logs``.
2. Loads the Prometheus metrics JSON.
3. Sends the data to Gemini (model ``gemini-1.5-flash``) using the
   ``google‑generativeai`` client. The API key is read from the environment
   variable ``GEMINI_API_KEY``.
4. Receives a Markdown report summarising the failure analysis and writes
   it to ``reports/AI_SRE_Analysis_<timestamp>.md``.

Network or API failures are caught and reported – the script will still
create a report file containing the error details so the user can retry.
"""

import os
import json
import glob
import datetime
import sys
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Configuration & constants
# ---------------------------------------------------------------------------
# Load GEMINI API key from environment (you may source the .env beforehand).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    sys.stderr.write("Error: GEMINI_API_KEY environment variable not set.\n")
    sys.exit(1)

# Directories relative to the repository root (the script is placed at the root).
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "experiments", "logs")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

# Prompt that drives the Gemini model.
PROMPT = (
    "You are a Senior Site Reliability Engineer. Analyze the attached Prometheus metrics.\n\n"
    "Identify the start and end times of the service failure.\n"
    "- Calculate the percentage of throughput degradation.\n"
    "- Compare the recovery time (MTTR) against a 2-second SLA.\n"
    "- Based on the failure pattern (e.g., cascading errors or resource exhaustion), "
    "recommend a specific resilience pattern like a Circuit Breaker, Retry with Exponential "
    "Backoff, or Bulkhead to prevent this in the future."
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def find_latest_json() -> str:
    """Return the path of the newest ``*.json`` file in ``LOGS_DIR``.

    Raises ``FileNotFoundError`` if no JSON files exist.
    """
    pattern = os.path.join(LOGS_DIR, "*.json")
    files = glob.glob(pattern)
    if not files:
        raise FileNotFoundError(f"No JSON telemetry files found in {LOGS_DIR}")
    # Choose the file with the most recent modification time.
    latest = max(files, key=os.path.getmtime)
    return latest


def load_json(path: str) -> Dict[str, Any]:
    """Read ``path`` and return the parsed JSON content."""
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def build_gemini_client():
    """Configure the google‑generativeai client and return a model instance."""
    try:
        import google.generativeai as genai
    except ImportError as exc:
        sys.stderr.write(
            "google-generativeai package not installed. Install with 'pip install google-generativeai'.\n"
        )
        raise exc
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel("gemini-1.5-flash")


def ask_gemini(model, metric_json: Dict[str, Any]) -> str:
    """Send the prompt + JSON payload to Gemini and return the response text.

    The JSON is embedded inside a fenced ``json`` block to preserve formatting.
    Any exception is caught and returned as an error string.
    """
    # Embed the JSON in a code block for clarity.
    json_block = f"```json\n{json.dumps(metric_json, indent=2)}\n```"
    full_prompt = f"{PROMPT}\n\n{json_block}"
    try:
        response = model.generate_content(full_prompt)
        # ``response.text`` contains the generated Markdown.
        return response.text
    except Exception as exc:
        return f"**Error contacting Gemini:** {exc}"


def write_report(content: str) -> str:
    """Write ``content`` to a timestamped Markdown file under ``REPORTS_DIR``.

    Returns the absolute path of the written file.
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    report_path = os.path.join(REPORTS_DIR, f"AI_SRE_Analysis_{timestamp}.md")
    with open(report_path, "w", encoding="utf-8") as fp:
        fp.write(content)
    return report_path


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main() -> None:
    try:
        latest_json_path = find_latest_json()
        telemetry = load_json(latest_json_path)
    except Exception as e:
        sys.stderr.write(f"Failed to load telemetry data: {e}\n")
        sys.exit(1)

    try:
        model = build_gemini_client()
    except Exception:
        sys.stderr.write("Unable to initialise Gemini client.\n")
        sys.exit(1)

    report_md = ask_gemini(model, telemetry)
    report_file = write_report(report_md)
    print(f"AI SRE analysis saved to {report_file}")


if __name__ == "__main__":
    main()
