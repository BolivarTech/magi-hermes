"""MAGI Plugin package — entry point for Hermes Agent.

This module is imported both via pip entry-point (``magi = "magi_plugin"``)
and via local directory plugin (``~/.hermes/plugins/magi/__init__.py``
re-exports from here).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

# ── Self-register as magi_plugin so absolute imports work ───────────────
# When loaded as a directory plugin under hermes_plugins.magi, all sibling
# modules must also be reachable via magi_plugin.* because the codebase was
# originally written for a pip-installable package.
_pkg_name = __name__
if "magi_plugin" not in sys.modules:
    sys.modules["magi_plugin"] = sys.modules[_pkg_name]

# Pre-register already-imported submodules under the magi_plugin.* alias.
# This is executed once after all imports below have resolved.
def _register_aliases() -> None:
    for _mod_name, _mod in list(sys.modules.items()):
        if _mod_name.startswith(_pkg_name + "."):
            _short = _mod_name[len(_pkg_name) + 1 :]
            _alias = f"magi_plugin.{_short}"
            if _alias not in sys.modules:
                sys.modules[_alias] = _mod

from magi_plugin.orchestrator import run_magi
from magi_plugin import schemas

_register_aliases()

logger = logging.getLogger(__name__)

# ── Trigger detection regexes ──────────────────────────────────────────
_TRIGGER_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bMAGI\b", re.IGNORECASE),
    re.compile(r"\bthree perspectives\b", re.IGNORECASE),
    re.compile(r"\bmulti[- ]?perspective analysis\b", re.IGNORECASE),
    re.compile(r"\bMAGI review\b", re.IGNORECASE),
]

_MIN_TRIGGER_LEN: int = 60


def _should_suggest_magi(user_message: str) -> bool:
    """Return True if the user message warrants an auto-suggestion."""
    if len(user_message) < _MIN_TRIGGER_LEN:
        return False
    return any(p.search(user_message) for p in _TRIGGER_PATTERNS)


def _on_pre_llm_call(
    session_id: str,
    user_message: str,
    conversation_history: list,
    is_first_turn: bool,
    model: str,
    platform: str,
    **kwargs: Any,
) -> dict[str, str] | None:
    """Hook: detect natural triggers and inject a gentle suggestion."""
    if not user_message or not _should_suggest_magi(user_message):
        return None

    suggestion = (
        "The user may be asking for a multi-perspective analysis. "
        "If the question involves genuine uncertainty, significant consequences, "
        "or hidden trade-offs, use the magi_analyze tool (mode: code-review, "
        "design, or analysis). If the answer is trivial or has a single clearly "
        "correct answer, respond directly without invoking MAGI."
    )
    return {"context": suggestion}


# ── Tool handler ────────────────────────────────────────────────────────
def _make_magi_handler(ctx: Any):
    """Build the magi_analyze tool handler bound to *ctx*."""

    def handler(args: dict, **kwargs) -> str:
        mode: str = args.get("mode", "analysis")
        content: str = args.get("content", "")
        if not content.strip():
            return json.dumps({"error": "No content provided for analysis."})

        print(f"[MAGI] Starting analysis... mode={mode}, launching 3 agents", flush=True)
        try:
            report = asyncio.run(run_magi(mode=mode, content=content))
            return json.dumps({
                "report": report.get("report", ""),
                "mode": mode,
                "consensus": report.get("consensus", {}),
                "degraded": report.get("degraded", False),
            })
        except Exception as exc:
            logger.warning("magi_analyze failed: %s", exc)
            return json.dumps({"error": str(exc)})

    return handler


# ── Slash-command handler ──────────────────────────────────────────────
def _make_slash_handler(ctx: Any):
    """Build the /magi handler bound to *ctx*."""

    _MODE_RE = re.compile(
        r"^(code-review|design|analysis)\s*[:\-]\s*(.+)$", re.IGNORECASE | re.DOTALL
    )
    _INIT_RE = re.compile(
        r"^--init-magi\s*(\S.*)?$", re.IGNORECASE
    )

    def handler(raw_args: str) -> str:
        raw = raw_args.strip()
        if not raw:
            return (
                "Usage: /magi <mode>: <content>\n"
                "       /magi --init-magi\n"
                "  Modes: code-review | design | analysis\n"
                "  Examples:\n"
                '    /magi code-review: Review this PR diff\n'
                '    /magi design: Should we use Redis or Postgres?\n'
                '    /magi analysis: Three perspectives on this bug\n'
                '    /magi --init-magi        # Scaffold .hermes/magi-ollama.toml'
            )

        # ── init branch ──────────────────────────────────────────────────
        init_m = _INIT_RE.match(raw)
        if init_m:
            from magi_plugin.ollama_init import write_template
            try:
                path = write_template()
                return f"MAGI Ollama config scaffolded:\n  {path}\n\nEdit the models if needed, then restart Hermes."
            except FileExistsError:
                return (
                    "MAGI Ollama config already exists.\n"
                    "  Run from a different repo or delete .hermes/magi-ollama.toml first."
                )
            except Exception as exc:
                logger.warning("/magi --init-magi failed: %s", exc)
                return f"--init-magi failed: {exc}"

        # ── analysis branch ──────────────────────────────────────────────
        m = _MODE_RE.match(raw)
        if m:
            mode = m.group(1).lower()
            content = m.group(2)
        else:
            mode = "analysis"
            content = raw

        try:
            print("[MAGI] Starting analysis...", flush=True)
            report = asyncio.run(run_magi(mode=mode, content=content))
            print("[MAGI] Analysis complete.", flush=True)
            return report.get("report", "MAGI returned empty report.")
        except Exception as exc:
            logger.warning("/magi failed: %s", exc)
            return f"MAGI analysis failed: {exc}"

    return handler


# ── Registration ───────────────────────────────────────────────────────
def register(ctx: Any) -> None:
    """Plugin entry point — wire tools, hooks, and commands."""

    # 1. Register the magi_analyze tool
    ctx.register_tool(
        name="magi_analyze",
        toolset="magi",
        schema=schemas.MAGI_ANALYZE,
        handler=_make_magi_handler(ctx),
        check_fn=lambda: True,
    )

    # 2. Register /magi slash command
    ctx.register_command(
        name="magi",
        handler=_make_slash_handler(ctx),
        description="Run multi-perspective MAGI analysis (Melchior, Balthasar, Caspar).",
        args_hint="<mode>: <content>",
    )

    # 3. Register trigger-detection hook
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)

    logger.debug("magi plugin: registered magi_analyze, /magi, pre_llm_call hook")
