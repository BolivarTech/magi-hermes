"""MAGI Orchestrator — async multi-model consensus via OpenAI-compatible endpoint.

Deterministic Python pipeline: launch 3 agents in parallel (with single-
shot retry on schema/JSON failures), validate, deduplicate, consensus,
ASCII report, and JSON artifact. Returns the full report dict.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from magi_plugin.models import (
    AGENTS,
    MAX_INPUT_SIZE,
    get_timeout,
    resolve_ollama_config,
)
from magi_plugin.sanitize import build_user_prompt, InvalidInputError
from magi_plugin.validate import ValidationError
from magi_plugin.consensus import determine_consensus
from magi_plugin.reporting import format_report
from magi_plugin.finding_validation import parse_diff_ranges, valid_files, validate_findings
from magi_plugin.review_context import enrich_code_review_context, resolve_diff
from magi_plugin.input_size import check_input_size
from magi_plugin.temp_dirs import (
    cleanup_old_runs,
    create_output_dir,
    project_run_root,
    sweep_legacy_runs_once,
)
from magi_plugin.run_lock import (
    write_lock,
    remove_lock,
    staleness_bound_for_timeout,
)
from magi_plugin.cost import aggregate_cost
from magi_plugin.agent_schema import AGENT_OUTPUT_JSON_SCHEMA

AGENT_PROMPTS_DIR = Path(__file__).parent / "agents"


class MagiBackendError(Exception):
    """Raised when an HTTP call to the OpenAI-compatible endpoint fails."""
    pass


class MagiInputError(Exception):
    """Raised when user input is malformed or too large."""
    pass


def _enable_utf8_console_io() -> None:
    """On Windows, reconfigure stdout/stderr to UTF-8 with backslashreplace.
    No-op on POSIX."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
            except Exception:
                pass


class _ResponseFormatRejected(Exception):
    """Internal signal: server returned 400 rejecting response_format -> R15 downgrade."""


def _http_post(
    host: str,
    body: dict[str, Any],
    timeout: int,
    api_key: str | None = None,
) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
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
            low = detail.lower()
            if exc.code == 400 and ("response_format" in low or "json_schema" in low):
                raise _ResponseFormatRejected() from None
            raise MagiBackendError(
                f"HTTP {exc.code}: {exc.reason} — {detail}"
            ) from None
        except (TimeoutError, OSError) as exc:
            raise MagiBackendError(f"Request timed out: {exc}") from None
        except urllib.error.URLError as exc:
            raise MagiBackendError(
                f"Cannot reach endpoint at {host}: {exc.reason}"
            ) from None

    raw = _call()
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MagiBackendError(f"Non-JSON response: {exc}") from exc
    if "choices" not in envelope or not envelope["choices"]:
        raise MagiBackendError(f"Unexpected response shape: {list(envelope.keys())}")
    return envelope["choices"][0]["message"]


def _response_format(structured: str) -> dict[str, Any] | None:
    if structured == "off":
        return None
    if structured == "object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "magi_agent_output",
            "strict": False,
            "schema": AGENT_OUTPUT_JSON_SCHEMA,
        },
    }


