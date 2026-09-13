# Evaluation: SocratiCode (github.com/giancarloerra/SocratiCode)

**Date:** 2026-09-11
**Verdict: do not adopt at current scale.** Not a quality judgement — the
tool is well built and its defaults are safe. It solves a problem this
repository does not have, and the numbers below are the reason.

Source was cloned read-only at `socraticode@1.13.3` and read directly.
Nothing was installed, built, or executed.

## The four conditions, checked

### 1. Fully local, no cloud embeddings — ✅ can be guaranteed

`src/services/embedding-config.ts`:

```ts
const rawProvider = process.env.EMBEDDING_PROVIDER || "ollama";
```

Local (`ollama`) is the hard default. The cloud providers are opt-in on
**two** independent conditions: `EMBEDDING_PROVIDER` must be explicitly
set to `openai`/`google`, *and* the matching key must be present —
`provider-openai.ts` throws without `OPENAI_API_KEY` rather than falling
back. Key presence alone never flips the provider, which matters here
because this environment already carries unrelated API keys.

No telemetry, analytics, or phone-home found anywhere in `src/`
(searched for posthog/segment/amplitude/mixpanel/telemetry).

So the "fully local" requirement is satisfiable and verifiable: leave
`EMBEDDING_PROVIDER` unset and set no embedding-provider keys.

### 2. AGPL-3.0 terms — ✅ no blocker for our use

`LICENSE` is the genuine AGPL-3.0 text; `package.json` declares
`AGPL-3.0-only`. The project is **dual-licensed** — `LICENSE-COMMERCIAL`
offers a paid alternative without copyleft obligations (Altaire Limited).

For the use we contemplated — running it **unmodified**, as a separate
local MCP server process, not redistributed and not offered to remote
users — AGPL imposes no obligation on TradeCC's own source. AGPL §13's
network clause triggers on *modified* versions made available to remote
users over a network; neither applies. Using AGPL software does not
relicense the code it reads.

The commercial license only becomes relevant if we ever modified and
distributed it, or offered it as a network service. Neither is planned.

### 3. Infrastructure — ❌ not available in this environment

| Requirement | Status here |
|---|---|
| Ollama (embeddings) | **absent** — no binary, nothing on `:11434` |
| Qdrant (vector store) | **absent** — nothing on `:6333` |
| Docker | present (`/usr/bin/docker`) |
| Node ≥ 18.17 | present (node 22) |

Docker being present means it *could* bootstrap Qdrant and Ollama, but
that is two containers plus an embedding-model download (nomic-embed-text
is ~270 MB) inside an ephemeral session container that is reclaimed on
inactivity — paid on every session.

### 4. Efficiency claim against our own usage — ❌ does not hold

This is the decisive finding. Measured on this repository, not quoted
from the project's README:

| Measure | Value | ≈ tokens |
|---|---|---|
| Entire tracked repo (123 files) | 507,936 bytes | **~127,000** |
| All `src/*.py` (68 files) | 296,785 bytes | **~74,000** |
| Mean source file | 4,364 bytes | **~1,090** |
| Largest single file (`test_paper.py`) | 14,408 bytes | **~3,600** |

A semantic index earns its keep when a codebase cannot fit in context and
navigating it costs many exploratory reads. **Our entire codebase is
~127k tokens**, and the part actually navigated during development —
`src/*.py` — is ~74k. A targeted `Grep` costs a few hundred tokens; a
targeted `Read` of an average file costs ~1,090.

Observed pattern across this session's work, including the point-in-time
audit that touched eight files: navigation resolved in **one to three
calls** each time — grep a symbol, read the region it names. Finding
every `evaluate_position` call site was a single grep. There is no
repeated large-context scan for an index to displace.

Set against that: two containers, a model download, an index build, and
incremental re-indexing on every edit — to accelerate lookups against a
corpus small enough to fit in context roughly twice over.

**Honest limitation of this finding.** Because Ollama is unavailable
here, this is not a measured A/B of SocratiCode's own performance. The
repository measurements are real; the savings side is a projection from
those numbers and observed call patterns. What is demonstrated is that
the *headroom* for savings is small, not that the tool underperforms its
claims.

## Verdict and revisit trigger

Moved to **PARKED** in `external-tools-registry.md` — a sound tool, the
wrong scale. Revisit if either becomes true:

- The repository passes roughly **500k tokens** (~4× current) or a few
  thousand files, such that targeted grep/read stops resolving in a
  handful of calls; or
- A large external corpus is vendored in (a dependency tree, historical
  datasets) that must be navigated semantically.

If revisited, the adoption conditions are already established: pin a
specific version, leave `EMBEDDING_PROVIDER` unset, set no
embedding-provider API keys, and re-verify the defaults above against the
pinned source rather than trusting this write-up.
