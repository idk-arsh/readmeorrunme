"""Typer CLI entry point: ``rormr``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import yaml

from .fetch import fetch_readme
from .parse import extract_quickstart_blocks
from .report import render_index, write_json_report
from .runner import run_blocks

app = typer.Typer(add_completion=False, help="readmeorrunme CLI")

DEFAULT_TARGETS_FILE = Path("targets.yaml")
DEFAULT_REPORTS_DIR = Path("reports")


def _load_targets(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    targets = data.get("targets") if isinstance(data, dict) else None
    if not isinstance(targets, list):
        raise typer.BadParameter(f"{path}: 'targets' must be a list")
    return targets


def _find_target(targets: list[dict[str, Any]], target_id: str) -> dict[str, Any]:
    for t in targets:
        if t.get("id") == target_id:
            return t
    known = ", ".join(sorted(t.get("id", "?") for t in targets))
    raise typer.BadParameter(f"unknown target {target_id!r}; known: {known}")


def _run_one(target: dict[str, Any], reports_dir: Path, timeout: int) -> None:
    typer.echo(f"[fetch] {target['id']} ← {target['repo']}")
    fetched = fetch_readme(
        repo=target["repo"],
        branch=target.get("branch", "main"),
        readme_path=target.get("readme_path"),
    )
    blocks = extract_quickstart_blocks(fetched.text)
    typer.echo(f"[parse] {len(blocks)} runnable block(s) in quickstart section")

    report = run_blocks(
        target_id=target["id"],
        target_name=target.get("name", target["id"]),
        repo=target["repo"],
        readme_url=fetched.url,
        base_image=target.get("base_image", "python:3.12-slim"),
        blocks=blocks,
        skip_reasons=target.get("skip_reasons", []) or [],
        per_block_timeout=timeout,
    )
    out = write_json_report(reports_dir, report)
    status = "ok" if report.first_failure_index is None and not report.container_error else "fail"
    typer.echo(f"[write] {out} · {status}")


@app.command("run")
def run_cmd(
    target_id: str = typer.Argument(..., help="target id from targets.yaml"),
    targets_file: Path = typer.Option(DEFAULT_TARGETS_FILE, "--targets", "-t"),
    reports_dir: Path = typer.Option(DEFAULT_REPORTS_DIR, "--reports", "-r"),
    timeout: int = typer.Option(90, "--timeout", help="per-block timeout seconds"),
) -> None:
    """Run a single target by id."""
    targets = _load_targets(targets_file)
    target = _find_target(targets, target_id)
    _run_one(target, reports_dir, timeout)


@app.command("run-all")
def run_all_cmd(
    targets_file: Path = typer.Option(DEFAULT_TARGETS_FILE, "--targets", "-t"),
    reports_dir: Path = typer.Option(DEFAULT_REPORTS_DIR, "--reports", "-r"),
    timeout: int = typer.Option(90, "--timeout"),
) -> None:
    """Run every target in targets.yaml, then regenerate the index."""
    targets = _load_targets(targets_file)
    for target in targets:
        try:
            _run_one(target, reports_dir, timeout)
        except Exception as exc:  # keep going; one bad target shouldn't kill the batch
            typer.echo(f"[error] {target.get('id')}: {exc}", err=True)
    out = render_index(reports_dir)
    typer.echo(f"[index] {out}")


@app.command("report")
def report_cmd(
    reports_dir: Path = typer.Option(DEFAULT_REPORTS_DIR, "--reports", "-r"),
) -> None:
    """Rebuild reports/index.html from existing JSON reports."""
    out = render_index(reports_dir)
    typer.echo(f"[index] {out}")


if __name__ == "__main__":
    app()
