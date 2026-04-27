"""
AI Comparator — Cross-run trend analysis.

Loads all saved experiment history and asks Gemini to identify
trends, regressions, and improvements across multiple runs.
"""

from dotenv import load_dotenv
import os
import json
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODELS = ["gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"]


def _call_gemini(prompt: str) -> str:
    """Call Gemini with automatic model fallback."""
    last_exc = None
    for model in MODELS:
        try:
            resp = client.models.generate_content(model=model, contents=prompt)
            return resp.text
        except Exception as e:
            last_exc = e
            continue
    raise RuntimeError(f"All Gemini models failed. Last error: {last_exc}")


def compare_experiments(history: list[dict]) -> str:
    """
    Analyze multiple experiment runs and identify trends.

    Args:
        history: List of experiment result dicts (each with baseline,
                 during_fault, post_recovery, config, timestamp).

    Returns:
        Markdown-formatted trend analysis report.
    """
    prompt = f"""You are a Senior SRE reviewing the historical results of multiple chaos engineering experiments run on the same microservices system over time.

Here is the complete experiment history (ordered chronologically):
{json.dumps(history, indent=2)}

Please provide a **Trend Analysis Report**:

### 1. Experiment Timeline
Summarize each experiment briefly (when it ran, what fault, what target).

### 2. Trend Detection
- Is baseline latency stable, improving, or degrading across runs?
- Are during-fault latencies getting worse or better? (indicating system hardening or degradation)
- Are recovery times improving? (faster return to baseline = better)

### 3. Service Resilience Ranking
Rank the tested services from MOST resilient to LEAST resilient, with data justification.

### 4. Most Fragile Component
Identify the single weakest service and explain WHY with specific numbers.

### 5. Progress Report
What has improved since the earliest experiment? What has gotten worse?

### 6. Next Steps
Based on the trends, what should the team focus on next?

Use specific numbers from the data. Be concise and data-driven.
"""
    return _call_gemini(prompt)
