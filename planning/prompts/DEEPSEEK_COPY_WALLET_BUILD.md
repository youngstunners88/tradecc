# DeepSeek work order — copy-wallet pipeline (TradeCC)

> **Provenance:** Human/Claude-authored work order for
> `deepseek/deepseek-v4-pro` via OpenRouter. DeepSeek implements; Claude Code
> and the human review before merge. Numeric claims in this file that cite
> prior research must be re-checked against the named scripts, not trusted
> from this prompt alone.

## Why you are doing this

TradeCC is a Python Solana trading bot running at $5–$10 position sizes,
paper-only behind an enforced validation gate. Directional EMA/RSI momentum is
**closed**. Live send exists and is **gated**. Copy-trading is **Blocked** in
the structural-edge inventory — not on economics, but because free RPC
enumeration of a point-in-time-clean wallet universe runs at ~0.41 tx/s.

Bitquery removes that crawl bottleneck. Your job is a **practical paper
pipeline**: extract a frozen wallet universe, rank it on a training window,
emit `TradeIntent`s from lagged source fills, and run them through the
existing risk engine in paper and backtest.

You do **not** unlock live mode. You do **not** put a model on the tick path.

## Non-negotiable — stop and say so rather than violate these

1. Never invent, request, or write a private key, seed phrase, or `.env`.
2. Read `BITQUERY_API_KEY` and `OPENROUTER_API_KEY` **only** from
   `os.environ`. No file-path loader, no CLI flag, no default value.
3. Do not add a `send` or `sign` path, and do not import `solders`.
   Execution already has Stage 6c/6d behind a gate.
4. Do not use GMGN/Fomo leaderboards, or any all-time-PnL-to-today list, as
   the candidate set.
5. Money is `decimal.Decimal`, never `float`.
6. Unknown config keys are an error, never an ignored field.
7. Do not touch `src/core/gate.py` or `ops/live-gate.json`.
8. Every new research `.md` starts with the provenance header from
   `.claude/skills/openrouter-deepseek/SKILL.md`.

If you find yourself about to violate one of these to make something work,
that is a signal the design is wrong. Say which rule and why, and stop.

## What you are given instead of the source tree

**You will not be sent `src/`.** The project's boundary keeps the bot's source
out of model context and that rule has no exceptions. Everything you need is
transcribed in `research/copy_wallet/INTERFACE_BRIEF.md`, which you **will**
be sent: the `Strategy` protocol, `Candle` / `Signal` / `SignalType`, the
registry pattern, `StrategyConfig`, and the cost API.

Read it carefully. §1 describes a real design trap and its required
resolution — see "The hardest part" below.

## The hardest part, stated up front

`Strategy.generate(token_mint, candles) -> Signal` is contractually **a pure
function of closed candles**: same inputs, same output, no I/O, no clock, no
randomness. The validation gate depends on that property.

Copying needs source-wallet fills, and the obvious implementation fetches them
inside `generate()`. **That is wrong** and will be rejected. It makes the
strategy non-replayable, so the backtest would measure something other than
what runs.

Required shape: the fill log is **frozen, filtered to the allowlist, sorted,
and injected at construction**. `generate()` decides eligibility by comparing
`fill.timestamp + lag_seconds` against `candles[-1].timestamp`, consulting
nothing later. That comparison *is* the look-ahead boundary and *is* the lag
model. A lag applied when fetching has not been applied at all.

## Build these

### A. Decision record
`planning/decisions/2026-09-16-reopen-copy-trading-via-bitquery.md`

Status: **conditional reopen of data collection only.** Protocol frozen
before any result is seen.

Hypothesis: following a PIT-clean allowlist of Solana wallets can produce
positive net expectancy at $5–$10 after calibrated costs and ≥60s lag, under
the backtesting replication rule.

Freeze in the record — and **leave the dates as `TBD` placeholders**; fill
them only after the extractor has run and printed the actual available
history. Do not invent a date range:

- Universe method: Bitquery DEX trades against named pool(s), selection window
- Ranking metric: training-window realised net PnL ÷ max drawdown (fixed, not searched)
- N wallets: top 3 (cap)
- Lag: 60 seconds
- Folds: expanding 3-fold, matching the 2026-09-10 walk-forward decision
- Benchmark: buy-and-hold of the same cash
- Stopping rule: Phase A (this ranking, no parameter grid) fails replication → stop

State plainly that a single ranking metric, chosen in advance and not searched,
is the point: a grid over metrics would manufacture a winner from noise.

