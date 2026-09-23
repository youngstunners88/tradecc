# Four silent failures of a validation clock

Hydra, 2026-09-23. All four were live at once. **None raised an error.** The
gate was blamed for weeks; the gate was never the problem.

---

## 1. Nothing called the thing

`package.json`:

```json
"hunt":    "tsx scripts/hunt_once.ts",
"promote": "tsx scripts/promote_wallet.ts",
"replay":  "tsx scripts/paper_copy_replay.ts",
"smoke":   "tsx scripts/smoke_dust_swap.ts",
```

**None of those four files existed.** 87 tests passed. The journal, the
lifecycle machine, the calibration maths, the plane guard — all built, all
correct, all waiting for a caller nobody had written.

The stated blocker was "no hunter calls `journal.record()`". That was true and
it was a description of the symptom. The cause was a manifest describing a
system that had never run.

`check_entrypoints.py` run against the real repo, before the fix:

```
MISSING (3): the manifest advertises files that do not exist.
  promote: tsx scripts/promote_wallet.ts   -> NOT FOUND
  replay:  tsx scripts/paper_copy_replay.ts -> NOT FOUND
  smoke:   tsx scripts/smoke_dust_swap.ts   -> NOT FOUND
```

**Check this first.** It is thirty seconds and it is the one that wastes weeks.

---

## 2. The store was volatile

`DecisionJournal` held everything in a `Map`.

A run measured in days spans process restarts. Every redeploy silently
restarted the clock at zero. The system would have reported a fresh two-day
run forever and never reached thirty — and the reports would have looked like
slow, honest progress the whole time.

**Durability must come before the clock starts**, not after. Append-only,
replayed on open. A resolve is a new line, never an edit of the line that
recorded the decision: if an outcome can be edited, it can be improved after
the fact.

The proof is two runs in separate processes:

```
run 1 -> 3 decisions, startedAt 2026-09-23T09:07:28Z
run 2 -> 5 decisions, startedAt 2026-09-23T09:07:28Z   <- unchanged
```

One run proves nothing. A dictionary looks identical.

---

## 3. The evidence was asserted

`lifecycle.ts` refused `watchlisted → trusted` without `paperMetricsPassed`.
The state machine was correct. But the flag was **a boolean the caller handed
in**, inside the caller's own gate object.

> A gate whose evidence is supplied by the thing being gated is a formality.

Fixed by deriving it from resolved outcomes inside `promote()`, and there is a
test that passes `paperMetricsPassed: true` in the caller's gates and asserts
the promotion is *still* refused.

Related: the first run after wiring returned `allowed=false` for every wallet.
That is the gate working. **If a first run returns `allowed=true`, something
is still asserting.**

---

## 4. The status tool under-reported

```ts
const positional = argv.filter((a) => !a.startsWith("--"));
const path = positional[0] ?? DEFAULT_LOG;
```

That keeps every *flag value*. `paper_status.ts --days 30` took `30` as the
log path, found no such file, and printed:

```
status  NOT STARTED -- no decisions journalled yet.
```

The clock had started forty seconds earlier. The tool said it had not.

> A status tool that under-reports is worse than no status tool, because the
> response to it is to go debug the thing that was working.

Same class as the mutation harness that reported "NOT CAUGHT" from a stale
`.pyc`, and the one that passed assertion text to `--test-name-pattern` and
ran zero tests. **A harness that lies about coverage is still a harness that
lies**, and it lies in the safe-seeming direction, which is why it survives.

Unknown flags are now refused rather than ignored: a silently dropped typo
runs with a default nobody asked for.

---

## Why shortening the window does not help

The gate has two conditions:

| Condition | Source |
|---|---|
| 30 days elapsed | calendar |
| 97 resolved outcomes | `n ≥ (1.96 / (2·tolerance))²`, ten-point tolerance |

Cutting 30 days to 2 moves the first and leaves the second exactly where it
was, because a shorter window does not produce more outcomes. The gate stays
shut, and the safety margin is gone. There is a test named
`test_shortening_the_calendar_does_not_unlock_the_gate`.

Report the two separately. A single "not ready" hides which is binding, and
the wrong one gets "fixed".
