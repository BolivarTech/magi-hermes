#!/usr/bin/env python3
"""Parse and validate agent JSON output from LLM backends.

Extracts structured JSON from various output formats, strips markdown
code fences, recovers the JSON verdict even when an agent wraps it in
natural-language prose (2.4.2), validates the result, and writes clean
JSON to the specified output file.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from magi_plugin.validate import MAX_INPUT_FILE_SIZE


_FENCE_START = re.compile(r"^```(?:json)?\s*\n?", re.IGNORECASE)
_FENCE_END = re.compile(r"\n?```\s*$")

_VERDICT_KEYS = ("agent", "verdict")
_LENIENT_RECOVERY_MAX_CHARS = 1_000_000
_MAX_BRACE_PROBES = 2_000


def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences wrapping the text."""
    text = text.strip()
    text = _FENCE_START.sub("", text)
    text = _FENCE_END.sub("", text)
    return text.strip()


def _extract_text(data: object) -> str:
    """Extract the meaningful text payload from backend JSON output."""
    if isinstance(data, dict) and "result" in data:
        return str(data["result"])
    if isinstance(data, dict) and "content" in data:
        content = data["content"]
        if not isinstance(content, list):
            raise ValueError(f"'content' must be a list, got {type(content).__name__}.")
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block["text"])
        raise ValueError("No text block found in 'content' array")
    if isinstance(data, str):
        return data
    if isinstance(data, dict) and "agent" in data and "verdict" in data:
        return json.dumps(data)
    raise ValueError(
        f"Unexpected output type: {type(data).__name__}. "
        f"Expected dict with 'result' or 'content' key, or plain string."
    )


def _embedded_verdict_object(text: str) -> dict[str, Any] | None:
    """Return the sole embedded JSON object that looks like an agent verdict.

    Schema-aware recovery: only objects carrying _VERDICT_KEYS qualify.
    Returns None on zero qualify, more than one qualify (ambiguous), or
    probe budget exhausted.
    """
    decoder = json.JSONDecoder()
    matches: list[dict[str, Any]] = []
    index = 0
    length = len(text)
    probes = 0
    while index < length and probes < _MAX_BRACE_PROBES:
        brace = text.find("{", index)
        if brace == -1:
            break
        probes += 1
        try:
            candidate, end = decoder.raw_decode(text, brace)
        except (json.JSONDecodeError, RecursionError):
            index = brace + 1
            continue
        if isinstance(candidate, dict) and all(key in candidate for key in _VERDICT_KEYS):
            matches.append(candidate)
            if len(matches) > 1:
                return None
        index = end if end > brace else brace + 1
    return matches[0] if len(matches) == 1 else None


def _loads_lenient(text: str) -> Any:
    """Parse JSON from text, tolerating natural-language prose around it.

    Fast path: strict json.loads. Fallback: embedded verdict recovery.
    Raises json.JSONDecodeError on failure (fail-closed).
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, RecursionError) as exc:
        if len(text) <= _LENIENT_RECOVERY_MAX_CHARS:
            verdict = _embedded_verdict_object(text)
            if verdict is not None:
                return verdict
        if isinstance(exc, RecursionError):
            raise json.JSONDecodeError(
                "Input nesting exceeds the JSON decoder limit", text, 0
            ) from exc
        raise


def parse_agent_output(input_path: str, output_path: str) -> None:
    """Read raw backend output, extract and validate JSON, write result.

    Args:
        input_path: Path to the raw JSON output file.
        output_path: Destination path for the cleaned JSON.
    """
    file_size = os.path.getsize(input_path)
    if file_size > MAX_INPUT_FILE_SIZE:
        raise ValueError(
            f"Input file {input_path} is {file_size} bytes, "
            f"exceeding maximum of {MAX_INPUT_FILE_SIZE} bytes."
        )
    with open(input_path, encoding="utf-8") as fh:
        data = json.load(fh)
    text = _extract_text(data)
    text = _strip_code_fences(text)
    parsed = _loads_lenient(text)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(parsed, fh, indent=2)
        fh.write("\n")


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "Usage: parse_agent_output.py <input_file> <output_file>",
            file=sys.stderr,
        )
        sys.exit(1)
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    try:
        parse_agent_output(input_path, output_path)
    except (json.JSONDecodeError, ValueError, FileNotFoundError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