### B. Bitquery client (research only)
`research/copy_wallet/bitquery_client.py`

- GraphQL over HTTP. **Verify the current endpoint and auth header against
  Bitquery's live documentation — do not guess from memory.** If either is
  uncertain, put it in a single named constant with a `# verify against docs`
  comment rather than scattering a guess through the file.
- Functions:
  - `dex_trades_for_pool(pool: str, start: datetime, end: datetime) -> list[dict]`
  - `dex_trades_for_trader(address: str, start: datetime, end: datetime) -> list[dict]`
- Pagination, bounded retry with backoff, an explicit timeout on every request.
- **No secrets in exceptions or logs.** Redact any URL that could carry a token.
- Offline tests against a fake transport. The unit suite must pass with no
  network available — mirror how `src/execution` is tested (a transport
  protocol with an injectable fake, so no ambient client can make a real
  request by accident).

### C. Universe extractor
`research/copy_wallet/extract_universe.py`

- Candidates = unique trader/account addresses appearing in pool trades
  **inside the selection window only**.
- Drop known **program** IDs via a static allow/deny list. Never drop an
  address for being unprofitable — that is the bias the method exists to
  avoid, and doing it silently would invalidate everything downstream.
- Emit the universe schema below. **Do not rank in this script.**

```json
{
  "schema": "tradecc.universe.v1",
  "selection_window_start": "ISO-8601",
  "selection_window_end": "ISO-8601",
  "pools": ["<pool_address>"],
  "chain": "solana",
  "source": "bitquery",
  "generated_at": "ISO-8601",
  "extractor_commit": "<git sha>",
  "filters": ["performance_blind only"],
  "candidates": ["<address>", "..."]
}
```

### D. Position book and ranking
`research/copy_wallet/positions.py`, `research/copy_wallet/rank.py`

- Reconstruct per-wallet, per-mint positions from buy/sell prints
  (balance-delta, or side + amount from Bitquery's DEXTrade fields).
- `rank.py` reads the universe plus the **training** window and writes
  `research/copy_wallet/allowlist.json`:

```json
{
  "schema": "tradecc.allowlist.v1",
  "universe": "research/universes/...",
  "train_start": "...",
  "train_end": "...",
  "metric": "net_pnl_over_max_dd",
  "wallets": [{"address": "...", "metric": "...", "n_trades": 0}]
}
```

- A wallet with too few trades to rank must be **excluded explicitly**, not
  ranked on two lucky fills. State the minimum in the decision record.

### E. The strategy
`src/strategy/strategy_copy.py`, registered as `"copy"`.

- `CopyStrategy.from_params(params: dict) -> CopyStrategy`, validating its own
  params and raising on anything unrecognised.
- Construction takes the frozen fill log and `lag_seconds` (default 60).
- `generate()` is pure, as above. Put the source wallet address and source
  fill timestamp into `Signal.metadata` as strings, so any signal is traceable
  to the fill that caused it.
- A feed protocol for later live/paper wiring is fine to define:

```python
class CopyFeed(Protocol):
    def source_fills_since(self, ts) -> list[SourceFill]: ...
```

but nothing on the tick path may call it inside `generate()`.

### F. Tests
`src/tests/test_strategy_copy.py`, `src/tests/test_copy_universe_schema.py`

Cover at minimum:

- **Look-ahead**: a fill at `T` produces no signal at a candle whose timestamp
  is `< T + lag`, and does produce one at `>= T + lag`. This is the test that
  matters most; write it first.
- Purity: the same fills and candles produce the same signal twice.
- Schema round-trip and rejection of a universe whose candidates fall outside
  the selection window.
- Registry: `build_strategy` returns `CopyStrategy` for `"copy"` and raises on
  a typo.
- An unknown param is rejected rather than ignored.

## How to verify before you hand back

```bash
PYTHONPATH=src python -m pytest src/tests/test_strategy_copy.py src/tests/test_copy_universe_schema.py
PYTHONPATH=src python -m pytest          # the whole suite must stay green
PYTHONPATH=src python -m cli paper --once --config config.paper.copy.yaml
```

## What to hand back

A unified diff or complete file contents per path, plus a short note listing:
anything you could not verify (especially the Bitquery endpoint and header),
any assumption you made about fields, and anything in this work order you
think is wrong. **The last item is genuinely wanted** — this project has paid
twice for numbers nobody re-derived, and a work order is no more trustworthy
than a model output.

Do not report a file as complete if you did not write it in full.
