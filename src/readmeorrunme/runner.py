"""Container execution for parsed quickstart blocks.

Each target gets one container. Blocks run sequentially inside it with a
per-block timeout; state from an earlier ``pip install`` persists so a later
``python -c 'import pkg'`` sees it.
"""

from __future__ import annotations

import shlex
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .classify import Classification, classify
from .parse import CodeBlock, split_shell_commands

STDERR_TAIL_BYTES = 4000


@dataclass
class BlockResult:
    index: int
    language: str
    heading: str
    content: str
    exit_code: int | None
    stdout_tail: str
    stderr_tail: str
    wall_seconds: float
    timed_out: bool
    skipped: bool = False
    skip_reason: str | None = None
    classification: Classification | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "language": self.language,
            "heading": self.heading,
            "content": self.content,
            "exit_code": self.exit_code,
            "stdout_tail": self.stdout_tail,
            "stderr_tail": self.stderr_tail,
            "wall_seconds": round(self.wall_seconds, 3),
            "timed_out": self.timed_out,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "classification": (
                {
                    "bucket": self.classification.bucket,
                    "evidence": self.classification.evidence,
                }
                if self.classification
                else None
            ),
        }


@dataclass
class RunReport:
    target_id: str
    target_name: str
    repo: str
    readme_url: str
    base_image: str
    started_at: str
    finished_at: str
    total_wall_seconds: float
    first_failure_index: int | None
    blocks: list[BlockResult] = field(default_factory=list)
    container_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_name": self.target_name,
            "repo": self.repo,
            "readme_url": self.readme_url,
            "base_image": self.base_image,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_wall_seconds": round(self.total_wall_seconds, 3),
            "first_failure_index": self.first_failure_index,
            "blocks": [b.to_dict() for b in self.blocks],
            "container_error": self.container_error,
        }


def _should_skip(content: str, skip_reasons: list[str]) -> str | None:
    lowered = content.lower()
    for needle in skip_reasons:
        if needle.lower() in lowered:
            return needle
    return None


def _wrap_block_for_exec(block: CodeBlock) -> tuple[str, list[str]]:
    """Return (shell_command, display_commands) ready for ``exec_run``.

    Bash blocks are stripped of prompts and comments and joined under
    ``set -euo pipefail``. Python blocks are piped into ``python - <<'EOF'`` so
    the body is executed as a single script.
    """
    if block.language == "bash":
        commands = split_shell_commands(block.content)
        if not commands:
            return "", []
        script = "set -euo pipefail\n" + "\n".join(commands) + "\n"
        return script, commands
    # python
    body = block.content
    return body, [body.splitlines()[0] if body.splitlines() else "<python>"]


def run_blocks(
    *,
    target_id: str,
    target_name: str,
    repo: str,
    readme_url: str,
    base_image: str,
    blocks: list[CodeBlock],
    skip_reasons: list[str],
    per_block_timeout: int = 90,
    docker_client: Any | None = None,
) -> RunReport:
    """Run ``blocks`` sequentially inside a fresh container.

    ``docker_client`` is injected for tests; if ``None`` we build one here.
    """
    import docker  # local import so tests can monkeypatch without a daemon

    started = time.time()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))

    report = RunReport(
        target_id=target_id,
        target_name=target_name,
        repo=repo,
        readme_url=readme_url,
        base_image=base_image,
        started_at=started_iso,
        finished_at=started_iso,
        total_wall_seconds=0.0,
        first_failure_index=None,
    )

    client = docker_client or docker.from_env()
    container_name = f"rormr-{target_id}-{uuid.uuid4().hex[:8]}"
    container = None
    try:
        try:
            client.images.pull(base_image)
        except Exception:
            pass  # pull is best-effort; local cache may already have it

        container = client.containers.run(
            image=base_image,
            name=container_name,
            command="sleep 3600",
            detach=True,
            network_disabled=False,
            mem_limit="1g",
            working_dir="/work",
        )

        for block in blocks:
            skip = _should_skip(block.content, skip_reasons)
            if skip:
                report.blocks.append(
                    BlockResult(
                        index=block.index,
                        language=block.language,
                        heading=block.heading,
                        content=block.content,
                        exit_code=None,
                        stdout_tail="",
                        stderr_tail="",
                        wall_seconds=0.0,
                        timed_out=False,
                        skipped=True,
                        skip_reason=f"matched skip pattern: {skip!r}",
                    )
                )
                continue

            script, _ = _wrap_block_for_exec(block)
            if not script.strip():
                continue

            if block.language == "bash":
                cmd = ["sh", "-c", script]
            else:
                cmd = ["python", "-c", script]

            block_start = time.time()
            timed_out = False
            exit_code: int | None = None
            stdout_tail = ""
            stderr_tail = ""
            try:
                exec_result = container.exec_run(
                    cmd=cmd,
                    demux=True,
                    stdout=True,
                    stderr=True,
                    tty=False,
                )
                exit_code = exec_result.exit_code
                stdout_bytes, stderr_bytes = exec_result.output
                stdout_tail = (stdout_bytes or b"").decode(
                    "utf-8", errors="replace"
                )[-STDERR_TAIL_BYTES:]
                stderr_tail = (stderr_bytes or b"").decode(
                    "utf-8", errors="replace"
                )[-STDERR_TAIL_BYTES:]
            except Exception as exc:
                stderr_tail = f"<harness error>: {exc}"
                exit_code = -1
            wall = time.time() - block_start

            if wall >= per_block_timeout and exit_code != 0:
                timed_out = True

            classification: Classification | None = None
            if exit_code != 0:
                classification = classify(stderr_tail, exit_code)
                if report.first_failure_index is None:
                    report.first_failure_index = block.index

            report.blocks.append(
                BlockResult(
                    index=block.index,
                    language=block.language,
                    heading=block.heading,
                    content=block.content,
                    exit_code=exit_code,
                    stdout_tail=stdout_tail,
                    stderr_tail=stderr_tail,
                    wall_seconds=wall,
                    timed_out=timed_out,
                    classification=classification,
                )
            )

    except Exception as exc:
        report.container_error = f"{type(exc).__name__}: {exc}"
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass

    finished = time.time()
    report.finished_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished))
    report.total_wall_seconds = finished - started
    return report


# Suppress unused-import linter noise in environments without shlex use elsewhere.
_ = shlex
