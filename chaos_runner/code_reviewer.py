"""
code_reviewer.py — Source Code Reader for AI Gate

Reads and chunks source files from a given directory, filtering to
code-relevant files only. Used to give the AI gate concrete source
context for more precise, actionable remediation advice.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

# Extensions to include
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".cs",
    ".rb", ".php", ".rs", ".cpp", ".c", ".h", ".yaml", ".yml",
    ".json", ".env.example", ".toml", ".sh",
}

# Directories to always skip
SKIP_DIRS = {
    "node_modules", "venv", ".venv", "env", "__pycache__", ".git",
    "dist", "build", ".next", "target", "vendor", ".idea", ".vscode",
    "coverage", "htmlcov", ".mypy_cache", ".pytest_cache", "eggs",
    ".eggs", "migrations",
}

# Hard cap on total characters sent to Gemini to stay within token budget
MAX_TOTAL_CHARS = 80_000
# Per-file cap so one huge file doesn't consume everything
MAX_FILE_CHARS = 8_000


def read_code_files(code_path: str | Path) -> list[dict]:
    """
    Walk the directory and return a list of:
      { "path": str, "content": str, "truncated": bool }
    
    Respects total character budget so we don't hit Gemini token limits.
    """
    root = Path(code_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"code-path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"code-path must be a directory: {root}")

    files: list[dict] = []
    total_chars = 0

    for file_path in sorted(root.rglob("*")):
        if total_chars >= MAX_TOTAL_CHARS:
            break

        # Skip hidden dirs and excluded dirs
        parts = set(file_path.parts)
        if any(p.startswith(".") or p in SKIP_DIRS for p in parts):
            continue

        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in CODE_EXTENSIONS:
            continue

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        truncated = False
        if len(content) > MAX_FILE_CHARS:
            content = content[:MAX_FILE_CHARS] + "\n... [file truncated]"
            truncated = True

        remaining = MAX_TOTAL_CHARS - total_chars
        if len(content) > remaining:
            content = content[:remaining] + "\n... [budget exceeded]"
            truncated = True

        rel_path = file_path.relative_to(root)
        files.append({
            "path": str(rel_path),
            "content": content,
            "truncated": truncated,
        })
        total_chars += len(content)

    return files


def format_for_prompt(files: list[dict]) -> str:
    """Format the file list into a compact code block for the Gemini prompt."""
    if not files:
        return "(no source files found)"

    parts = []
    for f in files:
        note = " [TRUNCATED]" if f["truncated"] else ""
        parts.append(
            f"### File: {f['path']}{note}\n"
            f"```\n{f['content']}\n```"
        )
    return "\n\n".join(parts)


def summarize(files: list[dict]) -> str:
    """Return a one-liner summary for CLI output."""
    total = sum(len(f["content"]) for f in files)
    truncated = sum(1 for f in files if f["truncated"])
    s = f"{len(files)} files, ~{total:,} chars"
    if truncated:
        s += f" ({truncated} truncated to fit token budget)"
    return s
