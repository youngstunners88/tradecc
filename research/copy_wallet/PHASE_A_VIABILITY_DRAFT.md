> **Provenance:** DeepSeek-assisted (`deepseek/deepseek-v4-pro-0813` via OpenRouter, 2026-09-16).
> Drafted by the model, **reviewed and verified before adoption**. Every
> numeric claim was re-derived independently and **all of them held** — see
> **Review record** at the end for the script and the figures.
>
> **Verdict: this hypothesis does not clear the `edge-viability-check` gate.**
> Per `CLAUDE.md`, that means no backtest gets built on it as written.
>
> Sources supplied to the model: `.claude/skills/edge-viability-check/SKILL.md`, `.claude/skills/copy-wallet-bitquery/SKILL.md`.

## Basis and inputs

**Given**
- Fixed cost per round trip: **$0.0127**, which does not scale down.
- Break-even gross at $5: **0.254%**.
- Break-even gross at $10: **0.127%**.
- Detection sample size:  
  \[
  n = (z_\alpha+z_\beta)^2\left(\frac{\sigma}{\mu}\right)^2
  \]
  with leading constant **7.8489** at 95% confidence / 80% power.

**Assumed / inferred**
- I treat this as a **structural** hypothesis: profit would come from mechanically copying an allowlist, not from predicting direction. Step 4 therefore asks **frequency × payoff**, not required direction accuracy.
- Let \(c\) = fraction of the source wallet’s move retained after the **60s copy lag**. \(c\) is unknown and must be estimated. It is a central variable for this gate.
- Let \(\sigma\) = per-round-trip standard deviation of net returns, and \(\mu\) = expected net edge per round trip.
- I use the project’s cross-asset noise ratio \(\sigma/E|move| \ge 1.33\) as a **lower-bound assumption** for per-trade noise. This is an inference from the edge-budget text, not a script run. If actual \(\sigma\) is higher, the gate fails harder.
- I use **30 days** as the default Phase A window because that is the project’s stated gate window, and also show 90-day sensitivity.

All trade counts below are **copyable round trips**, not raw allowlist trades. A wallet trade that cannot be filled 60s later is not a valid round trip and must not be counted.

---

## Step 1 — Claimed edge

The hypothesis says: *“following a point-in-time-clean allowlist of top-3 Solana wallets, with 60s copy lag, at 5–10 dollar positions, produces positive net expectancy after costs.”*

That is an existence claim, not an edge. It does not state a gross % per round trip.

For the gate, the claimed edge must be the **post-lag gross edge**, because the 60s delay means the copied trade does not get the source wallet’s entry.

Define:

\[
\mu_{\text{post-lag}} = c \cdot E_{\text{source}}
\]

where \(E_{\text{source}}\) is the source wallet’s expected gross move per trade and \(c<1\).

The hypothesis gives no number for either \(E_{\text{source}}\) or \(c\).

**Step 1 answer: FAIL / not ready.**  
A claim of “positive net expectancy” is not a quantifiable edge. The gate cannot proceed on that basis.

---

## Step 2 — Break-even clearance

Given:

\[
C = \$0.0127
\]

Break-even at $5:

\[
\frac{0.0127}{5} = 0.00254 = 0.254\%
\]

Break-even at $10:

\[
\frac{0.0127}{10} = 0.00127 = 0.127\%
\]

The copied trade enters 60s late, so it captures only \(c\) of the source move. Therefore the **required source edge before the lag** is:

\[
E_{\text{source}} > \frac{\text{break-even}}{c}
\]

If \(c<1\), the source wallet must have a larger gross edge than the break-even hurdle.

| Lag retention \(c\) | Required source edge at $5 | Required source edge at $10 |
|---:|---:|---:|
| 1.00 | 0.254% | 0.127% |
| 0.50 | 0.508% | 0.254% |
| 0.25 | 1.016% | 0.508% |
| 0.10 | 2.540% | 1.270% |
| 0.05 | 5.080% | 2.540% |

A 60s lag in actively traded Solana wallets almost certainly means \(c<1\), likely much less than 1 because much of the move can occur in the first minute. That raises the required source edge well above the bare break-even hurdle.

**Step 2 answer: FAIL / unproven.**  
The hypothesis does not state a post-lag edge large enough to clear break-even. The 60s lag makes the required source edge larger than the stated break-even, and the required \(c\) is unknown.

