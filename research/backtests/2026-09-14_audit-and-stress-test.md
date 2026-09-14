# Deep audit + stress test — 2026-09-14

Run after locking the 8% drawdown threshold, across the whole `src/` tree.
Six defects found, all fixed. **Two of the three most serious were found by
running the code, not by reading it** — which is the finding about the process
rather than the code.

## What was audited

| Pass | Method | Result |
|---|---|---|
| Float leakage in the money path | grep for `float(` outside tests | Clean — no `float()` anywhere in money or signal code |
| Broad exception handling | grep `except Exception` | Two, both deliberate and documented (telemetry, alerts) |
| Division sites | 25 sites read, then probed with adversarial inputs | 2 defects (below) |
| Risk controls | 8 adversarial intents + corrupted state | All 8 correctly vetoed |
| Coverage | `pytest --cov` | 96%; closed the gap in the paper exit path |
| Security scripts | both repo scanners | 0 critical, 0 high |
| Risk bypass | every `simulate()` traced to an `approve()` | No entry path bypasses risk |
| Stress | 400 hostile ticks × 6 market scenarios | 2 defects (below) |

## Findings

### 1. CRITICAL — quote prices were reciprocal on the SELL leg

`in/out` is quote-asset-per-token only on a BUY. A SELL sends the token, so the
same expression yielded the reciprocal. Entry comes from a BUY quote, exit from
a SELL quote. Against a Jupiter-shaped provider with SOL pinned at $100 on both
legs:

```
entry recorded = 0.1002    (USDC atomic per SOL atomic)
exit  recorded = 10.0200   (SOL atomic per USDC atomic)
=> gross P&L on $10 at an UNCHANGED price: $990.00
```

Two further consequences of the same root cause: prices were *atomic ratios*,
so `entry_price` (0.1002) was compared against a candle close (96) to fire
stop-loss and take-profit — neither control could work, and nothing raised.
And `Quote.token_mint` was always the output mint, which on a SELL is the quote
asset.

**Why the suite was green:** `MockQuoteSource` returned one orientation for
both sides and applied BUY-direction slippage to SELLs, so the test seam could
not express the error. No test crossed the real client and the P&L arithmetic.

### 2. HIGH — a silent 0% drawdown

`max_drawdown_pct` skipped any point where the running peak was non-positive,
so `[0, -5]` and `[-10, -20]` both reported **0%**. That number is what the
gate compares against the 8% threshold, where a silent 0 clears anything. Same
shape as the persisted-`Infinity` bug: a safety comparison satisfied by a value
that means "no answer". Unreachable on the normal path (capital is validated
positive), so it now raises.

### 3. HIGH — modelled cost of 38,880% of position size, approved

Found by stress test. Fees are lamports converted at a SOL price read from the
market, and nothing sanity-checked the result. At a corrupted price the first
trade's modelled cost reached **$3,888 on a $10 position** and every control
approved it — size was $10, slippage was in band, the breaker was clean, so
nothing had grounds to object. The `huge-price` scenario lost **$4,272 on a
$100 account** whose per-trade stop is $0.50.

Fixed with a fee-to-size ceiling (`risk/fees.py`, default 25%) rather than a
plausible-price band: a band is a market assumption that goes stale, and this
repo already shipped a hardcoded `sol_price_usd: 200` that was wrong by 2x
within days. Entries are vetoed; **exits never are** — refusing to close a
position because closing looks expensive leaves the bot holding risk it decided
to shed. Wired into both the paper trader and the backtest runner, since both
produce the expectancy the gate reads.

### 4. HIGH — the paper loop died on any non-`ProviderError` exception

`tick()`'s docstring promised "an exception escaping here would end the
session", but it caught only `ProviderError`. The stress run died at tick 14 of
400 in every scenario. Reachable in a month of unattended running: `OSError`
from the candle cache on a full disk, `JSONDecodeError` from a truncated cache,
`ValueError` from a zero price or a size rounding to no atomic units.

### 5. MEDIUM — a false urgent FINGERPRINT MISMATCH on every fresh install

Writing the 8% threshold raised an urgent alert whose body asserted "the
approval on file was granted against a different configuration" — on a gate
file with no approval at all. Absence was being read as mismatch. A gate that
cries wolf gets worked around.

### 6. LOW — bare `DivisionByZero` from `ClosedTrade.gross_pnl_usd`

Inconsistent with `Position`, which raises a descriptive `ValueError`.

## Stress results (400 ticks × 6 scenarios, after fixes)

Providers fail 18% of ticks (503s, resets, empty pages) and quotes fail 8%.

| Scenario | Ticks | Trades | Net $ | Max DD % | Provider errors |
|---|---|---|---|---|---|
| flat | 400 | 0 | 0.0000 | 0.00 | 71 |
| crash −70% | 400 | 0 | 0.0000 | 0.00 | 71 |
| melt-up | 400 | 0 | 0.0000 | 0.00 | 71 |
| whipsaw | 400 | 5 | +4.4593 | 0.00 | 81 |
| near-zero price | 400 | 5 | +0.7926 | 0.03 | 81 |
| huge price | 400 | **0** | 0.0000 | 0.00 | 82 |

No crashes. `huge-price` went from −$4,272 to refusing to trade at all.

The whipsaw and near-zero profits are **not evidence of edge** — they are
synthetic series built to stress arithmetic, and momentum remains closed per
`planning/decisions/2026-09-12-kill-ema-rsi-momentum.md`. The only claims here
are that the loop survives and the controls fire.

The harness is kept at `research/stress_paper_loop.py`. Re-run it after changes
to the paper loop, cost model, or risk engine.

## Evidence status

**No recorded result is invalidated.** No paper run has started, so nothing was
measured under the broken price arithmetic. The real cached-data backtest
re-runs unchanged after the fixes (23 trades, NET −1.7785, no entries blocked by
the new ceiling), confirming the fee check does not fire on legitimate trades.

Tests: 465 → 479.
