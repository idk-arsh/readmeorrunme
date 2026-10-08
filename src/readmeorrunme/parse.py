"""Markdown parsing: locate the quickstart section and extract runnable blocks."""

from __future__ import annotations

from dataclasses import dataclass

from markdown_it import MarkdownIt

QUICKSTART_HEADING_NEEDLES = ("quick", "install", "getting started")
RUNNABLE_LANGS = {"bash", "sh", "shell", "console", "python", "py"}


@dataclass
class CodeBlock:
    language: str  # normalized to "bash" or "python"
    content: str
    heading: str  # the H2 the block was found under
    index: int    # ordinal within the quickstart section (0-based)


def _norm_lang(info: str) -> str | None:
    tag = (info or "").strip().split()[0].lower() if info else ""
    if tag in {"bash", "sh", "shell", "console"}:
        return "bash"
    if tag in {"python", "py"}:
        return "python"
    return None


def _heading_matches_quickstart(text: str) -> bool:
    lower = text.lower()
    return any(needle in lower for needle in QUICKSTART_HEADING_NEEDLES)


def _heading_text(tokens: list, start_idx: int) -> str:
    # heading_open at start_idx, inline at start_idx+1, heading_close at +2
    if start_idx + 1 < len(tokens) and tokens[start_idx + 1].type == "inline":
        return tokens[start_idx + 1].content.strip()
    return ""


def extract_quickstart_blocks(markdown_text: str) -> list[CodeBlock]:
    """Pull runnable fenced blocks out of the first quickstart-ish H2.

    The heuristic: walk the token stream, find the first ``heading_open`` of
    level 2 whose text contains "Quick", "Install", or "Getting Started"
    (case-insensitive), then collect fenced code blocks until the next H1 or
    H2. ``bash``/``sh``/``shell``/``console`` become ``bash``;
    ``python``/``py`` become ``python``; everything else is skipped.
    """
    md = MarkdownIt("commonmark")
    tokens = md.parse(markdown_text)

    in_section = False
    section_heading = ""
    blocks: list[CodeBlock] = []
    i = 0
    ordinal = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            level = int(tok.tag[1:])
            text = _heading_text(tokens, i)
            if not in_section and level == 2 and _heading_matches_quickstart(text):
                in_section = True
                section_heading = text
            elif in_section and level in (1, 2):
                break
        elif in_section and tok.type == "fence":
            lang = _norm_lang(tok.info)
            if lang:
                blocks.append(
                    CodeBlock(
                        language=lang,
                        content=tok.content,
                        heading=section_heading,
                        index=ordinal,
                    )
                )
                ordinal += 1
        i += 1

    return blocks


def split_shell_commands(block_content: str) -> list[str]:
    """Split a bash fence into executable commands.

    README shell blocks commonly prefix lines with ``$`` or ``>`` for display,
    and may interleave ``# ...`` comments and blank lines. We strip prompts and
    skip comment/blank lines so each returned string is something a shell can
    actually run.
    """
    commands: list[str] = []
    for raw in block_content.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("$ "):
            stripped = stripped[2:]
        elif stripped.startswith("> "):
            stripped = stripped[2:]
        elif stripped in ("$", ">"):
            continue
        commands.append(stripped)
    return commands
