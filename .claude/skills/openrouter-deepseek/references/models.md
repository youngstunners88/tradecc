# DeepSeek model snapshot for TradeCC research

Verified against `https://openrouter.ai/api/v1/models` on **2026-09-14**.
A snapshot, not a source of truth — the catalogue changes, and a model ID
that no longer exists fails at runtime. Re-verify before relying on a row.

## Refreshing this file

```bash
curl -sS https://openrouter.ai/api/v1/models -o /tmp/models.json

python3 -c "
import json
for m in json.load(open('/tmp/models.json'))['data']:
    if 'deepseek-v4-pro' in m['id']:
        p = m['pricing']
        print(m['id'], '| ctx', m['context_length'],
              '| maxout', (m.get('top_provider') or {}).get('max_completion_tokens'),
              '| in \$%.3f/M' % (float(p['prompt']) * 1e6),
              '| out \$%.3f/M' % (float(p['completion']) * 1e6))
"
```

The endpoint needs no authentication, so this is safe to run any time and
consumes no credit. Do **not** add `OPENROUTER_API_KEY` to this command.

## Verified models

| Model ID | Context | Max output | Modality |
|---|---|---|---|
| `deepseek/deepseek-v4-pro` | 1,048,576 | 393,216 | text → text |
| `deepseek/deepseek-v4-pro-0813` | 1,048,576 | 393,216 | text → text |
| `deepseek/deepseek-v4-pro-0813:batch` | 1,048,576 | 943,718 | text → text |

`deepseek-v4-pro` is a **floating alias**. `-0813` is the dated snapshot it
currently points at. Research that a decision record will cite should use
the pin, so the run can be reproduced after the alias moves.

Neither accepts images or files — `gpt-6-astra` does, these do not. Convert
documents to text before sending.

## Pricing (USD per million tokens)

| Model | Input | Output | Cache read |
|---|---|---|---|
| `deepseek/deepseek-v4-pro` | $1.600 | $3.200 | $0.1350 |
| `deepseek/deepseek-v4-pro-0813` | $0.579 | $1.738 | $0.0184 |
| `deepseek/deepseek-v4-pro-0813:batch` | $0.660 | $1.980 | — |

Two things follow:

- **The pin is ~2.8× cheaper on input and ~1.8× cheaper on output** than the
  floating alias, for the same weights. Cache reads are ~7× cheaper.
- **The `:batch` variant is more expensive than the pin it batches**, unlike
  most `:batch` suffixes on OpenRouter. It is not a cost optimisation here.
  Use it only if asynchronous submission is what you want.

There is **no long-prompt price cliff** on these models — the rate is flat
across the full 1.05M context, unlike `openai/gpt-6-astra`, which doubles
input cost above 272k prompt tokens. That flat curve is the reason
heavy-context research routes here.

## Supported parameters

Both Pro variants: `tools`, `tool_choice`, `structured_outputs`,
`response_format`, `seed`, `stop`, `reasoning`, `reasoning_effort`,
`include_reasoning`, `logprobs`, `top_logprobs`, `logit_bias`,
`temperature`, `top_p`, `top_k`, `min_p`, `frequency_penalty`,
`presence_penalty`, `repetition_penalty`, `max_tokens`.

`deepseek-v4-pro` additionally accepts `max_completion_tokens`; the `-0813`
pin does not, so scripts that target both should use `max_tokens`.

## Cheaper siblings (not adopted)

`deepseek-v4-flash` ($0.075/$0.150) and `deepseek-v4.1-flash`
($0.150/$0.600) are an order of magnitude cheaper again. They are not the
default for this project's research work: the tasks routed here are
derivations where a wrong number is worse than an expensive one. If a task
is bulk summarisation rather than derivation, a Flash variant is the right
call — and the same provenance and review rules apply to it.
