"""
chaos_runner — Automated Resilience Gate for CI/CD Pipelines.

Reads a chaos-config.yml, runs pre-configured tests against a
running ChaosController instance, evaluates thresholds, generates
an AI-powered production-readiness report, and exits 0 (PASS) or 1 (FAIL).
"""
__version__ = "1.0.0"
