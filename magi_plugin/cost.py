#!/usr/bin/env python3
"""Per-run cost aggregation for MAGI.

Sums the authoritative total_cost_usd that the backend reports in each
agent's raw envelope ({agent}.raw.json). Total: any error degrades to 0.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

_RAW_FILE_SUFFIX = ".raw.json"
_COST_FIELD = "total_cost_usd"


def _agent_cost(output_dir: str, agent: str) -> float:
    path = os.path.join(output_dir, f"{agent}{_RAW_FILE_SUFFIX}")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return 0.0
        value = data.get(_COST_FIELD)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return 0.0
        return float(value) if math.isfinite(value) else 0.0
    except (OSError, json.JSONDecodeError, ValueError):
        return 0.0


def aggregate_cost(output_dir: str, agents: list[str]) -> dict[str, Any]:
    per_agent = {agent: _agent_cost(output_dir, agent) for agent in agents}
    return {"per_agent": per_agent, "total_usd": round(sum(per_agent.values()), 6)}
