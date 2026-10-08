"""Write per-target JSON reports and roll them up into a static HTML index."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from jinja2 import Template

from .runner import RunReport

INDEX_TEMPLATE = Template(
    """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>readmeorrunme — local report</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 2rem; max-width: 60rem; }
  h1 { font-size: 1.4rem; margin-bottom: 0.25rem; }
  .sub { color: #666; margin-bottom: 1.5rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.95rem; }
  th, td { text-align: left; padding: 0.55rem 0.7rem; border-bottom: 1px solid #ddd; vertical-align: top; }
  th { font-weight: 600; background: rgba(0,0,0,0.04); }
  .green { color: #137333; font-weight: 600; }
  .red   { color: #b3261e; font-weight: 600; }
  .muted { color: #777; }
  code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85rem; }
  @media (prefers-color-scheme: dark) {
    body { background: #121212; color: #e6e6e6; }
    th { background: rgba(255,255,255,0.06); }
    th, td { border-bottom-color: #333; }
    .muted { color: #999; }
  }
</style>
</head>
<body>
  <h1>readmeorrunme — local report</h1>
  <div class="sub">Generated {{ generated_at }} · {{ rows|length }} target(s)</div>
  <table>
    <thead>
      <tr>
        <th>Target</th>
        <th>Last green</th>
        <th>Last red</th>
        <th>Mean TTFR (s)</th>
        <th>Blocks (last run)</th>
        <th>Failure bucket</th>
      </tr>
    </thead>
    <tbody>
      {% for r in rows %}
      <tr>
        <td>
          <strong>{{ r.name }}</strong><br />
          <span class="muted"><code>{{ r.repo }}</code></span>
        </td>
        <td>{% if r.last_green %}<span class="green">{{ r.last_green }}</span>{% else %}<span class="muted">—</span>{% endif %}</td>
        <td>{% if r.last_red %}<span class="red">{{ r.last_red }}</span>{% else %}<span class="muted">—</span>{% endif %}</td>
        <td>{% if r.mean_ttfr is not none %}{{ "%.1f"|format(r.mean_ttfr) }}{% else %}<span class="muted">—</span>{% endif %}</td>
        <td>{{ r.last_block_summary }}</td>
        <td>{% if r.last_bucket %}<code>{{ r.last_bucket }}</code>{% else %}<span class="muted">—</span>{% endif %}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  <p class="muted" style="margin-top:2rem;font-size:0.85rem;">
    v0.1 · local-only · PR-first launch planned late November.
  </p>
</body>
</html>
"""
)


def write_json_report(reports_dir: Path, report: RunReport) -> Path:
    """Write ``report`` to ``reports/<target>/<date>.json`` and return the path."""
    target_dir = reports_dir / report.target_id
    target_dir.mkdir(parents=True, exist_ok=True)
    date = report.started_at[:10]
    out = target_dir / f"{date}.json"
    out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return out


def _summarize_runs(target_dir: Path) -> dict[str, Any]:
    """Look over every JSON report in ``target_dir`` and compute summary stats."""
    files = sorted(target_dir.glob("*.json"))
    last_green: str | None = None
    last_red: str | None = None
    ttfr_values: list[float] = []
    last_doc: dict[str, Any] | None = None

    for f in files:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        date = doc.get("started_at", "")[:10]
        green = (
            doc.get("first_failure_index") is None
            and not doc.get("container_error")
            and any(not b.get("skipped") for b in doc.get("blocks", []))
        )
        if green:
            if last_green is None or date > last_green:
                last_green = date
            # time-to-first-successful-run across non-skipped blocks
            wall = sum(
                b.get("wall_seconds", 0.0)
                for b in doc.get("blocks", [])
                if not b.get("skipped")
            )
            ttfr_values.append(wall)
        else:
            if last_red is None or date > last_red:
                last_red = date
        last_doc = doc

    executed = (
        [b for b in last_doc.get("blocks", []) if not b.get("skipped")]
        if last_doc
        else []
    )
    skipped = (
        [b for b in last_doc.get("blocks", []) if b.get("skipped")]
        if last_doc
        else []
    )
    passed = [b for b in executed if b.get("exit_code") == 0]
    summary = (
        f"{len(passed)}/{len(executed)} passed"
        + (f" · {len(skipped)} skipped" if skipped else "")
    )

    last_bucket: str | None = None
    if last_doc:
        for b in last_doc.get("blocks", []):
            cls = b.get("classification")
            if cls:
                last_bucket = cls.get("bucket")
                break

    return {
        "last_green": last_green,
        "last_red": last_red,
        "mean_ttfr": (sum(ttfr_values) / len(ttfr_values)) if ttfr_values else None,
        "last_block_summary": summary if last_doc else "no runs yet",
        "last_bucket": last_bucket,
        "repo": last_doc.get("repo") if last_doc else "",
        "name": last_doc.get("target_name") if last_doc else target_dir.name,
    }


def render_index(reports_dir: Path) -> Path:
    """Scan every ``reports/<target>/`` folder and write ``reports/index.html``."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for target_dir in sorted(p for p in reports_dir.iterdir() if p.is_dir()):
        summary = _summarize_runs(target_dir)
        summary["target_id"] = target_dir.name
        rows.append(summary)

    html = INDEX_TEMPLATE.render(
        rows=rows,
        generated_at=dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )
    out = reports_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    return out
