# Paper → Live Validation Gate Checklist

Use before any request to unlock live mode.

## Pre-requisites (must already be true)
- [ ] Risk controls implemented and unit-tested (see tradecc-risk-controls)
- [ ] Key loading follows safe solders pattern; no secrets in repo
- [ ] Every trade path simulates before send
- [ ] Position size still defaults to $5–$10
- [ ] Incident logging process exists under ops/

## Gate Criteria (enforced in `src/core/gate.py`)
- [ ] ≥ 30 days of paper mode against real market data
- [ ] Positive expectancy **after** realistic fees + slippage + Jupiter tiers
- [ ] Max drawdown ≤ pre-agreed threshold (threshold written in a decision record before the period started)
- [ ] **`trade_count` ≥ 12** closed round trips
- [ ] **`validated_fingerprint` matches the running config**
- [ ] Paper logs are complete enough to reconstruct every trading day
- [ ] No unexplained multi-day outages during the period

Every one of these is checked in code. The gate fails closed: a missing or
malformed field leaves live mode locked, and no input unlocks it by accident.

### The trade-count floor

`trade_count` must be at least `core.performance.MIN_POOLED_TRADES` (12) — the
same floor the walk-forward protocol uses, imported rather than restated so the
two cannot drift. The reason is concrete: the parameter sweep produced
**"+$0.47 on 3 trades"**, and a gate that accepts positive expectancy without a
sample size would unlock live trading on exactly that.

### The approval binding

`validated_fingerprint` ties an approval to the strategy and limits it was
granted against. Without it, a gate file approved for one strategy unlocks live
trading for **any** strategy, including one that was never tested.

Generate it against the config the bot will actually run:

```bash
.venv/bin/python -c "
import json, sys; sys.path.insert(0, 'src')
from core.config import load_config, fingerprint_sections
print(json.dumps(fingerprint_sections(load_config('config.paper.yaml', env={})), indent=2))"
```

Paste the result verbatim into the gate file.

**Covered** — change any of these and the gate re-locks:

| Section | What it digests |
|---|---|
| `strategy` | name, params, token_mints |
| `risk` | every field — position size, slippage cap, stop loss, take profit, daily loss limit |
| `costs` | every field — fees, priority fee per CU, Jito tip, ATA rent |
| `execution_assumptions` | `backtest.price_impact_pct` and `backtest.execution_slippage_pct` |

`execution_assumptions` is separated out because a validated expectancy figure
means nothing under different adverse-price assumptions than the ones it was
computed under.

**Deliberately excluded** — `state_dir`, `gate_file`, `data.cache_dir`,
`paper.poll_seconds`. These are file locations and polling cadence. They do not
change *what was validated*, so moving the bot to another machine or adjusting
the poll interval must not invalidate an approval. A gate that fails for
reasons unrelated to the evidence gets worked around, and a worked-around gate
protects nothing.

**If the binding fails**, the message names the section that moved, e.g.
`configuration changed since approval — 'risk' differs`. Two honest responses:
restore the approved values, or re-validate and re-approve under the new ones.
Regenerating the fingerprint to make the message go away is neither — it
converts the gate into a rubber stamp.

## Recovering from a halt

If the circuit breaker has tripped, or the risk state file is corrupt, trading
stays halted — corrupt state fails closed, so deleting the file does **not**
clear it. Recover deliberately:

```bash
.venv/bin/python -m cli clear-halt --config config.paper.yaml --acknowledge
```

It logs `risk.halt_cleared` with the previous reason. Read that reason first: a
breaker that tripped on real losses is not the same thing as a truncated file,
and only one of them is safe to clear and carry on.

## Documentation Required
- [ ] Decision record stating the max-drawdown threshold and paper start date
- [ ] Summary of paper results (expectancy calculation method, drawdown chart or numbers, notable incidents)
- [ ] Explicit user confirmation that the gate is considered met
- [ ] New decision record unlocking (or refusing) live mode

## After Unlock
- [ ] Live mode still starts at the small default size
- [ ] All circuit breakers remain active
- [ ] First live days treated as higher-observation period (extra logging / tighter manual review)
