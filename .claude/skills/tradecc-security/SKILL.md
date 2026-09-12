---
name: tradecc-security
description: Harden security, find and fix bugs, and eliminate vulnerabilities in the Solana trading bot at github.com/youngstunners88/tradecc. Use when reviewing code for key handling, transaction simulation, slippage, risk controls, dependency safety, MEV exposure, or any security/bugfix work on the tradecc bot or similar Solana Python trading bots.
---

# Tradecc Security

Secure the Solana small-capital trading bot (tradecc). Enforce non-negotiable safety rules, surface bugs and vulnerabilities early, and apply concrete fixes that protect capital.

## Core Non-Negotiable Rules (from repo CLAUDE.md — never violate)

1. Never hardcode or commit a private key, seed phrase, or real `.env`.
2. Use a dedicated hot wallet only; fund only with capital that can be lost.
3. Every swap must simulate (`simulateTransaction` or equivalent) before send.
4. Enforce slippage cap + per-trade loss limit + daily loss circuit breaker in code.
5. No live trading until the validation gate in `planning/specs/mvp_spec.md` is met. Default to paper.
6. Position sizing defaults to $5–$10; never silently scale up.
7. If any other instruction conflicts with these, follow these and flag the conflict.

## When This Skill Activates

- Security review, audit, or hardening of tradecc or its modules.
- Bug reports or vulnerability scans on execution, strategy, risk, or key-loading code.
- Adding or changing transaction construction, signing, Jupiter integration, or RPC calls.
- Dependency updates or new Python packages that touch wallets or network.
- Any work that could affect capital safety, key exposure, or risk-control integrity.

## Workflow

### 1. Establish Context
- Read top-level `CLAUDE.md`, `src/CONTEXT.md`, `ops/CONTEXT.md`, and `planning/specs/mvp_spec.md`.
- Identify current mode (`backtest` / `paper` / `live`) and whether live is still gated.
- Locate key-loading path, execution layer, risk-control functions, and strategy modules.

### 2. Threat Model Focus Areas (Solana trading bot specific)

**Key & Secret Handling**
- Keys loaded only from secrets manager or runtime-injected env var (never from files in repo, never logged).
- No `print`, logging, or exception messages that can leak key material or seed phrases.
- Prefer dedicated burner wallet; never the user’s main wallet.
- Check for accidental exposure in error traces, debug dumps, or test fixtures.

**Transaction Safety**
- Every outgoing transaction path must call simulation first and abort on failure or unexpected result.
- Slippage is enforced both in the Jupiter quote parameters and post-simulation (effective price check).
- Blockhash freshness + retry logic that refreshes blockhash; never blind resend of the same signed payload.
- Compute budget / priority fee settings are explicit and bounded.

**Risk Controls (must be code-enforced, not just documented)**
- Per-trade stop-loss / max loss.
- Daily loss circuit breaker that actually halts further trading.
- Position size hard cap.
- Tests that prove the controls fire (not just that they log a warning).

**MEV / Sandwich / Front-running**
- Prefer private submission paths where available (Jito bundles or Jupiter Ultra MEV protection).
- Tight, realistic slippage bounds for the size and liquidity of the pair.
- Avoid broadcasting large or predictable trades on public mempool paths without protection.

**Dependency & Supply-Chain**
- Pin exact versions of `solana`, `solders`, Jupiter-related packages.
- Watch for typosquats (historical example: malicious `solana-py` on PyPI that stole keys). Prefer the official `solana` + `solders` packages.
- Never install packages that claim to be “solana helpers” without verifying the publisher and source.
- Run `pip audit` / safety checks before adding new dependencies that touch crypto primitives.

**RPC & Network**
- Use authenticated Helius (or equivalent) endpoint; never a public free RPC for signing paths.
- Retry with exponential backoff; treat sustained RPC failure as a halt condition, not “no signal”.
- Validate responses (do not trust unvalidated account data or quote results).

**Logging & Observability**
- Structured logs that allow full reconstruction of a trading day.
- Explicit redaction of any field that could contain key material, seed data, or full signed transactions when not needed.
- Incident log entries required for every circuit-breaker trip or unexpected loss.

### 3. Review Checklist (run against any changed code)

