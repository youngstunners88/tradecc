# OpenRouter model snapshot for TradeCC

Verified against `https://openrouter.ai/api/v1/models` on **2026-09-09**,
re-verified **2026-09-10** — all four IDs, contexts, and prices unchanged.
Treat this as a snapshot, not a source of truth — the catalogue changes,
and a model ID that no longer exists fails at runtime. Re-verify before
relying on any row.

## Refreshing this file

```bash
curl -sS https://openrouter.ai/api/v1/models -o /tmp/models.json

python3 -c "
import json
d = json.load(open('/tmp/models.json'))['data']
for m in d:
    if 'astra' in m['id']:
        p = m['pricing']
        print(m['id'], '| ctx', m['context_length'],
              '| in \$%.2f/M' % (float(p['prompt']) * 1e6),
              '| out \$%.2f/M' % (float(p['completion']) * 1e6))
"
```

The endpoint needs no authentication, so this is safe to run any time and
does not consume credit.

## Verified models

| Model ID | Context | Max output | Modality |
|---|---|---|---|
| `openai/gpt-6-astra` | 1,050,000 | 128,000 | text + image + file → text |
| `openai/gpt-6-astra-pro` | 1,050,000 | 128,000 | text + image + file → text |
| `openai/gpt-6-astra:batch` | 1,050,000 | 128,000 | text + image + file → text |
| `openai/gpt-6-astra-pro:batch` | 1,050,000 | 128,000 | text + image + file → text |

`gpt-6-astra-pro` is the same underlying model as `gpt-6-astra`, served
with `reasoning.mode` set to `pro`. It is not a different or larger
model — it trades latency and reasoning tokens for answer quality on hard
problems.

## Pricing (USD per million tokens)

Identical for the standard and `-pro` variants; `-pro` costs more in
practice because it generates more reasoning tokens, not because the rate
differs.

| Tier | Input | Output | Cache read | Cache write |
|---|---|---|---|---|
| Standard | $10.00 | $50.00 | $1.00 | $12.50 |
| Prompt > 272,000 tokens | $20.00 | $75.00 | $2.00 | $25.00 |

Web search, where enabled, is billed separately at $10.00 per 1,000
requests.

### The 272k cliff

Crossing 272,000 prompt tokens doubles input cost and raises output cost
by 50% **for the whole request**, not just the excess. A prompt that
drifts from 270k to 275k tokens gets roughly twice as expensive for five
thousand extra tokens of context. Keep analysis prompts well clear of
that boundary, or deliberately past it — never accidentally straddling it.

## Supported parameters

`tools`, `tool_choice`, `structured_outputs`, `response_format`, `seed`,
`reasoning`, `reasoning_effort`, `include_reasoning`, `max_tokens`,
`max_completion_tokens`.

`seed` is worth using for any analysis you may need to reproduce — for
example, regenerating a backtest summary that gets referenced in a
decision record. It reduces variation between runs; it does not make the
call deterministic, which is part of why LLMs stay out of the trade path.
