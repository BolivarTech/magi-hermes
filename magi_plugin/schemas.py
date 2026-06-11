"""Tool schemas — what the LLM reads to decide when to use MAGI."""

from __future__ import annotations

MAGI_ANALYZE = {
    "name": "magi_analyze",
    "description": (
        "Run a multi-perspective MAGI analysis. Spawns three parallel LLM agents "
        "(Melchior the Scientist, Balthasar the Pragmatist, Caspar the Critic) "
        "against an OpenAI-compatible local endpoint, then synthesizes a weighted "
        "consensus and canonical ASCII report. "
        "Use this tool ONLY when: the user asks for code review, design analysis, "
        "trade-off evaluation, or explicitly requests 'MAGI', 'three perspectives', "
        "or 'multi-perspective analysis'. "
        "Do NOT use for trivial one-line fixes, obvious questions, or situations "
        "with a single clearly correct answer."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["code-review", "design", "analysis"],
                "description": (
                    "Analysis mode. code-review = review code/diffs; "
                    "design = architecture/approach decisions; "
                    "analysis = general problem/trade-off evaluation."
                ),
            },
            "content": {
                "type": "string",
                "description": (
                    "The full input to analyze: code snippet, diff, design document, "
                    "or question text. Be thorough — include relevant context."
                ),
            },
        },
        "required": ["mode", "content"],
    },
}
