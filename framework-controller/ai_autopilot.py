"""
AI Auto-Pilot — Fully autonomous chaos experiment runner.

Asks Gemini to analyze the architecture and return a STRUCTURED test plan
(as JSON), then automatically executes each test via the experiment runner,
collects results, and generates a combined AI remediation report.
"""

from dotenv import load_dotenv
import os
import json
import re
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


def generate_test_plan(architecture: str) -> list[dict]:
    """
    Ask Gemini to produce a structured JSON test plan for the architecture.

    Returns a list of test specs like:
    [
      {
        "target_service": "auth-service",
        "fault_type": "latency",
        "delay_ms": 3000,
        "hypothesis": "Gateway response time will increase by 3x",
        "severity": "mild"
      },
      ...
    ]
    """
    prompt = f"""You are a Senior Chaos Engineer. Analyze this Docker Compose architecture:

```yaml
{architecture}
```

Generate a chaos test plan as a JSON array. Each test should be an object with these EXACT keys:
- "target_service": the Docker Compose service name to attack (string)
- "fault_type": one of "latency" or "stress" (string)
- "delay_ms": milliseconds of delay, only if fault_type is "latency" (integer, 500-5000)
- "cpu": number of CPU workers, only if fault_type is "stress" (integer, 1-4)
- "stress_timeout": seconds for stress test, only if fault_type is "stress" (integer, 15-30)
- "hypothesis": what you predict will happen (string)
- "severity": "mild", "moderate", or "severe" (string)
- "rationale": why this test is valuable (string)

Rules:
- Do NOT target "prometheus" or "grafana" — only application services
- Generate exactly 3 tests, ordered mild → moderate → severe
- For latency tests: mild=500-1000ms, moderate=1500-3000ms, severe=4000-5000ms
- For stress tests: mild=1 CPU, moderate=2 CPU, severe=3-4 CPU
- Mix fault types (don't use all latency or all stress)

Return ONLY a raw JSON array. No markdown, no code fences, no explanation. Just the JSON.
"""
    raw = _call_gemini(prompt)

    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    try:
        plan = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to extract JSON array from the response
        match = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if match:
            plan = json.loads(match.group())
        else:
            raise ValueError(f"Gemini did not return valid JSON. Raw response:\n{raw[:500]}")

    # Validate and normalize
    valid_plan = []
    for test in plan:
        if not isinstance(test, dict):
            continue
        if "target_service" not in test or "fault_type" not in test:
            continue
        if test["fault_type"] not in ("latency", "stress"):
            continue
        valid_plan.append(test)

    if not valid_plan:
        raise ValueError("Gemini returned an empty or invalid test plan.")

    return valid_plan


def generate_combined_report(plan: list[dict], all_results: list[dict]) -> str:
    """
    After executing all tests, send the full plan + results to Gemini
    for a comprehensive combined analysis.
    """
    prompt = f"""You are a Senior Site Reliability Engineer conducting a comprehensive chaos engineering assessment.

I ran an AI-generated chaos test plan against a microservices system. Here is the FULL test plan and results:

## Test Plan (AI-Generated)
{json.dumps(plan, indent=2)}

## Execution Results
{json.dumps(all_results, indent=2)}

Please provide a comprehensive assessment:

### 1. Executive Summary
A 2-3 sentence verdict on the system's overall resilience.

### 2. Test-by-Test Analysis
For each test that was executed:
- What happened vs. what was hypothesized
- Whether the hypothesis was confirmed or refuted
- Key latency numbers (baseline vs during_fault vs post_recovery)

### 3. Overall Resilience Score: X/10
Assign a single score with mathematical justification based on:
- Average latency degradation factor
- Recovery speed (post_recovery vs baseline)
- Timeout/failure rate during faults

### 4. Critical Findings
The top 3 most important discoveries from this test suite.

### 5. Remediation Roadmap
Prioritized list of 3-5 specific technical fixes (e.g., "Add a 500ms timeout to the auth-service HTTP client", "Implement circuit breaker pattern on data-service calls").

Keep the response concise, data-driven, and actionable.
"""
    return _call_gemini(prompt)