async def _run_agent_core(
    agent_name: str,
    system_prompt_path: Path,
    prompt: str,
    model: str,
    host: str,
    timeout: int,
    api_key: str | None,
    structured: str,
    output_dir: str | None,
) -> dict[str, Any]:
    """Core agent run: build request, POST, parse JSON, return raw dict.

    Implements R15 single-shot downgrade: if the server rejects
    response_format with 400, retry once WITHOUT response_format.
    """
    system_prompt = system_prompt_path.read_text(encoding="utf-8")
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    def _try_post(with_format: bool = True) -> dict[str, Any]:
        b = dict(body)
        if with_format:
            rf = _response_format(structured)
            if rf is not None:
                b["response_format"] = rf
        return _http_post(host, b, timeout, api_key)

    try:
        message = await asyncio.to_thread(_try_post, True)
    except _ResponseFormatRejected:
        message = await asyncio.to_thread(_try_post, False)

    content = message.get("content", "")

    if isinstance(content, dict):
        raw_data = content
    else:
        text = str(content).strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\n?```\s*$", "", text)
            text = text.strip()
        try:
            raw_data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise json.JSONDecodeError(f"Agent {agent_name} returned invalid JSON", text, exc.pos) from exc

    # Minimal validation before full pipeline
    required = {"agent", "verdict", "confidence", "summary", "reasoning", "findings", "recommendation"}
    missing = required - set(raw_data.keys())
    if missing:
        raise ValidationError(f"Agent {agent_name} missing keys: {sorted(missing)}")
    raw_data["agent"] = agent_name
    if raw_data["verdict"] not in {"approve", "reject", "conditional"}:
        raise ValidationError(f"Agent {agent_name} invalid verdict: {raw_data['verdict']}")
    conf = raw_data["confidence"]
    if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        raise ValidationError(f"Agent {agent_name} invalid confidence: {conf}")

    # Save raw envelope for cost aggregation
    if output_dir is not None:
        try:
            raw_path = os.path.join(output_dir, f"{agent_name}.raw.json")
            with open(raw_path, "w", encoding="utf-8") as fh:
                json.dump({"content": content, "total_cost_usd": 0.0}, fh)
        except OSError:
            pass

    return raw_data


async def _run_agent(
    agent_name: str,
    system_prompt_path: Path,
    prompt: str,
    model: str,
    host: str,
    timeout: int,
    api_key: str | None,
    structured: str,
    output_dir: str | None,
) -> dict[str, Any]:
    """Launch one agent with single-shot retry on ValidationError/JSONDecodeError."""
    try:
        return await _run_agent_core(
            agent_name, system_prompt_path, prompt, model, host, timeout,
            api_key, structured, output_dir,
        )
    except (ValidationError, json.JSONDecodeError) as exc:
        # Retry once with corrective feedback
        retry_prompt = (
            f"{prompt}\n\n"
            f"---RETRY-FEEDBACK---\n"
            f"Your previous output was rejected: {exc}\n"
            f"Please correct the issue and produce a valid JSON object conforming to the schema."
        )
        return await _run_agent_core(
            agent_name, system_prompt_path, retry_prompt, model, host, timeout,
            api_key, structured, output_dir,
        )


def _a5_mode_strip(agents: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
    """A5: in design/analysis modes, null file/line so findings dedup by title."""
    if mode == "code-review":
        return agents
    for a in agents:
        for f in a.get("findings", []):
            f["file"] = None
            f["line"] = None
    return agents


def _apply_finding_guard(
    agents: list[dict[str, Any]],
    mode: str,
    files: set[str],
    ranges: dict[str, set[int]],
    summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Apply diff guard only in code-review mode.

    Populates *summary* with the guard's observable effect when provided.
    """
    if mode != "code-review" or not files:
        if summary is not None:
            summary["active"] = False
        return agents

    if summary is not None:
        summary.update(
            {
                "active": True,
                "files_in_diff": len(files),
                "total_dropped": 0,
                "total_annotated": 0,
                "per_agent": {},
            }
        )

    out: list[dict[str, Any]] = []
    for a in agents:
        try:
            original = a.get("findings", [])
            kept, dropped, annotated = validate_findings(original, files, ranges)
            a = {**a, "findings": kept}
            if dropped or annotated:
                # Compute dropped titles by order-preserving walk
                kept_idx = 0
                dropped_titles: list[str] = []
                for orig in original:
                    if (
                        kept_idx < len(kept)
                        and kept[kept_idx].get("title") == orig.get("title")
                        and kept[kept_idx].get("file") == orig.get("file")
                        and kept[kept_idx].get("line") == orig.get("line")
                    ):
                        kept_idx += 1
                    else:
                        dropped_titles.append(str(orig.get("title", "")))
                print(
                    f"[guard] {a['agent']}: dropped {dropped} "
                    f"titles={dropped_titles}, annotated {annotated}",
                    file=sys.stderr,
                )
                if summary is not None:
                    summary["per_agent"][a["agent"]] = {
                        "dropped": dropped,
                        "annotated": annotated,
                        "dropped_titles": dropped_titles,
                    }
                    summary["total_dropped"] += dropped
                    summary["total_annotated"] += annotated
        except Exception as exc:
            print(f"WARNING: finding guard failed for {a['agent']}: {exc}", file=sys.stderr)
        out.append(a)
    return out


async def run_magi(
    mode: str,
    content: str,
    *,
    host: str | None = None,
    models: dict[str, str] | None = None,
    timeout: int | None = None,
    output_dir: str | None = None,
    base_ref: str = "main",
    enrich: bool = True,
    keep_runs: int = 5,
    warn_input_tokens: int = 150_000,
) -> dict[str, Any]:
    """Run the full MAGI pipeline and return the canonical report dict.

    Returns:
        Dict with keys: agents, consensus, report (ASCII string),
        degraded, failed_agents, retried_agents, cost, input_size.
    """
    _enable_utf8_console_io()

    # Input size guard
    raw_input_chars = len(content)
    if len(content.encode("utf-8")) > MAX_INPUT_SIZE:
        raise MagiInputError(f"Input exceeds {MAX_INPUT_SIZE} bytes")
    est_tokens, oversized = check_input_size(content, warn_input_tokens)
    input_size_note: str | None = None
    if oversized:
        input_size_note = f"Input size warning: ~{est_tokens} estimated tokens ({raw_input_chars} chars)"

    # Config resolution
    cfg = resolve_ollama_config()
    _host = host or cfg["base_url"]
    _models = models or cfg["models"]
    _timeout = timeout or get_timeout()
    _api_key = cfg.get("api_key")
    _structured = cfg.get("structured", "schema")

    # Build prompt
    try:
        prompt = build_user_prompt(mode, content)
    except InvalidInputError as exc:
        raise MagiInputError(str(exc)) from exc

    # A2: resolve diff ONCE (code-review only) and share with enrichment + guard
    review_diff = ""
    if mode == "code-review":
        review_diff = resolve_diff(content, os.getcwd(), base_ref)

    # Code-review enrichment (fail-safe)
    enrichment_note: str | None = None
    if mode == "code-review" and enrich:
        enriched, enrichment_note = enrich_code_review_context(
            content, base_ref=base_ref, diff=review_diff,
        )
        if enriched != content:
            try:
                prompt = build_user_prompt(mode, enriched)
            except InvalidInputError as exc:
                raise MagiInputError(str(exc)) from exc

    # Temp dir + lock lifecycle
    _output_dir: str | None = output_dir
    run_dir: str | None = None
    if _output_dir is None:
        project_root = os.getcwd()
        run_root = project_run_root(project_root)
        run_dir = create_output_dir(None, run_root)
        _output_dir = run_dir
        sweep_legacy_runs_once()
        cleanup_old_runs(max(0, keep_runs - 1), run_root)
        bound = staleness_bound_for_timeout(_timeout)
        write_lock(run_dir, bound)

    try:
        semaphore = asyncio.Semaphore(3)
        retried_agents: list[str] = []
        failed_agents: list[str] = []

        print(f"[MAGI] Launching {len(AGENTS)} agents in parallel (timeout={_timeout}s each)...", flush=True)

        async def _run_one(agent_name: str) -> dict[str, Any] | None:
            async with semaphore:
                prompt_path = AGENT_PROMPTS_DIR / f"{agent_name}.md"
                model = _models.get(agent_name, "qwen3.5:397b-cloud")
                print(f"[MAGI] {agent_name} starting (model={model})...", flush=True)
                try:
                    result = await _run_agent(
                        agent_name, prompt_path, prompt, model, _host,
                        _timeout, _api_key, _structured, _output_dir,
                    )
                    print(f"[MAGI] {agent_name} finished", flush=True)
                    return result
                except (ValidationError, json.JSONDecodeError) as exc:
                    # This is the SECOND failure (retry already happened inside _run_agent)
                    failed_agents.append(agent_name)
                    retried_agents.append(agent_name)
                    print(f"[!] WARNING: {agent_name} failed after retry: {exc}", file=sys.stderr)
                    return None
                except Exception as exc:
                    failed_agents.append(agent_name)
                    print(f"[!] WARNING: {agent_name} failed: {exc}", file=sys.stderr)
                    return None

        results = await asyncio.gather(*[_run_one(a) for a in AGENTS])
        agents_raw = [r for r in results if r is not None]

        print(f"[MAGI] Agents complete: {len(agents_raw)}/{len(AGENTS)} succeeded", flush=True)

        if len(agents_raw) < 2:
            raise RuntimeError(
                f"Only {len(agents_raw)} agent(s) succeeded. Need at least 2 for consensus."
            )

        # Save JSON artifacts
        if _output_dir is not None:
            for a in agents_raw:
                try:
                    a_path = os.path.join(_output_dir, f"{a['agent']}.json")
                    with open(a_path, "w", encoding="utf-8") as fh:
                        json.dump(a, fh, indent=2)
                except OSError:
                    pass

        # Full validation via validate.py
        validated: list[dict[str, Any]] = []
        for a in agents_raw:
            try:
                validated.append(a)  # Already validated in _run_agent_core
            except Exception as exc:
                print(f"WARNING: Validation failed for {a['agent']}: {exc}", file=sys.stderr)

        if len(validated) < 2:
            raise RuntimeError(f"Fewer than 2 agents passed full validation ({len(validated)}).")

        # A5: outside code-review, strip file/line to None for title-based dedup
        if mode != "code-review":
            for a in validated:
                for fnd in a.get("findings", []):
                    fnd["file"] = None
                    fnd["line"] = None

        # A2: diff-grounded finding guard (code-review only)
        files: set[str] = set()
        ranges: dict[str, set[int]] = {}
        guard_summary: dict[str, Any] = {}
        if mode == "code-review" and review_diff:
            try:
                ranges = parse_diff_ranges(review_diff)
                files = set(ranges.keys())
            except Exception:
                files, ranges = set(), {}
            if files:
                print(f"[guard] active: {len(files)} file(s) in diff", file=sys.stderr)
            else:
                print("[guard] skipped: no resolvable diff", file=sys.stderr)
            validated = _apply_finding_guard(validated, mode, files, ranges, summary=guard_summary)

        # Recompute consensus on the guarded agents so the report reflects filtering
        if len(validated) >= 2:
            consensus = determine_consensus(validated)
        else:
            consensus = determine_consensus(agents_raw)  # fallback
        report_ascii = format_report(validated, consensus)

        # Cost aggregation
        cost = aggregate_cost(_output_dir or "", list(AGENTS))

        # Build report dict
        report: dict[str, Any] = {
            "agents": validated,
            "consensus": consensus,
            "report": report_ascii,
            "cost": cost,
            "input_size": {
                "chars": raw_input_chars,
                "est_tokens": est_tokens,
                "oversize": oversized,
                "warn_threshold_tokens": warn_input_tokens,
            },
        }
        if input_size_note:
            report["input_size_note"] = input_size_note
        if enrichment_note:
            report["enrichment_note"] = enrichment_note
        if guard_summary:
            report["guard"] = guard_summary
        if failed_agents:
            report["degraded"] = True
            report["failed_agents"] = sorted(failed_agents)
        else:
            report["degraded"] = False
        if retried_agents:
            report["retried_agents"] = sorted(set(retried_agents))

        # Save magi-report.json
        if _output_dir is not None:
            try:
                report_path = os.path.join(_output_dir, "magi-report.json")
                with open(report_path, "w", encoding="utf-8") as fh:
                    json.dump(report, fh, indent=2)
            except OSError:
                pass

        return report

    except Exception:
        # Failure path: remove temp dir + lock
        if run_dir is not None:
            remove_lock(run_dir)
            try:
                import shutil
                shutil.rmtree(run_dir, ignore_errors=True)
            except Exception:
                pass
        raise
    finally:
        # Success path: remove lock (dir stays for artifact inspection)
        if run_dir is not None:
            remove_lock(run_dir)


def run_magi_sync(
    mode: str,
    content: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Synchronous wrapper around run_magi."""
    return asyncio.run(run_magi(mode, content, **kwargs))
