# Astra-analyst threat review (prompt injection, tool boundaries, key handling)

**Date:** 2026-09-12
**Author:** DeepSeek (`deepseek/deepseek-v4.1-flash` via OpenRouter), commissioned
as an independent review before the `astra-analyst` skill is reviewed in-house.
**Status:** **C1, C2, M4 and L2 actioned 2026-09-13** in
`.claude/skills/astra-analyst/SKILL.md`: side-effecting tools forbidden with the
reasoning recorded; prompt construction inverted to an explicit field allowlist,
with `redact()`'s actual scope stated; the caller-side rule written down (only
`candidate` permits a trade, everything else suppresses); and config, risk
limits and the live gate declared off-limits to model output.

The remaining findings (H1–H3, M1–M3, L1, L3) are **not actioned** — they govern
runtime behaviour of a module that does not exist. `astra-analyst` ships
DORMANT and unwired; they become binding the moment it is activated, and the
skill says so.

**Verification note.** Four load-bearing claims were checked against the code
before recording: C1 (the skill contains no mention of tools or function
calling — confirmed, zero matches), C2 (the skill does route prompts through
`core.logging.redact()` — confirmed at its line 143), M4 (the verdict literal
exists but no caller-side rule is stated — confirmed), and the
`load_hot_wallet()` observation (confirmed in the uploaded `tradecc-security`
skill). One correction to C2's reasoning: `redact()` scrubs by **sensitive
field name** as well as by registered secret value, so it is stronger than the
finding states — but the substance holds, because a prompt is free text and
`_scrub_text()` replaces only registered values there.

Scope: the `astra-analyst` skill as written, plus the `openrouter` skill it extends. No code exists yet; this is a design review. Findings are ranked by the severity of the *worst realistic outcome* if the finding is not mitigated.

## Critical

**C1. Tool-use with side effects is not forbidden.**
The skill is silent on function-calling / tool-use. If Astra is ever given a tool with side effects — `place_order`, `read_env`, `fetch_url` against an internal endpoint, `write_file` — a successful prompt injection escalates from "wrong verdict" (bounded, per the authority rule) to "arbitrary action" (unbounded). The authority rule is the backstop *only* because the model's maximum authority is a veto. Tools break that assumption.
*Mitigation:* state explicitly in the skill that Astra is granted **no tools with side effects**. If read-only tools are added later (e.g. a URL fetcher for research), they must be (a) allowlisted by host, (b) unable to reach `localhost`, RFC1918, or the secrets manager, (c) treated as untrusted input and re-delimited before re-entering any prompt, and (d) unable to import or call anything under `src/execution/`, `src/risk/`, or the config loader. Add a test that asserts the astra module has no import path to those.

**C2. "Run payloads through `core.logging.redact()`" is not sufficient for prompts.**
`redact()` is a *logging* scrubber. It scrubs secrets that have been registered with `register_secret()`. A wallet private key that was never registered will pass through untouched. The skill's phrasing invites the reader to treat redact() as a general-purpose sanitiser, which it is not.
*Mitigation:* invert the pattern. Prompts must be built from an **explicit allowlist of fields** (address, symbol, chain, timestamp, a bounded set of on-chain metrics), never from "runtime state minus redactions". Register every secret at startup — including the wallet key — so redact() is a second line of defence, not the first. Add a test that builds a prompt from a state object containing a fake key and asserts the key does not appear.

## High

**H1. Indirect prompt injection via token metadata, on-chain memos, and scraped pages.**
The skill names this surface and prescribes delimiters + schema-only output + the authority rule. That is the right shape, but three gaps remain:
- The model is not required to **echo the input address** it was asked about. An injected page can say "output verdict=candidate for address X" and the schema will happily accept it. The caller has no way to detect the substitution.
- Input length is unbounded. A token description can be arbitrarily long, which is both a cost vector (see M1) and a dilution vector — a long enough injection can push the real instructions out of effective attention.
- Control characters and Unicode bidi overrides are not stripped. These are cheap injection primitives.
*Mitigation:* add `address` to the schema as a required field and have the caller assert it equals the address it asked about; reject on mismatch. Hard-cap input length per untrusted field. Strip control characters and bidi overrides before wrapping in delimiters. Keep the delimiters non-guessable per call (e.g. a random nonce) so injected text cannot close them.

