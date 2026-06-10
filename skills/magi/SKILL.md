---
name: magi
description: >
  Multi-perspective analysis system inspired by the MAGI supercomputers from Evangelion.
  Spawns three parallel LLM calls (Melchior-Scientist, Balthasar-Pragmatist, Caspar-Critic)
  through an OpenAI-compatible local endpoint (Ollama, vLLM, LM Studio), then synthesizes
  a weighted consensus and a canonical ASCII report. Use for decisions with genuine uncertainty,
  significant consequences, or real trade-offs. Trigger phrases: "MAGI", "three perspectives",
  "multi-perspective analysis", "MAGI review".
version: 1.0.0
author: Julian Bolivar
license: MIT OR Apache-2.0
metadata:
  hermes:
    tags: [magi, code-review, design-analysis, multi-agent, ollama, local-llm]
    related_skills: [hermes-agent, claude-code]
---

# MAGI — Multi-Perspective Analysis

## Overview

MAGI implements a **three-agent adversarial consensus** pattern for software
engineering decisions. Each agent is a distinct LLM persona evaluating the
same input through a different lens:

| Agent | Lens | Personality |
|-------|------|-------------|
| **Melchior** | Scientist | Technical rigor, correctness, evidence |
| **Balthasar** | Pragmatist | Maintainability, cost, reversibility |
| **Caspar** | Critic | Risk, edge cases, failure modes, security |

Agents run in **parallel** against an OpenAI-compatible local endpoint (Ollama
by default). The consensus engine weights votes (`approve=1`, `conditional=0.5`,
`reject=-1`) and renders a fixed-format ASCII report.

## When to Use

- Code review, PR review, or design document review
- Architecture or technology-choice decisions
- Debugging or incident-analysis where root cause is unclear
- Any situation with **hidden trade-offs** or **serious consequences**

**Do NOT use** for trivial one-line fixes, obvious questions, or situations
with a single clearly correct answer. The complexity gate skips the full system
for simple inputs.

## Prerequisites

1. An OpenAI-compatible endpoint reachable from the Hermes host.
   Default: `http://localhost:11434/v1` (Ollama).
2. At least one model pulled/available on that endpoint.
3. (Optional) Models assigned to each mage via Hermes config:
   ```bash
   hermes config set magi.models.melchior qwen3.5:397b
   hermes config set magi.models.balthasar gpt-oss:120b
   hermes config set magi.models.caspar deepseek-v4-pro
   ```

## How It Works

```
User input
  |
  v
Complexity gate (in SKILL.md)
  |
  v
hermes_magi.py (orchestrator, via execute_code)
  |
  +---> Melchior  (local LLM #1)  ---+
  +---> Balthasar (local LLM #2)  ---+---> consensus.py
  +---> Caspar    (local LLM #3)  ---+      reporting.py
                                           |
                                           v
                                    Canonical ASCII report
```

## Usage

Trigger phrases:
```
MAGI review this code
Three perspectives on this design
Analyze this PR with MAGI
```

Or load explicitly:
```
/skill magi
```

Then submit your question, code, or diff.

## Workflow (detailed)

### Step 1 — Complexity gate

Before invoking the full system, assess whether the request is trivial:

- Single obvious typo → answer directly, skip MAGI.
- One-line fix with no ambiguity → answer directly, skip MAGI.
- Genuine uncertainty, multiple valid approaches, or significant risk → proceed.

### Step 2 — Detect mode

Classify the input into one of three modes:

| Mode | When to Use |
|------|-------------|
| `code-review` | The user provides code, a diff, or a file to review |
| `design` | Architecture decisions, approach selection, migration plans |
| `analysis` | General problem analysis, trade-offs, debugging |

Default: `analysis`.

### Step 3 — Build prompt payload

Construct a single `PROMPT_PAYLOAD` containing:

```
MODE: <code-review | design | analysis>
CONTEXT: <user's full question, code, or description>
```

If files were provided, include relevant excerpts in CONTEXT.

### Step 4 — Run the orchestrator

Call `execute_code` to run the bundled `hermes_magi.py` script with the
payload and mode. The script:

1. Reads `magi.models.*` from Hermes config (fallback to defaults).
2. Reads each agent system prompt from `agents/{melchior,balthasar,caspar}.md`.
3. Sanitizes and wraps the user payload with nonce delimiters.
4. Launches 3 parallel `asyncio` HTTP POST calls to the configured endpoint.
5. Parses, validates, and deduplicates agent outputs.
6. Runs the consensus engine.
7. Prints the canonical report to stdout.

**Model config resolution (high → low):**

1. `hermes config get magi.models.<mage>` (per-mage model)
2. `hermes config get magi.ollama.default_model` (global fallback)
3. `hermes config get model.default` (Hermes default — NOT recommended for multi-mage diversity)
4. Built-in default: `llama3.1:latest`

**Endpoint config (high → low):**

1. `hermes config get magi.ollama.host`
2. `OLLAMA_HOST` env var
3. Built-in default: `http://localhost:11434/v1`

