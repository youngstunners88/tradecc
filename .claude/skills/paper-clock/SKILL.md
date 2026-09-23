---
name: paper-clock
description: |
  Start and run a validation clock that cannot be faked, for any system that
  must prove itself before it is allowed to act with real money or real
  consequences.

  Load this before building a "paper trading" mode, a shadow deployment, a
  canary, a dry-run period, or any gate of the form "prove it for N days
  first".

  The finding that makes this a skill: **the gate was never the blocker.**
  Hydra's live gate sat locked for weeks against a clock at zero, and the
  reason was not the gate's strictness, the strategy, or the data. It was that
  `package.json` advertised a `hunt` script whose file did not exist. Every
  library was built, tested and correct, waiting for a caller nobody had
  written.

allowed-tools: Bash Read

usage: |
  python3 -m pytest 10-Skills/paper-clock/tests -q

  # The four ways a validation clock silently reports zero
  cat 10-Skills/paper-clock/references/failure-modes.md
---
<!-- Vendored from Solomons-Chamber@a7b1fc1 10-Skills/paper-clock. Edit upstream, then re-vendor. -->

# Paper clock

A validation gate is a promise that nothing acts until evidence exists. The
promise is only as good as the weakest of four things, and **three of them
fail silently**.

## The four failures, in the order they bite

| # | Failure | What it looks like | Detected by |
|---|---|---|---|
| 1 | **No caller** | Every library green, clock at zero | Nothing. You must go looking. |
| 2 | **Volatile store** | Clock resets on every restart, forever near zero | Nothing. Looks like slow progress. |
| 3 | **Asserted evidence** | Gate passes on a flag the caller supplied | Nothing. Looks like a pass. |
| 4 | **Under-reporting tool** | Status says "not started" when it has | Nothing. Sends you to debug the working part. |

Every one of these was live in Hydra simultaneously. All four are absences —
the class of bug `reconcile.py` exists for. None raised an error.

### 1. Nothing calls the thing

The libraries were complete: a journal with calibration, Brier and ECE; a
lifecycle state machine refusing rank-skips; a plane guard. 87 passing tests.
Zero decisions recorded, because no file called `promote()`.

`package.json` listed `hunt`, `promote`, `replay` and `smoke`. **None of those
four files existed.** The manifest described a system that had never run.

> **Check first, before anything else:** for every entry point your manifest
> advertises, does the file exist, and does something call the function that
> writes the evidence? `scripts/check_entrypoints.py` does this.

### 2. The store is volatile

A clock measured in days spans process restarts. Hydra's journal was a `Map`.
Every redeploy silently restarted the run at zero — it would have reported a
fresh two-day run forever and never reached thirty.

**A validation clock must be durable before it is started, not after.**
Append-only, replayed on open. A resolve is a new line, never an edit: if an
outcome can be edited it can be improved after the fact.

### 3. The evidence is asserted, not derived

`lifecycle.ts` correctly refused `watchlisted → trusted` without
`paperMetricsPassed`. But that flag was **a boolean handed in by the caller**.

> A gate whose evidence is supplied by the thing being gated is a formality.

Derive it, from resolved outcomes, or the gate is theatre. There is a test
named for this: it passes a `paperMetricsPassed: true` in the caller's own
gate object and asserts the promotion is still refused.

### 4. The status tool under-reports

`paper_status.ts --days 30` read positionals as
`argv.filter(a => !a.startsWith("--"))` — which keeps every *flag value*. It
took `30` as the log path, found no such file, and printed
**"NOT STARTED — no decisions journalled"**.

The clock had started. The tool said it had not.

> A status tool that under-reports is worse than no status tool, because the
> response to it is to go debug the thing that was working.

Same class as the mutation harness that reported "NOT CAUGHT" from a stale
`.pyc`. A harness that lies about coverage is still a harness that lies.

## Start the clock correctly

```
1. check_entrypoints  — does a caller exist at all?
2. durable store      — append-only, replay verified ACROSS PROCESSES
3. derived evidence   — no caller-supplied gate flags
4. honest status      — parse args properly; refuse unknown flags
5. run it twice       — and assert the start time did not move
```

Step 5 is the one people skip. **Two runs, same `startedAt`, is the proof that
durability works.** One run proves nothing: an in-memory store looks identical.

```python
from clock import ClockStatus, verify_not_restarted
verify_not_restarted(before, after)   # raises if the clock reset
```

## What a healthy first run looks like

```
observed   3 distinct wallet(s)
  0x80b3...  d1  allowed=false
journalled 3 decision(s)
status     BLOCKED -- needs 30.00 more days and 97 more RESOLVED outcomes.
```

**`allowed=false` is the gate working.** Promotions are refused until resolved
outcomes exist. A refused decision is still a recorded prediction, and it is
exactly as much calibration evidence as an accepted one — a journal holding
only the decisions that went ahead cannot be calibrated at all.

If your first run reports `allowed=true`, something is asserting evidence.
Go back to failure 3.

## Seed the signal crudely, on purpose

Hydra's first hunter scores wallets on transfer size and nothing else. That is
deliberate:

> The journal exists to find out whether a confidence number is worth
> anything. Seeding it with an elaborate unvalidated score makes the first
> calibration report harder to interpret, not easier. **A bad signal that is
> measured beats a good one that is asserted.**

Replace the signal once there are enough resolved outcomes to judge a
replacement *against*. Not before.

## Two numbers, two blockers — report them separately

Elapsed days and resolved-outcome count fail for different reasons and at
different times. A single "not ready" hides which one is binding.

`MIN_RESOLVED = 97` is derived, not chosen: `n ≥ (1.96 / (2·tolerance))²` for a
ten-point error. Twenty flawless outcomes look like proof and are not.

**Shortening the calendar moves only one of the two.** Cutting 30 days to 2
leaves the 97-resolved-outcome check exactly where it was.

Hydra/tradecc now run a **2-day window, by the user's explicit decision
(2026-09-23)**, made after this was raised twice. Their revisit trigger:
*losing trades on paper*. Recorded beside the constant in `tradecc/core/gate.py`
and pinned by a test, so any change in either direction is a reviewed edit.

The right way to handle this: raise the consequence once or twice, then build
what was decided and write the provenance next to it. Don't keep re-arguing,
and don't silently refuse.

## Disclose the sampling frame

Hydra's hunter reads the head of the chain, so it only ever sees wallets active
*right now*. Wallets that made one excellent trade last week are invisible.

That does not invalidate the calibration — it *scopes* it. The resulting
numbers describe recently-active wallets specifically, and writing that down
before the numbers exist is what stops them being read as something broader
later.

## See also

- `10-Skills/outcome-resolution/` — the SECOND write; five silent biases in resolvers.
- `10-Skills/measure-first/` — the session protocol; pre-register before measuring.
- `10-Skills/irreversibility-harness/scripts/reconcile.py` — absence detection generally.
- `references/failure-modes.md` — full transcripts of all four.