---

## Step 3 — Detection clearance

Detection sample size:

\[
n = 7.8489\left(\frac{\sigma}{\mu}\right)^2
\]

Using the assumed noise lower bound \(\sigma \ge 1.33 E|move|\) and the retained edge \(\mu \approx c E|move|\):

\[
\frac{\sigma}{\mu} \ge \frac{1.33}{c}
\]

So:

\[
n \ge 7.8489\left(\frac{1.33}{c}\right)^2
\]

| Lag retention \(c\) | Required \(\sigma/\mu\) | Required round trips \(n\) |
|---:|---:|---:|
| 1.00 | 1.33 | 13.88 |
| 0.50 | 2.66 | 55.54 |
| 0.25 | 5.32 | 222.14 |
| 0.10 | 13.30 | 1,388.39 |
| 0.05 | 26.60 | 5,553.57 |

These are **optimistic lower bounds** because they use the lowest noise ratio and ignore the fact that the fixed-cost hurdle reduces \(\mu\) further. Including fixed cost makes \(n\) larger.

The replication rule requires pooled trades \(\ge 12\). For 12 trades:

\[
12 = 7.8489\left(\frac{1.33}{c}\right)^2
\]

Solving:

\[
c = \frac{1.33}{\sqrt{12/7.8489}}
\]

\[
\sqrt{12/7.8489} = 1.236477\ldots
\]

\[
c = \frac{1.33}{1.236477\ldots} = 1.07563\ldots
\]

That is impossible because \(c \le 1\).  
So **12 pooled trades is below the detection floor** for any realistic 60s-lag copy strategy under the project’s own noise lower bound.

Trade frequency required in a 30-day Phase A:

\[
f = \frac{n}{30}
\]

| Lag retention \(c\) | Required round trips \(n\) | Required trades/day, 30d | Required trades/day, 90d |
|---:|---:|---:|---:|
| 1.00 | 13.88 | 0.463 | 0.154 |
| 0.50 | 55.54 | 1.851 | 0.617 |
| 0.25 | 222.14 | 7.405 | 2.468 |
| 0.10 | 1,388.39 | 46.280 | 15.427 |
| 0.05 | 5,553.57 | 185.119 | 61.706 |

The pooled minimum of 12 trades only needs:

\[
\frac{12}{30} = 0.4\text{ copyable trades/day}
\]

or 0.133/day over 90 days. But the detection requirement dominates unless \(c\) is near 1, which is not plausible with a 60s lag.

**Step 3 answer: FAIL.**  
The 12-trade pooled minimum is far too small to detect the edge. For any plausible 60s retention \(c\), the required trade count is much higher, and the required frequency over 30 days is likely unavailable from a top-3 allowlist.

---

## Step 4 — Structural substitute: frequency × payoff

For a structural hypothesis, the question is:

\[
\text{profit} = f \cdot \text{payoff per trade}
\]

where \(f\) is the copyable trade frequency of the top-3 allowlist.

The prompt asks: **how often does a top-3 allowlist fire a copyable trade, and what would each trade need to pay?**

I do not have an empirical fire rate. That number was not given and cannot be derived from the materials provided. What can be derived is the **required** fire rate once \(c\) is known.

From Step 3, over 30 days:

- If \(c=0.25\), need **7.4 copyable trades/day**.
- If \(c=0.10\), need **46.3 copyable trades/day**.
- If \(c=0.05\), need **185.1 copyable trades/day**.

These are combined across the top-3 allowlist, and every counted trade must be a genuine copyable round trip after the 60s lag.

Each trade must pay enough to clear the fixed cost:

- At $5: each round trip must average **at least $0.0127** after lag and all variable costs.
- At $10: same dollar cost, but the gross percent hurdle is halved.

But detection imposes an additional constraint: the expected net edge per trade must be large relative to per-trade noise. Under the assumed noise bound, a small retained edge means the trade count requirement explodes.

The 60s lag is the central problem: it caps the retained payoff \(c\), which simultaneously raises the break-even source edge and the detection sample size.

**Step 4 answer: FAIL / not demonstrated.**  
The hypothesis provides no measured fire rate and no measured post-lag payoff. The arithmetic shows that, for a plausible 30-day window, the required combination of frequency and payoff is unlikely. The 60s lag makes the per-trade payoff too small relative to noise unless the allowlist fires a very large number of copyable trades.

