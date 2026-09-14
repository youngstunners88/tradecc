"""Delegate heavy-context research to DeepSeek V4 Pro, under the boundary.

This is the working half of `.claude/skills/openrouter-deepseek/SKILL.md`. The
skill states the rules; this is where they are enforced and where the calls
actually happen.

The point of it is a division of context, not just a division of labour:
DeepSeek reads the 200 KB of decision records and price summaries, and the
orchestrator reads the 2 KB that comes back. That is what makes delegation
worth doing when the orchestrator's own budget is the scarce resource.

Three properties are load-bearing:

1. **The guard runs before the client is constructed.** `deepseek_guard`
   allow-lists paths and deny-lists content, and raises rather than redacts.
   No network object exists until it has passed, so there is no window in
   which a forbidden payload could be sent by a later code path.
2. **One retry, never more.** Every attempt is billable and a long reasoning
   call can be expensive. A retry storm against an LLM is a bill, not a
   blip.
3. **Output is marked at the point of creation.** `--out` writes the
   provenance header itself, so an artifact cannot reach the repository
   unmarked by forgetting to add it afterwards.

Usage:

    export OPENROUTER_API_KEY=...            # env var only; never a path
    PYTHONPATH=src .venv/bin/python research/deepseek.py \
        --task edge-viability \
        --question "Derive the required direction accuracy at a 4h horizon." \
        --file research/backtests/2026-09-14_edge-budget.md \
        --out planning/architecture/2026-09-15-some-analysis.md

    # Always cost it first — this makes no call:
    ... --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.logging import register_secret  # noqa: E402
from execution.http import (  # noqa: E402
    HttpTransport,
    ProviderHttpClient,
    RetryPolicy,
    UrllibTransport,
)
from core.rate_limit import RateLimiter  # noqa: E402

from deepseek_guard import ForbiddenPayload, assert_sendable  # noqa: E402

BASE_URL = "https://openrouter.ai/api/v1"
API_KEY_ENV = "OPENROUTER_API_KEY"

# The floating alias, as specified. `--pin` selects the dated snapshot, which
# is the same weights at roughly a third of the price and is what research a
# decision record will cite should use — an alias moves, and a citation to a
# model that has moved cannot be re-run.
MODEL_ALIAS = "deepseek/deepseek-v4-pro"
MODEL_PIN = "deepseek/deepseek-v4-pro-0813"

# USD per token. Verified against the live catalogue 2026-09-14; refresh with
# the command in .claude/skills/openrouter-deepseek/references/models.md.
PRICING = {
    MODEL_ALIAS: {"in": Decimal("1.60"), "out": Decimal("3.20")},
    MODEL_PIN: {"in": Decimal("0.579"), "out": Decimal("1.738")},
}

# A long reasoning call over a large context is slow. The 15s provider default
# is tuned for quote endpoints and would time out every useful call here.
TIMEOUT_SECONDS = 600.0

# Billable attempts. The skill says one retry, then give up and log it.
MAX_ATTEMPTS = 2

# Rough and labelled as such: ~4 characters per token. Used only for the
# dry-run estimate, never for billing, which comes from the response's own
# usage block.
CHARS_PER_TOKEN = 4

BOUNDARY = """
You are a research assistant for a private trading-research repository. Your
role is analysis and drafting only.

You will never be given, and must never ask for: live trading-gate state,
configuration fingerprints, wallet addresses, private keys, or API keys. If
the material you were given appears to contain any of those, stop and say so
instead of using it — that indicates a mistake upstream of you.

Nothing you produce executes. Your output is read and verified by a human
before it is adopted, and any number you derive is re-derived independently
against the repository's own scripts before it changes a decision. Write for
that reader: show the derivation, state your assumptions, and mark clearly
anything you are inferring rather than computing.

Where you are uncertain, say so in the text. A confident wrong number is the
most expensive thing you can produce here, because it reads exactly like a
correct one.
""".strip()

TASKS: dict[str, str] = {
    "inventory-audit": """
Task: audit a proposed trading-edge category against an existing ledger of
closed categories.

The project has closed eight categories for four underlying causes: latency
or infrastructure races, adverse selection, data-infrastructure limits, and a
statistical detection floor. A candidate is not new if it lands in one of
those four.

For the candidate, determine: which existing category it most resembles;
which of the four causes would have to be escaped; whether it actually
escapes it and by what mechanism; and what published evidence exists that the
mechanism has been measured rather than asserted. Conclude with a plain
verdict — closed by cause N, or open pending a viability check. Do not soften
a closure to leave a door open.
""",
    "edge-viability": """
Task: derive the edge a hypothesis must deliver and whether it is available.

