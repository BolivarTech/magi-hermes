#!/usr/bin/env python3
"""Single JSON-Schema representation of the MAGI agent output contract.

Used by the Ollama backend for ``response_format`` (structured output).
MUST stay in lockstep with ``validate.py``.
"""

from __future__ import annotations

from typing import Any

AGENT_OUTPUT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "agent",
        "verdict",
        "confidence",
        "summary",
        "reasoning",
        "findings",
        "recommendation",
    ],
    "properties": {
        "agent": {"type": "string", "enum": ["melchior", "balthasar", "caspar"]},
        "verdict": {"type": "string", "enum": ["approve", "reject", "conditional"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "summary": {"type": "string"},
        "reasoning": {"type": "string"},
        "recommendation": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["severity", "title", "detail"],
                "properties": {
                    "severity": {"type": "string", "enum": ["critical", "warning", "info"]},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "file": {"type": ["string", "null"]},
                    "line": {"type": ["integer", "null"]},
                    "category": {"type": ["string", "null"]},
                },
            },
        },
    },
}
