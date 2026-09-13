# Capital-range sensitivity — every recorded negative at $5 / $10 / $25 / $100

**Date:** 2026-09-13
**Harness:** `research/capital_sensitivity.py`
**Rule:** `planning/decisions/2026-09-13-capital-range-sensitivity.md`, committed
at `26ad0f6` **before this harness existed** and before any number was computed.

## Verdict

**Raising capital does not rescue anything.** Five rounds re-run at four sizes;
one genuine flip found; the flip fails on criteria money cannot touch. Under
rule 2, every result still negative at $100 means the signal has no edge — and
that conclusion is not available for reinterpretation later.

## The finding that settles it

Net P&L is an exact linear function of position size:

> **net(size) = size × g − F**

where `g` is gross return per dollar and `F` is total fixed cost across the run.
Fitting `g` and `F` from **only the $5 and $100 points**, then predicting the
untouched middle two:

| Round | $5 | $10 predicted / actual | $25 predicted / actual | $100 | g per $ | F |
|---|---|---|---|---|---|---|
| Defaults, 1h | +0.1356 | +0.5815 / **+0.5815** | +1.9192 / **+1.9192** | +8.6079 | 0.089182 | $0.3103 |
| Sweep held-out, 4h | −0.1280 | −0.0769 / **−0.0769** | +0.0764 / **+0.0764** | +0.8429 | 0.010220 | $0.1791 |
| Phase B, 1h | +0.5922 | +1.2928 / **+1.2929** | +3.3947 / **+3.3947** | +13.9041 | 0.140125 | $0.1084 |

Maximum error across nine predictions: **0.000074**. The size effect is
*entirely* fixed-fee drag, tracking the cost curve as rule 1 requires.

**And that is precisely why capital does not help.** Money buys back `F` —
between $0.11 and $0.31 across a whole run — and changes nothing else. What
remains is `g`, and `g` is the problem:

| Size | Strategy per $ (1h defaults) | Buy-and-hold per $ | Captured |
|---|---|---|---|
| $5 | 0.02712 | 0.37392 | **7.3%** |
| $10 | 0.05815 | 0.39002 | 14.9% |
| $25 | 0.07677 | 0.39968 | 19.2% |
| $100 | 0.08608 | 0.40450 | **21.3%** |

As size → ∞ the strategy asymptotes at 0.0892 per dollar against buy-and-hold's
~0.405. **At infinite capital it captures roughly 22% of simply holding SOL.**

## Round 1 — sweep, held-out

The one genuine sign change in the whole exercise: **4h flips positive at $25
(+$0.0764) and $100 (+$0.8429)**, on held-out data.

It satisfies rule 1 exactly (zero prediction error above). It then fails rule 3:

- **3 trades**, against a floor of 12.
- Captures **1.0% of buy-and-hold at $25, 2.7% at $100** (+$0.84 vs +$31.41).

Three trades is the sweep's original "+$0.47 on 3 trades" pathology reappearing
at a larger size. A fee-driven flip is still a flip into a failing result.

| Size | 1h held-out | 4h held-out | 15m held-out |
|---|---|---|---|
| $5 | −0.3940 | −0.1280 | −0.6729 |
| $10 | −0.5343 | −0.0769 | −1.0110 |
| $25 | −0.9553 | **+0.0764** | −2.0255 |
| $100 | −3.0603 | **+0.8429** | −7.0979 |

1h "beats buy-and-hold" at every size only because buy-and-hold is *also*
negative on that window. All three intervals run on 3, 3 and 9 trades.

## Round 2 — cost-corrected, default parameters

| Size | 1h | 4h | 15m |
|---|---|---|---|
| $5 | +0.1356 | −0.4675 | −1.1448 |
| $10 | +0.5815 | −0.5494 | −1.7785 |
| $25 | +1.9192 | −0.7949 | −3.6798 |
| $100 | +8.6079 | **−2.0229** | **−13.1860** |