Work in gross percent per round trip. The project's fixed cost is about
$0.0127 per round trip and does not scale down, so at a $5 position the
break-even edge is 0.254% and at $10 it is 0.127%. Detection requires
n = (z_alpha + z_beta)^2 * (sigma/mu)^2 round trips; at 95% confidence and
80% power the leading constant is 7.8489.

Show every step of the arithmetic. State which numbers you were given, which
you assumed, and which you derived. Do not round intermediate values. Where a
holding period yields few trades, remember the detection floor rises with the
holding period — one floor does not apply across horizons, and a trade count
must be measured on the same basis as the gross it is paired with.

End with the four gate answers: claimed edge, break-even clearance, detection
clearance, and whether the return distribution plausibly contains it.
""",
    "decision-record": """
Task: draft a decision record.

Format: a title, the date, the decision in one sentence, the reasoning, what
was considered and rejected, and an explicit condition under which the
decision would be reopened. State the reason rather than only the rule — a
rule invites a workaround, a reason does not.

Be concrete about numbers and cite where each came from. If a claim in the
source material is asserted without evidence, say so in the draft rather than
repeating it as established.
""",
    "concept-lookup": """
Task: give the formal definition of a trading or statistical concept.

Provide the standard definition, the formula in unambiguous notation, the
parameters and their conventional values, and the assumptions under which the
formula holds. Note where implementations commonly differ from each other,
and flag any assumption that would be violated by high-noise,
thin-liquidity, 24/7 crypto markets specifically.
""",
    "freeform": """
