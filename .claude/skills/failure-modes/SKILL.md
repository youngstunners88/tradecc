---
name: failure-modes
description: The defect shapes that have actually shipped in this repo, with the detection recipe for each. Use before reviewing or writing code in the money, risk or gate path, when auditing, when a control "looks fine", or when deciding what to test. Read it as a checklist of what to go looking for, not as background.
---

# Failure Modes That Have Actually Shipped Here

Eleven real defects, sorted into five shapes. Every one passed review and a
green test suite. The point of the taxonomy is that the *shape* recurs even
when the code does not — so hunt the shape, not the last bug.

---

## Shape A — a value that means "no answer" satisfies a safety comparison

The most expensive shape in this repo. Three separate defects:

| Defect | Effect |
|---|---|
| `Infinity` persisted as realised P&L | A **$1,000 loss against a $5 daily limit did not halt trading** — `-1000 > -Infinity` is False |
| `Infinity` as the gate's drawdown threshold | Gate **unlocked at 99% observed drawdown** |
| `max_drawdown_pct` returning 0 for a non-positive peak | `[0, -5]` reported a **0% drawdown**, clearing any threshold |

**Why review misses it:** the comparison reads correctly. `observed > threshold`
is right. It is the *operand* that is meaningless, and the comparison politely
returns False.

**Detection recipe.** For every threshold comparison, ask what value makes it
return False without being a real measurement, then feed it that:

```python
for poison in (Decimal("Infinity"), Decimal("-Infinity"), Decimal("NaN"), None, 0):
    ...  # does the control still fire?
```

`core.types.finite_decimal` exists for this. Anything crossing a persistence
or config boundary into a safety check goes through it.

---

## Shape B — the same quantity in two units across a boundary

| Defect | Effect |
|---|---|
| Paper SELL sized in the quote asset | Asked Jupiter to price **0.01 SOL when the position held 0.098** — 9.8× off |
| SELL quote price derived as `in/out` | The **reciprocal** of the BUY price: a flat market showed **+$990 on a $10 position**, and atomic ratios were compared against candle closes to fire stop-loss |

**Why review misses it:** both sides are individually correct. The error only
exists in the relationship, and no single function is wrong.

**Detection recipe.** Wherever two values meet in one expression — a
subtraction, a ratio, a comparison — name the unit of each out loud. If they
came from different functions, write a test that computes the expression on
a case where the answer is known independently. For prices, the known case is
**a flat market: a round trip must lose exactly the costs.**

State the convention in the docstring of whatever produces the value. An
invariant nobody wrote down is one nobody can check.

---

## Shape C — a control that cannot fire, or fires on the wrong thing

| Defect | Effect |
|---|---|
| No trade-count floor at the gate | `+$0.47 on 3 trades` would have unlocked live trading |
| No fee-to-size ceiling | Modelled cost of **38,880% of a $10 position**, approved by every other control |
| 15% max-drawdown threshold | Needed **29 consecutive worst-case losses** to reach — decoration, not a gate |
| Security scan with 4 false CRITICALs on a clean repo | A control nobody can trust is a control everybody routes around |
| Absent fingerprint read as *mismatch* | Urgent alert on every fresh install, body asserting an approval that did not exist |

**Detection recipe.** Two questions per control:

1. **Can it fire?** Construct the input that trips it. If that input is
   impossible or absurd, the control is decoration — say so and re-derive the
   threshold from the system's real arithmetic.
2. **Does it fire only on that?** Construct the innocent input closest to the
   boundary. A control that also fires there gets worked around, and a
   worked-around control protects nothing.

Absence and violation are different states. "Never approved" is not "approved
for something else"; "not measured" is not "measured as zero".

---

## Shape D — a promise wider than the code

`PaperTrader.tick`'s docstring said *"an exception escaping here would end the
session"*. It caught `ProviderError` only. A stress run died at tick 14 of 400.

**Detection recipe.** Read the docstring as a specification and try to violate
it. Where it says "never", "always", or "cannot", find the input that does.
Docstrings in this repo are unusually load-bearing — they are where invariants
live — which makes an over-promise unusually dangerous.

---

## Shape E — a test seam that cannot express the error

Both Shape B defects were invisible because `MockQuoteSource` returned one
price orientation for both sides and applied BUY-direction slippage to SELLs.
Every paper test ran against a fake that *could not be wrong in the way the
real client was wrong*.

**Detection recipe.** For each fake, ask: **what could the real thing do that
this fake cannot?** That set is your blind spot, and it is invisible to
coverage tooling — the lines run, against input that cannot fail.

At least one test must cross the seam end to end against a fake shaped like the
real protocol (`src/tests/test_quote_price_units.py` is the worked example).
When you fix a defect in a real client, fix the fake in the same commit, or
the seam silently re-opens.

---

## Using this

Before merging anything in the money, risk or gate path, walk the five shapes
against your diff. It takes minutes and has a better hit rate than re-reading
the diff for style.

When a new defect ships, add it here under its shape — or open a sixth shape
if it genuinely does not fit. A ledger that is not updated becomes a story
about the past instead of a tool.