1h was already positive at $10 and stays positive — no verdict changed. 4h and
15m stay negative at every size and get *worse* in absolute dollars. Every
interval loses to buy-and-hold at every size.

Drawdown on the one positive case, absolute beside percentage as required:
1h **0.96% / $0.48** at $5 → **0.53% / $5.34** at $100.

## Round 3 — walk-forward Phase A

`replicated = False` in all twelve interval×size combinations.

| Size | 1h pooled | top fold | 4h pooled | 15m pooled |
|---|---|---|---|---|
| $5 | +0.1356 | 151% | −0.4675 | −1.1448 |
| $10 | +0.5815 | 82% | −0.5494 | −1.7785 |
| $25 | +1.9192 | 68% | −0.7949 | −3.6798 |
| $100 | +8.6079 | **63%** | −2.0229 | −13.1860 |

Concentration improves with size but never clears the 60% bar. Money shrinks
the concentration failure and does not fix it.

## Round 4 — walk-forward Phase B

| Size | 1h pooled / trades / top fold | 4h pooled / trades | 15m pooled / trades |
|---|---|---|---|
| $5 | +0.5922 / 10 / 64% | +0.5426 / 7 | −0.5095 / 14 |
| $10 | +1.2929 / 10 / 61% | +1.1498 / 7 | −0.6383 / 10 |
| $25 | +3.3947 / 10 / 59% | +2.9715 / 7 | −2.4490 / 14 |
| $100 | +13.9041 / 10 / **58%** | +12.0796 / 7 | −9.2532 / 14 |

**Trade counts are identical at every size** — 1h: 10, 10, 10, 10. 4h: 7, 7, 7,
7. The floor is 12. Position size cannot manufacture trades, and the trade floor
is the criterion Phase B fails at every size. The per-fold parameter picks are
also identical across sizes, confirming the search is size-invariant.

(The $10 1h figure of +1.2929 reproduces the post-audit re-measurement in
`2026-09-10_walk-forward-phase-b.md` exactly — the harness is reproducing the
recorded result, not inventing a new one.)

## Round 5 — cross-sectional momentum

Nothing passes at any size. Concentration is the binding failure throughout.

| Size | best combination | pooled | top fold | verdict |
|---|---|---|---|---|
| $5 | L=30,N=1 | +3.4337 | 89% | fail: spread, trades |
| $10 | L=7,N=1 | +13.4381 | 94% | fail: spread |
| $25 | L=7,N=1 | +36.5558 | 90% | fail: spread |
| $100 | L=7,N=1 | **+152.1446** | **88%** | fail: spread |

**+$152 at $100** is the single best argument in this report for writing the
interpretation rule first. It is the same 2026-09-12 failure at a bigger size:
one fold carrying the result.

## Round 6 — regime detection

**Size-invariant; stated, not re-run**, per rule 5. Its refutation was that 1
trade in 59 entered a trend-labelled bar. Entry timing does not depend on
position size, so the trend arm is empty at $5 and empty at $100. Four
identical empty arms would have dressed a non-result as coverage.

## What this closes

Under **rule 2**, every result still negative at $100 — 1h held-out, 15m in both
rounds, 4h at defaults, all of Phase A, all six cross-sectional combinations —
means **the signal has no edge**. Not "needs more capital". At $100 the hurdle
is 0.23% against 0.47% at $5: there is almost no fee relief left to buy, and
the two positive cases are positive for reasons that fail every other bar.

The capital-raise path is closed on evidence.

## What this does not close

- It does not speak to strategies never tested. It says the *tested* ones do
  not become viable with more money.
- It does not authorise trading at any size. The gate is unchanged.
- It does not change the bot's configured position size. `RiskConfig` defaults
  and the soft ceiling are untouched; the $25 and $100 runs set
  `position_size_override_ack` explicitly, as CLAUDE.md rule 6 intends.
