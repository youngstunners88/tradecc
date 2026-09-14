# Decision: Stage 6c/6d — signing and sending

**Date:** 2026-09-14
**Authorisation:** the user's explicit phrase, after the standdown recorded in
`2026-09-13-stage6-execution-order.md`. That record said the preconditions for
sending would exist before the ability to send. They did, and now the ability
does too.

## What was built

| Stage | Module | What it can do |
|---|---|---|
| 6c | `src/live/signing.py` | Load a keypair **from an environment variable only**, and sign bytes |
| 6d | `src/live/sender.py` | Check every precondition together, then transmit **at most once** |
| — | `HeliusTransactionSubmitter` | The raw `sendTransaction` call, and nothing else |

## The problem that shaped the design

The authorisation issued by Stage 6a is bound to the digest of the bytes that
were **simulated**. Simulation runs with `sigVerify: false` on an *unsigned*
transaction. What gets transmitted is *signed*, and therefore has a different
digest.

A naive sender compares the authorisation to the signed bytes, finds they
differ, and either refuses every send or gets "fixed" by dropping the check.
Both outcomes destroy the guarantee. So the sender proves the relationship
instead of comparing digests:

1. the authorisation matches the unsigned bytes the signer reports it started from;
2. the signed transaction's message is byte-identical to that unsigned message —
   **parsed independently**, not taken on the signer's word;
3. the signature over that message actually verifies.

Together: *the bytes about to be transmitted are a correctly signed instance of
precisely the transaction that was simulated and authorised.*

Point 2 is the one that is easy to omit. `SignedTransaction` supplies both
halves, so a buggy or substituted signer returning a signature over a different
message would satisfy every digest comparison. A test constructs exactly that
transaction and asserts the refusal.

## Key handling (CLAUDE.md rule 1)

- **Environment variable only.** `SOLANA_PRIVATE_KEY`, registered as a secret
  *before* parsing so a parse failure cannot log it.
- **A path is refused.** `/home/user/keypair.json` and friends raise rather
  than being read. "Just point it at the keypair file" is how a key ends up
  committed, so the affordance does not exist.
- **No error message contains key material.** Malformed input is reported by
  length and shape. A test asserts the offending value never appears.
- **`SoldersSigner`'s entire public surface is `{public_key, sign}`** — pinned
  by a test. There is no method that returns the key.

## Hot-wallet ceiling (CLAUDE.md rule 2)

Rule 2 — a dedicated wallet, never the user's main one, funded only with
capital they can afford to lose — was enforced by nothing but prose, because
until now nothing could send. It is now enforced approximately but usefully:
**the sender refuses to transmit from a wallet holding more than
`risk.max_hot_wallet_sol` (default 1.0 SOL).**

Nothing can prove a wallet is "dedicated". What it can notice is that the
wallet holds more than a throwaway should, which is the observable consequence
of pointing this at the wrong wallet. Expressed in SOL rather than USD so the
check needs no price feed — the one input that has already gone wrong here.

**A balance lookup that fails is a refusal, not a pass.** Not knowing the
balance is not the same as knowing it is small.

## Every refusal, and it is fail-closed throughout

| Condition | Behaviour |
|---|---|
| No authorisation | refuse — the ordinary state |
| Authorisation for different bytes | refuse |
| Signed message ≠ authorised message | refuse |
| Signature does not verify | refuse |
| Authorisation already used | refuse — re-sending is how one trade becomes two |
| Authorisation older than 30s | refuse — blockhashes expire |
| Authorisation timestamped in the future | refuse |
| Wallet above the hot ceiling | refuse |
| Balance unreadable | refuse |

All reasons are reported together, so fixing one does not reveal the next at
send time. A **refused** send does not consume the authorisation; a **spent**
one is marked before transmitting, so a provider error after the bytes reach
the cluster cannot become a double-send.

## Verified, not asserted

Each control was disabled in turn and the suite re-run:

| Control disabled | Tests that fail |
|---|---|
| signature/message verification | 2 |
| digest binding | 2 |
| single-use | 1 |
| staleness | 2 |
| hot-wallet ceiling | 4 |
| key-path refusal | 4 |

The send chain was traced rather than assumed: exactly **one** caller of
`send_transaction` (the gate), and `SendAuthorization` is constructed in
exactly **one** place, only after a successful, digest-matched, fresh
simulation.

`HeliusRpcClient` stays read-only — sending lives on a subclass, so the surface
tests asserting the read-only client cannot transmit still pass unchanged. Same
reasoning as `JupiterSwapClient` subclassing `JupiterQuoteClient`.

## Dependency

`solders` enters as an **optional** `live` extra, not a base dependency: a
paper or backtest install carries no key-handling library at all. It is in
`dev` because the 6c/6d suite exercises real signing against real transaction
bytes — faking the cryptography would test the fake, and this is the one place
where "the seam could not express the error" is unaffordable.

## What this does NOT do

- **It does not trade.** Nothing calls the sender. `cmd_live` still refuses at
  the gate, which reports **seven failures**. Wiring the autonomous loop to
  real sends is a further decision, deliberately not taken here.
- **It does not unlock the gate.** 30 days of paper evidence, ≥12 trades,
  positive net expectancy, the 8% drawdown threshold and human approval all
  stand untouched.
- **It does not supply a strategy.** No candidate clears the detection floor in
  `2026-09-14-minimum-detectable-edge.md`. The bot can now place a trade it has
  no reason to place.
