#!/usr/bin/env python3
"""MAGI consensus engine.

Applies weight-based scoring to agent verdicts and produces a unified
consensus with confidence calculation, findings deduplication, and
dissent tracking.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from magi_plugin.finding_id import generate_finding_id
from magi_plugin.validate import clean_title

VERDICT_WEIGHT: dict[str, float] = {
    "approve": 1,
    "conditional": 0.5,
    "reject": -1,
}

_SEVERITY_ORDER: dict[str, int] = {"critical": 0, "warning": 1, "info": 2}
_UNKNOWN_SEVERITY_RANK = 99
_EPSILON: float = 1e-9


def _severity_rank(severity: str) -> int:
    return _SEVERITY_ORDER.get(severity, _UNKNOWN_SEVERITY_RANK)


def _dedup_key(title: str) -> str:
    return unicodedata.normalize("NFKC", clean_title(title)).casefold()


def _consensus_short_verdict(score: float, has_conditions: bool) -> str:
    if abs(score - 1.0) < _EPSILON:
        return "approve"
    if abs(score - (-1.0)) < _EPSILON:
        return "reject"
    is_positive = score > _EPSILON
    if is_positive and has_conditions:
        return "conditional"
    if is_positive:
        return "approve"
    return "reject"


def _format_consensus_label(
    score: float,
    consensus_short: str,
    split: tuple[int, int],
) -> str:
    if abs(score - 1.0) < _EPSILON:
        return "STRONG GO"
    if abs(score - (-1.0)) < _EPSILON:
        return "STRONG NO-GO"
    is_tie = abs(score) < _EPSILON
    if is_tie:
        return "HOLD -- TIE"
    split_label = f"({split[0]}-{split[1]})"
    if consensus_short == "conditional":
        return f"GO WITH CAVEATS {split_label}"
    if consensus_short == "approve":
        return f"GO {split_label}"
    return f"HOLD {split_label}"


def _finding_key(f: dict[str, Any]) -> tuple[str, str]:
    file = f.get("file")
    line = f.get("line")
    if (
        isinstance(file, str)
        and file
        and isinstance(line, int)
        and not isinstance(line, bool)
        and line > 0
    ):
        return ("id", generate_finding_id(file, line, f.get("category") or "other"))
    return ("title", _dedup_key(f["title"]))


def _deduplicate_findings(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for a in agents:
        for f in a.get("findings", []):
            key = _finding_key(f)
            existing = findings_by_key.get(key)
            if existing is None:
                merged = {**f, "sources": [a["agent"]]}
                if key[0] == "id":
                    merged["id"] = key[1]
                findings_by_key[key] = merged
                continue
            existing["sources"].append(a["agent"])
            if _severity_rank(f["severity"]) < _severity_rank(existing["severity"]):
                existing["severity"] = f["severity"]
                existing["detail"] = f["detail"]

    return sorted(findings_by_key.values(), key=lambda f: _severity_rank(f["severity"]))


def _compute_confidence(
    majority_agents: list[dict[str, Any]],
    num_agents: int,
    score: float,
) -> float:
    majority_conf: float = sum(a["confidence"] for a in majority_agents)
    base_confidence = majority_conf / num_agents
    weight_factor = (abs(score) + 1) / 2
    return float(round(max(0.0, min(1.0, base_confidence * weight_factor)), 2))


def determine_consensus(agents: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply weight-based scoring to determine consensus.

    Args:
        agents: List of validated agent output dictionaries (minimum 2).

    Returns:
        Consensus dictionary.
    """
    num_agents = len(agents)
    if num_agents < 2:
        raise ValueError(f"determine_consensus requires at least 2 agents, got {num_agents}")

    agent_names = [a["agent"] for a in agents]
    if len(agent_names) != len(set(agent_names)):
        raise ValueError(f"Duplicate agent names detected: {agent_names}")

    verdicts = [a["verdict"] for a in agents]
    score = sum(VERDICT_WEIGHT[v] for v in verdicts) / num_agents
    has_conditions = "conditional" in verdicts

    consensus_short = _consensus_short_verdict(score, has_conditions)
    consensus_side = "reject" if consensus_short == "reject" else "approve"

    majority_agents = []
    dissent_agents = []
    for a in agents:
        eff = "approve" if a["verdict"] == "conditional" else a["verdict"]
        if eff == consensus_side:
            majority_agents.append(a)
        else:
            dissent_agents.append(a)

    split = (len(majority_agents), len(dissent_agents))
    consensus = _format_consensus_label(score, consensus_short, split)

    all_findings = _deduplicate_findings(agents)

    conditions = [
        {"agent": a["agent"], "condition": a["summary"]}
        for a in agents
        if a["verdict"] == "conditional"
    ]

    confidence = _compute_confidence(majority_agents, num_agents, score)

    return {
        "consensus": consensus,
        "consensus_verdict": consensus_short,
        "confidence": confidence,
        "votes": {a["agent"]: a["verdict"] for a in agents},
        "majority_summary": " | ".join(
            f"{a['agent'].capitalize()}: {a['summary']}" for a in majority_agents
        ),
        "dissent": [
            {"agent": a["agent"], "summary": a["summary"], "reasoning": a["reasoning"]}
            for a in dissent_agents
        ],
        "findings": all_findings,
        "conditions": conditions,
        "recommendations": {a["agent"]: a["recommendation"] for a in agents},
    }
