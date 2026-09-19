# Seven "AI trading" repos, reviewed against this project's own standards

**Date:** 2026-09-19
**Source:** a YouTube walkthrough ("I went through all of the best finance
GitHubs... I didn't realize how much alpha was actually within these GitHubs").
Transcript supplied by the user, who asked to "chew on the meat and digest
what's nutritional for our build."

Every star count, licence and disclaimer below was **verified against the repo
itself**, not taken from the transcript. Where the video and the repository
disagree, that is noted — it happens more than once, and always in the same
direction.

---

## The headline problem with the source

The video's thesis is that alpha lives in the tooling. This project's own
finding, arrived at expensively, is the opposite, and it is written into
`CLAUDE.md`:

> The binding constraints are position size and data access, not the code.

That is not a difference of opinion. It is the output of arithmetic this repo
already ran: directional prediction needs 73.8–94.8% accuracy against an
achievable mid-50s (`2026-09-14-close-directional-prediction-class.md`); the
detection floor at $5–$10 is ~14 round trips *for a perfect strategy*; eight
structural categories are closed for four underlying causes
(`2026-09-14-structural-edge-inventory.md`).

**Nothing in these seven repos changes σ/μ, the fixed cost per round trip, or
the detection floor.** More analyst agents produce more narrative per hour.
They do not make a faint edge detectable, and they cannot make a negative
expectancy positive. Capability is not edge, and the whole cost of this
project's last month was learning to tell them apart.

That is the gristle. Here is the meat.

---

## Verified findings, repo by repo

| Repo | Video's claim | What the repo actually says | Verdict here |
|---|---|---|---|
| **OpenBB** (73.2k ★) | "free Bloomberg terminal", breadth of data | **AGPLv3.** No documentation of point-in-time data, as-reported-vs-restated, or survivorship handling. Own disclaimer: "The data contained in the Open Data Platform is not necessarily accurate." | **EVALUATING** — see below, the licence and the PIT gap both matter |
| **TradingView MCP** | charts on your behalf | Drives the TradingView **desktop app** | **PARKED** — no Solana DEX coverage |
| **Fincept Terminal** (~32k ★) | research desk, QuantLab | Video itself: "you can do this with Claude anyway, the value is having everything in one place"; QuantLab needs the paid plan | **REJECTED** — UI convenience, not capability we lack |
| **Chinese multi-market repo** (65.1k ★) | watchlist → LLM → verdict dashboard | Video itself: "this won't be a daily driver for me" | **REJECTED** — a notifier over signals we don't have |
| **TradingAgents** | multi-agent trading firm | — | **Already assessed.** In the registry since 2026-09-11 as *reference only, never installed*; it is what flagged the look-ahead-bias class we then audited for |
| **AI Hedge Fund** (63.5k ★) | "turn Claude into Warren Buffett", build a fund | README: **"for educational purposes only and is not intended for real trading"**, **"the system does not actually make any trades"**, and **no profitability claims at all** | **REJECTED as signal.** See below |
| **Alpaca MCP** (972 ★) | the execution layer that ties it together | MIT. Defaults to paper. Own warning: "This server can place real trades and access your portfolio." | **PARKED for tradecc** (wrong venue), **noted for hydra** |

### The AI Hedge Fund gap is worth stating plainly

The video presents this repo as encoding named investors' judgement — "it's
actually studied their historical profile." The repo's own README says it is
educational, executes nothing, and claims no returns. **The repo author is
being straight; the video is doing the overselling.**

What the code actually does is encode stylistic heuristics into prompts. An
LLM told to reason like Graham will produce Graham-flavoured prose about any
ticker you give it. That is a plausible-narrative generator. Whether its
aggregate signal beats buy-and-hold net of costs, out-of-sample, over enough
round trips to clear the detection floor — nothing in the repo measures, and
the README does not claim it does.

Run it through this project's own gate and it fails at **step 1**: no gross
edge per round trip is stated. That is not a technicality. It is the most
common way a hypothesis fails here, and it fails before any data is touched.

### OpenBB is the one that touches a real constraint — and still may not help

Data access is one of the two binding constraints, so OpenBB deserves a
serious look rather than a reflex. Two findings temper it:

1. **It is AGPLv3.** This project reviewed AGPL-3.0 six days ago for PineTS
   (`2026-09-14-pinets-license-review.md`) and concluded §13's
   network-provision clause is the real forward risk for a trading bot that
   might ever expose a dashboard. **OpenBB carries the identical clause**, and
   the video never mentions the licence at all.
2. **Breadth is not the axis that blocks us.** The inventory blocks
   copy-trading and pump.fun on *point-in-time-clean* enumeration — data as it
   stood at decision time, free of survivorship and restatement. OpenBB's
   documentation says nothing about point-in-time snapshots, as-reported
   versus restated figures, or survivorship. Aggregating more current-snapshot
   providers does not produce PIT-clean history, and quietly assuming it does
   is exactly the look-ahead trap this repo already audited for once.

So: worth evaluating on the narrow question *"does any OpenBB provider expose
as-reported-at-the-time history?"* — and not worth adopting on breadth alone.

### Alpaca: right idea, wrong venue, and one flag from live

Genuinely the most useful thing in the video, and the one place it is
appropriately modest ("not a lot of stars" — 972, correct). Real broker, real
paper-trading API, MIT, defaults to paper.

Two reasons it is not a tradecc adoption:

- **Venue mismatch.** US equities/options/crypto. tradecc is Solana spot via
  Jupiter. It does not execute what this bot trades.
- **Paper and live are one boolean apart.** `ALPACA_PAPER_TRADE: "false"` is
  the entire distance. For a project whose rule 5 is *no live trading until
  the validation gate is met*, a tool where live mode is a single env-var flip
  — set in a config file an LLM can edit — is a risk surface worth naming out
  loud, not a convenience.

It is a better fit for **hydra**, which already specifies a CEX venue slot
(`robinhood_crypto`) and a broker-adjacent execution plane. Logged there as a
candidate, not adopted.

---

## What was actually nutritional

Three things, none of which is a repo to install.

**1. The gate should be callable, not remembered.** Every claim in that video
would have been resolved in seconds by arithmetic this repo already owns. It
wasn't, because the arithmetic lived in a skill document that runs only when
somebody reads it. That is now fixed: `research/edge_gate.py` and the MCP
server `research/edge_gate_mcp.py` make the four-step gate a function and a
tool call. **This is the real deliverable from the video** — not adopting
anything it recommended, but noticing that nothing it recommended could have
been screened quickly.

**2. "Educational only" disclaimers are load-bearing and get stripped in
transit.** The AI Hedge Fund README is honest. By the time the claim reaches a
viewer it has become "build a fund with $100k deployed capital." When
assessing any future repo, read the repo's own disclaimer before the
enthusiasm of whoever is recommending it.

**3. Star count is popularity, not validation.** 63.5k stars sit on a repo
that explicitly makes no profitability claim. Stars measure how many people
liked an idea, which is precisely the quantity that says nothing about whether
an edge survives costs and sampling.

---

## What this does not do

It does not reopen any strategy. Per `CLAUDE.md`, the inventory is read first
and nothing here escapes any of the four causes — these are tools, not
hypotheses. The one genuinely open thread is the narrow OpenBB
point-in-time question, which is a *data-access* question and is logged as
EVALUATING rather than acted on.
