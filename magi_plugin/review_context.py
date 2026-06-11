#!/usr/bin/env python3
"""Deterministic, bounded, fail-safe review-context enrichment for MAGI
code-review mode. Runs only when the working tree is clean (== HEAD).
Never raises into the orchestrator (R7).
"""

from __future__ import annotations

import keyword
import os
import re
import subprocess

from magi_plugin.finding_validation import added_lines_by_file, extract_touched_files

_ENRICH_MAX_CHARS = 512_000
_DEF_WINDOW_LINES = 40
_MAX_CANDIDATES = 60
_MAX_DEFS = 40
_MAX_DEFS_PER_NAME = 5
_GIT_TIMEOUT = 30
_MAX_FILE_BYTES = 262_144
_MAX_TOUCHED_FILES = 50
_DIFF_MARKERS = ("diff --git ", "--- a/", "+++ b/")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DEF_RE = re.compile(r"^[\t ]*(?:def|class)[\t ]+([A-Za-z_][A-Za-z0-9_]*)")
_STRING_RE = re.compile(r"""(['"]).*?\1""")
_EXTRA_EXCLUDE = frozenset(
    {
        "self", "cls", "True", "False", "None",
        "print", "len", "range", "str", "int",
        "float", "bool", "dict", "list", "set", "tuple",
    }
)
_SOFT_KWLIST: frozenset[str] = frozenset(getattr(keyword, "softkwlist", []))


def _contains_diff(text: str) -> bool:
    return any(marker in text for marker in _DIFF_MARKERS)


def _read_file_safe(repo_root: str, rel_path: str, cache: "dict[str, str | None]") -> "str | None":
    if rel_path in cache:
        return cache[rel_path]
    content: "str | None" = None
    root_real = os.path.realpath(repo_root)
    full = os.path.realpath(os.path.join(repo_root, rel_path))
    try:
        inside = os.path.commonpath([root_real, full]) == root_real
    except ValueError:
        inside = False
    if inside:
        try:
            if os.path.isfile(full) and os.path.getsize(full) <= _MAX_FILE_BYTES:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                content = None if "\x00" in text else text
        except OSError:
            content = None
    cache[rel_path] = content
    return content


