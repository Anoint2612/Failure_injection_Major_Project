"""
cli.py — chaos-runner Command Line Interface

Entry point for the CI/CD Resilience Gate.

Usage:
    chaos-runner run --config chaos-config.yml
    chaos-runner run --config chaos-config.yml --code-path ./src
    chaos-runner validate --config chaos-config.yml
"""
from __future__ import annotations

import sys

import click

from chaos_runner.config_loader import load_config


@click.group()
@click.version_option(version="1.0.0", prog_name="chaos-runner")
def cli():
    """🔥 Chaos Runner — AI-Powered Resilience Gate for CI/CD Pipelines."""
    pass


@cli.command()
@click.option("--config", "-c", default="chaos-config.yml", show_default=True,
              help="Path to the chaos configuration YAML file.")
def validate(config: str):
    """Validate a chaos-config.yml without running any tests."""
    click.echo(f"  Validating config: {config}")
    try:
        cfg = load_config(config)
        click.secho(f"  ✅ Config is valid — {len(cfg.tests)} test(s) for {len(cfg.services)} service(s)", fg="green")
        for t in cfg.tests:
            click.echo(f"    • {t.id} ({t.type}) → {t.target} [{t.on_fail}]")
    except Exception as e:
        click.secho(f"  ❌ Config invalid: {e}", fg="red", err=True)
        sys.exit(1)


@cli.command()
@click.option("--config", "-c", default="chaos-config.yml", show_default=True,
              help="Path to the chaos configuration YAML file.")
@click.option("--controller-url", default=None,
              help="Override the ChaosController URL from config (e.g. http://chaos-controller:5050).")
@click.option("--no-ai", is_flag=True, default=False,
              help="Skip AI verdict (useful when GEMINI_API_KEY is not available).")
@click.option("--output-html", default=None, help="Override HTML report output path.")
@click.option("--output-json", default=None, help="Override JSON report output path.")
@click.option(
    "--code-path", default=None,
    help="Path to the application source directory. When provided, the AI will review code "
         "alongside test results and give specific file:line remediation advice."
)
def run(config: str, controller_url: str | None, no_ai: bool, output_html: str | None, output_json: str | None, code_path: str | None):
    """
    Run the full resilience test suite and generate a production-readiness report.

    Exits with code 0 if the gate passes, 1 if it fails.
    """
    from chaos_runner.ai_gate import get_ai_verdict
    from chaos_runner.report_generator import generate, write_reports
    from chaos_runner.test_executor import run_all
    from chaos_runner.threshold_evaluator import evaluate_all

    click.echo()
    click.secho("╔══════════════════════════════════════════════════╗", fg="cyan")
    click.secho("║   🔥  ChaosRunner — Resilience Gate  🔥           ║", fg="cyan")
    click.secho("╚══════════════════════════════════════════════════╝", fg="cyan")
    click.echo()

    # 1. Load Config
    click.echo(f"  📄 Loading config: {config}")
    try:
        cfg = load_config(config)
    except Exception as e:
        click.secho(f"  ❌ Failed to load config: {e}", fg="red", err=True)
        sys.exit(1)

    if controller_url:
        cfg.controller.url = controller_url.rstrip("/")

    click.secho(f"  Project   : {cfg.project}", fg="bright_white")
    click.secho(f"  Controller: {cfg.controller.url}", fg="bright_white")
    click.secho(f"  Tests     : {len(cfg.tests)}", fg="bright_white")
    if code_path:
        click.secho(f"  Code Path : {code_path} (AI code review enabled)", fg="bright_yellow")
    click.echo()

    # 2. Execute Tests
    click.echo("  🚀 Running tests (sequential)...")
    try:
        results = run_all(cfg)
    except ConnectionError as e:
        click.secho(f"  ❌ {e}", fg="red", err=True)
        sys.exit(1)

    for r in results:
        icon = "✅" if r.success else "❌"
        click.echo(f"    {icon} {r.test_id} ({r.test_type}) — {r.duration_s}s")
        if r.error:
            click.secho(f"       Error: {r.error}", fg="red")

    click.echo()

    # 3. Evaluate thresholds
    click.echo("  📏 Evaluating thresholds...")
    gate = evaluate_all(results, cfg)

    for v in gate.verdicts:
        color = {"PASS": "green", "FAIL": "red", "WARN": "yellow", "ERROR": "magenta"}.get(v.status, "white")
        click.secho(f"    {v.status_icon} {v.test_id}: {v.status}", fg=color)
        for reason in v.reasons:
            click.secho(f"       → {reason}", fg=color)

    click.echo()

    # 4. Load source code for review (optional)
    code_context = None
    if code_path and not no_ai and cfg.report.ai_summary:
        from chaos_runner.code_reviewer import read_code_files, format_for_prompt, summarize
        click.echo(f"  🔍 Reading source code from: {code_path}")
        try:
            files = read_code_files(code_path)
            code_context = format_for_prompt(files)
            click.secho(f"     {summarize(files)}", fg="bright_yellow")
        except Exception as e:
            click.secho(f"  ⚠️  Could not read code: {e} — skipping code review", fg="yellow")
        click.echo()

    # 5. AI Verdict
    ai_verdict = ""
    if cfg.report.ai_summary and not no_ai:
        mode = "with code review" if code_context else "telemetry only"
        click.echo(f"  🤖 Requesting AI production verdict from Gemini ({mode})...")
        ai_verdict = get_ai_verdict(cfg, gate, [r.raw for r in results], code_context=code_context)
        click.echo()
        # Print first 15 lines of AI output to stdout
        for line in ai_verdict.split("\n")[:15]:
            click.echo(f"    {line}")
        click.echo()

    # 5. Generate Report
    html_path = output_html or cfg.report.output_path
    json_path = output_json or cfg.report.json_path

    click.echo(f"  📝 Writing reports → {html_path}, {json_path}")
    html, json_report = generate(cfg, gate, results, ai_verdict)
    write_reports(html, json_report, html_path, json_path)

    # 6. Final Gate Decision
    click.echo()
    if gate.is_pass:
        click.secho("╔══════════════════════════════════════════════════╗", fg="green")
        click.secho("║   ✅  GATE PASSED — READY FOR PRODUCTION          ║", fg="green")
        click.secho("╚══════════════════════════════════════════════════╝", fg="green")
        click.echo()
        sys.exit(0)
    else:
        click.secho("╔══════════════════════════════════════════════════╗", fg="red")
        click.secho("║   ❌  GATE FAILED — DO NOT DEPLOY                 ║", fg="red")
        click.secho("╚══════════════════════════════════════════════════╝", fg="red")
        click.echo()
        click.secho(f"  Blocking failures ({len(gate.blocking_failures)}):", fg="red")
        for v in gate.blocking_failures:
            click.secho(f"    • {v.test_id}: {', '.join(v.reasons)}", fg="red")
        click.echo()
        sys.exit(1)


if __name__ == "__main__":
    cli()
