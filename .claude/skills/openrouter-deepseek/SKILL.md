---
name: openrouter-deepseek
description: Routes heavy-context research and analysis work — structural-edge inventory analysis, edge-viability arithmetic, decision-record drafting, literature and formula lookup — to DeepSeek V4 Pro via OpenRouter. Use when a research task needs a large context window or a long derivation drafted cheaply. Read the isolation boundary first: DeepSeek is a research assistant with no access to gate state, fingerprint data, or wallet information, and nothing it produces reaches a trade decision without a human review step.
---

# DeepSeek V4 Pro via OpenRouter (research only)

This is a **narrow extension** of the `openrouter` skill, not a replacement.
Every hard boundary in `.claude/skills/openrouter/SKILL.md` applies here
unchanged. What this skill adds is one model, one job, and one isolation
boundary that is stricter than the general one.

The job: compute-heavy drafting over large contexts, where Claude Code
orchestrates and reviews and DeepSeek does the volume work.

## The isolation boundary

DeepSeek handles **research and analysis tasks only**. Concretely:

**Never send it:**

| Forbidden input | Where it lives | Why |
|---|---|---|
| Live gate state | `ops/live-gate.json`, `GateResult`, `GateSnapshot` | The gate is the single control that keeps real money off the network. Nothing outside the repo needs to know whether it is open. |
| Fingerprint data | `validated_fingerprint`, `config.py` digests | The fingerprint is what proves the running config matches the approved one. It is an integrity value, not research material. |
| Wallet information | `SOLANA_PRIVATE_KEY`, public key, balances, tx signatures, hot-wallet address | Rule 1 and rule 2 of `CLAUDE.md`. A public key is still an identifier tying this bot to on-chain activity. |
| Any secret | every name in `SECRET_ENV_NAMES` (`src/cli.py`) | Rule 3 of the `openrouter` skill. |
| Raw runtime config or `.env` contents | `config/*.toml` at runtime, environment dumps | Contains the above by construction. |

**Never let its output do:**

- No DeepSeek output feeds a trade decision **without a human review step in
  between**. Not via a `TradeIntent`, not via a parameter value copied into
  config, not via a threshold pasted into a decision record that later gets
  implemented. A number DeepSeek produced must be re-derived by code or by
  hand before anything acts on it.
- DeepSeek is never called from `src/`. It has no import path into the bot.
  It is invoked from research and drafting workflows, by an operator, on
  demand. There is no scheduled or automatic call.
- No DeepSeek output is committed without the provenance note below.

