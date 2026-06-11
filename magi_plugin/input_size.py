#!/usr/bin/env python3
"""Input-size estimation and oversize detection for MAGI.

MAGI reviews each input whole (no map-reduce). This module estimates
the input's token footprint with a stdlib-only heuristic (chars / 4).
"""

from __future__ import annotations

#: Divisor for the chars->tokens heuristic (English avg ~4 chars/token).
_CHARS_PER_TOKEN: int = 4


def estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


def check_input_size(text: str, threshold: int) -> tuple[int, bool]:
    """Return (estimated_tokens, exceeds) where exceeds is True iff estimate > threshold."""
    est = estimate_tokens(text)
    return est, est > threshold
