---
name: openrouter
description: Access LLMs through OpenRouter for TradeCC's research, analysis, and reporting work — backtest summaries, incident write-ups, v0.2 wallet-vetting analysis. Use whenever adding an LLM call, choosing a model, handling an OpenRouter API key, or estimating token costs. Read the hard boundaries first — an LLM must never sit in the trade-decision or execution path for v0.1, which is deterministic momentum/TA by design.
---

# OpenRouter for TradeCC

OpenRouter is a single OpenAI-compatible endpoint in front of many model
providers. One API key, one request shape, and models can be swapped by
changing a string.

## Hard boundaries (read before writing any call)

TradeCC is a money-adjacent codebase. These are not style preferences:

1. **No LLM in the trade-decision path.** The strategy is deterministic
   EMA/RSI precisely so it can be backtested and reproduced. A model call
   in the signal path makes the backtest meaningless — you cannot
   validate a strategy whose decisions are non-deterministic and change
   under the vendor's silent model updates. **This still holds in v0.2.**
   The v0.2 extension grants Astra research and *veto* authority only,
   with every proposal frozen into deterministic code before it can
   affect a trade — see the `astra-analyst` skill and
   `planning/decisions/2026-09-10-v02-intelligence-architecture.md`.
2. **An LLM never bypasses the risk engine.** If model output ever
   proposes a trade, it produces a `TradeIntent` that goes through
   `RiskEngine.approve()` like anything else. There is no "the model was
   confident" override.
3. **Never send secrets to a model.** No private key, seed phrase, `.env`
   contents, or raw config dumps. Reuse `core.logging.redact()` on any
   payload built from runtime state before it goes into a prompt.
4. **Never send an API key in a prompt or log it.** `OPENROUTER_API_KEY`
   loads from the environment at runtime. Register it with
   `core.logging.register_secret()` at startup so it is scrubbed if it
   ever reaches a log line.
5. **Cost is a real constraint.** At $5–$10 position sizes, an
   inattentive analysis loop can cost more than the trading does. Budget
   deliberately — see Cost below.

## Where an LLM genuinely fits here

- Summarising a backtest run into the `research/backtests/` write-up
  format (net-of-fees numbers still come from code, not the model).
- Drafting an incident log from structured logs after a circuit-breaker
  trip.
- **v0.2 only:** qualitative wallet-vetting analysis — and only under the
  gating rules in the `web-research-vetting` skill.

## Auth and endpoint

```bash
# Never committed. Set in the environment / secrets manager.
OPENROUTER_API_KEY=sk-or-v1-...
```

Base URL: `https://openrouter.ai/api/v1` — the Chat Completions shape is
OpenAI-compatible, so the `openai` Python SDK works by pointing
`base_url` at it.

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ["OPENROUTER_API_KEY"],
)

response = client.chat.completions.create(
    model="openai/gpt-6-astra",
    messages=[{"role": "user", "content": prompt}],
    max_tokens=2000,
)
```

Two optional headers, `HTTP-Referer` and `X-Title`, attribute usage on
OpenRouter's dashboards. Pass them via `default_headers` if you want
TradeCC's usage identifiable.

## Model selection

Default to **`openai/gpt-6-astra`** for substantive analysis work.

**Never hardcode a model ID from memory.** The catalogue changes; a stale
or invented slug fails at runtime. Verify against the live list first —
it needs no auth:

```bash
curl -sS https://openrouter.ai/api/v1/models \
  | python3 -c "import json,sys; [print(m['id']) for m in json.load(sys.stdin)['data'] if 'astra' in m['id']]"
```

See `references/models.md` for the verified snapshot and how to refresh it.

### Variants worth knowing
- `openai/gpt-6-astra` — the default.
- `openai/gpt-6-astra-pro` — the same underlying model served with
  `reasoning.mode` set to `pro`. Use for genuinely hard analysis, not as
  a reflex.
- `:batch` suffixes — asynchronous batch processing, appropriate for
  non-urgent bulk work like re-summarising a backlog of backtests.

## Cost

Verified 2026-09-09 (per million tokens, USD):

| | Input | Output | Cache read | Cache write |
|---|---|---|---|---|
| Standard | $10.00 | $50.00 | $1.00 | $12.50 |
| **Prompts over 272k tokens** | **$20.00** | **$75.00** | $2.00 | $25.00 |

Two things follow from that table:

- **There is a price cliff at 272k prompt tokens**, where input doubles
  and output rises 50%. Astra's 1.05M context does not mean filling it is
  cheap. Trim context rather than dumping whole log files into a prompt.
- **Cache reads are 10x cheaper than fresh input.** For repeated analysis
  over a stable corpus, structure prompts so the shared prefix is cached.

Set `max_tokens` on every call. An unbounded call against a 128k
max-output model is an unbounded bill.

## Failure handling

Model calls are best-effort infrastructure, exactly like PostHog: a
failed analysis call must never interrupt or block trading. Wrap calls so
an exception degrades to "no summary generated" rather than propagating
into a trading loop. Do not add retry storms — one retry, then give up
and log it.
