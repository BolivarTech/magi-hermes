#!/usr/bin/env python3
"""Temp-directory housekeeping for the MAGI orchestrator.

Extracted so the orchestrator no longer has to hold the LRU +
symlink-traversal + mtime-tie-break rules in the same file.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import time

from magi_plugin.run_lock import LOCK_STALE_AFTER_SECONDS, is_dir_live

MAGI_DIR_PREFIX = "magi-run-"
MAGI_RUNS_CONTAINER = "magi-runs"
LEGACY_SWEEP_MARKER = ".legacy-swept"


def _scan_magi_dirs(tmp_root: str) -> list[tuple[float, str]]:
    results: list[tuple[float, str]] = []
    try:
        for entry in os.scandir(tmp_root):
            if not (entry.is_dir() and entry.name.startswith(MAGI_DIR_PREFIX)):
                continue
            try:
                mtime = entry.stat().st_mtime
            except OSError:
                continue
            results.append((mtime, entry.path))
    except OSError:
        pass
    return results


def _safe_temp_prefix(tmp_root: str) -> str:
    prefix = os.path.normcase(os.path.realpath(tmp_root))
    if not prefix.endswith(os.sep):
        prefix += os.sep
    return prefix


def _safe_rmtree_under(path: str, safe_prefix: str) -> None:
    resolved = os.path.normcase(os.path.realpath(path))
    if not resolved.startswith(safe_prefix):
        print(
            f"WARNING: Skipping cleanup of {path} (resolves outside temp root)",
            file=sys.stderr,
        )
        return
    try:
        shutil.rmtree(resolved)
    except OSError as exc:
        print(f"WARNING: Failed to remove old run {resolved}: {exc}", file=sys.stderr)


def cleanup_old_runs(keep: int, run_root: str | None = None) -> None:
    if keep < 0:
        return
    if run_root is None:
        run_root = tempfile.gettempdir()
    try:
        magi_dirs = _scan_magi_dirs(run_root)
    except OSError:
        return
    candidates = [(mtime, path) for (mtime, path) in magi_dirs if not is_dir_live(path)]
    if len(candidates) <= keep:
        return
    candidates.sort(key=lambda entry: (-entry[0], entry[1]))
    safe_prefix = _safe_temp_prefix(run_root)
    for _, path in candidates[keep:]:
        _safe_rmtree_under(path, safe_prefix)


def create_output_dir(output_dir: str | None, run_root: str | None = None) -> str:
    if output_dir is not None:
        os.makedirs(output_dir, exist_ok=True)
        return output_dir
    if run_root is None:
        run_root = tempfile.gettempdir()
    return tempfile.mkdtemp(prefix=MAGI_DIR_PREFIX, dir=run_root)


def project_run_root(project_root: str) -> str:
    norm = os.path.normcase(os.path.realpath(project_root))
    key = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
    tmp_root = tempfile.gettempdir()
    root = os.path.join(tmp_root, MAGI_RUNS_CONTAINER, key)
    try:
        os.makedirs(root, exist_ok=True)
    except OSError as exc:
        print(
            f"WARNING: could not create per-project run root {root}: {exc}; "
            f"falling back to {tmp_root}",
            file=sys.stderr,
        )
        return tmp_root
    return root


def sweep_legacy_runs_once() -> None:
    tmp_root = tempfile.gettempdir()
    container = os.path.join(tmp_root, MAGI_RUNS_CONTAINER)
    marker = os.path.join(container, LEGACY_SWEEP_MARKER)
    try:
        os.makedirs(container, exist_ok=True)
        if os.path.exists(marker):
            return
    except OSError:
        return
    now = time.time()
    safe_prefix = _safe_temp_prefix(tmp_root)
    entries = _scan_magi_dirs(tmp_root)
    for mtime, path in entries:
        if now - mtime >= LOCK_STALE_AFTER_SECONDS:
            _safe_rmtree_under(path, safe_prefix)
    try:
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write("swept\n")
    except OSError:
        pass
