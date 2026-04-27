"""
threshold_evaluator.py — PASS/FAIL Logic

Takes test results and evaluates them against the thresholds defined
in the chaos config. Returns per-test verdicts and an overall gate decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from chaos_runner.config_loader import ChaosConfig, TestConfig, Thresholds
from chaos_runner.test_executor import TestResult


@dataclass
class TestVerdict:
    test_id: str
    test_type: str
    target: str
    status: str          # "PASS" | "FAIL" | "ERROR" | "WARN"
    on_fail: str         # "block" | "warn"
    reasons: List[str] = field(default_factory=list)

    # Metrics for the report
    baseline_avg_latency: Optional[float] = None
    fault_avg_latency: Optional[float] = None
    recovery_avg_latency: Optional[float] = None
    latency_regression_pct: Optional[float] = None
    payload_total: int = 0
    payload_5xx_count: int = 0
    payload_crash_count: int = 0
    payload_5xx_rate: float = 0.0
    payload_crash_rate: float = 0.0
    duration_s: float = 0.0

    @property
    def is_blocking_failure(self) -> bool:
        return self.status == "FAIL" and self.on_fail == "block"

    @property
    def status_icon(self) -> str:
        return {"PASS": "✅", "FAIL": "❌", "WARN": "⚠️", "ERROR": "🔴"}.get(self.status, "❓")


@dataclass
class GateDecision:
    overall: str              # "PASS" | "FAIL"
    verdicts: List[TestVerdict]
    blocking_failures: List[TestVerdict]

    @property
    def is_pass(self) -> bool:
        return self.overall == "PASS"

    @property
    def banner(self) -> str:
        if self.is_pass:
            return "✅  READY FOR PRODUCTION"
        return "❌  DO NOT DEPLOY — RESILIENCE GATE FAILED"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _avg(items: list, key: str = "latency") -> Optional[float]:
    vals = [r.get(key) for r in items if isinstance(r.get(key), (int, float))]
    return round(sum(vals) / len(vals), 3) if vals else None


def _regression_pct(baseline: float, fault: float) -> float:
    if baseline == 0:
        return 0.0
    return round(((fault - baseline) / baseline) * 100, 1)


# ── Evaluators ────────────────────────────────────────────────────────────────

def _evaluate_latency_or_stress(
    result: TestResult,
    test: TestConfig,
    thresholds: Thresholds,
) -> TestVerdict:
    verdict = TestVerdict(
        test_id=result.test_id,
        test_type=result.test_type,
        target=result.target,
        on_fail=test.on_fail,
        status="PASS",
        duration_s=result.duration_s,
    )

    if not result.success:
        verdict.status = "ERROR"
        verdict.reasons.append(f"Test execution failed: {result.error}")
        return verdict

    raw = result.raw
    baseline_rows = raw.get("baseline", [])
    fault_rows = raw.get("during_fault", [])
    recovery_rows = raw.get("post_recovery", [])

    verdict.baseline_avg_latency = _avg(baseline_rows)
    verdict.fault_avg_latency = _avg(fault_rows)
    verdict.recovery_avg_latency = _avg(recovery_rows)

    if verdict.baseline_avg_latency and verdict.fault_avg_latency:
        verdict.latency_regression_pct = _regression_pct(
            verdict.baseline_avg_latency, verdict.fault_avg_latency
        )
        if verdict.latency_regression_pct > thresholds.latency_regression_percent:
            verdict.reasons.append(
                f"Latency regression {verdict.latency_regression_pct}% "
                f"exceeds threshold {thresholds.latency_regression_percent}%"
            )
            verdict.status = "FAIL"

    # Check for 5xx / timeout responses in any phase
    all_rows = baseline_rows + fault_rows + recovery_rows
    error_rows = [
        r for r in all_rows
        if r.get("status") == "timeout" or (
            isinstance(r.get("status"), int) and r.get("status", 0) >= 500
        )
    ]
    if error_rows:
        verdict.reasons.append(
            f"{len(error_rows)} probe request(s) returned 5xx/timeout"
        )
        verdict.status = "FAIL"

    return verdict


def _evaluate_payload(
    result: TestResult,
    test: TestConfig,
    thresholds: Thresholds,
) -> TestVerdict:
    verdict = TestVerdict(
        test_id=result.test_id,
        test_type=result.test_type,
        target=result.target,
        on_fail=test.on_fail,
        status="PASS",
        duration_s=result.duration_s,
    )

    if not result.success:
        verdict.status = "ERROR"
        verdict.reasons.append(f"Test execution failed: {result.error}")
        return verdict

    raw = result.raw
    payload_results = raw.get("payload_results", [])
    verdict.payload_total = len(payload_results)

    if verdict.payload_total == 0:
        verdict.reasons.append("No payload test cases were executed — OpenAPI discovery may have failed")
        verdict.status = "WARN"
        return verdict

    crashes = [
        r for r in payload_results
        if r.get("status") in ("timeout_or_error", "timeout")
    ]
    five_xx = [
        r for r in payload_results
        if isinstance(r.get("status"), int) and r.get("status", 0) >= 500
    ]

    verdict.payload_crash_count = len(crashes)
    verdict.payload_5xx_count = len(five_xx)
    verdict.payload_crash_rate = round(100 * len(crashes) / verdict.payload_total, 1)
    verdict.payload_5xx_rate = round(100 * len(five_xx) / verdict.payload_total, 1)

    if verdict.payload_crash_rate > thresholds.max_payload_crash_rate_percent:
        verdict.reasons.append(
            f"Crash/timeout rate {verdict.payload_crash_rate}% "
            f"exceeds threshold {thresholds.max_payload_crash_rate_percent}% "
            f"({len(crashes)} of {verdict.payload_total} cases)"
        )
        verdict.status = "FAIL"

    if verdict.payload_5xx_rate > thresholds.max_5xx_rate_percent:
        verdict.reasons.append(
            f"5xx rate {verdict.payload_5xx_rate}% "
            f"exceeds threshold {thresholds.max_5xx_rate_percent}% "
            f"({len(five_xx)} of {verdict.payload_total} cases)"
        )
        verdict.status = "FAIL"

    # Also evaluate the bombing degradation phase
    baseline_rows = raw.get("baseline", [])
    fault_rows = raw.get("during_fault", [])
    verdict.baseline_avg_latency = _avg(baseline_rows)
    verdict.fault_avg_latency = _avg(fault_rows)

    if verdict.baseline_avg_latency and verdict.fault_avg_latency:
        verdict.latency_regression_pct = _regression_pct(
            verdict.baseline_avg_latency, verdict.fault_avg_latency
        )
        if verdict.latency_regression_pct > thresholds.latency_regression_percent:
            verdict.reasons.append(
                f"Degradation bombing: latency regression {verdict.latency_regression_pct}% "
                f"exceeds threshold {thresholds.latency_regression_percent}%"
            )
            verdict.status = "FAIL"

    return verdict


# ── Public API ─────────────────────────────────────────────────────────────────

def evaluate_all(
    results: list[TestResult],
    config: ChaosConfig,
) -> GateDecision:
    """Evaluate all test results against thresholds and produce a GateDecision."""
    test_map: Dict[str, TestConfig] = {t.id: t for t in config.tests}
    verdicts: list[TestVerdict] = []

    for result in results:
        test = test_map.get(result.test_id)
        if not test:
            continue

        if result.test_type == "payload":
            verdict = _evaluate_payload(result, test, config.thresholds)
        else:
            verdict = _evaluate_latency_or_stress(result, test, config.thresholds)

        # Downgrade FAIL to WARN if on_fail == warn
        if verdict.status == "FAIL" and test.on_fail == "warn":
            verdict.status = "WARN"

        verdicts.append(verdict)

    blocking = [v for v in verdicts if v.is_blocking_failure]
    overall = "FAIL" if blocking else "PASS"

    return GateDecision(
        overall=overall,
        verdicts=verdicts,
        blocking_failures=blocking,
    )
