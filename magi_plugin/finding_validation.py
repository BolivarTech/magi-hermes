#!/usr/bin/env python3
"""Diff-grounded validation of MAGI findings (code-review only).

Ports panóptico's hallucination guard and adds the line-range check.
Pure stdlib and total — never raises into the orchestrator.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from magi_plugin.finding_id import normalize_path

#: ``@@ -a,b +c,d @@`` — old start/count (g1/g2) and new start/count (g3/g4).
_HUNK_RE = re.compile(r"^@@ -(\\d+)(?:,(\\d+))? \\+(\\d+)(?:,(\\d+))? @@")
#: New-file (post-image) header path. The ``b/`` prefix is git-specific.
_NEWFILE_RE = re.compile(r"^\\+\\+\\+ (?:b/)?(.+)$")
#: Old-file header prefix.
_OLDFILE_PREFIX = "--- "
#: Margin for line-range fuzz (LLM counting error).
LINE_RANGE_MARGIN = 3


def _clean_newfile_path(captured: str) -> str | None:
    """Normalize a captured ``+++`` header path."""
    path = captured.split("\t", 1)[0].strip()
    if not path or path == "/dev/null":
        return None
    return path


def _iter_diff_events(diff: str) -> Iterator[tuple[Any, ...]]:
    """Walk a unified diff once, yielding its structural events.

    Yields:
    * ("file", path) — a new-file header.
    * ("add", lineno, body) — an added post-image line (+ stripped).
    """
    lines = diff.splitlines()
    n = len(lines)
    current: str | None = None
    new_line = 0
    old_rem = 0
    new_rem = 0
    i = 0
    while i < n:
        raw = lines[i]
        if raw.startswith("diff --git "):
            old_rem = new_rem = 0
            i += 1
            continue
        if old_rem > 0 or new_rem > 0:
            if raw.startswith("\\ "):
                i += 1
                continue
            if raw.startswith("+"):
                if current is not None:
                    yield ("add", new_line, raw[1:])
                new_line += 1
                new_rem -= 1
                i += 1
                continue
            if raw.startswith("-"):
                old_rem -= 1
                i += 1
                continue
            new_line += 1
            old_rem -= 1
            new_rem -= 1
            i += 1
            continue
        # Outside any hunk: structural lines only.
        if raw.startswith(_OLDFILE_PREFIX):
            m = _NEWFILE_RE.match(lines[i + 1]) if i + 1 < n else None
            if m:
                current = _clean_newfile_path(m.group(1))
                if current is not None:
                    yield ("file", current)
                i += 2
                continue
            i += 1
            continue
        h = _HUNK_RE.match(raw)
        if h:
            new_line = int(h.group(3))
            old_rem = int(h.group(2)) if h.group(2) else 1
            new_rem = int(h.group(4)) if h.group(4) else 1
            i += 1
            continue
        i += 1


def extract_touched_files(diff: str) -> list[str]:
    """Return the ordered (raw) post-image paths a unified diff touches."""
    return [ev[1] for ev in _iter_diff_events(diff) if ev[0] == "file"]


def added_lines_by_file(diff: str) -> dict[str, list[str]]:
    """Map each (raw) post-image path to its added (+) line bodies."""
    result: dict[str, list[str]] = {}
    current: str | None = None
    for ev in _iter_diff_events(diff):
        if ev[0] == "file":
            current = ev[1]
        elif current is not None:
            result.setdefault(current, []).append(ev[2])
    return result


def parse_diff_ranges(diff: str) -> dict[str, set[int]]:
    """Map each touched file (normalized) to its changed post-image line numbers."""
    ranges: dict[str, set[int]] = {}
    current: str | None = None
    for ev in _iter_diff_events(diff):
        if ev[0] == "file":
            current = normalize_path(ev[1])
            ranges.setdefault(current, set())
        elif current is not None:
            ranges[current].add(ev[1])
    return ranges


def valid_files(diff: str) -> set[str]:
    """Return the set of normalized file paths present in diff."""
    return set(parse_diff_ranges(diff).keys())


def _line_outside_range(line: Any, rng: set[int], margin: int) -> bool:
    if not isinstance(line, int) or isinstance(line, bool):
        return False
    return bool(rng) and not any(abs(line - r) <= margin for r in rng)


def validate_findings(
    findings: list[dict[str, Any]],
    files: set[str],
    ranges: dict[str, set[int]],
    margin: int = LINE_RANGE_MARGIN,
) -> tuple[list[dict[str, Any]], int, int]:
    """Filter findings against the diff. Returns (kept, dropped, annotated).

    * No file -> kept (not validatable).
    * file in files -> in-diff; line outside changed range (+/- margin)
      -> soft-annotate "[outside changed range]".
    * file not exact but basename uniquely matches a diff file ->
      soft-annotate "[path unverified]" and run line-range check.
    * No match -> hard-drop (hallucinated file).
    """
    base_counts: dict[str, int] = {}
    base_to_file: dict[str, str] = {}
    for vf in files:
        b = vf.rsplit("/", 1)[-1]
        base_counts[b] = base_counts.get(b, 0) + 1
        base_to_file[b] = vf
    kept: list[dict[str, Any]] = []
    dropped = 0
    annotated = 0
    for f in findings:
        file = f.get("file")
        if not file or not isinstance(file, str):
            kept.append(f)
            continue
        nf = normalize_path(file)
        if nf in files:
            if _line_outside_range(f.get("line"), ranges.get(nf, set()), margin):
                f = {**f, "detail": "[outside changed range] " + str(f.get("detail", ""))}
                annotated += 1
            kept.append(f)
        elif base_counts.get(nf.rsplit("/", 1)[-1], 0) == 1:
            resolved = base_to_file[nf.rsplit("/", 1)[-1]]
            detail = str(f.get("detail", ""))
            if _line_outside_range(f.get("line"), ranges.get(resolved, set()), margin):
                detail = "[outside changed range] " + detail
            f = {**f, "detail": "[path unverified] " + detail}
            annotated += 1
            kept.append(f)
        else:
            dropped += 1
    return kept, dropped, annotated
