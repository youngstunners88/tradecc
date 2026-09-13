# Decision: pump.fun graduation duration — pre-registration, written before any data exists

**Date:** 2026-09-13
**Status:** Rules locked. **Zero observations collected.** Collection is not
started and is not authorised by this document.
**Feasibility basis:** `research/backtests/2026-09-13_pumpfun-graduation-feasibility.md`

## Why this record exists before the collector

The feasibility probe found this hypothesis **data-clean, cheap, and not
testable retrospectively**: the reachable pump.fun sample is either the last
~24 hours of graduations or the oldest ~1,000 from January 2024, and the middle
— graduations 30–120 days old — is unreachable from either end. The only route
to a sample is forward collection, which means the rules can be fixed before a
single observation exists.

That is an unusually strong position to pre-register from, and it is also the
one where pre-registration matters most. A forward-collected sample arrives
gradually; whoever reads the first thirty rows will form an opinion before the
sample is complete, and every parameter left unfixed today is a parameter that
opinion can quietly set later. Five hypotheses have already failed against this
bar. The bar is why those failures were trustworthy, and an interesting idea
does not get a lighter one.

## The hypothesis, stated so it can fail

> Slower bonding-curve fills indicate organic demand rather than manufactured
> demand, and predict better post-graduation performance.

`fill_duration = graduation_time − token_creation_time`

**Directional claim (locked):** *longer* fill duration predicts *better*
post-graduation return. If the measured relationship runs the other way, that
is a **refutation of this hypothesis**, not the discovery of a new one. A
significant inverse result may be recorded as an observation; it may not be
traded on under this record, and reversing the sign to rescue the idea is
exactly the move this clause forecloses.

## Variable sourcing — two providers, neither able to mark its own homework

| Quantity | Source | Field |
|---|---|---|
| `token_creation_time` | pump.fun v3 (`frontend-api-v3.pump.fun/coins`) | `created_timestamp` |
| `graduation_time` | GeckoTerminal | `pool_created_at` |
| Post-graduation OHLCV | GeckoTerminal | daily/hourly bars |

Fill duration is a difference between two providers, so neither provider can
define the variable in its own favour. The qlo repository's claimed numbers
were not used to derive any of this and are not consulted at any stage.

## Collection protocol (locked)

- **Poll, not webhook.** 1,000 rows spans 24.4 hours; a **twice-daily poll**
  (~12h apart) of newest graduated coins covers the stream with ~2× margin
  against a burst. Webhooks were rejected: they need an API key and a
  persistently reachable HTTPS endpoint, and they buy nothing polling lacks.
- **Record at observation time.** Every graduation seen is written to the
  cohort file with its observation timestamp, *before* any post-graduation
  price exists. This is what makes the sample point-in-time clean by
  construction — the same property the wallet-universe work could not obtain
  at any budget.
- **No filtering at selection.** Every graduation in the window enters the
  cohort. Not the interesting ones, not the liquid ones, not the ones still
  alive when the analysis runs. Filtering at observation time is how
  survivorship bias re-enters through the back door, having been shown the
  front door in `2026-09-13-copy-trading-wallet-universe.md`.
- **A gap in collection is recorded, not patched.** If a poll is missed, the
  missed interval is marked as a hole in the cohort file. Back-filling from the
  newest-first endpoint after the fact would silently reintroduce the exact
  selection asymmetry this protocol exists to avoid.

## Measurement (locked before any observation)

- **Forward horizon: 30 days** from graduation. Chosen because GeckoTerminal
  retains ~184 daily bars, so a 30-day horizon leaves ample retention margin,
  and because a shorter window measures launch mechanics rather than the
  organic demand the hypothesis is about. One horizon, fixed. Reporting a
  7/14/30/60-day grid and leading with the best one is a multiple-comparisons
  result dressed as a finding.
- **Return definition:** close-to-close from the first full bar after
  `pool_created_at` to the bar 30 days later, cost-corrected with the existing
  model (`net(size) = size × g − F`, `F ≈ $0.0127` per round trip recurring).
- **Dead tokens are priced, not dropped.** A token whose pool stops trading or
  goes to zero enters the sample at its realised return, floored at −100%.
  Dropping it is survivorship bias, and in this category it is the *dominant*
  bias: the tokens that vanish are precisely the manufactured-demand cases the
  hypothesis claims to distinguish.