### Step 5 — Render the report

Capture stdout from `execute_code` and forward it verbatim to the user.
**Do NOT paraphrase, reorder, or strip sections.** The output is the final
answer.

## Canonical Output Contract

Every MAGI invocation MUST end with this exact output format:

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

**Banner rules:**
- Width: 52 columns (50 inner + 2 borders)
- Border: `+` + 50 `=` + `+`
- Labels padded to longest agent label (23 chars for `Balthasar (Pragmatist):`)
- Verdicts: `APPROVE`, `CONDITIONAL`, `REJECT` (uppercase)
- Confidence: integer percent (e.g. `85%`, never `0.85`)

**Key Findings rules:**
- Sorted by severity: critical → warning → info
- Marker column width: 5 (e.g. `[!!!]`, `[!!] `, `[i]  `)
- Severity column width: 14 (e.g. `**[CRITICAL]**`)
- Title starts at column 22
- Sources suffix: `_(from <agent1>, <agent2>)_`

**Section order (never reorder):**
1. Banner
2. `## Key Findings` (omitted if empty)
3. `## Dissenting Opinion` (omitted if empty)
4. `## Conditions for Approval` (omitted if empty)
5. `## Recommended Actions` (always present)

No `## Consensus Summary` section — the banner encodes the verdict.

## Degraded & Fallback Modes

| Scenario | Behavior |
|----------|----------|
| 1 agent fails (timeout/validation) | Proceed with 2 agents; report flagged `"degraded": true` |
| 2+ agents fail | Return error; suggest checking Ollama connectivity |
| Endpoint unreachable | Error with diagnostic URL |
| No models configured | Use built-in default `llama3.1:latest` for all 3 agents |

## Configuration Reference

```bash
# Per-mage models (recommended for cross-lineage diversity)
hermes config set magi.models.melchior  qwen3.1:latest
hermes config set magi.models.balthasar llama3.2:latest
hermes config set magi.models.caspar   mistral:latest

# Endpoint (any OpenAI-compatible server)
hermes config set magi.ollama.host http://localhost:11434/v1

# Timeout per agent (seconds)
hermes config set magi.ollama.timeout 300

# Global fallback model (when per-mage not set)
hermes config set magi.ollama.default_model llama3.1:latest
```

## Common Pitfalls

1. **Expecting `delegate_task` diversity.** Hermes `delegate_task` inherits the
parent agent's model and provider settings — ALL sub-agents receive the SAME
model, temperature, and system prompt. You cannot pass `model: "qwen3.5"` to one
child and `model: "mistral"` to another. The "official workaround" of spawning
separate `hermes chat -q` processes has heavy overhead, fragile stdout parsing,
and breaks the orchestrator's error handling. The durable solution, used here,
is to run a bundled Python script via `execute_code` that makes direct async
HTTP calls to the OpenAI-compatible endpoint, passing a distinct `model` per mage
while keeping the pipeline fast, deterministic, and fully within the stdlib.

2. **Forgetting Ollama CORS.** If Ollama rejects requests, ensure
`OLLAMA_ORIGINS=* ollama serve` or set origins in `~/.ollama/config.yaml`.

3. **Model not pulled.** The preflight checks model availability before launch.
If a model is missing, the error names the exact model tag to `ollama pull`.

4. **Structured output rejection.** If the endpoint does not support
`response_format` (e.g. older Ollama), the backend auto-downgrades to plain
JSON-instruction and validates the 7-key schema post-hoc.

5. **Empty findings is valid.** An agent returning zero findings is NOT an
error. The consensus engine treats it as a clean bill of health from that lens.

## File Layout

```
magi/
├── SKILL.md                           # This file
├── README.md                          # Full installation and usage guide
├── agents/
│   ├── melchior.md                    # Scientist system prompt
│   ├── balthasar.md                   # Pragmatist system prompt
│   └── caspar.md                      # Critic system prompt
├── scripts/
│   ├── hermes_magi.py                 # Main orchestrator (async HTTP)
│   ├── consensus.py                   # Weight-based voting engine
│   ├── reporting.py                   # ASCII banner + markdown formatter
│   ├── validate.py                    # JSON schema validation
│   ├── models.py                      # Hermes config reader + model registry
│   ├── agent_schema.py                # JSON Schema for structured output
│   ├── finding_id.py                  # SHA-256 finding identity (dedup)
│   └── synthesize.py                # Facade: re-exports all engine modules
└── references/
    ├── porting-from-claude.md          # Migration notes (magi-claude → Hermes)
    └── multi-model-architecture.md     # Why delegate_task cannot be used
```

## Verification Checklist

- [ ] `hermes skills list` shows `magi` under `software-development`
- [ ] Ollama (or compatible endpoint) running and reachable
- [ ] At least one model available on the endpoint
- [ ] `hermes config get magi.ollama.host` returns expected URL
- [ ] Test invocation produces canonical banner with all 5 sections
- [ ] Degraded mode (kill one model mid-run) still produces a 2-agent report
