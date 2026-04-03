#!/usr/bin/env python3
"""scenario_generator.py – AI‑driven experiment configuration generator.

This script reads the project's ``docker-compose.yml`` file, sends its contents
to the Gemini model (``gemini-1.5-flash``) and asks the model to identify the
most critical service dependency and produce a **JSON** configuration for a new
failure experiment (e.g., injecting latency between two services).

The resulting JSON is written to ``experiments/scenarios/scenario_<timestamp>.json``
so that the ``controller.py`` (or any future orchestrator) can consume it.
Network or API errors are caught; the script still writes a file containing the
error details to aid debugging.
"""

import os
import sys
import json
import datetime
import glob
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Load environment configuration (GEMINI_API_KEY)
# ---------------------------------------------------------------------------
# Optionally load a .env file if present (requires python‑dotenv).
try:
    from dotenv import load_dotenv

    # Locate .env in the repository root (two levels up from this file).
    dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
except Exception:
    # Silently ignore if python‑dotenv is not installed.
    pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    sys.stderr.write("Error: GEMINI_API_KEY environment variable not set.\n")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DOCKER_COMPOSE_PATH = os.path.join(BASE_DIR, "docker-compose.yml")
SCENARIO_DIR = os.path.join(BASE_DIR, "experiments", "scenarios")

# Prompt for the model – exactly as requested.
PROMPT = (
    "Based on this microservices architecture, identify the most critical service "
    "dependency. Generate a JSON configuration for a new failure experiment that "
    "targets this weakness (e.g., injecting 500ms latency between Gateway and Data "
    "service)."
)

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def read_compose_file() -> str:
    """Return the raw ``docker-compose.yml`` contents as a string."""
    if not os.path.exists(DOCKER_COMPOSE_PATH):
        raise FileNotFoundError(
            f"docker-compose.yml not found at {DOCKER_COMPOSE_PATH}"
        )
    with open(DOCKER_COMPOSE_PATH, "r", encoding="utf-8") as fp:
        return fp.read()


def build_gemini_client():
    """Configure the Google GenerativeAI client and return a model instance."""
    try:
        import google.generativeai as genai
    except ImportError as exc:
        sys.stderr.write(
            "google-generativeai package missing – install with 'pip install google-generativeai'.\n"
        )
        raise exc
    genai.configure(api_key=GEMINI_API_KEY)
    return genai.GenerativeModel("gemini-1.5-flash")


def ask_gemini(model, compose_yaml: str) -> str:
    """Send the compose file and prompt to Gemini, returning the raw response.

    The compose content is embedded in a fenced ``yaml`` block so the model can
    parse it reliably.
    """
    yaml_block = f"```yaml\n{compose_yaml}\n```"
    full_prompt = f"{PROMPT}\n\n{yaml_block}"
    try:
        response = model.generate_content(full_prompt)
        return response.text  # Expected to be a JSON snippet.
    except Exception as exc:
        return json.dumps({"error": f"Gemini request failed: {exc}"}, indent=2)


def write_scenario(content: str) -> str:
    """Write ``content`` (JSON string) to a timestamped file under ``SCENARIO_DIR``.

    Returns the absolute path of the created file.
    """
    os.makedirs(SCENARIO_DIR, exist_ok=True)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(SCENARIO_DIR, f"scenario_{timestamp}.json")
    # Ensure the file contains valid JSON – if ``content`` is not JSON, write as‑is.
    try:
        parsed = json.loads(content)
        # Re‑dump with indentation for readability.
        with open(out_path, "w", encoding="utf-8") as fp:
            json.dump(parsed, fp, indent=2)
    except json.JSONDecodeError:
        # Not valid JSON – store raw text for debugging.
        with open(out_path, "w", encoding="utf-8") as fp:
            fp.write(content)
    return out_path


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------


def main() -> None:
    try:
        compose_yaml = read_compose_file()
    except Exception as e:
        sys.stderr.write(f"Failed to read docker-compose.yml: {e}\n")
        sys.exit(1)

    try:
        model = build_gemini_client()
    except Exception:
        sys.stderr.write("Unable to initialise Gemini client.\n")
        sys.exit(1)

    response_text = ask_gemini(model, compose_yaml)
    out_file = write_scenario(response_text)
    print(f"Scenario JSON saved to {out_file}")


if __name__ == "__main__":
    main()
