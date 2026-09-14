---
name: structural-edge-inventory
description: The complete ledger of trading-edge categories considered for TradeCC, each with its verdict and the reason behind it. Read this BEFORE proposing, researching, or building toward any strategy idea — including one that feels new, and especially when a reframe ("structural not directional", "event-driven", "mechanical") makes the space feel freshly open. It is not. Every category on the list is closed, and this records why.
---

# Structural Edge Inventory

When directional prediction closed
(`planning/decisions/2026-09-14-close-directional-prediction-class.md`), the
natural next thought was: *fine — the edge must be structural rather than
predictive.* That reframe is correct and it is **not** a new frontier. Every
structural category available to a $5–$10 Solana spot trader had already been
examined, most of them before this project wrote a line of code.

This skill exists so that conclusion survives a fresh session, and so nobody
re-derives a closed verdict at the cost of another test window.

## The ledger

| Category | Verdict | Reason | Recorded where |
|---|---|---|---|
| Cross-DEX arbitrage | **Rejected** | Latency race; dominated by professional, co-located, low-latency operators | `2026-09-09-strategy-and-stack.md`, `CLAUDE.md:31`, `mvp_spec.md` |
| Sniping new launches | **Rejected** | Same latency race, plus MEV exposure | `2026-09-09-strategy-and-stack.md`, `CLAUDE.md:31` |
| Copy-trading (rigorous) | **Blocked** | Data infrastructure, not economics — point-in-time-clean wallet enumeration needs ~9,982h at the cheapest pool's 0.41 tx/s | `2026-09-13-copy-trading-wallet-universe.md` |
| pump.fun graduation timing | **Parked** | Data infrastructure — historical middle window unreachable; only forward collection works, a weeks-long commitment that was declined | `2026-09-13-pumpfun-graduation-duration.md`, PR #5 |
| Directional prediction | **Closed (class)** | Requires 73.8–94.8% direction accuracy; achievable is mid-50s | `2026-09-14-close-directional-prediction-class.md` |
| Capital-range increase | **Closed** | Costs were never the binding constraint; strategy asymptotes at ~22% of buy-and-hold | `2026-09-13-capital-range-sensitivity.md` |
| DEX market-making / LP | **Rejected** | Loss-versus-rebalancing — a passive LP is adversely selected by arbitrageurs; the fee income does not compensate | ⚠️ **not recorded in-repo** (see below) |
| Funding-rate carry / basis | **On hold** | Requires a perps venue (not Solana spot), and a $100–500 minimum — outside both the current scope and the $5–$10 size | ⚠️ **not recorded in-repo** (see below) |

## Two verdicts are asserted but undocumented

**DEX market-making (LVR) and funding-rate carry do not appear anywhere in the
repository.** They were stated as established findings, and they are plausible
ones, but a future session grepping `planning/` will not find them and may
re-open either as a "new idea".

Treat them as **real verdicts with missing citations**. Either is a legitimate
candidate for a proper decision record if it is ever revisited — not because
the verdict is doubted, but because an undocumented verdict is one nobody can
check and everybody can accidentally repeat.

## The reasons collapse into four

This is the useful part. Eight categories, four causes:

1. **Latency / infrastructure races** — cross-DEX arb, sniping. Lost to
   co-located professionals before we start.
2. **Adverse selection** — market-making. Being the passive side means being
   picked off by whoever is faster.
3. **Data infrastructure** — copy-trading, pump.fun. The signal may well exist;
   we cannot obtain point-in-time-clean data to test it at our access level.
4. **Detection floor** — directional prediction, capital-range. The edge is
   smaller than the measurement can resolve at our size.

**A new idea is not new if it lands in one of those four.** That is the test to
apply before anything else: name the category, name the cause it would have to
escape, and say how it escapes. "It feels different" is not an escape.

## Is anything left?

**No.** Not on this list, at $5–$10 on Solana spot with retail data access.

Every category is closed, and — this is the part worth sitting with — **most
were closed before the project began**, in the original strategy research. The
last two weeks of work did not narrow a wide field. It confirmed, expensively
and rigorously, a field that was already narrow.

Candidates sometimes raised that are **also** closed by the four causes above,
without needing their own investigation:

- *Liquidation hunting* → latency race (cause 1)
- *Stablecoin depeg arbitrage* → latency race when it matters (cause 1)
- *CEX↔DEX listing arbitrage* → latency race, plus venue and capital (cause 1)
- *Statistical arbitrage on correlated pairs* → a spread is still a draw from a
  return distribution (cause 4 — `edge_budget.py` applies unchanged)
- *Routing/fee-tier arbitrage inside Jupiter* → Jupiter already optimises it;
  no residual to capture
- *MEV / sandwiching* → out of scope on conduct grounds, and a latency race

## What that leaves — and it is not a strategy

The honest conclusion is that **the binding constraints are position size and
data access, not the code and not the search effort.** Three responses follow,
and all three are the user's call, not something to build toward:

1. **Accept the finding.** The machinery is complete and correct; there is no
   identified edge to run through it. Stopping is a legitimate outcome of a
   rigorous search, not a failure of one.
2. **Change the capital scale materially.** Funding-rate carry becomes
   examinable at $100–500 on a perps venue. That is a different project with a
   different risk profile, not a bigger version of this one.
3. **Change the data access.** Causes 3 blocks two otherwise-live candidates.
   Paid, historical, point-in-time-clean data would reopen copy-trading and
   pump.fun as *testable* — not as known-good.

## Heavy analysis routes to DeepSeek

When a candidate is genuinely not in the ledger and needs real work — a
literature sweep for whether the mechanism has been measured elsewhere, a
frequency-and-payoff estimate, a draft ledger entry — route the volume work
to `.claude/skills/openrouter-deepseek` (`deepseek/deepseek-v4-pro` via
OpenRouter). The context windows here are large (whole decision records,
whole price series summaries) and that is what the model is cheap at.

The division of labour does not move:

- **DeepSeek drafts.** Literature lookup, arithmetic derivation, formula
  verification against concept definitions from the LuxAlgo reference
  (`planning/architecture/external-tools-registry.md` — reference only, not
  installed), and a first pass at the ledger row.
- **Claude Code orchestrates and reviews.** Which of the four causes the
  candidate must escape, whether the escape argument holds, and whether
  anything is committed — those are not the model's calls.
- **The verdict is the user's.** Per the standing instruction, nothing is
  built toward a structural edge without coming back to them first.

Two constraints carry over verbatim from the DeepSeek skill:

1. **Send it no gate state, no fingerprint data, no wallet information, and
   no secrets.** The ledger, the decision records and public market data are
   all fair game; the bot's runtime state is not.
2. **Any ledger entry or analysis document DeepSeek helped write carries the
   provenance note** — DeepSeek-assisted, reviewed before adoption, numeric
   claims re-derived independently. An undocumented verdict is one nobody can
   check; an unmarked model draft is the same problem wearing a different hat.

## How to use this

**Before proposing any strategy idea:**

1. Find it in the ledger. If it is there, it is closed — read the reason.
2. If it is not there, name which of the four causes it must escape and how.
3. If it escapes all four, run `.claude/skills/edge-viability-check` **before**
   writing any backtest.
4. Only then is it a candidate worth a decision record.

**Add to this ledger whenever a category is closed**, with the reason and the
citation. A verdict nobody can find is a verdict that gets paid for twice.
