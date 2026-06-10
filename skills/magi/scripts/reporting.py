#!/usr/bin/env python3
"""MAGI report formatting.

Generates the ASCII verdict banner and the full human-readable
markdown report from agent outputs and consensus data.
"""

from __future__ import annotations

from typing import Any

AGENT_TITLES: dict[str, tuple[str, str]] = {
    "melchior": ("Melchior", "Scientist"),
    "balthasar": ("Balthasar", "Pragmatist"),
    "caspar": ("Caspar", "Critic"),
}

_BANNER_WIDTH: int = 52
_BANNER_INNER: int = _BANNER_WIDTH - 2

_FINDING_MARKER_WIDTH: int = 5
_FINDING_SEVERITY_WIDTH: int = 14

_SEVERITY_MARKERS: dict[str, str] = {
    "critical": "[!!!]",
    "warning": "[!!]",
    "info": "[i]",
}


def _agent_title(agent_name: str) -> tuple[str, str]:
    return AGENT_TITLES.get(agent_name, (agent_name.capitalize(), "Agent"))


def _agent_label(agent_name: str) -> str:
    name, title = _agent_title(agent_name)
    return f"{name} ({title}):"


_ELLIPSIS: str = "..."


def _fit_content(content: str, width: int, *, preserve_suffix: str = "") -> str:
    if len(content) <= width:
        return content
    if not preserve_suffix or len(preserve_suffix) + len(_ELLIPSIS) >= width:
        cutoff = max(1, width - len(_ELLIPSIS))
        return content[:cutoff] + _ELLIPSIS
    prefix_budget = width - len(_ELLIPSIS) - len(preserve_suffix)
    prefix_source = content[: -len(preserve_suffix)]
    return prefix_source[:prefix_budget] + _ELLIPSIS + preserve_suffix


def format_banner(agents: list[dict[str, Any]], consensus: dict[str, Any]) -> str:
    labels = [_agent_label(a["agent"]) for a in agents]
    max_label_len = max((len(label) for label in labels), default=0)

    lines: list[str] = []
    border = "+" + "=" * _BANNER_INNER + "+"
    lines.append(border)
    lines.append("|" + "MAGI SYSTEM -- VERDICT".center(_BANNER_INNER) + "|")
    lines.append(border)

    for agent, label in zip(agents, labels):
        verdict_display = agent["verdict"].upper()
        conf_pct = f"{agent['confidence']:.0%}"
        verdict_suffix = f" {verdict_display} ({conf_pct})"
        content = f"  {label:<{max_label_len}}{verdict_suffix}"
        fitted = _fit_content(content, _BANNER_INNER, preserve_suffix=verdict_suffix)
        lines.append("|" + fitted.ljust(_BANNER_INNER) + "|")

    lines.append(border)
    cons_content = f"  CONSENSUS: {consensus['consensus']}"
    fitted_cons = _fit_content(cons_content, _BANNER_INNER)
    lines.append("|" + fitted_cons.ljust(_BANNER_INNER) + "|")
    lines.append(border)

    return "\n".join(lines)


def _format_finding_line(finding: dict[str, Any]) -> str:
    severity = finding["severity"]
    marker = _SEVERITY_MARKERS.get(severity, "[?]")
    severity_label = f"**[{severity.upper()}]**"
    sources = ", ".join(finding.get("sources", ["unknown"]))
    return (
        f"{marker:<{_FINDING_MARKER_WIDTH}} "
        f"{severity_label:<{_FINDING_SEVERITY_WIDTH}} "
        f"{finding['title']} _(from {sources})_"
    )


def format_report(agents: list[dict[str, Any]], consensus: dict[str, Any]) -> str:
    sections: list[str] = [format_banner(agents, consensus), ""]

    if consensus["findings"]:
        sections.append("## Key Findings")
        for finding in consensus["findings"]:
            sections.append(_format_finding_line(finding))
        sections.append("")

    if consensus["dissent"]:
        sections.append("## Dissenting Opinion")
        for dissent in consensus["dissent"]:
            name, title = _agent_title(dissent["agent"])
            sections.append(f"**{name} ({title})**: {dissent['summary']}")
        sections.append("")

    if consensus["conditions"]:
        sections.append("## Conditions for Approval")
        for cond in consensus["conditions"]:
            name, _ = _agent_title(cond["agent"])
            sections.append(f"- **{name}**: {cond['condition']}")
        sections.append("")

    sections.append("## Recommended Actions")
    for agent_name, rec in consensus["recommendations"].items():
        name, title = _agent_title(agent_name)
        sections.append(f"- **{name}** ({title}): {rec}")

    return "\n".join(sections)
