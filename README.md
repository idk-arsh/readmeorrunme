# readmeorrunme

A nightly runner that pulls down the README of an OSS devtool, pulls out the
quickstart code blocks, and runs them in a fresh container to see whether they
still work.

If a block fails, the run captures stderr, the exit code, how long it took,
and tags the failure into one of six buckets (`missing-dep`, `python-floor`,
`undocumented-env`, `needs-API-key`, `network-required`, `docs-drift`).

## Status

Early WIP. v0.1 runs locally only. The PR-first launch is targeted for late
November, once there is a visible track record of merged fixes to point at.
Nothing is auto-posted anywhere until then.

## What v0.1 does

- Fetches a target's README from GitHub (handles `README.md` and `README.rst`,
  picks the top-level file).
- Parses it with `markdown-it-py` and takes the first H2 whose heading matches
  `Quick`, `Install`, or `Getting Started` as the quickstart section.
- Pulls out fenced `bash` / `sh` / `python` blocks from that section.
- Runs them in order inside a fresh `python:3.12-slim` or `node:20-alpine`
  container, 90 s per block, captures stdout, stderr tail, exit code, and wall
  time.
- Classifies any failure by rule-based matching on the stderr text.
- Writes a per-target JSON report under `reports/<target>/<date>.json` and
  rolls up all targets into a one-page `reports/index.html` summary.

Anything that needs API keys, GPUs, or paid cloud auth is skipped and logged
in the report, not failed. Opt-in `.readmeorrunme.yaml`, the GitHub App that
files PRs, the nightly cron, and the public scoreboard are v0.2.

## Install

```bash
pip install -e .
```

Requires Python 3.12+ and a working Docker daemon on the host.

## Use

```bash
rormr run duckdb-python
rormr run-all
rormr report
```

`run <target>` runs one target by its id in `targets.yaml`. `run-all` runs
every target. `report` rebuilds `reports/index.html` from existing JSON.

Seed targets live in `targets.yaml`.

## What's next

- Weekend 2: GitHub Actions cron, GitHub App that opens draft PRs with the
  failing block + container log + proposed fix, 7-day private embargo clause,
  opt-in `.readmeorrunme.yaml`, public scoreboard on GitHub Pages (opted-in
  repos only).
- Mid-November: a writeup on what the first month of nightly runs across ~20
  data-tool quickstarts actually looked like.

## License

MIT.
