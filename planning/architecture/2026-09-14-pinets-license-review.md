# PineTS licence review — does using it create an obligation?

**Date:** 2026-09-14
**Status:** Report only. **PineTS is not installed and nothing here proposes
installing it.**
**Source:** the LuxAlgo/PineTS repository itself, not a third-party summary.

## What it is

An open-source transpiler and runtime that runs Pine Script with 1:1 syntax
compatibility on **Node.js and browsers** (plus Deno/Bun). Originally by
Alaa-eddine K., since acquired by LuxAlgo.

## The licence

**AGPL-3.0, with a commercial dual-licence option** (business@luxalgo.com for
proprietary or closed-source use without AGPL obligations).

## The obligation, for this project specifically

**At present: none.** TradeCC is private, non-commercial research that is
neither distributed to others nor offered as a network service. AGPL-3.0's
copyleft triggers on **conveying** the software or **providing it over a
network** — internal and personal use creates no source-release obligation.

The AGPL's distinguishing feature over GPL is §13: making the software
available to users **over a network** counts as distribution. That is the
clause to watch, because it catches deployments that feel private:

| Scenario | Obligation |
|---|---|
| Running the bot on your own machine or VPS, for yourself | **None** |
| Keeping the repository private | **None** |
| Publishing the repository publicly with PineTS code or a derivative in it | Release under AGPL-3.0 |
| Offering the bot as a hosted service, SaaS, or public API others interact with | **Release the whole work under AGPL-3.0**, even without distributing binaries |
| Letting anyone else run a copy | Release under AGPL-3.0 |
| Selling it, or embedding it in something proprietary | Commercial licence from LuxAlgo |

**The practical risk is the fourth row, and it is not hypothetical for a
trading bot.** "Let a friend use it", "put a dashboard on it", "run it for
someone else's capital" all plausibly cross into network-provision, and the
obligation then reaches the *entire combined work* — the risk engine, the gate,
the execution stack — not just the PineTS portion. AGPL's reach is the whole
derivative, and mixing it into a codebase you may later want to keep closed is
a decision that is cheap now and expensive to reverse.

**I am not a lawyer and this is not legal advice.** It is a reading of the
licence text and the repository's own statements, recorded so the decision is
made with the terms visible rather than after the code is entangled.

## The reason the licence may not matter anyway

**PineTS is Node.js/browser. This project is Python.** Using it means running a
second runtime and marshalling data across a process boundary, for the sole
purpose of executing Pine Script — a language nothing in this repository uses.
That cost exists independently of the licence.

And per `2026-09-14-close-directional-prediction-class.md`, the indicators Pine
Script expresses are **directional**, which is the class this project just
closed on measurement grounds. A faster way to compute EMA/RSI variants does
not move the 73.8% accuracy bound; it computes the same unreachable thing more
conveniently.

## Recommendation

**Do not install it, and not primarily for licence reasons.** The licence is
manageable while the repo stays private and unhosted. The stronger objections
are that it adds a second runtime and that it serves a strategy class already
closed.

If a future need genuinely calls for Pine Script execution, the decision has
two parts and both should be explicit: (a) accept AGPL-3.0 and the constraint
it places on ever hosting or distributing this bot, or obtain the commercial
licence; and (b) justify the second runtime on its own merits.

**Reading the documentation and referencing concept definitions creates no
obligation at all.** That is what the LuxAlgo MCP Library tools are for, and it
is how this project already treats TradingAgents, freqtrade and jesse.
