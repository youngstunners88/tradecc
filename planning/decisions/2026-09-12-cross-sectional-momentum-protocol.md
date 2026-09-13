# Decision: Cross-Sectional Momentum Protocol (2026-09-12)

## Context

Single-pair EMA/RSI momentum has been rejected across four rounds, and
buy-and-hold beat it on every interval
(`research/backtests/2026-09-11_momentum_lookahead-audit-and-buy-hold-baseline.md`).
External research proposed cross-sectional (basket) momentum as the one
remaining momentum variant worth testing: ranking a universe and holding
the top slice diversifies away the single-pair blow-up risk.

This record fixes the protocol **before the harness is built and before
any parameter is tried**. Capital is unchanged at **$10 total** — the
research's own estimate is that basket momentum needs ~$100+, so a
cost-driven failure here is an expected outcome, not a reason to raise
capital.

The only thing inspected beforehand is **what the data can support**,
which is a property of the data source rather than of any strategy
result. That inspection turned out to be decisive and is recorded below.

## What the data actually supports

Probed GeckoTerminal's top Solana pools (5 pages, deepest pool per base
token, 2026-09-12). Two facts govern everything that follows.

**1. Volume-ranked "top pools" are not a tradeable universe.** The list
is dominated by micro-liquidity names — WOTF at $2,387 reserves against
$2.0M daily volume — and several report **$0 reserves against $135M
volume**. Ranking a universe by volume would select almost entirely for
these. Liquidity, not volume, is the filter.

**2. History, not liquidity, is the binding constraint.** Daily-bar
depth across the most liquid tokens:

| Token | Liquidity | Daily bars |
|---|---|---|
| SOL / USDC | $29.1M | **184** |
| PUMP / USDC | $20.4M | **184** |
| RAY / SOL | $3.3M | **184** |
| SPYx / USDC | $2.9M | **184** |
| MET / USDC | $2.5M | **184** |
| ORE / USDC | $0.48M | **142** |
| Starbucks / SOL | $7.2M | 1 |
| STONK / SOL | $4.9M | 14 |
| EMBER / SOL | $0.82M | 4 |
| GTA 6 / SOL | $0.69M | 2 |
| HOOD / SOL | $1.27M | 1 |

Lowering the liquidity floor does **not** widen the universe: the
additional names are days old. At any floor, the set with usable history
is the same handful. This removes the fork between "few liquid names" and
"many illiquid names" — the second option does not exist in this data.

## The universe (fixed here)

**Rule:** USDC-quoted pools, deepest pool per base token, ≥ 120 daily
bars of history, ≥ $250k reserves. Resolved as of 2026-09-12:

**SOL, PUMP, SPYx, MET, ORE — five tokens.**

**RAY is excluded despite qualifying on liquidity and history** because
its deepest pool is SOL-quoted. Converting it to USD is arithmetically
exact only if timestamps align perfectly, and a silent misalignment would
corrupt precisely the cross-sectional ranking the test depends on. On an
already-underpowered test, one extra name does not justify a new failure
mode. This exclusion is fixed now — it may **not** be revisited after
seeing results.

## Strategy specification (fixed here)

- **Interval:** daily (`1d`). Matches the literature's weekly/monthly
  rebalance convention; 184 bars is the most calendar time available.
- **Signal:** trailing total return over a lookback `L`, ranked across
  the universe.
- **Hold:** the top `N` names, equally weighted.
- **Rebalance:** every 7 days.
- **Grid (the entire search space):** `L ∈ {7, 14, 30}` days,
  `N ∈ {1, 2}`. Six combinations. The grid is small deliberately — with
  this little data, a wide search would fit noise, and the sweep already
  demonstrated what that produces.
- **Capital:** **$10 total**, split equally across held positions
  (`$10/N`). Total exposure never exceeds $10, so CLAUDE.md rule 6 holds
  without an override. Note this makes per-position size $5 at `N=2`.
- **Costs:** the existing `CostModel`, unchanged. ATA rent is charged
  once per mint across the whole run, as in the single-pair runner.

## Benchmarks (both mandatory)

Per the stricter bar the external research proposes, beating zero is not
the test. The strategy must beat **both**, net of identical costs:

1. **Buy-and-hold SOL** over the same window.
2. **Equal-weight buy-and-hold basket** of the same five tokens.

The second matters more: it isolates whether *ranking* adds anything over
simply owning the universe. A strategy that beats SOL only because the
basket beat SOL has demonstrated nothing about momentum.

## Pass criteria (locked)

All of the following:

1. Net > 0 in ≥ 2 of 3 walk-forward folds.
2. Pooled net > 0.
3. No single fold contributes > 60% of pooled net.
4. Pooled trade count ≥ 12.
5. **Beats buy-and-hold SOL**, net, pooled.
6. **Beats the equal-weight basket**, net, pooled.

Any failure → it did not pass. Write it up and stop: no widening the
grid, no adding names, no changing the rebalance cadence, no re-picking
the universe.

## Known limitation, stated before the result

**The ≥2-distinct-regimes requirement almost certainly cannot be met.**
184 daily bars is ~6 months of one asset class, which is plausibly a
single regime. This test therefore cannot satisfy criterion (5) of the
research's proposed bar in its strongest form, and **a pass here would
mean "not refuted on six months of data", never "confirmed".**

A five-name universe is also thin for a cross-sectional strategy: holding
the top 1–2 of 5 is closer to a concentrated bet than to the diversified
ranking the literature studies, where universes run to dozens or hundreds
of names. The diversification argument that motivated this test is
therefore only weakly available here.

Both limitations are recorded now so that neither is discovered after the
fact and used to reinterpret a result in whichever direction suits it.

## What this record forecloses

- Widening the universe, the grid, or the rebalance cadence after seeing
  results.
- Re-admitting RAY, or any SOL-quoted pool, post-hoc.
- Raising capital above $10 in response to a cost-driven failure.
- Reporting a pass on criteria 1–4 while omitting 5 and 6.
- Treating a pass as gate-clearing: the live gate additionally requires
  30 days of paper trading and a pre-set drawdown threshold.
