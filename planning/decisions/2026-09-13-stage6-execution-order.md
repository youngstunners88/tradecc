# Decision: Stage 6 build order — refusals before capability

**Date:** 2026-09-13
**Status:** In progress. Stage 6a (send authorisation) built; 6b (signing and
sending) not started.

## The constraint this order answers

Stage 6 is the only code in this project that can lose money by executing. It
is also the only code that cannot be validated by backtest: a send either
happens on chain or it does not.

The usual order — write the sender, then guard it — produces guards that are
bolted on, and a guard bolted on can be bypassed by any path that predates it.
So the order here is inverted:

> **The preconditions for sending exist before the ability to send.**

Stage 6a is `src/live/preflight.py`. It contains no network call, no key
handling, and no method that transmits anything. It decides whether a send is
permitted and produces evidence of that decision.

## Why authorisation binds to bytes

"Simulate, then send" as a sequence still permits sending *something else*: a
rebuilt transaction, a retry with a refreshed blockhash, a different route
fetched between the two steps. Each is a transaction that was never simulated,
and in every case the prose rule was followed.

So `SendAuthorization` carries the **SHA-256 digest of the exact transaction
that was simulated**, and the sender will compare digests before transmitting.
A transaction differing by one byte has no authorisation — not by policy, but
because the token it would need was never issued. This is the enforceable form
of CLAUDE.md rule 3.

`SendAuthorization` holds no send method by design. It is evidence, not
capability. A test asserts its public surface is exactly
`{transaction_digest, authorized_at, size_usd, authorizes}` so the distinction
cannot erode by accident.

## What preflight refuses

| Condition | Refusal |
|---|---|
| Risk did not approve | carries risk's own rejections through, unmodified |
| Process not configured `live` | refuses — configuration errors around money fail closed |
| Intent not claiming `live` | refuses |
| No simulation | refuses — rule 3's default is refusal, not a warning |
| Simulation failed | refuses, quoting the chain's error |
| Simulation was of different bytes | refuses — rebuild and re-simulate |
| Simulation older than 30s | refuses — blockhashes expire in ~60s |
| Simulation timestamped in the future | refuses — a clock disagreement is not evidence |

All failures are reported together, so fixing one does not reveal the next at
send time.

Risk's verdict is **carried, not re-derived**. `RiskEngine.approve` already
owns sizing, the slippage cap, the circuit breaker and the live gate; a second
implementation of any of them would eventually disagree with the first, and the
disagreement would surface as a trade that passed one and not the other.

## Verified, not asserted

Each refusal was disabled in turn and the suite re-run:

| Check disabled | Tests that fail |
|---|---|
| simulation checks | 7 |
| digest binding | 1 |
| staleness | 1 |
| configured-mode | 3 |
| risk verdict | 2 |

440 tests, 96% coverage.

## What is deliberately NOT built yet

- **Signing.** No keypair loading, no `solders`/`solana` dependency. The
  environment has neither installed, and adding them is a separate, reviewed
  step.
- **Sending.** No RPC transmit path.
- **Transaction building.** No Jupiter `/swap` call.

## The standing caveat

This does not bring live trading closer than the gate allows, and building it
is not a judgement that trading should begin. **No strategy has demonstrated an
edge** — momentum is closed (`2026-09-12-kill-ema-rsi-momentum.md`),
cross-sectional momentum failed, regime conditioning was refuted, and
copy-trading's rigorous form is blocked. The live gate additionally requires 30
days of paper evidence and a max-drawdown threshold that has never been set.

Stage 6 is strategy-agnostic infrastructure: whatever eventually trades needs
it, and it is safer built deliberately now than hurriedly later. It remains
inert until the gate opens, and the gate opens on evidence.