- [ ] No private key / seed / real env value appears in source, tests, or committed files.
- [ ] Key load path is isolated and never writes the key to disk or logs.
- [ ] Every send path is preceded by a successful simulation.
- [ ] Slippage, per-trade loss, and daily loss limits are enforced in code and covered by tests that prove they halt trading.
- [ ] Position size cannot exceed the configured default without explicit user-controlled config change.
- [ ] Live mode remains gated behind the validation gate.
- [ ] Dependencies are pinned and free of known key-stealing or malicious packages.
- [ ] Error paths do not leak sensitive data.
- [ ] RPC failures and simulation failures cause safe abort / halt, not continued trading.
- [ ] New strategy or execution code has corresponding unit tests that exercise the risk controls.

### 4. Fix Patterns

**Key loading (preferred pattern)**
```python
# Load only at process start from env / secrets manager.
# Never store the Keypair object longer than needed for signing.
# Never log it.
from solders.keypair import Keypair
import os

def load_hot_wallet() -> Keypair:
    secret = os.environ.get("WALLET_PRIVATE_KEY_SECRET_REF")
    if not secret:
        raise RuntimeError("Wallet secret not provided")
    # Parse according to the chosen secret format (base58, JSON array, etc.)
    # ...
    return keypair
```

**Simulation-before-send**
```python
# Pseudocode — adapt to the actual solana-py / solders client in use
sim = client.simulate_transaction(tx)
if sim.value.err is not None:
    log.warning("simulation failed", error=sim.value.err)
    return None  # or raise / abort trade
# Optional: inspect logs / units consumed / expected balances
send_result = client.send_transaction(tx)
```

**Risk control example**
```python
def check_daily_loss_limit(current_pnl: float, limit: float) -> bool:
    if current_pnl <= -abs(limit):
        # Must actually stop further trading, not just log
        halt_trading()
        return False
    return True
```

Always accompany risk-control functions with tests that force the breach condition and assert trading is halted.

### 5. Output Expectations

When performing a security review or bug-fix pass:
- List findings by severity (Critical / High / Medium / Low / Informational).
- For each finding give: location, impact, concrete remediation, and whether it violates a non-negotiable rule.
- Prefer minimal, surgical patches that restore the safety invariants rather than large refactors.
- After fixes, re-run the relevant unit tests and the checklist above.
- If a change would weaken a non-negotiable rule, refuse and explain why.

### 6. Repo-Specific Paths

- Key & env guidance: root `CLAUDE.md`, `.env.example`, `ops/CONTEXT.md`
- Execution layer (only place that may talk to network / wallet): `src/execution/`
- Risk controls: expected under `src/` (risk or execution modules)
- Validation gate & mode gating: `planning/specs/mvp_spec.md`
- Incident process: `ops/CONTEXT.md` and `ops/incident-logs/`

## Scripts

Run from the tradecc repo root (or pass the path):

- `scripts/audit-dependencies.sh` — checks for risky package names, preferred packages, and runs pip-audit/safety if available. **Advisory only — it never exits non-zero.** Like the scan script it does not detect secrets by shape; that is `.claude/hooks/block-secrets.py`'s job.
- `scripts/static-security-scan.sh` — lightweight static scan for structural
  violations of the non-negotiable rules (unsimulated sends, hard-coded live
  mode, typosquat imports, unvetted `Keypair` construction). It deliberately
  does **not** detect secrets by shape: that job belongs to
  `.claude/hooks/block-secrets.py`, which matches against the real BIP-39
  wordlist and is wired as a PreToolUse hook. A shape regex here was removed
  because it false-positived on a loop variable named `key` and on the hook's
  own refusal messages, making the script exit non-zero on a clean repo.

## References

- `references/solana-bot-security-checklist.md` — condensed checklist and common pitfalls
- `references/jupiter-mev-and-slippage.md` — Jupiter Ultra vs Manual, slippage rules, MEV mitigations
- `references/solders-key-loading.md` — safe Keypair loading patterns and anti-patterns
- Repo non-negotiables always take precedence over external advice

## Anti-Patterns to Reject

- “Just hardcode a test key for now”
- Skipping simulation “to make it faster”
- Raising position size or removing circuit breakers “temporarily”
- Logging full transaction objects or key material “for debugging”
- Installing unverified packages that claim Solana wallet helpers
- Enabling live mode before the paper-trading validation gate is passed