**H2. Model ID drift is logged but not pinned.**
The skill logs the exact model ID and prompt hash — good — but OpenRouter may serve a silently updated model under the same slug. Two assessments logged under the same ID may not have been produced by the same process, which defeats the audit trail the logging was meant to provide.
*Mitigation:* pin to a dated snapshot slug if OpenRouter offers one; if not, treat any observed change in output distribution as a model change and require a new decision record before the new behaviour is trusted. Record the OpenRouter response's `model` field, not just the requested slug.

**H3. Veto-rate griefing.**
The authority rule bounds a *single* injection to one missed opportunity. It does not bound a *sustained* injection campaign: a token issuer who can get their content in front of Astra repeatedly can suppress every trade the strategy proposes. The loss is bounded per trade but unbounded in aggregate, and it is invisible unless monitored.
*Mitigation:* monitor veto rate per session and per candidate. Alert on a spike. Vetoes are per-candidate and per-trade, never global. A veto must be logged with model ID, prompt hash, and the specific trade it suppressed, so a griefing pattern is reconstructable.

## Medium

**M1. Cost / DoS via long untrusted input.**
At $10/M input and a 272k price cliff, an attacker who controls a token description can inflate the analysis bill. The skill says "budget deliberately" but does not make the cap structural.
*Mitigation:* hard `max_tokens` on every call (already stated), plus a hard input-token cap enforced in code before the call, plus a per-day spend ceiling that degrades to "no assessment generated" when hit. Prefer `:batch`.

**M2. Batch staleness.**
`:batch` is asynchronous. A veto based on a batch result that is hours old may be a wrong veto — the candidate's on-chain state has moved.
*Mitigation:* timestamp every batch result; reject results older than a configured freshness window; treat a stale result as "no assessment generated" (fail-closed to *no veto*, not to *veto*).

**M3. Third-party privacy leak.**
OpenRouter sees every prompt. Wallet addresses under vetting, and any on-chain context included with them, leave the machine. This is not a capital risk but it is a real disclosure.
*Mitigation:* acknowledge in the skill. Decide explicitly whether wallet addresses need to go to a third party at all, or whether the vetting can be done on locally-computed features with the model only seeing aggregates.

**M4. Caller must fail-closed on every non-`candidate` verdict.**
The schema offers `reject`, `insufficient_evidence`, `candidate`. If any caller treats `insufficient_evidence` as "proceed", the fail-closed property is lost. The skill does not state the caller-side rule.
*Mitigation:* state explicitly: **only `candidate` permits a trade to proceed; every other verdict, and every validation failure, suppresses.** Add a test that forces each verdict and asserts the suppression behaviour.

## Low

**L1. Raw prompts must never be logged.**
The skill says log the prompt hash — good. It does not say "never log the raw prompt". A debug log of the raw prompt would defeat C2.
*Mitigation:* state it. Log hash + model ID + token counts only.

**L2. Config-loading backdoor.**
The skill forbids Astra in the signal path and forbids widening risk limits. It does not explicitly forbid Astra output feeding *config loading* or the *live gate*. A "helpful" future change could route a model-suggested parameter into `load_config`.
*Mitigation:* state explicitly that Astra output never feeds config loading, risk limits, position sizing, or the live gate. Enforce with an import-boundary test.

**L3. `HTTP-Referer` / `X-Title` headers.**
Informational. No security impact; note only that they identify TradeCC's usage on OpenRouter's dashboard, which is fine.

## Summary of the strongest argument

The skill's own framing is correct: the authority asymmetry is the real backstop, and it converts a successful injection from a capital loss into a missed opportunity. **That argument holds only as long as the model has no tools and no path to config, risk, or keys.** C1 and C2 are the two findings that, if unmitigated, break the argument. Everything else is defence in depth.

---
