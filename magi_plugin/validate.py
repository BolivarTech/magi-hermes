#!/usr/bin/env python3
"""MAGI agent output validation.

Loads and validates JSON output files produced by the three MAGI agents
(Melchior, Balthasar, Caspar) against the expected schema.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from magi_plugin.finding_id import normalize_category


class ValidationError(Exception):
    """Raised when agent output fails validation.

    Attributes:
        message: Human-readable description of the validation failure.
        filepath: Path to the file that failed validation, if applicable.
    """

    def __init__(self, message: str, filepath: str = "") -> None:
        self.filepath = filepath
        super().__init__(f"{filepath}: {message}" if filepath else message)


VALID_AGENTS: set[str] = {"melchior", "balthasar", "caspar"}
VALID_VERDICTS: set[str] = {"approve", "reject", "conditional"}
VALID_SEVERITIES: set[str] = {"critical", "warning", "info"}

_REQUIRED_KEYS = frozenset(
    {
        "agent",
        "verdict",
        "confidence",
        "summary",
        "reasoning",
        "findings",
        "recommendation",
    }
)

_REQUIRED_FINDING_KEYS = frozenset({"severity", "title", "detail"})
MAX_INPUT_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB
_MAX_FINDINGS_PER_AGENT: int = 100
_MAX_FIELD_LENGTH: int = 50_000
_MAX_TITLE_LENGTH: int = 500
_MAX_DETAIL_LENGTH: int = 10_000
_ZERO_WIDTH_RE = re.compile(r"[\u200B-\u200F\u2028-\u202F\u2060-\u206F\uFEFF\u00AD]")
_CONTROL_WHITESPACE_RE = re.compile(r"[\t\n\v\f\r\x85]")


def clean_title(raw: str) -> str:
    """Return *raw* with invisible characters and edge whitespace removed."""
    stripped_invisibles = _ZERO_WIDTH_RE.sub("", raw)
    without_breaks = _CONTROL_WHITESPACE_RE.sub(" ", stripped_invisibles)
    return without_breaks.strip()


def load_agent_output(filepath: str) -> dict[str, Any]:
    """Load and validate a single agent's JSON output.

    Args:
        filepath: Path to the agent JSON file.

    Returns:
        Validated agent output dictionary.

    Raises:
        ValidationError: If the file cannot be read, is not valid JSON,
            or its content fails any structural / value check.
    """
    try:
        file_size = os.path.getsize(filepath)
        if file_size > MAX_INPUT_FILE_SIZE:
            raise ValidationError(
                f"File exceeds maximum size of {MAX_INPUT_FILE_SIZE} bytes "
                f"(got {file_size} bytes).",
                filepath,
            )
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Invalid JSON: {exc}", filepath) from exc
    except OSError as exc:
        raise ValidationError(f"Cannot read file: {exc}", filepath) from exc

    if not isinstance(data, dict):
        raise ValidationError(
            f"Top-level JSON must be an object, got {type(data).__name__}.",
            filepath,
        )

    missing = _REQUIRED_KEYS - set(data.keys())
    if missing:
        raise ValidationError(f"Agent output missing keys: {sorted(missing)}", filepath)

    agent = data["agent"]
    if not isinstance(agent, str) or agent not in VALID_AGENTS:
        raise ValidationError(
            f"Unknown agent '{agent}'. Must be one of {sorted(VALID_AGENTS)}.",
            filepath,
        )

    verdict = data["verdict"]
    if not isinstance(verdict, str) or verdict not in VALID_VERDICTS:
        raise ValidationError(
            f"Invalid verdict '{verdict}'. Must be one of {sorted(VALID_VERDICTS)}.",
            filepath,
        )

    confidence = data["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValidationError(
            f"Confidence must be a number, got {type(confidence).__name__}.",
            filepath,
        )
    if not (0.0 <= confidence <= 1.0):
        raise ValidationError(
            f"Confidence must be between 0.0 and 1.0, got {confidence}.",
            filepath,
        )

    for field in ("summary", "reasoning", "recommendation"):
        value = data[field]
        if not isinstance(value, str):
            raise ValidationError(
                f"Field '{field}' must be a string, got {type(value).__name__}.",
                filepath,
            )
        if len(value) > _MAX_FIELD_LENGTH:
            raise ValidationError(
                f"Field '{field}' exceeds maximum length of {_MAX_FIELD_LENGTH} characters.",
                filepath,
            )

    findings = data["findings"]
    if not isinstance(findings, list):
        raise ValidationError(
            f"Findings must be a list, got {type(findings).__name__}.",
            filepath,
        )
    if len(findings) > _MAX_FINDINGS_PER_AGENT:
        raise ValidationError(
            f"Findings list has {len(findings)} items, "
            f"exceeding maximum of {_MAX_FINDINGS_PER_AGENT}.",
            filepath,
        )
    for idx, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise ValidationError(
                f"Finding at index {idx} must be a dict, got {type(finding).__name__}.",
                filepath,
            )
        f_missing = _REQUIRED_FINDING_KEYS - set(finding.keys())
        if f_missing:
            raise ValidationError(
                f"Finding at index {idx} missing keys: {sorted(f_missing)}.",
                filepath,
            )
        for field in ("severity", "title", "detail"):
            if not isinstance(finding[field], str):
                raise ValidationError(
                    f"Finding at index {idx} field '{field}' must be a string, "
                    f"got {type(finding[field]).__name__}.",
                    filepath,
                )
        if finding["severity"] not in VALID_SEVERITIES:
            raise ValidationError(
                f"Finding at index {idx} has invalid severity "
                f"'{finding['severity']}'. "
                f"Must be one of {sorted(VALID_SEVERITIES)}.",
                filepath,
            )
        cleaned = clean_title(finding["title"])
        if not cleaned:
            raise ValidationError(
                f"Finding at index {idx} has empty or whitespace-only title.",
                filepath,
            )
        if len(cleaned) > _MAX_TITLE_LENGTH:
            raise ValidationError(
                f"Finding at index {idx} title exceeds maximum length "
                f"of {_MAX_TITLE_LENGTH} characters.",
                filepath,
            )
        finding["title"] = cleaned
        if len(finding["detail"]) > _MAX_DETAIL_LENGTH:
            raise ValidationError(
                f"Finding at index {idx} detail exceeds maximum length "
                f"of {_MAX_DETAIL_LENGTH} characters.",
                filepath,
            )
        file_val = finding.get("file")
        if file_val is not None and not isinstance(file_val, str):
            file_val = None
        line_val = finding.get("line")
        if line_val is not None:
            if isinstance(line_val, bool):
                line_val = None
            elif isinstance(line_val, int):
                pass
            elif isinstance(line_val, float) and line_val.is_integer():
                line_val = int(line_val)
            else:
                line_val = None
        if isinstance(line_val, int) and line_val <= 0:
            line_val = None
        finding["file"] = file_val
        finding["line"] = line_val
        finding["category"] = normalize_category(finding.get("category"))

    return dict(data)
