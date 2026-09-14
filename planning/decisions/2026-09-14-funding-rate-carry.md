> **Provenance:** DeepSeek-assisted (`deepseek/deepseek-v4-pro-0813` via
> OpenRouter, 2026-09-14). Drafted by the model, reviewed and verified before
> adoption. Every numeric claim was re-derived independently and all held —
> see **Review record** at the end. The draft's own
> [Source]/[Derived]/[Recalled]/[Inferred] tags are the model's and were spot-checked,
> not taken on trust.
>
> Source supplied to the model: `planning/architecture/2026-09-14-structural-edge-inventory.md`.

# Funding-rate carry on hold — wrong venue, wrong capital scale

**Date:** 2026-09-14  
**Status:** On hold — closed by scope and capital, not by impossibility  
**Source of the verdict this supplies:** `planning/architecture/2026-09-14-structural-edge-inventory.md`, ledger row: *Funding-rate carry | On hold | Wrong venue; $100–500 minimum*

## Decision

Funding-rate carry remains on hold because it requires a perps venue and a capital scale the source records as a $100–$500 minimum, which is categorically outside this project’s Solana-spot-only, $5–$10 retail account constraint; this record supplies the missing reasoning for a previously uncited ledger verdict rather than a new investigation.

## What this record is and is not

The inventory audit explicitly noted that funding-rate carry and DEX market-making warnings “appear nowhere in this repository” and were “supplied as established findings.” This record closes the citation gap for funding-rate carry. It is not a new empirical study, and no new venue data has been analyzed here. Where a number below comes from repository text it is marked **[Source]**; where it is arithmetic from such a number it is marked **[Derived]**; where it comes from general market knowledge rather than repository data it is marked **[Recalled]**; where it is a conclusion drawn from the source’s constraints it is marked **[Inferred]**.

Across the eight-category ledger, this is the one category closed by scope and capital rather than by an impossibility. Latency, adverse selection, data infrastructure, and detection floor close the other categories for reasons that cannot be fixed by simply adding capital. Funding-rate carry is different: the mechanism is real, but the project is not in the venue or at the capital scale where the mechanism can be accessed.

## Mechanics

A perps funding rate is a periodic payment between long and short perp traders intended to keep the perp price close to spot. **[Recalled, standard mechanism]** When funding is positive, longs pay shorts; when it is negative, shorts pay longs.

The delta-neutral carry is:

- buy spot,
- short the same notional of the perpetual.

The spot and perp legs offset each other on price movement, so the position is approximately flat to the underlying asset. The trade’s return comes primarily from the funding stream on the short perp leg, minus fees, funding on adverse intervals, transfer/custody costs, and any execution slippage. **[Derived from mechanism]**

What the trade actually earns is not price appreciation. Net carry is approximately:

> funding received on the perp short  
> minus trading fees and spread  
> minus any funding paid when funding flips negative  
> minus the cost of capital split across two legs  
> minus liquidation tail risk.

At a small scale, the last two items dominate and the gross funding stream is too small to matter.

## Realistic magnitude of funding rates

The repository contains no historical funding-rate dataset, so the figures in this section are **[Recalled]** — general market knowledge, not repo-verified evidence.

Major perps venues commonly use an 8-hour funding interval. **[Recalled]** As an order-of-magnitude guide:

| 8-hour funding rate | Annualized if sustained (× 3 × 365) | Typical context |
|---|---:|---|
| 0.01% | 10.95% | large-cap perps baseline on major CEXs |
| 0.03% | 32.85% | common mid/alt perp regime |
| 0.10% | 109.5% | momentum or mania, usually short-lived |

The annualized figures are arithmetic **[Derived]**: e.g., `0.01% × 3 × 365 = 10.95%`. They are not a prediction and not a sustainable return, because funding does not stay fixed.

How often funding is negative is regime-dependent. **[Recalled]** Over a full market cycle, large-cap perps on major venues may be negative on the order of 20–40% of 8-hour intervals. In a sustained selloff, negative funding can persist for many consecutive intervals; in a bull-mania regime, positive funding can persist. Smaller assets and SOL perps can be more volatile. I cannot defend the 20–40% figure from any repository file; there is no such dataset here. Treat it as illustrative, not as a trading input.

At this project’s scale the gross numbers are not meaningful even if the trade were executable. If one could put on an un-levered $5–$10 notional carry:

- at 0.01% per 8h: **$0.0005–$0.001 per interval**;
- at 0.10% per 8h: **$0.005–$0.01 per interval**.

Those figures are arithmetic **[Derived]**. They are below any realistic fee, withdrawal, or operational minimum. The reported $100–$500 minimum is the actual blocker, not the potential carried income.

## Why this is structural, not directional

Funding-rate carry does not require predicting price. The two legs cancel first-order asset exposure, and the expected return comes from the funding spread. That is what makes it structurally different from the directional-prediction category that was closed on the detection floor **[Source]**.

Directional prediction closes because the expected edge is smaller than measurement can resolve at this size. Funding-rate carry does not fail that test. It fails earlier: at the venue and margin step. It is not that the edge is too small to detect; it is that the trade cannot be put on at all within the current scope.