---

## Gate answers

1. **Claimed edge:** FAIL.  
   The hypothesis does not state a gross % per round trip. “Positive net after costs” is not an edge estimate.

2. **Break-even clearance:** FAIL / unproven.  
   At $5 the post-lag gross edge must exceed **0.254%**, and at $10 it must exceed **0.127%**. Because of the 60s lag, the source edge must be even larger:  
   \[
   E_{\text{source}} > \frac{0.254\%}{c}
   \]
   at $5. No \(c\) is given, so clearance cannot be shown.

3. **Detection clearance:** FAIL.  
   Under the project’s noise lower bound, 12 pooled trades can only detect an edge if the copied trade captures **more than 100%** of the source move, i.e. \(c \approx 1.076\), which is impossible. For any realistic \(c<1\), required round trips are far above 12.

4. **Does the return distribution plausibly contain it?** No.  
   The structural payoff is a 60s-delayed residual from someone else’s trade. The 60s lag caps the retained edge, raises the required source edge, and massively increases the detection sample. There is no measured fire rate and no measured post-lag payoff. The frequency × payoff product required to clear the gate within a 30-day window is not demonstrated and is likely unavailable at $5–$10 positions.

## Plain conclusion

This hypothesis **cannot clear the gate**. It is not ready at Step 1 because it has no numeric edge. The 60s copy lag makes the break-even hurdle harder than the stated 0.254%/0.127% suggests, and it makes the detection requirement much larger than the 12-trade pooled minimum. A backtest should not be built on this hypothesis as written. If anything, a data-collection-only Phase A could measure \(c\) and the actual copyable fire rate, but the hypothesis as a backtest candidate should be stopped here.

---

## Review record

Re-derived independently before adoption, per `.claude/skills/openrouter-deepseek`,
which defines "reviewed" as re-derived rather than re-read. **Nothing needed
correcting.** Reproduce with:

```python
Z2, NOISE, FIXED = 7.8489, 1.33, Decimal("0.0127")
n = Z2 * (NOISE / c) ** 2
c_needed_for_12 = NOISE / sqrt(12 / Z2)
```

| Claim | Verification |
|---|---|
| Break-even 0.254% / 0.127% | `0.0127/5`, `0.0127/10` ✓ |
| Required source edge = break-even ÷ c | 0.508/1.016/2.540/5.080% at c = 0.5/0.25/0.1/0.05 ✓ |
| `n = 7.8489 (1.33/c)²` | 13.88 / 55.54 / 222.14 / 1,388.39 / 5,553.57 ✓ |
| Trades per day, 30d and 90d | every row ✓ |
| **c required for n=12 to suffice = 1.0756** | `1.33 / √(12/7.8489)` = 1.07564 ✓ — **greater than 1, so impossible** |

The draft used **1.33**, the *lowest* value in the project's measured noise
range of 1.33–1.55. That is the generous end: at 1.55 every requirement gets
worse. The conclusion is robust to the choice.

### The finding that is bigger than copy-trading

The detection floor at **c = 1** — a hypothetical perfect, zero-lag copy — is
**13.88 round trips.** The backtesting skill's replication rule requires
**pooled trades ≥ 12.**

**The pooled-12 minimum sits below the detection floor by 1.88 trades even in
the impossible best case.** That is not a fact about copy-trading; it is a
fact about the rule. A strategy that "replicates" on exactly 12 trades has
not been detected at 95/80 under this project's own noise measurement — it has
been guessed at, with a rule that says otherwise.

This is the same error class the `edge-viability-check` skill was built to
catch: a protocol that is rigorous about *not fooling yourself on a result*,
while permitting a sample that cannot produce a trustworthy result either way.

**The rule is marked "locked" in the backtesting skill and has not been
changed here.** Changing a locked decision rule is the user's call, not a
side effect of a research draft. The finding is recorded in the skill as a
flag, and raised for decision.

### What this does and does not stop

**Stops:** building a backtest on this hypothesis as written. Steps 1, 2 and 4
fail for want of a measured number, and Step 3 fails on arithmetic.

**Does not stop:** the extraction work. The universe extractor and position
book *measure* the two numbers the gate is missing — the post-lag retention
`c` and the copyable fire rate. Collecting them is how the hypothesis would
become statable at all. What must not happen is sliding from "we collected
data" to "we ran a backtest and it passed on 12 trades".