- **Test form:** cross-sectional. Rank the cohort by `fill_duration`, compare
  the slow tertile against the fast tertile, and against the benchmark below.

## Pass criteria — the same bar as every prior test

1. **Majority of walk-forward folds positive** (expanding window, 3 folds).
2. **Pooled net positive.**
3. **No fold contributes more than 60% of pooled net** (`Decimal("0.60")`, the
   same check in `research/walk_forward.py:161`). Cross-sectional momentum's
   +$13.44 was 94% one fold; that failure mode is live here.
4. **Pooled trades ≥ `MIN_POOLED_TRADES` (12)**, imported from
   `src/core/performance.py`, not restated as a literal.
5. **Beats the benchmark.** The benchmark is **equal-weight every graduation in
   the cohort**, not buy-and-hold SOL. The question is whether `fill_duration`
   *selects*; a strategy that merely rides a category-wide move has shown
   nothing about the variable. Both benchmarks are reported; criterion 5 is
   scored on the equal-weight one.
6. **Absolute dollar drawdown reported beside the percentage**, at every size,
   per rule 4 of `2026-09-13-capital-range-sensitivity.md`.

Failing any one of the six is a failure. A result that passes five and misses
concentration is the same failure it has been every previous time.

## Stopping rule (locked)

The verdict is called at **whichever comes first**:

- **90 days of collection elapsed**, or
- **200 cohort tokens with a matured 30-day window.**

At that point the analysis runs **once** against the criteria above and the
outcome is recorded. Specifically foreclosed:

- **No extension to chase significance.** "Another month would settle it" is
  not available after seeing the numbers. If the sample is genuinely too small
  at the stopping point, the recorded verdict is *underpowered* — a distinct
  outcome from *refuted*, and it does not authorise trading either.
- **No interim peeking that changes the rules.** Progress may be reported as a
  row count. It may not be reported as a preliminary result, and an early
  reading may not alter the horizon, the tertile split, or the criteria.
- **No re-cut of the same data.** One analysis, one verdict. Quartiles instead
  of tertiles, a different horizon, or a liquidity filter added after the fact
  are new hypotheses requiring a fresh cohort — not a second look at this one.

## Interpretation rule (locked)

**1. A positive result is a signal about the variable only if it survives all
six criteria.** The slow tertile beating the fast tertile on pooled net alone
is not a finding; it is the first of six checks.

**2. A negative result closes the hypothesis, not the horizon.** If slow fills
do not predict better performance over 30 days, the recorded conclusion is that
fill duration does not carry the claimed information — not that the horizon was
wrong. Rule 5 of the capital-sensitivity record exists for the same reason and
is the model for this one.

**3. Category re-entry stays scoped to this hypothesis.** `CLAUDE.md:31` puts
sniping new launches out of scope pending an explicit ask. The explicit ask
covered *this* hypothesis. A pass here authorises further work on **this**
variable and nothing else in the pump.fun category; it is not a general reopening.

**4. A pass does not authorise live trading.** It authorises a paper
implementation behind the unchanged validation gate, which this record does not
touch.

## What this record does NOT do

- **It does not start collection.** Not one poll has run. Starting is a
  weeks-to-months commitment whose verdict cannot arrive sooner, and that
  resource call is the user's, not mine. This record exists so that the day
  collection starts, the rules are already fixed and unfixable.
- **It does not reopen Stage 6c/6d or the max-drawdown threshold.** Both remain
  stood down pending an explicit instruction naming them.
- **It does not add a dependency.** pump.fun v3 and GeckoTerminal are both
  keyless; GeckoTerminal is already in the stack and contract-tested.
- **It does not change the live gate, risk defaults, or position sizing.**

## The expected outcome, stated in advance

Most likely: **no relationship**, or one too weak to survive the concentration
check on a cohort this size. Memecoin post-graduation returns are dominated by
variance that a single creation-to-graduation duration is unlikely to explain,
and the five prior hypotheses failed for reasons — concentration, replication,
sample size — that apply here with equal force.

Stating that now is the point. If the numbers come back flat, this record is
what makes "flat" a result rather than a prompt to re-cut until something moves.
