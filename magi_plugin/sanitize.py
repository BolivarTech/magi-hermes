#!/usr/bin/env python3
"""Defense-in-depth user-prompt construction for MAGI orchestrator.

Sanitizes consumer-supplied content before embedding it in the LLM
user prompt. Four ordered layers: newline normalization, invisible
stripping, header neutralization, nonce-wrapped delimiters with a
fail-closed collision check.
"""

from __future__ import annotations

import re
import secrets
from typing import Protocol

from magi_plugin.validate import ValidationError


class _RngLike(Protocol):
    def getrandbits(self, k: int, /) -> int: ...


class InvalidInputError(Exception):
    """Raised when content cannot be safely embedded in a user prompt.

    Structural guard: this class is intentionally a sibling of
    ValidationError, NOT a subclass, so the orchestrator retry handler
    does NOT silently consume it.
    """


# --- Layer 1: newline normalization --------------------------------------
_NEWLINE_RE = re.compile(r"\r\n|\r|[\u000B\u000C\u0085\u2028\u2029]")


def normalize_newlines(s: str) -> str:
    """Convert every Unicode line separator in s to \\n."""
    return _NEWLINE_RE.sub("\n", s)


# --- Layer 2: invisible-character stripping --------------------------------
_INVISIBLE_RE = re.compile(r"[\u200B-\u200F\u2028-\u202F\u2060-\u206F\uFEFF\u00AD]")


def strip_invisibles(s: str) -> str:
    """Remove zero-width, bidi, soft-hyphen, and Unicode separator codepoints."""
    return _INVISIBLE_RE.sub("", s)


# --- Layer 3: header neutralization ----------------------------------------
_HEADER_RE = re.compile(r"(?m)^([\t ]*)(MODE|CONTEXT|---BEGIN|---END)(\s|:|$)")


def neutralize_headers(s: str) -> str:
    """Insert a two-space prefix before lines starting with reserved keywords."""
    return _HEADER_RE.sub(r"\1  \2\3", s)


# --- Layer 4: nonce + delimiters + fail-closed -----------------------------


def build_user_prompt(
    mode: str,
    content: str,
    rng: _RngLike | None = None,
) -> str:
    """Build the canonical MAGI user prompt with defense-in-depth sanitization.

    Args:
        mode: One of "code-review", "design", "analysis".
        content: Raw consumer-supplied content. May be adversarial.
        rng: Optional injectable RNG. None uses secrets.randbits.

    Raises:
        InvalidInputError: If the generated nonce appears as a literal
            substring of the sanitized content.

    Returns:
        The user prompt string ready to send to the LLM.
    """
    step1 = normalize_newlines(content)
    step2 = strip_invisibles(step1)
    sanitized = neutralize_headers(step2)

    if rng is None:
        nonce_val = secrets.randbits(128)
    else:
        nonce_val = rng.getrandbits(128)
    nonce = f"{nonce_val:032x}"

    if nonce in sanitized:
        raise InvalidInputError("content contains generated nonce; refuse and retry")

    return (
        f"MODE: {mode}\n"
        f"---BEGIN USER CONTEXT {nonce}---\n"
        f"{sanitized}\n"
        f"---END USER CONTEXT {nonce}---"
    )
