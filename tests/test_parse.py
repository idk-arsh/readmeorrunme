"""Parser tests: known-shape README → expected block list."""

from __future__ import annotations

import textwrap

from readmeorrunme.parse import extract_quickstart_blocks, split_shell_commands


SAMPLE_README = textwrap.dedent(
    """\
    # supertool

    A thing that does things.

    ## Overview

    Lorem ipsum.

    ```python
    # this one is BEFORE the quickstart section, must be ignored
    print("nope")
    ```

    ## Quickstart

    Install:

    ```bash
    $ pip install supertool
    ```

    Then run it:

    ```python
    import supertool
    supertool.go()
    ```

    A yaml example that should be skipped:

    ```yaml
    key: value
    ```

    ## Development

    ```bash
    pytest
    ```
    """
)


def test_quickstart_section_picked():
    blocks = extract_quickstart_blocks(SAMPLE_README)
    assert len(blocks) == 2
    assert blocks[0].language == "bash"
    assert "pip install supertool" in blocks[0].content
    assert blocks[0].heading.lower().startswith("quickstart")

    assert blocks[1].language == "python"
    assert "import supertool" in blocks[1].content


def test_installation_heading_matches():
    md = "## Installation\n\n```bash\nnpm install foo\n```\n"
    blocks = extract_quickstart_blocks(md)
    assert len(blocks) == 1
    assert blocks[0].language == "bash"


def test_getting_started_heading_matches():
    md = "## Getting Started\n\n```sh\ncurl example.com\n```\n"
    blocks = extract_quickstart_blocks(md)
    assert len(blocks) == 1
    assert blocks[0].language == "bash"  # sh normalised to bash


def test_no_matching_section_returns_empty():
    md = "## Changelog\n\n```bash\necho hi\n```\n"
    assert extract_quickstart_blocks(md) == []


def test_split_shell_commands_strips_prompts_and_comments():
    block = textwrap.dedent(
        """\
        $ pip install foo
        # this is a comment
        > python -c 'print(1)'

        echo done
        """
    )
    cmds = split_shell_commands(block)
    assert cmds == [
        "pip install foo",
        "python -c 'print(1)'",
        "echo done",
    ]
