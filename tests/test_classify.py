"""Classifier tests: canonical stderr samples per bucket."""

from __future__ import annotations

import pytest

from readmeorrunme.classify import classify

CASES = [
    (
        "missing-dep",
        "Traceback (most recent call last):\n"
        "  File \"<stdin>\", line 1, in <module>\n"
        "ModuleNotFoundError: No module named 'polars'",
    ),
    (
        "missing-dep",
        "sh: 1: dbt: command not found",
    ),
    (
        "python-floor",
        "ERROR: Package 'uv' requires a different Python: 3.10.4 not in '>=3.12'",
    ),
    (
        "undocumented-env",
        "KeyError: 'MYAPP_CONFIG_PATH'",
    ),
    (
        "needs-API-key",
        "openai.AuthenticationError: 401 Unauthorized · check your OPENAI_API_KEY",
    ),
    (
        "network-required",
        "requests.exceptions.ConnectionError: HTTPSConnectionPool(host='api.example.com', port=443): "
        "Max retries exceeded (Caused by NameResolutionError: Temporary failure in name resolution)",
    ),
    (
        "docs-drift",
        "AssertionError: expected 3 rows, got 0",
    ),
]


@pytest.mark.parametrize("expected,stderr", CASES)
def test_classify_buckets(expected: str, stderr: str) -> None:
    result = classify(stderr)
    assert result.bucket == expected, (
        f"stderr={stderr!r} classified as {result.bucket} ({result.evidence!r}),"
        f" wanted {expected}"
    )


def test_empty_stderr_falls_through_to_docs_drift() -> None:
    result = classify("")
    assert result.bucket == "docs-drift"
