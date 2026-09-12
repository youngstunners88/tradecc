# Paper → Live Validation Gate Checklist

Use before any request to unlock live mode.

## Pre-requisites (must already be true)
- [ ] Risk controls implemented and unit-tested (see tradecc-risk-controls)
- [ ] Key loading follows safe solders pattern; no secrets in repo
- [ ] Every trade path simulates before send
- [ ] Position size still defaults to $5–$10
- [ ] Incident logging process exists under ops/

## Gate Criteria (from mvp_spec.md)
- [ ] ≥ 30 days of paper mode against real market data
- [ ] Positive expectancy **after** realistic fees + slippage + Jupiter tiers
- [ ] Max drawdown ≤ pre-agreed threshold (threshold written in a decision record before the period started)
- [ ] Paper logs are complete enough to reconstruct every trading day
- [ ] No unexplained multi-day outages during the period

## Documentation Required
- [ ] Decision record stating the max-drawdown threshold and paper start date
- [ ] Summary of paper results (expectancy calculation method, drawdown chart or numbers, notable incidents)
- [ ] Explicit user confirmation that the gate is considered met
- [ ] New decision record unlocking (or refusing) live mode

## After Unlock
- [ ] Live mode still starts at the small default size
- [ ] All circuit breakers remain active
- [ ] First live days treated as higher-observation period (extra logging / tighter manual review)
