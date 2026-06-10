#!/usr/bin/env python3
"""Hermes MAGI Orchestrator — async multi-model consensus via OpenAI-compatible endpoint.

Usage:
    python hermes_magi.py --mode code-review --input "file.py" --output report.txt
    python hermes_magi.py --mode design --input "should we use redis?" --output report.txt
    cat payload.txt | python hermes_magi.py --mode analysis --output report.txt

Exit codes:
    0 — Success (report written to stdout or --output)
    1 — Failure (less than 2 agents succeeded, or endpoint unreachable)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import secrets
import socket
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────
AGENTS = ("melchior", "balthasar", "caspar")
AGENT_PROMPTS_DIR = Path(__file__).parent.parent / "agents"
VALID_MODES = ("code-review", "design", "analysis")
DEFAULT_HOST = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.1:latest"
DEFAULT_TIMEOUT = 300
MAX_INPUT_SIZE = 10 * 1024 * 1024  # 10 MB

_ZERO_WIDTH_RE = re.compile(r"[\u200B-\u200F\u2028-\u202F\u2060-\u206F\uFEFF\u00AD]")
_CONTROL_WS_RE = re.compile(r"[\t\n\v\f\r\x85]")
_HEADER_RE = re.compile(r"(?m)^([\t ]*)(MODE|CONTEXT|---BEGIN|---END)(\s|:|$)")


# ── Config helpers ─────────────────────────────────────────────────────
def resolve_config() -> tuple[str, dict[str, str], int]:
    """Return (host, models_dict, timeout) via models.py."""
    from models import get_models, get_host, get_timeout
    host = get_host()
    models = get_models()
    timeout = get_timeout()
    return host, models, timeout


# ── Sanitize ───────────────────────────────────────────────────────────
def build_user_prompt(mode: str, content: str) -> str:
    """Build the canonical MAGI user prompt with defense-in-depth sanitization."""
    step1 = _CONTROL_WS_RE.sub("\n", content)
    step2 = _ZERO_WIDTH_RE.sub("", step1)
    sanitized = _HEADER_RE.sub(r"\1  \2\3", step2)
    nonce = f"{secrets.randbits(128):032x}"
    if nonce in sanitized:
        raise RuntimeError("Nonce collision in user content; retry")
    return (
        f"MODE: {mode}\n"
        f"---BEGIN USER CONTEXT {nonce}---\n"
        f"{sanitized}\n"
        f"---END USER CONTEXT {nonce}---"
    )


# ── HTTP backend ───────────────────────────────────────────────────────
class MagiBackendError(Exception):
    pass


async def run_agent(
    agent_name: str,
    system_prompt_path: Path,
    prompt: str,
    model: str,
    host: str,
    timeout: int,
) -> dict[str, Any]:
    """Post to /chat/completions and return parsed agent JSON."""
    system_prompt = system_prompt_path.read_text(encoding="utf-8")
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "temperature": 0.7,
    }
    # Structured output support (Ollama 0.5+ / vLLM / etc.)
    body["response_format"] = {"type": "json_object"}

    headers = {"Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/chat/completions",
        data=data,
        headers=headers,
        method="POST",
    )

    def _call() -> bytes:
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace") if exc.fp else ""
            raise MagiBackendError(
                f"HTTP {exc.code}: {exc.reason} — {detail}"
            ) from None
        except (socket.timeout, TimeoutError) as exc:
            raise MagiBackendError(f"Request timed out: {exc}") from None
        except urllib.error.URLError as exc:
            raise MagiBackendError(
                f"Cannot reach endpoint at {host}: {exc.reason}"
            ) from None

    raw = await asyncio.to_thread(_call)
    try:
        envelope = json.loads(raw)
        content = envelope["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise MagiBackendError(f"Unexpected response shape: {exc}") from exc

    # Some servers return the JSON object directly; others return a JSON string.
    if isinstance(content, dict):
        return content
    text = str(content).strip()
    # Strip fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    return json.loads(text)


# ── Parse/validate ─────────────────────────────────────────────────────
def parse_and_validate(agent_name: str, raw_data: dict[str, Any]) -> dict[str, Any]:
    """Minimal lightweight validation (full validation happens in validate.py)."""
    required = {"agent", "verdict", "confidence", "summary", "reasoning", "findings", "recommendation"}
    missing = required - set(raw_data.keys())
    if missing:
        raise ValueError(f"Missing keys: {sorted(missing)}")
    raw_data["agent"] = agent_name  # Enforce correct agent field
    if raw_data["verdict"] not in {"approve", "reject", "conditional"}:
        raise ValueError(f"Invalid verdict: {raw_data['verdict']}")
    conf = raw_data["confidence"]
    if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        raise ValueError(f"Invalid confidence: {conf}")
    # Normalize findings
    findings = raw_data.get("findings", [])
    if not isinstance(findings, list):
        raise ValueError("findings must be a list")
    for f in findings:
        if f.get("severity") not in {"critical", "warning", "info"}:
            f["severity"] = "info"
    return raw_data


# ── Main orchestrator ──────────────────────────────────────────────────
async def run_magi(
    mode: str,
    content: str,
    output_file: str | None = None,
) -> int:
    host, models, timeout = resolve_config()

    # Build prompt
    prompt = build_user_prompt(mode, content)

    # Launch agents in parallel
    semaphore = asyncio.Semaphore(3)

    async def _run_one(agent_name: str) -> dict[str, Any] | None:
        async with semaphore:
            prompt_path = AGENT_PROMPTS_DIR / f"{agent_name}.md"
            model = models[agent_name]
            try:
                raw = await run_agent(
                    agent_name, prompt_path, prompt, model, host, timeout
                )
                return parse_and_validate(agent_name, raw)
            except Exception as exc:
                print(f"WARNING: {agent_name} failed: {exc}", file=sys.stderr)
                return None

    results = await asyncio.gather(*[_run_one(a) for a in AGENTS])
    agents = [r for r in results if r is not None]

    if len(agents) < 2:
        print(
            f"ERROR: Only {len(agents)} agent(s) succeeded. Need at least 2 for consensus.",
            file=sys.stderr,
        )
        return 1

    # Full validation via validate.py
    sys.path.insert(0, str(Path(__file__).parent))
    from validate import load_agent_output, ValidationError
    from consensus import determine_consensus
    from reporting import format_report

    # Write temp files for load_agent_output
    tmpdir = tempfile.mkdtemp(prefix="magi_")
    validated = []
    for a in agents:
        tpath = Path(tmpdir) / f"{a['agent']}.json"
        tpath.write_text(json.dumps(a), encoding="utf-8")
        try:
            validated.append(load_agent_output(str(tpath)))
        except ValidationError as exc:
            print(f"WARNING: Validation failed for {a['agent']}: {exc}", file=sys.stderr)

    if len(validated) < 2:
        print("ERROR: Fewer than 2 agents passed full validation.", file=sys.stderr)
        return 1

    consensus = determine_consensus(validated)
    report = format_report(validated, consensus)

    if output_file:
        Path(output_file).write_text(report, encoding="utf-8")
    else:
        print(report)

    return 0


# ── CLI ────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="MAGI Multi-Perspective Analysis")
    parser.add_argument("--mode", choices=VALID_MODES, default="analysis", help="Analysis mode")
    parser.add_argument("--input", "-i", help="Input file or inline text")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Per-agent timeout")
    args = parser.parse_args()

    if args.input:
        ipath = Path(args.input)
        if ipath.exists():
            content = ipath.read_text(encoding="utf-8")
        else:
            content = args.input
    else:
        content = sys.stdin.read()

    if len(content.encode("utf-8")) > MAX_INPUT_SIZE:
        print(f"ERROR: Input exceeds {MAX_INPUT_SIZE} bytes", file=sys.stderr)
        return 1

    return asyncio.run(run_magi(args.mode, content, args.output))


if __name__ == "__main__":
    sys.exit(main())
