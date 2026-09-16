> **Provenance:** DeepSeek-assisted (`deepseek/deepseek-v4-pro-0813` via
> OpenRouter, 2026-09-14). Drafted by the model, reviewed and verified before
> adoption. Every numeric claim was re-derived independently; two did not
> survive and were corrected — see **Review record** at the end.
>
> Source supplied to the model: `planning/architecture/2026-09-14-structural-edge-inventory.md`.

# DEX market-making rejected — loss-versus-rebalancing

**Date:** 2026-09-14

**Decision:** Passive DEX market-making/liquidity provision on Solana spot at $5–$10 position sizes is rejected: expected loss-versus-rebalancing plus fixed costs exceeds any plausible fee income, and the adverse selection is structural.

**Provenance note:** The verdict was already recorded in `planning/architecture/2026-09-14-structural-edge-inventory.md` as *Rejected for adverse selection (LVR)*, but with no in-repo citation. This record supplies the missing reasoning and derivation. It is not a new investigation; it is the documentation that the inventory said was absent.

---

## 1. What LVR is

Loss-versus-rebalancing (LVR) is the expected shortfall of a passive AMM LP relative to a benchmark strategy that holds the same risky-asset exposure but rebalances continuously at the external market price, rather than trading with arbitrageurs at the pool’s stale price.

Formally, let \(S_t\) be the external market price and \(V(S_t)\) the value of the LP’s reserves as a function of price. If \(S_t\) follows a geometric Brownian motion with volatility \(\sigma\), the expected instantaneous LVR is

\[
\text{LVR}_t \, dt = \frac{\sigma^2}{2} S_t^2 \left(-V''(S_t)\right) dt
\]

where \(V''\) is the second derivative of the LP value with respect to price. The term \(-V''(S_t)\) is positive for an LP position because the LP’s value function is concave in price: the LP is short convexity.

For a constant-product market maker, \(V(S) = 2\sqrt{kS}\), so

\[
-S^2 V''(S) = \frac{V}{4}
\]

and therefore

\[
\text{LVR rate} = \frac{\sigma^2 V}{8}.
\]

This is the standard result: LVR scales with the square of volatility and with position value, and in the absence of fees it equals the arbitrageur’s profit. With a fee, the arbitrageur’s profit is \(\text{LVR} - \text{fees paid}\), and the LP’s net PnL is \(\text{fees} - \text{LVR}\).

Source for the formal framework: Milionis, Moallemi, Roughgarden, and Zhang, *Automated Market Making and Loss-Versus-Rebalancing* (2022), arXiv:2208.06046.

---

## 2. Why a passive LP is adversely selected, and why fees do not generally compensate

When the external price moves, an arbitrageur trades against the pool before the passive LP can adjust. The LP effectively sells the asset that just became underpriced and buys the asset that just became overpriced, at prices that are stale relative to the external market. That is adverse selection: the LP systematically trades on the wrong side of informed flow.

Fee income does not compensate in the general case. Let \(L\) be LVR over a period and \(F_{\text{arb}}\) be fees paid by arbitrageurs. An arbitrageur only trades if their profit after fees is nonnegative, so

\[
F_{\text{arb}} \le L.
\]

Therefore the LP’s net from arbitrage flow alone is

\[
F_{\text{arb}} - L \le 0.
\]

Positive net PnL requires uninformed flow fees \(F_{\text{noise}}\) large enough that

\[
F_{\text{noise}} + F_{\text{arb}} - L > 0.
\]

In many real pools, uninformed flow is not large enough to cover LVR, and published measurements show LVR exceeding total fee income. The burden is on anyone proposing LP to show that uninformed flow is sufficient; it cannot be assumed.

---

## 3. Published measurements of LVR on real AMM pools

The main published quantification is in Milionis et al. (2022), which measures LVR for Uniswap v2 and v3 pools over May 2021–April 2022.

- I recall that the paper reports LVR for the WETH-USDC 0.3% pool on the order of **$94 million** over that period, and that LVR exceeded fee income for many pools.
- **I am recalling this figure from memory and have not re-verified it against the paper.** Treat it as order-of-magnitude, not as a precise number to be quoted without checking.
- The paper’s qualitative finding — that LVR is a large, often dominant, cost for passive LPs — is established and is the relevant point for this decision.

No in-repo measurement exists. The inventory’s rejection was asserted without a citation, and this record is supplying the external reference rather than a new empirical study.

---

## 4. Concentrated liquidity does not change the conclusion

Concentrated liquidity increases fee income per unit of capital when the price is inside the LP’s range, but it also increases LVR per unit of capital because the position has more negative convexity inside the range. In the narrow-range limit, LVR per unit of capital is higher than for a constant-product pool.

Concentrated liquidity therefore concentrates adverse selection; it does not remove it. Active range management can in principle earn more, but that is a different strategy from passive LP. It requires frequent rebalancing and range adjustment, which is infeasible at $5–$10 because of the fixed costs discussed next.

Conclusion: concentrated liquidity does not reopen the decision.

---

## 5. Why this fails specifically at $5–$10, not merely in general

The general LVR problem is already enough to reject passive LP. At $5–$10, additional fixed costs make the position even less viable.

### Minimum viable position

There is no measured minimum-viable-position threshold in the repository. But at $5–$10, the fixed costs alone are a material fraction of any plausible fee income. The position would need to be much larger before fixed costs become negligible.

### Rent and transaction costs

- The fixed cost per round trip is given in the project context as **$0.0127**.
- At a $10 position, that is **0.127%** per round trip.
- At a $5 position, that is **0.254%** per round trip.

A 0.3% pool fee on one full turnover of the entire position is:

- $10 × 0.003 = **$0.03** at $10
- $5 × 0.003 = **$0.015** at $5

