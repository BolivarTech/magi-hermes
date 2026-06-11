#!/usr/bin/env python3
"""Stable, structured identity for MAGI findings.

Pure stdlib. SHA-256 based finding identity for cross-agent dedup.
"""

from __future__ import annotations

import hashlib

CATEGORY_SLUGS: tuple[str, ...] = (
    "buffer-overflow", "null-deref", "resource-leak", "unvalidated-input",
    "race-condition", "error-handling", "hardcoded-secret", "integer-overflow",
    "injection", "logic-error", "type-mismatch", "deprecated-api",
    "performance", "style", "documentation", "other",
)
_CATEGORY_SET = frozenset(CATEGORY_SLUGS)
DEFAULT_CATEGORY = "other"
_FINDING_ID_HEX_LEN = 16


def normalize_path(path: str) -> str:
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    while "//" in p:
        p = p.replace("//", "/")
    return p


def normalize_category(value: str | None) -> str:
    if not isinstance(value, str):
        return DEFAULT_CATEGORY
    slug = value.strip().lower().replace("_", "-").replace(" ", "-")
    return slug if slug in _CATEGORY_SET else DEFAULT_CATEGORY


def generate_finding_id(file: str, line: int, category: str) -> str:
    payload = f"{normalize_path(file)}:{int(line)}:{normalize_category(category)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_FINDING_ID_HEX_LEN]
