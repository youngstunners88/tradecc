# Structural edge inventory — is anything actually left?

**Date:** 2026-09-14
**Purpose:** Answer, before treating "structural edges" as an open direction,
whether any category remains that has not already been closed for a documented
reason. The full ledger and its usage rules live in
`.claude/skills/structural-edge-inventory`; this records the audit's finding.

## The finding

**Nothing is left.** Not at $5–$10, on Solana spot, with retail data access.

Every structural category was already examined, and **most were closed before
this project wrote a line of code** — in the original strategy research that
scaffolded it. The reframe from "directional" to "structural" felt like it
opened a frontier. It did not. It named a space that was already surveyed.

## The ledger, compressed

| Category | Verdict | Cause |
|---|---|---|
| Cross-DEX arbitrage | Rejected | Latency race |
| Sniping new launches | Rejected | Latency race + MEV |
| DEX market-making / LP | Rejected | Adverse selection (LVR) |
| Funding-rate carry | On hold | Wrong venue; $100–500 minimum |
| Copy-trading (rigorous) | Blocked | Data infrastructure |
| pump.fun graduation timing | Parked | Data infrastructure |
| Directional prediction | Closed (class) | Detection floor |
| Capital-range increase | Closed | Detection floor, read from the other end |

## Eight categories, four causes

The compression is the useful result:

1. **Latency / infrastructure races** — lost to co-located professionals.
2. **Adverse selection** — the passive side gets picked off.
3. **Data infrastructure** — the signal may exist; we cannot obtain
   point-in-time-clean data to test it at our access level.
4. **Detection floor** — the edge is smaller than our measurement can resolve.

**A candidate is not new if it lands in one of those four.** That test disposes
of the usual next suggestions without separate investigation: liquidation
hunting, depeg arbitrage and CEX↔DEX listing arbitrage are all cause 1;
statistical arbitrage on correlated pairs is cause 4, since a spread is still a
draw from a return distribution and `edge_budget.py` applies unchanged.

## Two verdicts need citations

**DEX market-making (LVR) and funding-rate carry appear nowhere in this
repository.** They were supplied as established findings and they are
plausible — but a future session grepping `planning/` will not find them, and
may re-open either as a fresh idea.

They are recorded in the skill's ledger with that caveat marked. If either is
ever revisited, it deserves a proper decision record — not because the verdict
is in doubt, but because an undocumented verdict is one nobody can check and
anybody can accidentally repeat.

## What the constraint actually is

Not the code: the execution stack is complete, hardened through repeated
adversarial testing, and correct. Not the search effort: four hypotheses were
tested to protocol and a fifth class was closed analytically.

**The binding constraints are position size and data access.**

- Position size sets the detection floor (cause 4) and decides which venues
  are even reachable (funding carry needs $100–500).
- Data access decides whether causes-3 candidates are testable at all.

Neither is a coding problem, which is why more architecture would not have
helped — the conclusion the capability audit reached independently.

## Three honest responses

All three are the user's call. **None should be built toward without an
explicit decision.**

1. **Accept the finding.** The machinery works; there is no identified edge to
   run through it. Stopping is a legitimate outcome of a rigorous search.
2. **Change the capital scale materially.** Funding-rate carry becomes
   examinable at $100–500 on a perps venue — a different project with a
   different risk profile, not a larger version of this one.
3. **Change the data access.** Paid, historical, point-in-time-clean data would
   make copy-trading and pump.fun *testable* again. Testable, not known-good.

## What this audit does NOT say

- **Not that no edge exists in crypto.** It says none was found that is
  reachable at this size with this data access, and that every category
  examined has a specific documented reason for being closed.
- **Not that the work was wasted.** The execution stack, the risk controls, the
  gate and the measurement tools are real and reusable. What is missing is a
  strategy, and knowing that cheaply is worth more than believing otherwise
  expensively.
- **Not a permanent verdict.** Each closure names the condition that would
  reopen it. Causes 1 and 2 are structural and unlikely to move; causes 3 and 4
  are functions of money and data access, and both are purchasable.
