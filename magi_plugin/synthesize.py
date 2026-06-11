#!/usr/bin/env python3
"""MAGI Synthesis Engine — facade module.

Re-exports from validate, consensus, and reporting for backward compatibility.
"""

from __future__ import annotations

from magi_plugin.validate import (
    VALID_AGENTS,
    VALID_SEVERITIES,
    VALID_VERDICTS,
    ValidationError,
    clean_title,
    load_agent_output,
)
from magi_plugin.consensus import (
    VERDICT_WEIGHT,
    determine_consensus,
)
from magi_plugin.reporting import (
    AGENT_TITLES,
    format_banner,
    format_report,
)

__all__ = [
    "AGENT_TITLES",
    "VALID_AGENTS",
    "VALID_SEVERITIES",
    "VALID_VERDICTS",
    "VERDICT_WEIGHT",
    "ValidationError",
    "clean_title",
    "determine_consensus",
    "format_banner",
    "format_report",
    "load_agent_output",
]