**What it may have:** public market data, price series already on disk,
published research, indicator and concept definitions, the text of existing
decision records, and arithmetic stated in the abstract ("fixed cost $0.0127
per round trip, position size $10, required accuracy for a payoff
distribution with these moments"). Note the last one carries no wallet, no
gate, and no key — the arithmetic of this project is not secret; its state is.

## Provenance: mandatory on every artifact

Any project artifact that DeepSeek helped produce — decision record, analysis
document, inventory entry, derivation — carries this note, placed at the top
under the title:

```markdown
> **Provenance:** DeepSeek-assisted (`deepseek/deepseek-v4-pro` via
> OpenRouter, YYYY-MM-DD). Drafted by the model, reviewed and verified
> before adoption. Numeric claims re-derived independently — see
> {script or method}.
```

This is the same standard every external source in this project carries. An
unmarked model draft is an unsourced claim, and this repository has already
paid once for a number nobody re-derived.

**"Reviewed" means re-derived, not re-read.** The two errors in
`edge_budget.py` (one detection floor across horizons; mixed bases between
edge and sample) both survived re-reading and both died on re-derivation.
A flattering answer from a model is exactly what a flattering error looks
like — so for any number that changes a decision, run it through
`research/trade_power.py` or `research/edge_budget.py` rather than accepting
the model's arithmetic.

## Auth

```bash
# Environment variable only. Never a file path, never committed,
# never interpolated into a prompt or a log line.
export OPENROUTER_API_KEY=sk-or-v1-...
```

`OPENROUTER_API_KEY` is already registered in `SECRET_ENV_NAMES`
(`src/cli.py`), so `register_secret()` masks it before any component reads
the environment. **Registration happens before use** — if you invoke DeepSeek
from a script outside the CLI bootstrap, call `register_secret()` on it
first, in the same order `_bootstrap()` does.

Do not add a key-file loader, a `--api-key` flag, or a `.env` read path.
The registration pattern is env-var-only for every key in this project and
DeepSeek is not the exception.

## Calling it

Base URL `https://openrouter.ai/api/v1`, OpenAI-compatible, so the same
client as the `openrouter` skill with the model string swapped:

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

response = client.chat.completions.create(
    model="deepseek/deepseek-v4-pro",
    messages=[
        {"role": "system", "content": RESEARCH_ONLY_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ],
    max_tokens=8000,   # always set — see Cost
    seed=17,           # supported; use it for anything you may need to re-run
)
```

`seed`, `structured_outputs`, `response_format`, `tools` and
`reasoning_effort` are all supported on this model — verified, not assumed.
`seed` reduces run-to-run variation; it does not make the call
deterministic, which is part of why no model sits in the trade path.

### The system prompt does not enforce the boundary

Write one that states the research-only role, but do not treat it as the
control. The boundary is enforced by **what you put in the prompt**, upstream
of the model. A model instructed not to use wallet data it was given has
still been given wallet data. Filter at the call site.

## The tool

`research/deepseek.py` is the working implementation. Prefer it over writing a
fresh call: the guard, the provenance header, the cost accounting and the
retry ceiling are all in it, and a hand-rolled call has none of them.

```bash
# Always cost it first. This runs the guard and sends nothing.
PYTHONPATH=src .venv/bin/python research/deepseek.py \
    --task edge-viability --question "..." --file research/notes.md --dry-run

# Then run it. --pin for anything a decision record will cite.
PYTHONPATH=src .venv/bin/python research/deepseek.py \
    --task decision-record --pin --max-tokens 24000 \
    --file planning/architecture/some-inventory.md \
    --out planning/decisions/2026-09-15-something.md \
    --question "..."
```

Tasks: `inventory-audit`, `edge-viability`, `decision-record`,
`concept-lookup`, `freeform`. Each carries a role prompt on top of the
boundary statement.

Without `--out` the answer prints to stdout. **That is the delegation working
as intended**: DeepSeek reads the 200 KB of decision records and the
orchestrator reads the 2 KB that comes back. When the orchestrator's own
context is the scarce resource, that asymmetry is the entire reason to
delegate — not the price per token.

### The guard is a real control, not a comment

`research/deepseek_guard.py` allow-lists paths (`planning/`, `research/`,
`docs/`, `.claude/skills/`, plus `README.md` and `CLAUDE.md`) and deny-lists
content on top of that, so a key pasted into an otherwise sendable research
note is still caught on the way out. It **raises rather than redacts** — a
payload that needed redacting was assembled wrongly, and silently fixing it
hides the assembly bug. It runs before the client is constructed, so there is
no window in which a forbidden payload could be sent by a later code path.

There is deliberately **no override flag**. A control with an override is a
control that gets overridden at the moment it matters. If the guard refuses
something you believe is safe, change the input, or change the guard in a
commit someone can review — not at the call site.

`src/` is not on the allow-list. Code review is not one of the jobs this skill
assigns DeepSeek.

### Budget for the reasoning chain, not just the answer

This is a reasoning model: it spends completion budget thinking before it
writes anything. A `max_tokens` that looks generous for the answer can be
consumed entirely by the chain, and what comes back is an HTTP 200 with a
length-truncated choice and **empty content** — not an error.

The first real run of this tool failed exactly that way at
`--max-tokens 6000`. The client now names the failure and tells you to raise
the ceiling; the default is 16,000 and a substantial decision record wants
24,000. For calibration: an 8,500-character decision record cost 11,000
completion tokens, of which **8,900 were reasoning**.

Cost comes from OpenRouter's own `usage.cost` where it is reported, not from
the local price table — the table is a snapshot and goes stale silently.

## Model choice and cost

Verified against the live catalogue on **2026-09-14**:

| Model | Context | Max output | Input /M | Output /M | Cache read /M |
|---|---|---|---|---|---|
| `deepseek/deepseek-v4-pro` | 1,048,576 | 393,216 | $1.60 | $3.20 | $0.135 |
| `deepseek/deepseek-v4-pro-0813` | 1,048,576 | 393,216 | **$0.579** | **$1.738** | $0.0184 |

Both are `text→text` only — no image or file input, unlike `gpt-6-astra`.
Send documents as text.

**`-0813` is a pinned snapshot of the same model at roughly a third of the
price** (2.8× cheaper input, 1.8× cheaper output, 7× cheaper cache reads).
`deepseek-v4-pro` is a floating alias that will move to a newer snapshot
without notice. For reproducible research — anything a decision record will
cite — prefer the pin: a citation to a floating alias cannot be re-run.

Against the general-analysis default `openai/gpt-6-astra` ($10.00 / $50.00),
DeepSeek Pro is ~6× cheaper on input and ~16× cheaper on output, which is
the whole reason this skill exists. It does not have Astra's 272k price
cliff either — the rate is flat across the context window.

**Still set `max_tokens` on every call.** A 393k max-output model with no
bound is an unbounded bill, and at $5–$10 position sizes an inattentive
analysis loop costs more than the trading does.

Re-verify before relying on any row — the refresh command is in
`references/models.md` and needs no authentication.

## Failure handling

Same as `openrouter`: best-effort infrastructure. A failed call degrades to
"no draft generated". One retry, then log it and stop. Nothing in the
trading path waits on it — and since DeepSeek is never called from `src/`,
nothing in the trading path can.

## Where this is wired

- `.claude/skills/structural-edge-inventory` — literature lookup for
  categories not yet in the ledger, and drafting a new ledger entry.
- `.claude/skills/edge-viability-check` — the arithmetic derivation in
  steps 1 and 4, and formula verification against concept definitions from
  the LuxAlgo reference (`planning/architecture/external-tools-registry.md`).

In both, the division of labour is fixed: **Claude Code orchestrates and
reviews, DeepSeek drafts.** The gate verdict, the decision to proceed, and
what gets committed are never the model's.