Task: as stated in the question below. Show your working and mark inference
separately from computation.
""",
}


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    # DeepSeek V4 Pro is a reasoning model: it spends completion budget on a
    # reasoning chain before producing any answer text. Those tokens are
    # billed as completion tokens and are counted inside `completion_tokens`,
    # so this is reported for visibility, never added on top.
    reasoning_tokens: int = 0
    # OpenRouter returns what it actually charged. Preferred over the local
    # price table, which is a snapshot and goes stale silently.
    reported_cost: Decimal | None = None

    def cost_usd(self, model: str) -> Decimal | None:
        if self.reported_cost is not None:
            return self.reported_cost
        price = PRICING.get(model)
        if price is None:
            return None
        million = Decimal(1_000_000)
        return (
            Decimal(self.prompt_tokens) / million * price["in"]
            + Decimal(self.completion_tokens) / million * price["out"]
        )


def build_prompt(task: str, question: str, files: list[Path]) -> tuple[str, str]:
    """Return (system, user). Files are inlined with their paths as labels."""
    system = f"{BOUNDARY}\n\n{TASKS[task].strip()}"
    parts = [f"## Question\n\n{question.strip()}"]
    for path in files:
        relative = path.resolve().relative_to(REPO_ROOT).as_posix()
        parts.append(f"## Source: {relative}\n\n{path.read_text().strip()}")
    return system, "\n\n---\n\n".join(parts)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def call(
    *,
    system: str,
    user: str,
    model: str,
    max_tokens: int,
    seed: int | None,
    api_key: str,
    transport: HttpTransport | None = None,
) -> tuple[str, Usage]:
    client = ProviderHttpClient(
        provider="openrouter-deepseek",
        transport=transport or UrllibTransport(),
        limiter=RateLimiter(20),
        retry=RetryPolicy(max_attempts=MAX_ATTEMPTS),
        timeout=TIMEOUT_SECONDS,
    )
    payload: dict[str, object] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        # Always bounded. A 393k-max-output model with no ceiling is an
        # unbounded bill.
        "max_tokens": max_tokens,
    }
    if seed is not None:
        payload["seed"] = seed

    response = client.request(
        "POST",
        f"{BASE_URL}/chat/completions",
        headers={
            # The key travels in a header, never in the URL or the prompt.
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-Title": "tradecc-research",
        },
        body=json.dumps(payload).encode(),
    )
    body = response.json()
    choices = body.get("choices") or []
    if not choices:
        raise RuntimeError(f"no choices in response: {json.dumps(body)[:400]}")
    choice = choices[0]
    content = (choice.get("message") or {}).get("content") or ""
    usage = body.get("usage") or {}
    completion_tokens = int(usage.get("completion_tokens") or 0)
    reasoning_tokens = int(
        ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0
    )
    raw_cost = usage.get("cost")

    if not content.strip():
        # The failure this actually produces in practice. A reasoning model
        # spends completion budget thinking before it writes anything, so a
        # `max_tokens` that looks generous for the answer can be consumed
        # entirely by the reasoning chain — and what comes back is a
        # length-truncated choice with empty content, not an error. Diagnosed
        # generically ("empty completion") this costs an afternoon; named, it
        # costs one retry with a bigger ceiling.
        if choice.get("finish_reason") == "length":
            raise RuntimeError(
                f"output budget exhausted before any answer text: "
                f"{reasoning_tokens:,} of {completion_tokens:,} completion tokens went to "
                f"reasoning and the response was truncated. Raise --max-tokens "
                f"(currently {max_tokens:,}) and run again."
            )
        raise RuntimeError(
            f"model returned an empty completion (finish_reason="
            f"{choice.get('finish_reason')!r})"
        )

    return content, Usage(
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        reported_cost=Decimal(str(raw_cost)) if raw_cost is not None else None,
    )


def provenance_header(model: str, sources: list[Path], on: date) -> str:
    """Written at creation time so an artifact cannot arrive unmarked."""
    cited = ", ".join(f"`{p.resolve().relative_to(REPO_ROOT).as_posix()}`" for p in sources)
    lines = [
        f"> **Provenance:** DeepSeek-assisted (`{model}` via OpenRouter, {on.isoformat()}).",
        "> Drafted by the model. **Not yet reviewed** — review and independently",
        "> re-derive every numeric claim before adopting this, and replace this",
        "> line with the reviewed form from",
        "> `.claude/skills/openrouter-deepseek/SKILL.md` once you have.",
    ]
    if cited:
        lines.append(f">\n> Sources supplied to the model: {cited}.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", choices=sorted(TASKS), required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--file", action="append", default=[], type=Path,
                        help="Source file to inline. Repeatable. Allow-listed by deepseek_guard.")
    parser.add_argument("--out", type=Path, help="Write the draft here with a provenance header.")
    parser.add_argument("--pin", action="store_true",
                        help=f"Use {MODEL_PIN} — same weights, ~1/3 the price, reproducible.")
    parser.add_argument("--max-tokens", type=int, default=16000,
                        help="Covers the reasoning chain and the answer — a reasoning "
                             "model spends this budget thinking before it writes.")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--dry-run", action="store_true",
                        help="Run the guard and cost the call. Sends nothing.")
    args = parser.parse_args(argv)

    model = MODEL_PIN if args.pin else MODEL_ALIAS
    files: list[Path] = list(args.file)

    # Registration before use, in the same order `src/cli.py:_bootstrap` does
    # it — so the key is masked before anything here can log.
    api_key = (os.environ.get(API_KEY_ENV) or "").strip()
    register_secret(api_key or None)

    try:
        assert_sendable(
            files=files,
            texts={"--question": args.question},
            repo_root=REPO_ROOT,
        )
    except ForbiddenPayload as exc:
        print(str(exc), file=sys.stderr)
        return 2

    system, user = build_prompt(args.task, args.question, files)

    if args.dry_run:
        prompt_tokens = estimate_tokens(system + user)
        price = PRICING[model]
        million = Decimal(1_000_000)
        low = Decimal(prompt_tokens) / million * price["in"]
        high = low + Decimal(args.max_tokens) / million * price["out"]
        print(f"dry run — nothing sent. guard: pass ({len(files)} file(s))")
        print(f"model:  {model}")
        print(f"prompt: ~{prompt_tokens:,} tokens (estimate at {CHARS_PER_TOKEN} chars/token)")
        print(f"cost:   ${low:.4f} input, up to ${high:.4f} with {args.max_tokens:,} output tokens")
        return 0

    if not api_key:
        print(
            f"{API_KEY_ENV} is not set. It is an environment variable only — "
            "never a file path, never committed. See "
            ".claude/skills/openrouter-deepseek/SKILL.md.",
            file=sys.stderr,
        )
        return 1

    try:
        content, usage = call(
            system=system,
            user=user,
            model=model,
            max_tokens=args.max_tokens,
            seed=args.seed,
            api_key=api_key,
        )
    except Exception as exc:  # noqa: BLE001 — degrade to "no draft", never raise into a caller
        print(f"deepseek call failed, no draft generated: {exc}", file=sys.stderr)
        return 1

    cost = usage.cost_usd(model)
    summary = (
        f"{usage.prompt_tokens:,} in / {usage.completion_tokens:,} out"
        + (f" ({usage.reasoning_tokens:,} reasoning)" if usage.reasoning_tokens else "")
        + (f" — ${cost:.4f}" if cost is not None else "")
    )

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        header = provenance_header(model, files, date.today())
        args.out.write_text(f"{header}\n\n{content.rstrip()}\n")
        print(f"wrote {args.out} ({len(content):,} chars) — {summary}")
        print("UNREVIEWED. Re-derive every number before this is adopted.")
    else:
        print(content)
        print(f"\n---\n{model} — {summary}. UNREVIEWED.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
