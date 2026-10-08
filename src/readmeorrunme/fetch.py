"""Fetch a README blob from a GitHub repo.

Handles the two common extensions (``README.md`` and ``README.rst``) and lets
callers pin to a specific path for repos (Polars, DuckDB) where the top-level
``README.md`` is the one we care about but sub-packages ship their own.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

RAW_BASE = "https://raw.githubusercontent.com"


@dataclass
class FetchedReadme:
    url: str
    text: str
    extension: str  # "md" or "rst"


def _raw_url(repo: str, branch: str, path: str) -> str:
    return f"{RAW_BASE}/{repo}/{branch}/{path}"


def fetch_readme(
    repo: str,
    branch: str = "main",
    readme_path: str | None = None,
    *,
    client: httpx.Client | None = None,
    timeout: float = 20.0,
) -> FetchedReadme:
    """Return the README for ``repo`` at ``branch``.

    If ``readme_path`` is given, fetch that path verbatim. Otherwise try
    ``README.md`` first, then ``README.rst``.
    """
    close = False
    if client is None:
        client = httpx.Client(timeout=timeout, follow_redirects=True)
        close = True
    try:
        candidates: list[str]
        if readme_path:
            candidates = [readme_path]
        else:
            candidates = ["README.md", "README.rst"]

        last_err: Exception | None = None
        for path in candidates:
            url = _raw_url(repo, branch, path)
            try:
                resp = client.get(url)
            except httpx.HTTPError as exc:
                last_err = exc
                continue
            if resp.status_code == 200:
                ext = "rst" if path.lower().endswith(".rst") else "md"
                return FetchedReadme(url=url, text=resp.text, extension=ext)
            last_err = RuntimeError(f"{url} -> HTTP {resp.status_code}")

        raise RuntimeError(f"could not fetch README for {repo}@{branch}: {last_err}")
    finally:
        if close:
            client.close()
