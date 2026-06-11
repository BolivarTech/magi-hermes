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
| Retry logic | Single-shot on schema/JSON fail | Identical (v2.2.0 / v2.2.4) |
| Finding guard | Diff-grounded validation | Identical (v3.0.0 Block A) |
| Code-review enrichment | Git diff + symbol lookup | Identical (A2, F2, F3) |
| A5 mode strip | Null file/line in design/analysis | Identical |
| JSON report output | `magi-report.json` artifact | Identical |
| Temp dir lifecycle | LRU + locks + cleanup | Identical (v2.6.0) |
| Input size warning | Chars/4 heuristic | Identical |
| Cost tracking | Aggregate `total_cost_usd` | Identical |
| Sanitization | 4-layer defense-in-depth | Identical |
| Windows UTF-8 | `reconfigure` on startup | Identical (v2.2.6) |
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

- [Hermes Agent](https://hermes-agent.nousresearch.com/) installed
- An OpenAI-compatible endpoint reachable from the Hermes host (default: `http://localhost:11434/v1`)
- Python 3.11+

---

## Installation

Hermes uses a **directory plugin** system. The standard Hermes installer runs from a stripped virtual environment without `pip`, so the `pyproject.toml` entry-point is reserved for advanced users running Hermes from source. The method below works for all standard installations.

### Step 1 — Clone the repository

```bash
git clone https://github.com/BolivarTech/MAGI-Hermes.git
cd MAGI-Hermes
```

### Step 2 — Install as a directory plugin

Hermes looks for plugins under `~/.hermes/plugins/<name>/`. The path `~/.hermes` expands automatically on every OS (Linux/macOS: `$HOME/.hermes`, Windows: `%USERPROFILE%\AppData\Local\hermes`).

```bash
# Create the plugin directory
mkdir -p ~/.hermes/plugins/magi

# Copy the entire repo contents (preserves the magi_plugin/ package)
cp -r . ~/.hermes/plugins/magi/
```

> **Tip:** On Windows PowerShell the same command is:
> ```powershell
> $pluginsDir = "$env:USERPROFILE\AppData\Local\hermes\plugins\magi"
> New-Item -ItemType Directory -Force -Path $pluginsDir
> Copy-Item -Path "$(Get-Location)\*" -Destination $pluginsDir -Recurse -Force
> ```

After copying, `~/.hermes/plugins/magi/` should contain:

```
~/.hermes/plugins/magi/
├── __init__.py              # delegates to magi_plugin.register()
├── plugin.yaml              # Hermes plugin manifest
├── pyproject.toml           # optional build metadata
├── LICENSE
├── LICENSE-APACHE
├── README.md
└── magi_plugin/             # implementation package
    ├── __init__.py            # register(ctx) + sys.modules shim
    ├── orchestrator.py
    ├── models.py
    ├── schemas.py
    ├── consensus.py
    ├── validate.py
    ├── finding_validation.py
    ├── review_context.py
    ├── sanitize.py
    ├── input_size.py
    ├── temp_dirs.py
    ├── run_lock.py
    ├── cost.py
    ├── parse_agent_output.py
    ├── reporting.py
    ├── finding_id.py
    ├── agent_schema.py
    ├── synthesize.py
    ├── status_display.py
    ├── stderr_shim.py
    ├── subprocess_utils.py
    ├── backend.py
    ├── ollama_backend.py
    ├── ollama_config.py
    ├── ollama_init.py
    ├── ollama_preflight.py
    └── agents/
        ├── melchior.md
        ├── balthasar.md
        └── caspar.md
```

> **How it works:** Hermes imports the root `__init__.py`, which calls `magi_plugin.register(ctx)`. A `sys.modules` shim inside `magi_plugin/__init__.py` guarantees that absolute imports (`from magi_plugin.X import ...`) resolve correctly regardless of whether the plugin is loaded as a directory plugin or via pip.

### Step 3 — Enable the plugin

Hermes is **opt-in**: only plugins listed in `plugins.enabled` are loaded.

Run **outside** Hermes (in your regular shell):

```bash
hermes plugins enable magi
```

Or edit `~/.hermes/config.yaml` manually and ensure `enabled` is a **YAML list**, not a string:

```yaml
plugins:
  enabled:
    - magi
```

> **Common mistake:** `hermes config set plugins.enabled "[magi]"` writes the string literal `enabled: '[magi]'`, which Hermes ignores. Always use `hermes plugins enable magi` or a proper YAML list.

### Step 4 — Restart Hermes

Plugin discovery runs **once at startup**.

```bash
exit    # or /exit if you are inside Hermes
hermes  # start Hermes again
```

### Step 5 — Verify

Inside Hermes:

```bash
/plugins
```

Expected output:

```
User plugins (1):
  ● magi v2.0.1 [enabled]
```

If it shows `[not enabled] — not enabled in config`, run `hermes plugins enable magi` **outside** Hermes and restart again.

---

### Updating the plugin

Pull the latest changes and re-copy:

```bash
cd MAGI-Hermes
git pull

# Re-install
cp -r . ~/.hermes/plugins/magi/
```

> **Tip:** On Windows PowerShell the same command is:
> ```powershell
> cd MAGI-Hermes
> git pull
> $pluginsDir = "$env:USERPROFILE\AppData\Local\hermes\plugins\magi"
> Copy-Item -Path "$(Get-Location)\*" -Destination $pluginsDir -Recurse -Force
> ```

Then restart Hermes (`exit` + `hermes`).

---

### Advanced: pip install (source builds only)

This method is **only for developers who build Hermes from source** using a shared Python virtual environment. It does NOT work with the standard Hermes installer.

#### When does this apply?

| Scenario | Method to use |
|----------|--------------|
| Standard Hermes installer (most users) | Directory plugin (see Step 2 above) |
| Running Hermes from Git source (`python -m hermes_agent`) | `pip install -e .` |
| Developing Hermes core itself | `pip install -e .` |
| Hermes installed via `uv tool install` or `pipx` | Directory plugin only |

The standard Hermes installer bundles its own isolated, stripped virtual environment. That venv **lacks pip, setuptools and importlib.metadata**, so any package you install with `pip` elsewhere on your system is invisible to it.

#### How to check which scenario you are in

```bash
# Run this outside Hermes
python -c "import hermes_agent; print(hermes_agent.__file__)"
```

- If it prints a path inside `site-packages` of your **own** venv → you have a source/shared install → `pip install -e .` works.
- If the command fails with `ModuleNotFoundError` → you have the standard installer → **use the directory plugin**.

#### If you are in the source-build scenario

```bash
# Activate the SAME venv where Hermes itself is installed
source /path/to/hermes-venv/bin/activate

# Install MAGI plugin in editable mode
cd MAGI-Hermes
pip install -e .
```

Hermes will auto-discover the plugin via the `pyproject.toml` entry-point on next startup. Then enable and restart as usual.

> **Never mix methods.** If you install via `pip` AND copy as directory plugin, Hermes may load duplicate registrations. Pick one.

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
/magi --init-magi              # Scaffold .hermes/magi-ollama.toml
```

The `--init-magi` sub-command creates a repo-level config file with the default
cross-lineage model trio pre-filled. Never overwrites an existing file.

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
    ├── ollama_init.py               # TOML scaffolding command
    └── agents/
        ├── melchior.md              # Scientist prompt
        ├── balthasar.md             # Pragmatist prompt
        └── caspar.md                # Critic prompt
```

---

## License

Dual-licensed under MIT OR Apache-2.0.
