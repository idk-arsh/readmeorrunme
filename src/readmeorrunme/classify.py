"""Rule-based failure bucketing from stderr text.

Six buckets, applied in order of specificity. The order matters: a
``ModuleNotFoundError: No module named 'openai'`` reads as ``missing-dep``
until you notice the module name is a credentialed SDK, which flips the row to
``needs-API-key`` upstream of exec. We don't try to be clever here — the YAML
``skip_reasons`` list is where API-keyed blocks are filtered before they ever
run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

BUCKETS = (
    "missing-dep",
    "python-floor",
    "undocumented-env",
    "needs-API-key",
    "network-required",
    "docs-drift",
)


@dataclass
class Classification:
    bucket: str
    evidence: str  # the matched substring / pattern, for human review


_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "python-floor",
        re.compile(
            r"(requires python\s*>=|python_requires|python version\s*[<>=]|"
            r"ERROR: Package .* requires a different Python)",
            re.IGNORECASE,
        ),
        "python version floor",
    ),
    (
        "needs-API-key",
        re.compile(
            r"(api[\s_-]?key|unauthori[sz]ed|401\b|403\b|authentication (failed|required)|"
            r"missing token|invalid token|OPENAI_API_KEY|ANTHROPIC_API_KEY|MOTHERDUCK_TOKEN)",
            re.IGNORECASE,
        ),
        "credentialed call",
    ),
    (
        "network-required",
        re.compile(
            r"(temporary failure in name resolution|could not resolve host|"
            r"nodename nor servname|connection refused|connection timed out|"
            r"name or service not known|network is unreachable|getaddrinfo)",
            re.IGNORECASE,
        ),
        "network reachability",
    ),
    (
        "undocumented-env",
        re.compile(
            r"(environment variable .* (not set|is required|must be set)|"
            r"missing required (env|environment)|KeyError:\s*['\"][A-Z_]+['\"])",
            re.IGNORECASE,
        ),
        "env var expected but undocumented",
    ),
    (
        "missing-dep",
        re.compile(
            r"(ModuleNotFoundError|No module named|command not found|"
            r"ImportError:\s*No module|error: externally-managed-environment|"
            r"ERROR: Could not find a version|npm ERR!\s+code\s+E404)",
            re.IGNORECASE,
        ),
        "dependency not installed",
    ),
]


def classify(stderr: str, exit_code: int | None = None) -> Classification:
    """Return the best-fit failure bucket for a stderr tail.

    If nothing matches, we return ``docs-drift`` — the catch-all for "the
    command ran but the documented behaviour isn't what happened." That bucket
    is also where human review is most useful, so keeping it as the default
    pushes genuinely novel breakage to the top of the triage queue.
    """
    haystack = stderr or ""
    for bucket, pattern, evidence in _PATTERNS:
        match = pattern.search(haystack)
        if match:
            return Classification(bucket=bucket, evidence=match.group(0))
    return Classification(bucket="docs-drift", evidence="unmatched stderr")
