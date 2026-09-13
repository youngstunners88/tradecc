---
name: web-research-vetting
description: GATED — use Firecrawl, TinyFish, or BrowserUse to gather qualitative research on candidate wallets for v0.2 copy-trading vetting (research/wallet-tracking/). Do NOT use this skill for v0.1 work, for core price/OHLC data, or for anything execution-related — v0.1 is momentum/TA only and copy-trading is explicitly out of scope until the user greenlights v0.2. If asked to use these tools before v0.2 is greenlit, say so and confirm scope with the user rather than proceeding.
---

# Web Research Tools — Gated to v0.2 Wallet Vetting

This skill exists so the tools are documented and ready, not so they get
used early. Per `planning/decisions/2026-09-09-strategy-and-stack.md`,
copy-trading is v0.2, not v0.1 — this skill should not trigger on
anything related to the current momentum/TA build.

## When this actually applies (v0.2, once greenlit)
Researching a candidate wallet for `research/wallet-tracking/` before it
can be considered a copy-trading target — per that workspace's
`CONTEXT.md`, a wallet needs win rate, max drawdown, median hold time,
and red-flag checks logged before it's eligible.

- **Firecrawl** — pull a wallet's public activity, a project's docs, or
  socials into clean markdown for qualitative read (e.g., does this
  wallet's public presence match its on-chain claims; does a token it
  holds have real docs or is it a shell).
- **TinyFish / BrowserUse** — structured extraction from sites that
  don't expose an API (e.g., pulling a leaderboard page), or for
  multi-step browsing tasks a plain scrape can't handle.

## Hard boundaries
- **Never a substitute for on-chain data.** Win rate, drawdown, and hold
  time come from real on-chain transaction history via a proper RPC/API
  (Helius, Solscan), not from scraping. These tools are for qualitative
  supplementary signal only.
- **Never used for core v0.1 price/OHLC data.** That's Helius/Jupiter's
  job — scraping is not an appropriate price-data source for a system
  making trade decisions.
- **Respect target sites' terms of service.** Don't scrape behind
  login walls or in ways that violate a site's stated terms — flag to
  the user if a research target requires that instead of working around
  it.

## Logging requirement
Any finding from these tools that feeds into a wallet-vetting decision
must be written into `research/wallet-tracking/` with a source link and
date — not left implicit in a chat response.
