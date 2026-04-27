"""
ai_gate.py — Gemini Production Readiness Verdict

Sends aggregated test results to Gemini and requests a final,
structured "READY FOR PRODUCTION" / "DO NOT DEPLOY" verdict.

When source code is provided via --code-path, includes a code review
section so Gemini can point to specific files and line numbers.
"""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from chaos_runner.config_loader import ChaosConfig
    from chaos_runner.threshold_evaluator import GateDecision


def _build_prompt(
    config: "ChaosConfig",
    gate: "GateDecision",
    raw_results: list,
    code_context: Optional[str] = None,
) -> str:
    summary = {
        "project": config.project,
        "overall_gate": gate.overall,
        "total_tests": len(gate.verdicts),
        "passed": sum(1 for v in gate.verdicts if v.status == "PASS"),
        "failed": sum(1 for v in gate.verdicts if v.status == "FAIL"),
        "warnings": sum(1 for v in gate.verdicts if v.status == "WARN"),
        "errors": sum(1 for v in gate.verdicts if v.status == "ERROR"),
        "blocking_failures": [
            {"test": v.test_id, "reasons": v.reasons} for v in gate.blocking_failures
        ],
        "thresholds": config.thresholds.model_dump(),
        "test_verdicts": [
            {
                "id": v.test_id,
                "type": v.test_type,
                "target": v.target,
                "status": v.status,
                "reasons": v.reasons,
                "latency_regression_pct": v.latency_regression_pct,
                "payload_5xx_rate": v.payload_5xx_rate,
                "payload_crash_rate": v.payload_crash_rate,
            }
            for v in gate.verdicts
        ],
    }

    code_section = ""
    code_review_instructions = ""
    if code_context:
        code_section = f"""
---
## Source Code Under Review
The following source files were submitted alongside the runtime tests.
Use them to give SPECIFIC file-path and line-level recommendations.

{code_context}
---
"""
        code_review_instructions = """
### 🔬 Code Review Findings
For each issue found in the source code that corresponds to a test failure or risk:
- **[filename:approx_line] — [Issue Name]**: [1 sentence — what the code does wrong] -> **Fix**: [exact code-level change needed]
Write "No code issues found." if the code looks correct for all failing areas.
"""

    who = "Site Reliability Engineer AND Application Security Engineer"
    context_note = "and the application source code " if code_context else ""

    return f"""
You are an expert {who}.
You are reviewing automated resilience test results {context_note}for a microservices system.

## Runtime Test Results
{json.dumps(summary, indent=2)}
{code_section}
Provide a BRIEF, STRUCTURED production-readiness report STRICTLY in this format — no extra prose:

### 🎯 Production Verdict
[Must be exactly one of: READY FOR PRODUCTION / CONDITIONAL PASS / DO NOT DEPLOY]

### 📋 Executive Summary
[2-3 sentences. What did you test? Did the system hold up? One clear overall takeaway.]

### 🔍 Key Findings
- **[Test ID / Issue]**: [1 sentence — what failed or passed and why it matters]
- Repeat for each failing or warning test. Skip passing tests.

### 🛠️ Required Fixes Before Deployment
- **[Fix Name]**: [1 sentence — exact technical remediation required]
- Repeat for each blocking failure. Write "None — system is production ready." if no fixes needed.
{code_review_instructions}"""


def get_ai_verdict(
    config: "ChaosConfig",
    gate: "GateDecision",
    raw_results: list,
    code_context: Optional[str] = None,
) -> str:
    """Call Gemini and return the structured production-readiness verdict.

    Args:
        config: The chaos configuration.
        gate: The evaluated gate decision with all verdicts.
        raw_results: Raw telemetry dicts from each test run.
        code_context: Optional formatted source code string from code_reviewer.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return (
            "AI verdict unavailable — GEMINI_API_KEY not set in environment.\n"
            f"Gate decision: **{gate.overall}** (based on threshold evaluation only)"
        )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        prompt = _build_prompt(config, gate, raw_results, code_context=code_context)
        models = ["gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
        for model in models:
            try:
                resp = client.models.generate_content(model=model, contents=prompt)
                return resp.text
            except Exception as e:
                print(f"  [ai_gate] Model {model} failed: {e}, trying next...")
                continue
        return "All Gemini models failed. Threshold-based gate decision applies."
    except ImportError:
        return "google-genai not installed. Run: pip install google-genai"
    except Exception as e:
        return f"AI verdict error: {e}"