## Binding constraints at this project’s scale

1. **Venue is wrong.** The project is Solana spot only. A short perpetual requires a perps venue, whether CEX or perp DEX. That is a scope change, not a larger position on the existing stack. **[Source/Inferred]**

2. **The reported capital minimum is 10–100× the current position size.** The ledger gives $100–$500 as the minimum. A $10 account is 10–50× below the lower bound; a $5 account is 20–100× below it. **[Source/Arithmetic]**

3. **The source does not say whether the $100–$500 is per leg or total.** Two-legged carry is structurally a split-capital position: spot consumes one side, perp margin consumes the other. If the minimum is per leg, the real minimum is roughly $200–$1,000 plus liquidation buffer. If the minimum is total, there is no buffer at the low end. This ambiguity is worth resolving before any future test. **[Inferred]**

4. **Liquidation risk on the short perp leg is real even though the book is delta-neutral.** Delta-neutral means the spot rise offsets the perp loss over time, but not that margin will be available during a sharp basis dislocation. A short perp marked against rising spot needs margin, while the spot leg may not be instantly or cheaply convertible at the same venue.

5. **Making it operable requires changing the actual constraints, not the strategy.** The minimum useful scale is at least the source’s lower bound of $100–$500 per leg, plus enough buffer to survive negative funding and basis widening. The audit’s “change the capital scale materially” response is the relevant path. **[Source]**

## Risks that delta-neutrality does not solve

Delta-neutrality removes most first-order price direction risk. It does not remove:

- **Funding flipping negative.** The short perp then pays funding, and the trade carries a negative stream until the position closes or funding reverts. Frequency and magnitude are regime-dependent; the repo has no dataset to model this.
- **Exchange/counterparty risk.** A spot leg on one venue and a perp leg on another, or both on a CEX, introduces custodial, withdrawal, API, and venue-solvency risk. Delta-neutral returns can be wiped out by platform failure.
- **Liquidation of the perp leg during a spot-perp basis dislocation.** If the basis widens against the short, the perp leg loses mark-to-market value. If the position cannot meet margin, the perp leg is liquidated, crystallizing the loss while the spot leg remains — turning a temporary basis move into a permanent one-sided loss.
- **Basis risk on exit.** A perp has no fixed expiry, so the trade is not guaranteed to converge at a known terminal date; the exit basis can differ from the entry basis.

## What was considered and rejected

- **Retaining the verdict without citation.** Rejected because an undocumented verdict is one nobody can check and anybody can accidentally repeat — the exact problem the audit named.
- **Treating the missing citation as if the verdict were doubtful.** Rejected because the scale mismatch is independently decisive: the trade needs a venue and minimum capital this project does not have.
- **Running a “micro” carry at $5–$10 anyway.** Rejected because it is below the reported minimum and, even in an illustrative un-levered case, would generate sub-cent funding flows before fees.
- **Using the existing Solana spot stack as a workaround.** Rejected because the short-perp leg cannot be created by spot-only execution; adding it is a different venue and risk profile.
- **Reclassifying this as a directional trade.** Rejected because that would abandon the structural property and fall back into the detection-floor closure.

## Reopening condition

Reopen this decision only if the project changes one of the two named constraints: the venue access or the capital scale. Specifically, it becomes testable only when there is at least $100–$500 of risk capital per leg on a perps venue **[Source, with the per-leg ambiguity noted]**, plus a liquidation buffer, plus the ability to run the two-legged position and record funding, fees, and basis dislocations. Testable means examining actual funding history and execution against those costs — not known-good.

The reason is not a rule: at the current scale, the trade is not merely unattractive; it is unreachable. Reopen when the reach problem is solved, not when someone finds a cleverer description of the same strategy.

---

## Review record

Re-derived before adoption. Unlike the LVR record, nothing here needed
correcting — one malformed table separator was the only edit.

| Claim | Verification |
|---|---|
| 0.01% per 8h → 10.95% annualised | `0.0001 × 3 × 365 = 0.1095` ✓ |
| 0.03% → 32.85%, 0.10% → 109.5% | ✓ by the same arithmetic |
| $5–$10 notional at 0.01%/8h → $0.0005–$0.001 per interval | `0.0001 × 5`, `× 10` ✓ |
| $5–$10 at 0.10%/8h → $0.005–$0.01 | `0.001 × 5`, `× 10` ✓ |
| $10 is 10–50× below a $100–$500 minimum; $5 is 20–100× | ✓ |

**Left flagged, not verified:** the claim that large-cap perp funding is
negative in 20–40% of 8-hour intervals. The model flagged it as unverifiable
from this repository and it stays flagged. It is not load-bearing — the
verdict turns on venue access and capital scale, both of which bind before
any funding statistic matters.

**The one substantive addition the review agrees with:** the draft noticed
that the ledger's "$100–$500 minimum" does not say whether it is per leg or
total, and that a two-legged position plausibly doubles it. That ambiguity was
not in the source and is worth resolving before this is ever reopened.