So a single round trip consumes **42%** of the gross fee income from one full turnover at $10, and **85%** at $5. Actual LP fee income is a fraction of pool fees, so the true figure is worse.

Solana token-account rent locks up capital. The rent-exempt minimum is **0.00203928 SOL per token account** and an LP position needs two, so **0.00407856 SOL**.

*Corrected on review.* The draft priced this at a SOL price of $20–$30 and called the result "0.8%–2.4% of a $5 position". Both halves were wrong. This repository's own measured SOL price over the 1h backtest window is **$87.53** (`research/backtests/2026-09-10_cost-model-correction.md`) — a hardcoded $200 was already caught here once as wrong by 2x, and $20–$30 repeats that class of error in the other direction. At $87.53 the lockup is **$0.357**: **7.1% of a $5 position**, **3.6% of a $10 one**. The draft's percentage was also arithmetically wrong for the size it named — $0.08 is 1.6% of $5, not 0.8%.

*Also corrected:* rent is a **capital lockup, not an expense**. The rent-exempt deposit is refunded when the token account is closed, so it does not consume the position the way a fee does. It still binds at this size — 7.1% of a $5 position sitting in a non-earning deposit — but the honest framing is opportunity cost, not a sunk $0.357. The draft treated it as a cost, which overstated the case.

### Rebalancing frequency

LVR is defined relative to a continuously rebalanced benchmark. At this position size, that benchmark is not executable.

Using 80% annualized volatility as an illustrative Solana spot assumption (not a measured value), the LVR rate for a constant-product pool is \(\sigma^2 V / 8\):

- At $10: \(0.8^2 \times 10 / 8 = \$0.8\) per year ≈ **$0.0022/day**
- At $5: \(0.8^2 \times 5 / 8 = \$0.4\) per year ≈ **$0.0011/day**

A single rebalance costs $0.0127, which is **5.8×** the daily LVR at $10 and **11.6×** at $5. So the rebalancing strategy that LVR benchmarks against cannot pay for itself at this size. The LP is stuck with the adverse selection.

---

## 6. Reopening condition

Reopen this decision only if we can demonstrate from point-in-time data that expected fee income from uninformed flow exceeds LVR plus fixed costs at the intended position size, with a margin.

Concretely: at $0.0127 per round trip, expected daily net fee income after LVR would need to be at least **$0.127** for one round trip to be no more than 10% of daily net. Under optimistic assumptions — 0.3% fee, full daily turnover, and zero LVR — that implies a position size on the order of **$40+**. Real LVR would push the required size higher. This is an illustrative threshold, not a measured edge.

Alternatively, if the venue introduces a mechanism that removes or rebates LVR — for example, oracle-based pricing or batch auctions — the adverse-selection cause would be removed and the decision should be reopened.

---

## Considered and rejected

- **Passive constant-product LP:** rejected because LVR is structural and fee income from arbitrage flow cannot exceed LVR.
- **Concentrated liquidity LP:** rejected because it increases LVR per unit of capital and requires active management that is infeasible at $5–$10.
- **Active rebalancing to capture the LVR benchmark:** rejected because a single rebalance costs several times the daily LVR at this position size.
- **Fee income as compensation:** rejected because no evidence exists that uninformed flow at this size is sufficient to cover LVR plus fixed costs, and the arbitrage participation constraint implies arbitrage fees alone cannot do so.

---

## Review record

Re-derived by hand before adoption, per `.claude/skills/openrouter-deepseek`,
which defines "reviewed" as re-derived rather than re-read.

**Checked and correct:**

| Claim | Verification |
|---|---|
| `V(S) = 2√(kS)` for a constant-product pool | From `x·y=k`, `S=y/x`: `x=√(k/S)`, `y=√(kS)`, `V = y + Sx = 2√(kS)` ✓ |
| `−S²V'' = V/4` | `V'' = −½√k·S^(−3/2)`, so `−S²V'' = ½√(kS) = V/4` ✓ |
| LVR rate `= σ²V/8` | `(σ²/2)·(V/4)` ✓ |
| LVR at σ=0.8: $0.0022/day at $10, $0.0011/day at $5 | `0.64×10/8 = 0.8/yr ÷ 365 = 0.002192` ✓ |
| Fixed cost 0.127% at $10, 0.254% at $5 | `0.0127/10`, `0.0127/5` ✓ — matches `research/trade_power.py` |
| One round trip is 42% / 85% of a full-turnover 0.3% pool fee | `0.0127/0.030 = 42.3%`, `0.0127/0.015 = 84.7%` ✓ |
| Reopening threshold "on the order of $40+" | `0.127/0.003 = $42.33` ✓ |
| arXiv:2208.06046 = Milionis, Moallemi, Roughgarden & Zhang | Correct identifier ✓ |

**Corrected:**

1. **Rent as a share of position size** — arithmetically wrong (0.8% quoted for
   a $5 position when the figure given was 1.6%), and priced at a SOL price
   this repository has already measured at roughly 3x higher.
2. **Rent characterised as a cost** — it is a refundable deposit, so a lockup.
   The correction makes that paragraph weaker in kind and larger in magnitude.
3. **"about 6× / 12×"** replaced with the derived 5.8× / 11.6×.

**Left flagged, not verified:** the $94M WETH-USDC LVR figure attributed to
Milionis et al. The model flagged it as unverified recall and it stays flagged.
It is not load-bearing: the verdict rests on the participation constraint
`F_arb ≤ L`, which is an identity about who trades and why, not on any
particular pool's measured total.

**Not re-derived, because it is not arithmetic:** the concentrated-liquidity
argument in §4. It is a claim about the sign of convexity, consistent with the
framework in §1. A reader who wants to dispute this verdict should dispute it
there, not in the numbers.
