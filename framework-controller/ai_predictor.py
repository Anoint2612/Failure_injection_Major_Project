"""
AI Predictor — Pre-experiment resilience prediction.

Analyzes the Docker Compose architecture and live system health
to predict resilience weaknesses BEFORE any faults are injected.
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


def predict_resilience(architecture: str, live_status: list[dict]) -> str:
    """
    Predict system resilience based on architecture and live health.

    Args:
        architecture: Docker Compose YAML string.
        live_status: List of service status dicts from the /status endpoint.

    Returns:
        Markdown-formatted predictive resilience assessment.
    """
    prompt = f"""You are a Senior Site Reliability Engineer performing a **pre-chaos assessment** of a microservices system. You have NOT injected any faults yet — your job is to predict weaknesses by analyzing the architecture and current health.

## Docker Compose Architecture
```yaml
{architecture}
```

## Current Live Health Status
```json
{json.dumps(live_status, indent=2)}
```

Provide a **Pre-Flight Resilience Assessment**:

### 🛡️ Predicted Resilience Score: X/10
Rate the system's predicted resilience BEFORE any testing, based on architectural analysis alone. Justify with specific observations.

### 🔍 Dependency Map
Map out which services depend on which (inferred from the architecture). Identify:
- Synchronous call chains (e.g., gateway → auth → data)
- Single points of failure (services with no redundancy)
- Blast radius estimates (if service X goes down, who is affected?)

### ⚠️ Top 3 Predicted Weaknesses
For each:
1. The weakness (be specific)
2. Why it's dangerous
3. What fault type would expose it

### 📋 Architecture Recommendations
Specific improvements that would raise the resilience score:
- Missing patterns (circuit breakers, retries, timeouts, health checks)
- Infrastructure gaps (no replicas, no resource limits, no graceful shutdown)
- Network risks (all on same network, no segmentation)

### 🎯 Suggested First Test
Based on your analysis, what single chaos test should be run first, and why?

Be specific, actionable, and data-driven. Reference actual service names from the architecture.
"""
    return _call_gemini(prompt)
