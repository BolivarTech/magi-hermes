# MAGI — Multi-Perspective Analysis Skill for Hermes Agent

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT%20OR%20Apache--2.0-blue.svg)](#license)
[![Ollama](https://img.shields.io/badge/ollama-compatible-green.svg)](https://ollama.ai/)

A Hermes Agent skill that implements a **multi-perspective analysis system** inspired by the [MAGI supercomputers](https://evangelion.fandom.com/wiki/Magi) from *Neon Genesis Evangelion*. 

Forked from the original [magi-claude](https://github.com/BolivarTech/magi-claude) plugin.

Three specialized AI agents independently analyze the same problem from complementary — and deliberately adversarial — perspectives, then synthesize their verdicts via weight-based majority vote. Unlike the original Claude Code plugin, this version runs on **any OpenAI-compatible local endpoint** (Ollama, vLLM, LM Studio, etc.) with **genuine cross-lineage model diversity**.

---

## Why Three Adversarial Perspectives?

### The MAGI in Evangelion

In *Neon Genesis Evangelion* (1995, Hideaki Anno / Gainax), the MAGI are three supercomputers that govern Tokyo-3's critical decisions. Each embodies a different facet of their creator, Dr. Naoko Akagi: **Melchior** (the scientist), **Balthasar** (the mother), and **Caspar** (the woman). Decisions require consensus — no single perspective dominates.

This design reflects a profound insight: **complex decisions benefit from structured disagreement**. A single decision-maker, no matter how capable, carries blind spots. Three independent evaluators with different priorities surface risks, trade-offs, and opportunities that any one of them would miss.

### The Theory in Practice

The adversarial multi-perspective model addresses well-documented cognitive biases in software engineering:

| Bias | How MAGI Mitigates It |
|------|----------------------|
| **Confirmation bias** | Three agents with different evaluation criteria are unlikely to share the same blind spots |
| **Anchoring** | Agents analyze independently — no agent sees the others' output before forming its own verdict |
| **Groupthink** | Caspar (Critic) is designed to be adversarial; its role is to find fault, not agree |
| **Optimism bias** | The weight-based scoring penalizes reject (-1) more heavily than approve (+1), making negative signals harder to override |
| **Status quo bias** | Each agent evaluates from first principles against its own criteria, not against "how things are done" |

The key insight is that **disagreement between agents is a feature, not a failure**. When Melchior (Scientist) approves but Caspar (Critic) rejects, the dissent surfaces a genuine tension between technical correctness and risk tolerance. Unanimous agreement on non-trivial input may indicate insufficiently differentiated prompts, not actual consensus.

In practice, the system works best for decisions with:
- **Genuine uncertainty** — multiple valid approaches exist
- **Significant consequences** — the cost of a wrong decision is high
- **Hidden trade-offs** — benefits and risks are not immediately obvious

For trivial questions with one clear answer, the complexity gate skips the full system and responds directly.

---

## How It Differs from the Original

| Feature | Original Claude Plugin | This Hermes Skill |
|---------|----------------------|-------------------|
| Backend | `claude -p` CLI | OpenAI-compatible HTTP (Ollama, vLLM, LM Studio) |
| Provider lock-in | Anthropic only | Any endpoint with `/v1/chat/completions` |
| Model diversity | Prompt-only | **Real cross-model diversity** (distinct model per mage) |
| Config system | Custom TOML files | Native `hermes config set ...` |
| Cross-platform | Terminal only | Terminal + Telegram + Discord + Slack + ... |
| Memory | None | Persistent via Hermes memory system |
| Sub-agent mechanism | `claude -p` parallel | `asyncio` + `urllib` direct HTTP |

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
- At least one model available on that endpoint
- Python 3.11+ (uses `asyncio` and modern dict syntax)

---

## Installation

### From GitHub (for users)

```bash
# 1. Install directly from the raw SKILL.md URL
hermes skills install https://raw.githubusercontent.com/BolivarTech/magi-hermes/main/skills/magi/SKILL.md

# 2. Verify installation
hermes skills list
# Should show 'magi' under software-development
```

### Local Development

```bash
# Clone the repository
git clone https://github.com/BolivarTech/magi-hermes.git
cd magi-hermes

# Link the skill into your Hermes skills directory (Windows)
mklink /D "%LOCALAPPDATA%\hermes\skills\software-development\magi" "skills\magi"

# Reload Hermes to pick up the new skill
hermes reload
```

---

## Configuration

### Required

```bash
# Set the endpoint for your local OpenAI-compatible server (optional — defaults to localhost)
hermes config set magi.ollama.host http://localhost:11434/v1
```

### Recommended — Model Diversity

For maximum analytical diversity, assign **different model families** to each mage:

```bash
# Qwen for analytical depth (scientist)
hermes config set magi.models.melchior qwen3.1:latest

# Llama for balanced pragmatism
hermes config set magi.models.balthasar llama3.2:latest

# Mistral for adversarial rigor
hermes config set magi.models.caspar mistral:latest
```

**Why different models?** Each model family has distinct training data, strengths, and biases. A Qwen model trained on mathematical reasoning thinks differently about code correctness than a Mistral model optimized for instruction following. This **cross-lineage diversity** is the core advantage over single-model multi-prompt systems.

### Optional

```bash
# Global fallback model (when per-mage not set)
hermes config set magi.ollama.default_model llama3.1:latest

# Per-agent timeout in seconds
hermes config set magi.ollama.timeout 300
```

### Environment Variable Fallbacks

If Hermes config is not available, the system falls back to:

```bash
export OLLAMA_HOST=http://localhost:11434/v1
export MAGIMODEL_MELCHIOR=qwen3.1:latest
export MAGIMODEL_BALTHASAR=llama3.2:latest
export MAGIMODEL_CASPAR=mistral:latest
export MAGIMODEL_DEFAULT=llama3.1:latest
```

---

## Usage

### Natural Triggers

Once the skill is loaded, invoke with trigger phrases:

```
MAGI review this code
Give me three perspectives on this design
Analyze this PR with MAGI
Three perspectives on this problem
```

Or load explicitly:
```
/skill magi
```

### Modes

| Mode | When to Use | Example |
|------|-------------|---------|
| `code-review` | Reviewing code or diffs | "MAGI review this PR" |
| `design` | Evaluating architecture decisions | "MAGI analyze this migration plan" |
| `analysis` | General problem analysis, trade-offs | "MAGI should we use Redis or Postgres for this?" |

Default mode: `analysis`.

### CLI (Direct Execution)

The skill can also run standalone, outside of Hermes:

```bash
# Via the script directly
python skills/magi/scripts/hermes_magi.py --mode code-review --input file.py --output report.txt

# Or pipe input
cat design.md | python skills/magi/scripts/hermes_magi.py --mode design --output report.txt
```

| Flag | Default | Description |
|------|---------|-------------|
| `--mode` | `analysis` | One of: `code-review`, `design`, `analysis` |
| `--input` | stdin | Input file or inline text |
| `--output` | stdout | Output file for the report |
| `--timeout` | `300` | Per-agent timeout in seconds |

---

## How It Works

```
User input
  |
  v
SKILL.md (complexity gate + mode detection)
  |
  v
hermes_magi.py (async orchestrator)
  |
  +---> Melchior  (HTTP to LLM #1)  ---+
  +---> Balthasar (HTTP to LLM #2)  ---+---> consensus.py
  +---> Caspar    (HTTP to LLM #3)  ---+      reporting.py
                                            |
                                            v
                                     Canonical ASCII report
```

### Step by Step

1. **Complexity gate** — Simple questions are answered directly without invoking three agents.
2. **Parallel dispatch** — Three async HTTP POST calls run concurrently, each with a distinct system prompt and a different model.
3. **Independent analysis** — Each agent evaluates the same input through its unique lens and produces a structured JSON verdict.
4. **Validation** — Each agent's output is parsed and validated against the agent JSON schema.
5. **Weight-based vote** — The consensus engine computes a weighted score, deduplicates findings, and generates a consensus report.

### Consensus Rules

Verdicts are weighted: `approve = 1`, `conditional = 0.5`, `reject = -1`.

```
score = sum(weight[verdict] for each agent) / num_agents
```

| Score | Consensus |
|-------|-----------|
| 1.0 (unanimous approve) | **STRONG GO** |
| -1.0 (unanimous reject) | **STRONG NO-GO** |
| > 0 with conditionals | **GO WITH CAVEATS** |
| > 0 without conditionals | **GO (N-M)** |
| <= 0 | **HOLD (N-M)** |

Labels are dynamic: `(N-M)` reflects the actual majority/minority split (e.g., `GO (2-1)` or `HOLD (1-1)` in degraded mode).

### Confidence Formula

```
weight_factor = (abs(score) + 1) / 2    # symmetric for approve and reject
base_confidence = sum(majority_confidence) / num_agents
confidence = base_confidence * weight_factor
```

Using `abs(score)` ensures that both unanimous approve and unanimous reject produce high confidence. At `score = 0` (exact tie), confidence is halved — appropriate for an undecided split.

---

## Output Example

```
+==================================================+
|          MAGI SYSTEM -- VERDICT                  |
+==================================================+
|  Melchior (Scientist):   APPROVE (90%)           |
|  Balthasar (Pragmatist): CONDITIONAL (85%)       |
|  Caspar (Critic):        REJECT (78%)            |
+==================================================+
|  CONSENSUS: GO WITH CAVEATS (2-1)                |
+==================================================+

## Key Findings
[!!!] **[CRITICAL]** SQL injection in query builder _(from melchior, caspar)_
[!!]  **[WARNING]**  Missing retry logic for API calls _(from balthasar)_
[i]   **[INFO]**     Consider adding request timeout _(from caspar)_

## Dissenting Opinion
**Caspar (Critic)**: Risk of data loss outweighs shipping speed...

## Conditions for Approval
- **Balthasar**: Add integration tests before merge

## Recommended Actions
- **Melchior** (Scientist): Fix SQL injection, add parameterized queries
- **Balthasar** (Pragmatist): Ship after adding integration tests
- **Caspar** (Critic): Rework query layer before proceeding
```

### Output Contract

Every MAGI invocation ends with this exact format:

- **Banner** — 52-column ASCII table with agent verdicts and confidence
- **Key Findings** — Sorted by severity (critical → warning → info), deduplicated by content hash
- **Dissenting Opinion** — Only when at least one agent disagrees with the majority
- **Conditions for Approval** — Only when agents voted `conditional`
- **Recommended Actions** — Always present, one per agent

The banner is **machine-parseable** and **human-readable**.

---

## Degraded Mode

When an agent fails (timeout, parse error, validation error, endpoint unreachable):
- Warning printed to stderr identifying the failed agent and reason
- Synthesis proceeds if >= 2 agents succeeded
- Report proceeds normally; missing agent is simply omitted from the banner

If fewer than 2 agents succeed, the system exits with error and diagnostic output.

---

## Project Structure

```
skills/magi/
  SKILL.md                    -- Orchestrator (mode detection, config, workflow)
  README.md                   -- This file
  agents/
    melchior.md               -- Scientist system prompt
    balthasar.md              -- Pragmatist system prompt
    caspar.md                 -- Critic system prompt (adversarial by design)
  scripts/
    hermes_magi.py            -- Async orchestrator (HTTP to OpenAI-compatible endpoint)
    synthesize.py             -- Facade: re-exports from validate, consensus, reporting
    validate.py               -- ValidationError + load_agent_output schema validation
    consensus.py              -- VERDICT_WEIGHT + determine_consensus (weight-based scoring)
    reporting.py              -- AGENT_TITLES + format_banner + format_report (ASCII)
    models.py                 -- Hermes config reader + model registry
    finding_id.py             -- SHA-256 finding identity (deduplication)
    agent_schema.py           -- JSON Schema for structured output
pyproject.toml                -- Python >= 3.11, dual license, tool config
```

### Module Architecture

The synthesis engine is split into focused, single-responsibility modules:

| Module | Responsibility | Key Exports |
|--------|---------------|-------------|
| `validate.py` | Schema validation | `ValidationError`, `load_agent_output` |
| `consensus.py` | Weight-based scoring | `VERDICT_WEIGHT`, `determine_consensus` |
| `reporting.py` | ASCII banner + markdown report | `format_banner`, `format_report` |
| `models.py` | Config resolution | `get_models()`, `get_host()`, `get_timeout()` |
| `synthesize.py` | Facade (re-exports all above) | All public symbols |

**Import convention:** Always import from `synthesize` (the facade), not directly from sub-modules:

```python
from synthesize import load_agent_output, determine_consensus, format_report
```

---

## Troubleshooting

### Ollama rejects requests (CORS error)

Start Ollama with open origins:
```bash
OLLAMA_ORIGINS=* ollama serve
```

Or set `origins: ["*"]` in `~/.ollama/config.yaml`.

### Model not found

Pull the model first:
```bash
ollama pull llama3.1:latest
```

### Endpoint unreachable

Verify connectivity:
```bash
curl http://localhost:11434/v1/models
```

### One agent consistently fails validation

Check the agent's output file in the temp directory (printed in stderr). Most common causes:
- Missing a required JSON key
- Verdict value not in `{approve, reject, conditional}`
- Confidence outside `[0.0, 1.0]`
- Findings not a list of objects with `{severity, title, detail}`

---

## Requirements

| Component | Required | Notes |
|-----------|----------|-------|
| Hermes Agent | For trigger-mode usage | CLI mode works standalone |
| OpenAI-compatible endpoint | Yes | Ollama, vLLM, LM Studio, etc. |
| Python 3.11+ | Yes | Uses `asyncio`, `dict[str, Any]` syntax |

### Dev Dependencies

```bash
pip install pytest ruff mypy
```

---

## Running Tests

```bash
# All tests
python -m pytest tests/ -v

# Full verification (tests + lint + types)
make verify

# Individual checks
make test        # pytest
make lint        # ruff check
make typecheck   # mypy
```

---

## License

Dual licensed under [MIT](LICENSE) OR [Apache-2.0](LICENSE-APACHE), at your option.

---

## Credits

The MAGI concept originates from [*Neon Genesis Evangelion*](https://en.wikipedia.org/wiki/Neon_Genesis_Evangelion) (1995) by Hideaki Anno / Gainax. The three supercomputers — Melchior, Balthasar, and Caspar — govern critical decisions through structured consensus, each embodying a different facet of their creator Dr. Naoko Akagi.

This skill is a fork of the [magi-claude](https://github.com/BolivarTech/magi-claude) plugin by Julian Bolivar, adapted for Hermes Agent to support any OpenAI-compatible local endpoint with genuine cross-model diversity.

Original plugin: © Julian Bolivar.
Hermes migration: © Julian Bolivar and contributors.