def _git(repo_root: str, *args: str) -> tuple[int, str]:
    try:
        result = subprocess.run(
            ["git", "-C", repo_root, *args],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return -1, ""
    return result.returncode, result.stdout


def _git_toplevel(start: str) -> str | None:
    rc, out = _git(start, "rev-parse", "--show-toplevel")
    if rc != 0:
        return None
    return out.strip() or None


def _tree_is_clean(repo_root: str) -> bool:
    rc, out = _git(repo_root, "status", "--porcelain", "--untracked-files=no")
    return rc == 0 and out.strip() == ""


def enrich_code_review_context(
    input_content: str,
    *,
    repo_root: str | None = None,
    base_ref: str = "main",
    max_chars: int = _ENRICH_MAX_CHARS,
    diff: str | None = None,
) -> tuple[str, str]:
    """Return (content, note); content unchanged on no-op. Never raises (R7)."""
    try:
        return _enrich(input_content, repo_root, base_ref, max_chars, diff)
    except Exception as exc:
        return input_content, f"enrichment skipped (error: {exc!r})"


def _coheres(content: str, added: list[str]) -> bool:
    return all(a.strip() == "" or a.strip() in content for a in added)


def _collect_touched(
    repo_root: str, diff_text: str, cache: "dict[str, str | None]"
) -> "tuple[list[tuple[str, str]], list[str]]":
    added_by_file = added_lines_by_file(diff_text)
    touched: list[tuple[str, str]] = []
    mismatched: list[str] = []
    for path in list(dict.fromkeys(extract_touched_files(diff_text)))[:_MAX_TOUCHED_FILES]:
        content = _read_file_safe(repo_root, path, cache)
        if content is None:
            continue
        if not _coheres(content, added_by_file.get(path, [])):
            mismatched.append(path)
            continue
        touched.append((path, content))
    return touched, mismatched


def _code_part(line: str) -> str:
    if line.lstrip().startswith("#"):
        return ""
    line = _STRING_RE.sub("", line)
    idx = line.find("  #")
    return line[:idx] if idx != -1 else line


def _defined_names(texts: list[str]) -> set[str]:
    names: set[str] = set()
    for text in texts:
        for line in text.splitlines():
            m = _DEF_RE.match(line)
            if m:
                names.add(m.group(1))
    return names


def _candidate_identifiers(diff_text: str, defined: set[str]) -> list[str]:
    ordered: dict[str, None] = {}
    for raw in diff_text.splitlines():
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        for tok in _IDENT_RE.findall(_code_part(raw[1:])):
            if tok in keyword.kwlist or tok in _SOFT_KWLIST or tok in _EXTRA_EXCLUDE or tok in defined:
                continue
            ordered.setdefault(tok, None)
            if len(ordered) >= _MAX_CANDIDATES:
                return list(ordered)
    return list(ordered)


def _read_excerpt(repo_root: str, rel_path: str, line_no: int, cache: "dict[str, str | None]") -> "str | None":
    content = _read_file_safe(repo_root, rel_path, cache)
    if content is None:
        return None
    lines = content.splitlines()
    start = max(0, line_no - 1)
    return "\n".join(lines[start : start + _DEF_WINDOW_LINES])


def _grep_defs(repo_root: str, names: list[str], cache: "dict[str, str | None]") -> "list[tuple[str, int, str]]":
    if not names:
        return []
    alt = "|".join(re.escape(n) for n in names)
    pattern = rf"^[\t ]*(def|class)[\t ]+({alt})([^A-Za-z0-9_]|$)"
    rc, out = _git(repo_root, "grep", "-nE", pattern)
    if rc != 0:
        return []
    defs: list[tuple[str, int, str]] = []
    seen: set[tuple[str, int]] = set()
    per_name: dict[str, int] = {}
    for hit in out.splitlines():
        parts = hit.split(":", 2)
        if len(parts) < 3:
            continue
        path, line_s, body = parts
        try:
            line_no = int(line_s)
        except ValueError:
            continue
        m = _DEF_RE.match(body)
        name = m.group(1) if m else None
        if name is not None and per_name.get(name, 0) >= _MAX_DEFS_PER_NAME:
            continue
        key = (path, line_no)
        if key in seen:
            continue
        seen.add(key)
        excerpt = _read_excerpt(repo_root, path, line_no, cache)
        if excerpt is not None:
            defs.append((path, line_no, excerpt))
            if name is not None:
                per_name[name] = per_name.get(name, 0) + 1
        if len(defs) >= _MAX_DEFS:
            break
    return defs


def _git_diff(repo_root: str, base_ref: str) -> "str | None":
    rc, out = _git(repo_root, "diff", f"{base_ref}...HEAD")
    if rc != 0:
        return None
    return out or None


def resolve_diff(input_content: str, repo_root: str, base_ref: str) -> str:
    """Resolve the review diff: input-embedded diff, else git diff <base>...HEAD.

    TOTAL: returns "" on ANY failure.
    """
    try:
        if _contains_diff(input_content):
            return input_content
        root = _git_toplevel(repo_root or os.getcwd())
        if root is None or not _tree_is_clean(root):
            return ""
        return _git_diff(root, base_ref) or ""
    except Exception:
        return ""


def _assemble(
    input_content: str,
    touched: list[tuple[str, str]],
    defs: list[tuple[str, int, str]],
    max_chars: int,
) -> tuple[str, str]:
    _TF_HDR = "## Touched files (full content)"
    _SD_HDR = "## Referenced symbol definitions"
    _JOIN = 2
    parts: list[str] = [input_content]
    used = len(input_content)
    omitted: list[str] = []
    file_blocks = sorted(((p, f"### {p}\n```\n{c}\n```") for p, c in touched), key=lambda pb: len(pb[1]))
    kept_files: list[str] = []
    for path, block in file_blocks:
        extra = len(block) + _JOIN + (len(_TF_HDR) + _JOIN if not kept_files else 0)
        if used + extra <= max_chars:
            kept_files.append(block)
            used += extra
        else:
            omitted.append(f"file {path}")
    if kept_files:
        parts.append(_TF_HDR + "\n\n" + "\n\n".join(kept_files))
    kept_defs: list[str] = []
    for path, line_no, excerpt in defs:
        block = f"### {path}:{line_no}\n```\n{excerpt}\n```"
        extra = len(block) + _JOIN + (len(_SD_HDR) + _JOIN if not kept_defs else 0)
        if used + extra <= max_chars:
            kept_defs.append(block)
            used += extra
        else:
            omitted.append(f"def {path}:{line_no}")
    if kept_defs:
        parts.append(_SD_HDR + "\n\n" + "\n\n".join(kept_defs))
    if len(parts) == 1:
        return input_content, "enrichment skipped (nothing within budget)"
    note = f"enriched: {len(kept_files)} file(s), {len(kept_defs)} def(s)"
    if omitted:
        note += f"; omitted {len(omitted)} unit(s) over budget"
    return "\n\n".join(parts), note


def _enrich(
    input_content: str,
    repo_root: str | None,
    base_ref: str,
    max_chars: int,
    diff: str | None = None,
) -> tuple[str, str]:
    root = _git_toplevel(repo_root or os.getcwd())
    if root is None:
        return input_content, "enrichment skipped (not a git repo)"
    if not _tree_is_clean(root):
        return input_content, "enrichment skipped (working tree not clean: uncommitted changes)"
    diff_text = resolve_diff(input_content, root, base_ref) if diff is None else diff
    if not diff_text:
        return input_content, "enrichment skipped (no diff context)"
    cache: dict[str, str | None] = {}
    touched, mismatched = _collect_touched(root, diff_text, cache)
    defined = _defined_names([c for _p, c in touched])
    defs = _grep_defs(root, _candidate_identifiers(diff_text, defined), cache)
    if not touched and not defs:
        note = "enrichment skipped (no readable context)"
        if mismatched:
            note = f"enrichment skipped (diff/HEAD mismatch: {len(mismatched)} file(s))"
        return input_content, note
    content, note = _assemble(input_content, touched, defs, max_chars)
    if mismatched and content != input_content:
        note += f"; {len(mismatched)} file(s) skipped (diff/HEAD mismatch)"
    return content, note
