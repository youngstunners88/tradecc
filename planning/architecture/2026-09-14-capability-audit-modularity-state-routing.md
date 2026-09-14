# Capability Audit: Modularity, State Management, Routing

**Status:** Audit, not a build spec. This document exists to answer one
question honestly — "does TradeCC need new architecture for skills,
separation of concerns, state management, or routing?" — before anyone
builds toward that request. The answer, checked against what's actually
in the repo as of `main` + PR #10, is **no**. What follows is the
mapping, so that answer is verifiable rather than asserted.

## Why this document exists

A request for "powerful skills," "effective modularity," "immaculate
state management," and "effective routing systems" describes desired
qualities, not a gap. Before any of those qualities get treated as a
build target, this audit checks whether they're already present under
more specific names — because building new abstraction on top of
already-solved problems adds surface area without adding capability,
and surface area is exactly what a money-adjacent codebase should
minimize, not maximize, absent a concrete need.

## Modularity / separation of concerns — already built

| Requested quality | Where it actually lives | Evidence it works |
|---|---|---|
| Pluggable strategies | `src/strategy/` — strategy modules share one interface; adding a new strategy requires no change to `execution/` or `risk/` | Cross-sectional momentum was added and later removed as a strategy candidate without touching execution or risk code |
| Independent, testable layers | `execution/`, `risk/`, `strategy/`, `live/` are separately unit-tested with injected fakes at the transport layer, not mocks of internal functions | The two SELL-path pricing bugs (paper sizing, reciprocal quote orientation) were found *because* this separation let adversarial tests isolate the execution layer from strategy and risk |
| Clear boundaries between read-only and money-moving code | `JupiterQuoteClient` (read-only) vs. the swap-building/signing/sending classes are deliberately separate classes, not methods on one client | A test explicitly asserts no `send`/`sign`/`submit`/`broadcast`/`keypair`-named method exists anywhere on the read-only client |

**Conclusion:** the separation-of-concerns request is already satisfied. There is no monolith to break apart.

## State management — already built, recently hardened

| Requested quality | Where it actually lives | Evidence it works |
|---|---|---|
| Durable, correct state across restarts | `PaperSessionStore` (elapsed-days tracking survives restarts, corrupt sessions refuse to resume rather than silently reopening a clock) | Verified directly: a stale one-tick session was correctly discarded rather than resumed, preventing a false 3-day head start on the 30-day gate |
| Fail-closed on corruption | `RiskStateStore` — unreadable, unchecksummed, or tampered daily risk state loads as halted, not clean | Verified live: truncating the file produces `halted=True`, not a fresh day |
| Evidence-bound approvals | `validated_fingerprint` in the live gate binds an approval to a SHA-256 digest of the exact strategy, risk, and cost config it was evaluated against — now including `capital_base`, closing the gap where an unpinned denominator could turn a 12% drawdown into a gate-passing 0.12% | A regenerated fingerprint fails closed with a message naming the exact section that changed |
| Deliberate recovery paths | `clear-halt --acknowledge` is the only way to clear a halt; deleting the state file is not a workaround, it's refused by the loader | Tested directly — the acknowledge guard has its own regression test |

**Conclusion:** state management here is not "immaculate" by decoration — it's hardened by five separate incidents (the SELL sizing bug, the fingerprint-rubber-stamp risk, the corrupt-state fail-open bug, the unpinned capital-base denominator, the absence-read-as-mismatch bug) each fixed and regression-tested individually. Any claim that state management is a weak point should be checked against this table first.

## Routing — already built

| Requested quality | Where it actually lives | Evidence it works |
|---|---|---|
| Mode-based dispatch | `backtest` / `paper` / `live` / `gate` are distinct, independently tested CLI modes with different behavioral contracts | `live` mode refuses with exit code 2 and names the missing gate criteria, rather than silently degrading to paper behavior |
| Structural (not prose) enforcement of routing rules | `SendAuthorization` binds to the digest of exact simulated bytes; a transaction differing by one byte has no valid authorization token, regardless of which code path constructed it | A dedicated test simulates a substituted-signer attack and confirms the sender rejects it |
| Alerting routed to the right event, not a time window | `core.gate_watch` alerts on gate-state *transitions* (unlock, re-lock, fingerprint mismatch, changed failure set) rather than polling — a steady gate stays silent, which is the actual point of the rate limit | End-to-end verified through the CLI: first observation alerts, unchanged gate stays silent, unlock fires urgent |

**Conclusion:** routing exists, is tested, and is structural rather than convention-based where it matters most (send authorization). There is no missing router.

## What is actually missing

One thing, and it is not architectural: **a strategy that has cleared validation.**

As of this audit:
- Momentum (EMA/RSI): closed, six converging negative results.
- Cross-sectional momentum: failed, concentration check.
- Regime detection: refuted, premise contradicted by the data.
- Copy-trading (rigorous form): blocked, wallet-universe enumeration infeasible at current data access.
- pump.fun graduation-duration: parked, not pursued (weeks-long forward-only commitment declined).
- Capital-range increase: closed, evidence shows the constraint was never fees — the strategy captures ~22% of buy-and-hold even at infinite capital.

The execution stack (Stage 6a/b/c/d) is complete, tested, and correctly refuses to send anything the gate hasn't approved. It has no strategy to approve. That is the entire gap.

## What this means for any future "let's add capability" request

Before building toward a request like the one that prompted this
document, check it against this audit first:

1. **If the request names a concrete capability the tables above don't
   cover** (a specific data source, a specific new signal type, a
   specific execution improvement) — that's real scope. Route it
   through the normal process: decision record, pre-registration where
   it touches a strategy claim, propose before build.
2. **If the request is a general call for the system to be "more
   powerful" or "more capable" without naming a concrete gap** — the
   answer is this document. Point back to it rather than building new
   abstraction to satisfy a feeling rather than a requirement.

The honest state of this project is: the machinery is done and hardened
through repeated adversarial testing. The open question was never
architectural. It was, and remains, whether there is an edge worth
routing that machinery toward.
