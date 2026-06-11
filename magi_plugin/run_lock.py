#!/usr/bin/env python3
"""Process-liveness locking for MAGI run directories.

Each run directory carries a .magi-lock file naming the PID and ISO
start timestamp. cleanup_old_runs consults is_dir_live so a concurrent
MAGI session never prunes a live run.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

LOCK_FILENAME = ".magi-lock"
LOCK_STALE_AFTER_SECONDS = 21_600  # 6 hours
_PROBE_FAILURE_WARNED: bool = False


def _warn_probe_failure(probe: str, exc: Exception) -> None:
    global _PROBE_FAILURE_WARNED
    if not _PROBE_FAILURE_WARNED:
        _PROBE_FAILURE_WARNED = True
        print(
            f"WARNING: run_lock.{probe} unexpected liveness-probe error"
            f" ({type(exc).__name__}: {exc}); treating as live",
            file=sys.stderr,
        )


def is_pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid > 4_294_967_295:
        return True
    try:
        if sys.platform == "win32":
            return _is_pid_alive_windows(pid)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return True
        return True
    except Exception as exc:
        _warn_probe_failure("is_pid_alive", exc)
        return True


def _is_pid_alive_windows(pid: int) -> bool:
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
        kernel32.WaitForSingleObject.restype = ctypes.c_uint
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        SYNCHRONIZE = 0x00100000
        WAIT_TIMEOUT = 0x00000102
        ERROR_ACCESS_DENIED = 5
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if not handle:
            return ctypes.get_last_error() == ERROR_ACCESS_DENIED
        try:
            return bool(kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT)
        finally:
            kernel32.CloseHandle(handle)
    except (OSError, AttributeError, ImportError):
        return True


def _lock_path(run_dir: str) -> str:
    return os.path.join(run_dir, LOCK_FILENAME)


def _dir_is_fresh(run_dir: str) -> bool:
    try:
        return (time.time() - os.path.getmtime(run_dir)) < LOCK_STALE_AFTER_SECONDS
    except OSError:
        return True


def staleness_bound_for_timeout(timeout: int) -> int:
    return max(2 * timeout + 600, LOCK_STALE_AFTER_SECONDS)


def write_lock(run_dir: str, max_age_seconds: int | None = None) -> None:
    bound = LOCK_STALE_AFTER_SECONDS if max_age_seconds is None else int(max_age_seconds)
    payload = f"{os.getpid()}\n{datetime.now(timezone.utc).isoformat()}\n{bound}\n"
    final = _lock_path(run_dir)
    tmp = final + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp, final)
    except OSError as exc:
        print(f"WARNING: could not write run lock in {run_dir}: {exc}", file=sys.stderr)
        try:
            os.remove(tmp)
        except OSError:
            pass


def _parse_lock(run_dir: str) -> tuple[int | None, float | None, int | None]:
    try:
        with open(_lock_path(run_dir), encoding="utf-8", errors="replace") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None, None, None
    pid: int | None = None
    age: float | None = None
    bound: int | None = None
    if lines:
        try:
            pid = int(lines[0].strip())
        except ValueError:
            pid = None
    if len(lines) > 1:
        try:
            started = datetime.fromisoformat(lines[1].strip())
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - started).total_seconds()
        except ValueError:
            age = None
    if len(lines) > 2:
        try:
            bound = int(lines[2].strip())
        except ValueError:
            bound = None
    return pid, age, bound


def read_lock(run_dir: str) -> int | None:
    return _parse_lock(run_dir)[0]


def remove_lock(run_dir: str) -> None:
    try:
        os.remove(_lock_path(run_dir))
    except OSError:
        pass


def is_dir_live(run_dir: str) -> bool:
    try:
        return _is_dir_live_inner(run_dir)
    except Exception as exc:
        _warn_probe_failure("is_dir_live", exc)
        return True


def _is_dir_live_inner(run_dir: str) -> bool:
    pid, age, bound = _parse_lock(run_dir)
    if pid is None:
        lock = _lock_path(run_dir)
        if not os.path.exists(lock):
            return False
        return _dir_is_fresh(run_dir)
    if not is_pid_alive(pid):
        return False
    if age is None or age < 0:
        return _dir_is_fresh(run_dir)
    threshold = LOCK_STALE_AFTER_SECONDS if bound is None else max(bound, LOCK_STALE_AFTER_SECONDS)
    if age >= threshold:
        return False
    return True
