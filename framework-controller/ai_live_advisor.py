"""
AI Live Advisor — Real-time fault triage during active chaos.

When a fault is actively injected, this module provides real-time
AI guidance on the blast radius, affected services, and whether
to escalate or recover.
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


def advise_live(
    active_fault: dict,
    live_status: list[dict],
    architecture: str = None,
) -> str:
    """
    Provide real-time AI triage advice during an active fault.

    Args:
        active_fault: Dict describing the currently injected fault
                      (e.g. {"service": "auth-service", "fault_type": "latency", "params": {"delay_ms": 3000}})
        live_status: Current health status of all services from /status.
        architecture: Optional Docker Compose YAML for context.

    Returns:
        Markdown-formatted real-time advisory.
    """
    arch_section = ""
    if architecture:
        arch_section = f"""
## System Architecture
```yaml
{architecture}
```
"""

    prompt = f"""You are an SRE responding to a LIVE chaos experiment in progress. A fault has been deliberately injected and you need to provide real-time triage.

## Active Fault
```json
{json.dumps(active_fault, indent=2)}
```

## Current System Health (Live)
```json
{json.dumps(live_status, indent=2)}
```
{arch_section}
Provide RAPID real-time guidance:

### 🚨 Blast Radius Assessment
Which services are currently affected by this fault? Which are still healthy? Is the damage contained or spreading?

### 📊 Impact Severity: LOW / MEDIUM / HIGH / CRITICAL
Rate the current impact with a one-line justification.

### 🔮 Cascading Failure Prediction
Based on the current state, predict what will happen in the next 30-60 seconds if the fault is NOT recovered:
- Will other services start timing out?
- Is there a risk of cascading failure?
- Could this trigger a full outage?

### 💡 Recommended Action
Should the operator:
- **HOLD** — the system is handling it well, keep observing
- **RECOVER** — the blast radius is expanding, recover now
- **ESCALATE** — the system is too stable, inject a harder fault to find real weaknesses

Explain your reasoning in 1-2 sentences.

### 🔧 What to Watch
3 specific metrics or behaviors to monitor right now.

Keep this SHORT and actionable — this is a live incident response, not a post-mortem.
"""
    return _call_gemini(prompt)
