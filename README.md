# MAGI Plugin for Hermes Agent

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)
[![Ollama](https://img.shields.io/badge/ollama-compatible-green.svg)](https://ollama.ai/)

A **Hermes Agent plugin** that implements the **multi-perspective analysis**
system inspired by the [MAGI supercomputers](https://evangelion.fandom.com/wiki/Magi)
from *Neon Genesis Evangelion*.

Three specialized AI agents independently analyze the same problem from
complementary — and deliberately adversarial — perspectives, then synthesize
their verdicts via deterministic weight-based majority vote. This plugin is
**functionally equivalent** to the production MAGI-Claude v2.6.0 system,
migrated to run as a native Hermes plugin over any OpenAI-compatible endpoint
with genuine cross-lineage model diversity.

Forked from the original [magi-claude](https://github.com/BolivarTech/magi-claude)
and the [magi-hermes skill](https://github.com/BolivarTech/magi-hermes).

---

## Why Three Adversarial Perspectives?

### The MAGI in Evangelion

In *Neon Genesis Evangelion* (1995, Hideaki Anno / Gainax), the MAGI are three
supercomputers that govern Tokyo-3's critical decisions. Each embodies a
different facet of their creator, Dr. Naoko Akagi: **Melchior** (the scientist),
**Balthasar** (the mother), and **Caspar** (the woman). Decisions require
consensus — no single perspective dominates.

### The Theory in Practice

The adversarial multi-perspective model addresses well-documented cognitive
biases:

| Bias | How MAGI Mitigates It |
|------|----------------------|
| **Confirmation bias** | Three agents with different evaluation criteria are unlikely to share the same blind spots |
| **Anchoring** | Agents analyze independently — no agent sees the others' output before forming its own verdict |
| **Groupthink** | Caspar (Critic) is designed to be adversarial; its role is to find fault, not agree |
| **Optimism bias** | The weight-based scoring penalizes reject (-1) more heavily than approve (+1), making negative signals harder to override |
| **Status quo bias** | Each agent evaluates from first principles against its own criteria, not against "how things are done" |

---

## How It Differs from the Original

| Feature | Original Claude Plugin | This Hermes Plugin |
|---------|----------------------|-------------------|
| Backend | `claude -p` CLI | OpenAI-compatible HTTP (Ollama, vLLM, LM Studio) |
| Provider lock-in | Anthropic only | Any endpoint with `/v1/chat/completions` |
| Model diversity | Prompt-only | **Real cross-model diversity** (distinct model per mage) |
| Config system | Custom TOML files | TOML + env precedence (see below) |
| Cross-platform | Terminal only | Terminal + Telegram + Discord + Slack + ... |
| Retry logic | Single-shot on schema/JSON fail | ✅ Identical (v2.2.0 / v2.2.4) |
| Finding guard | Diff-grounded validation | ✅ Identical (v3.0.0 Block A) |
| Code-review enrichment | Git diff + symbol lookup | ✅ Identical (A2, F2, F3) |
| A5 mode strip | Null file/line in design/analysis | ✅ Identical |
| JSON report output | `magi-report.json` artifact | ✅ Identical |
| Temp dir lifecycle | LRU + locks + cleanup | ✅ Identical (v2.6.0) |
| Input size warning | Chars/4 heuristic | ✅ Identical |
| Cost tracking | Aggregate `total_cost_usd` | ✅ Identical |
| Sanitization | 4-layer defense-in-depth | ✅ Identical |
| Windows UTF-8 | `reconfigure` on startup | ✅ Identical (v2.2.6) |
| Integration | Claude Code plugin | **Hermes Agent native plugin** |

---

## Agents

| Agent | Codename | Lens | Personality |
|-------|----------|------|-------------|
| **Melchior** | Scientist | Technical rigor and correctness | Precise, evidence-based, favors proven solutions |
| **Balthasar** | Pragmatist | Practicality and maintainability | Grounded, trade-off oriented, advocates for the team |
| **Caspar** | Critic | Risk, edge cases, and failure modes | Adversarial by design, finds what others miss |

---

## Prerequisites

- Hermes Agent installed and configured
- An OpenAI-compatible endpoint reachable from the Hermes host (default: `http://localhost:11434/v1`)
- Python 3.11+ (uses `asyncio`, `tomllib`, modern dict syntax)

---

## Installation

### Via pip

```bash
pip install magi-hermes-plugin
```

Hermes auto-discovers the plugin on next startup via the entry-point declared
in `pyproject.toml`:
```toml
[project.entry-points."hermes_agent.plugins"]
magi = "magi_plugin"
```

### As a directory plugin

```bash
git clone https://github.com/BolivarTech/magi-hermes.git
cd magi-hermes
mkdir -p ~/.hermes/plugins/magi
ln -s "$(pwd)/magi-hermes-plugin"/* ~/.hermes/plugins/magi/
hermes
```

### Enable

```bash
hermes plugins list          # Should show magi
hermes plugins enable magi   # Enable if not already active
```

---

## Configuration

MAGI uses a **layered configuration** with the following precedence per key
(high → low):

1. `MAGI_OLLAMA_*` environment variables
2. Repo-level TOML `.hermes/magi-ollama.toml`
3. Global TOML `~/.hermes/magi-ollama.toml`
4. Generic env fallbacks (`OLLAMA_HOST`, `OLLAMA_API_KEY`)
5. Built-in defaults

### Default Models (production-proven)

These are the models tested in production with MAGI-Claude v2.6.0 under the
Ollama cloud tier "Máximo". They provide **cross-lineage diversity**
(Qwen + GPT-OSS + DeepSeek):

| Mage | Default Model | Role |
|------|---------------|------|
| Melchior | `qwen3.5:397b-cloud` | Scientist — theoretical analysis |
| Balthasar | `gpt-oss:120b-cloud` | Pragmatist — practical trade-offs |
| Caspar | `deepseek-v4-pro:cloud` | Critic — adversarial review |

### TOML config file example

```toml
# ~/.hermes/magi-ollama.toml  (or .hermes/magi-ollama.toml in repo)
base_url = "http://localhost:11434/v1"
api_key = "sk-..."          # optional; omit for no auth
structured = "schema"       # "schema" | "object" | "off"

[models]
melchior = "qwen3.5:397b-cloud"
balthasar = "gpt-oss:120b-cloud"
caspar = "deepseek-v4-pro:cloud"
```

### Environment variable overrides

```bash
export MAGI_OLLAMA_HOST="http://localhost:11434/v1"
export MAGI_OLLAMA_API_KEY="sk-..."
export MAGI_OLLAMA_STRUCTURED="schema"
export MAGI_OLLAMA_MODEL_MELCHIOR="qwen3.5:397b-cloud"
export MAGI_OLLAMA_MODEL_BALTHASAR="gpt-oss:120b-cloud"
export MAGI_OLLAMA_MODEL_CASPAR="deepseek-v4-pro:cloud"
```

### Hermes config.yaml (legacy, still supported)

```bash
hermes config set magi.ollama.host http://localhost:11434/v1
hermes config set magi.models.melchior qwen3.5:397b-cloud
hermes config set magi.models.balthasar gpt-oss:120b-cloud
hermes config set magi.models.caspar deepseek-v4-pro:cloud
```

---

## Usage

### Tool invocation (LLM-driven)

When Hermes detects a natural trigger phrase ("MAGI review", "three
perspectives", "multi-perspective analysis"), it suggests the `magi_analyze`
tool. The LLM can then call it with the appropriate mode and content.

### Slash command

```bash
/magi code-review: Review this PR diff
/magi design: Should we use Redis or Postgres?
/magi analysis: Three perspectives on this bug
```

### Python API

```python
from magi_plugin.orchestrator import run_magi_sync

report = run_magi_sync(
    mode="code-review",
    content="```diff\n...\n```",
    base_ref="main",
)
print(report["report"])          # ASCII consensus report
print(report["consensus"])       # Structured consensus dict
print(report["cost"])            # Per-agent cost aggregation
print(report["input_size"])      # Estimated token footprint
```

The returned `report` dict always contains:
- `agents` — validated agent outputs
- `consensus` — weighted majority verdict
- `report` — formatted ASCII string
- `cost` — per-agent + total USD (from raw envelopes)
- `input_size` — chars, estimated tokens, oversize flag
- `degraded` / `failed_agents` / `retried_agents` — when applicable
- `guard` — finding guard summary (code-review only)
- `enrichment_note` — context enrichment summary (code-review only)

Additionally, `magi-report.json` is written to the run directory for audit.

---

## Architecture

```
MAGI-Hermes/
├── plugin.yaml                    # Hermes plugin manifest
├── pyproject.toml                 # Build + entry-point
├── __init__.py                    # Re-export for directory install
└── magi_plugin/
    ├── __init__.py                  # register(ctx) — tools, hooks, commands
    ├── orchestrator.py              # Async pipeline + retry + guard + enrichment
    ├── models.py                    # Config resolution + model registry
    ├── schemas.py                   # Tool schema for magi_analyze
    ├── consensus.py                 # Deterministic weighted voting
    ├── validate.py                  # Strict JSON schema validation
    ├── finding_validation.py        # Diff-grounded finding guard
    ├── review_context.py            # Git diff enrichment + symbol lookup
    ├── sanitize.py                  # 4-layer prompt sanitization
    ├── input_size.py                # Token estimation + oversize detection
    ├── temp_dirs.py                 # LRU temp lifecycle + per-project namespace
    ├── run_lock.py                  # Process-liveness locking
    ├── cost.py                      # Cost aggregation from raw envelopes
    ├── parse_agent_output.py        # Lenient JSON recovery from prose
    ├── reporting.py                 # ASCII report formatting
    ├── finding_id.py                # SHA-256 deduplication + category normalization
    ├── agent_schema.py              # JSON Schema for structured output
    └── agents/
        ├── melchior.md              # Scientist prompt
        ├── balthasar.md             # Pragmatist prompt
        └── caspar.md                # Critic prompt
```

---

## License

Dual-licensed under MIT OR Apache-2.0.
