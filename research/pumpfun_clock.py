"""pump.fun graduation clock: forward, point-in-time collection. Observation only.

Implements, literally:
  planning/decisions/2026-09-13-pumpfun-graduation-duration.md   (the sealed test)
  planning/decisions/2026-09-23-pumpfun-clock-amendment.md       (stream + cadence)

It records graduations. It does not price them, rank them, or decide anything:
the 30-day returns and the one-shot verdict belong to a later script that runs
once, at the stopping rule. No key, no wallet, no send, no language model.

    python3 research/pumpfun_clock.py --init          # once, starts the clock
    python3 research/pumpfun_clock.py --poll          # every 2 hours
    python3 research/pumpfun_clock.py --poll --dry-run
    python3 research/pumpfun_clock.py --status

THE LOG IS APPEND-ONLY JSONL, one event per line:

  init      clock id, start time, SHA-256 of both sealed records
  poll      coverage check result, and a HOLE if the window fell short
  grad      a cohort member: mint, pool, created, graduated, fill hours
  excluded  a graduation seen and deliberately not in the cohort, with the
            reason (pre_clock | fill_ge_cutoff | bad_timestamps)

Exclusions are logged rather than silently skipped, so the cohort can be
audited against everything that was seen.

REFUSALS: a missing log without --init, a corrupt line, an unknown event kind,
or a log whose first event is not `init`. Starting a fresh clock over a lost
or damaged one silently resets a 30-day measurement. src/paper/session.py
refuses for the same reason.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
CLOCK_FILE = ROOT / "research" / "clocks" / "pumpfun_graduation.jsonl"
SEALED = (
    "planning/decisions/2026-09-13-pumpfun-graduation-duration.md",
    "planning/decisions/2026-09-23-pumpfun-clock-amendment.md",
)

# Locked by the amendment.
FILL_CUTOFF_H = 20.0
POLL_INTERVAL_H = 2.0

PUMP_LIST = ("https://frontend-api-v3.pump.fun/coins?offset={offset}&limit={limit}"
             "&sort=created_timestamp&order=DESC&complete=true&includeNsfw=true")
GECKO_MULTI = "https://api.geckoterminal.com/api/v2/networks/solana/pools/multi/{addrs}"
PAGE = 50
MAX_OFFSET = 1200     # measured: offset 1200 returns nothing
GECKO_BATCH = 30      # multi-pool endpoint limit

EVENT_KINDS = frozenset({"init", "poll", "grad", "excluded"})


class ClockError(RuntimeError):
    pass


@dataclass(frozen=True)
class Coin:
    mint: str
    created_ts: float          # unix seconds
    pool: str | None


@dataclass
class ClockState:
    clock_id: str
    t_init: float
    last_poll_t: float | None = None
    known: set[str] = field(default_factory=set)   # mints recorded as grad or excluded
    cohort: int = 0
    excluded: int = 0
    holes: int = 0
    polls: int = 0


# --- log -------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> ClockState:
    """Replay the log. Refuses anything it cannot trust."""
    if not path.exists():
        raise ClockError(
            f"{path} does not exist. Refusing to start a clock implicitly -- a lost "
            "log must not become a fresh 30-day measurement. Use --init, once."
        )
    state: ClockState | None = None
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError as e:
            raise ClockError(f"{path}:{n} is not valid JSON ({e}); refusing to continue a corrupt clock") from None
        kind = ev.get("kind")
        if kind not in EVENT_KINDS:
            raise ClockError(f"{path}:{n} unknown event kind {kind!r}; refusing to skip it")
        if state is None:
            if kind != "init":
                raise ClockError(f"{path}:{n} first event is {kind!r}, not init")
            state = ClockState(clock_id=ev["clock_id"], t_init=float(ev["t"]))
            continue
        if kind == "init":
            raise ClockError(f"{path}:{n} second init; one log, one clock")
        if kind == "poll":
            state.last_poll_t = float(ev["t"])
            state.polls += 1
            state.holes += 1 if ev.get("hole") else 0
        elif kind == "grad":
            if ev["mint"] in state.known:
                raise ClockError(f"{path}:{n} {ev['mint']} recorded twice")
            state.known.add(ev["mint"])
            state.cohort += 1
        elif kind == "excluded":
            state.known.add(ev["mint"])
            state.excluded += 1
    if state is None:
        raise ClockError(f"{path} is empty; refusing")
    return state


def append(path: Path, events: Iterable[dict]) -> None:
    with path.open("a") as f:
        for ev in events:
            f.write(json.dumps(ev, sort_keys=True) + "\n")


def init_event(now: float, root: Path = ROOT) -> dict:
    return {
        "kind": "init",
        "clock_id": f"pumpfun-grad-{uuid.uuid4().hex[:8]}",
        "t": now,
        "sealed": {p: sha256_of(root / p) for p in SEALED},
        "fill_cutoff_h": FILL_CUTOFF_H,
        "poll_interval_h": POLL_INTERVAL_H,
    }


# --- pure rules ------------------------------------------------------------

def coverage(oldest_created_age_h: float, listing_exhausted: bool,
             hours_since_prev: float) -> tuple[bool, dict | None]:
    """The locked check: complete iff the window reaches cutoff + gap.

    `listing_exhausted` means the API ran out of rows before the page cap, so
    the window already holds every graduated coin -- complete by definition.
    """
    need = FILL_CUTOFF_H + hours_since_prev
    if listing_exhausted or oldest_created_age_h >= need:
        return True, None
    return False, {"window_reached_h": round(oldest_created_age_h, 3), "needed_h": round(need, 3),
                   "uncovered_fill_h": [round(oldest_created_age_h - hours_since_prev, 3), FILL_CUTOFF_H]}


def classify(coin: Coin, graduation_ts: float, t_init: float) -> tuple[str, str | None]:
    """('grad', None) or ('excluded', reason). Never looks at price."""
    if graduation_ts < coin.created_ts:
        return "excluded", "bad_timestamps"
    if graduation_ts < t_init:
        return "excluded", "pre_clock"
    if (graduation_ts - coin.created_ts) / 3600 >= FILL_CUTOFF_H:
        return "excluded", "fill_ge_cutoff"
    return "grad", None


def poll(
    state: ClockState,
    list_page: Callable[[int, int], list[dict]],
    lookup_graduations: Callable[[Sequence[str]], dict[str, float]],
    now: float,
) -> list[dict]:
    """One poll. Returns the events to append; writes nothing itself."""
    coins: list[Coin] = []
    exhausted = False
    offset = 0
    while offset < MAX_OFFSET:
        page = list_page(offset, PAGE)
        if not page:
            exhausted = True
            break
        for c in page:
            if not c.get("complete"):
                continue
            coins.append(Coin(mint=c["mint"], created_ts=float(c["created_timestamp"]) / 1000,
                              pool=c.get("pump_swap_pool") or c.get("pool_address")))
        if len(page) < PAGE:
            exhausted = True
            break
        offset += PAGE

    oldest_age_h = max(((now - c.created_ts) / 3600 for c in coins), default=0.0)
    prev = state.last_poll_t if state.last_poll_t is not None else state.t_init
    complete, hole = coverage(oldest_age_h, exhausted, (now - prev) / 3600)

    # A coin created more than FILL_CUTOFF_H before the previous poll cannot
    # have graduated SINCE that poll with a fill under the cutoff, so it can
    # never enter the cohort now: no lookup needed. Pure arithmetic on the
    # predictor's own definition -- it cannot see the outcome.
    horizon = prev - FILL_CUTOFF_H * 3600
    fresh = [c for c in coins if c.mint not in state.known and c.created_ts >= horizon]
    pools = sorted({c.pool for c in fresh if c.pool})
    grad_ts = lookup_graduations(pools) if pools else {}

    events: list[dict] = []
    unresolved = 0
    for c in fresh:
        g = grad_ts.get(c.pool) if c.pool else None
        if g is None:
            # Not indexed yet, or no pool: NOT excluded. Retried next poll while
            # it stays in the window; counted so a lost coin is visible.
            unresolved += 1
            continue
        verdict, reason = classify(c, g, state.t_init)
        base = {"mint": c.mint, "pool": c.pool, "created_ts": c.created_ts,
                "graduation_ts": g, "fill_h": round((g - c.created_ts) / 3600, 4),
                "observed_at": now}
        if verdict == "grad":
            events.append({"kind": "grad", **base})
        else:
            events.append({"kind": "excluded", "reason": reason, **base})

    events.insert(0, {
        "kind": "poll", "t": now, "prev_t": prev,
        "listed": len(coins), "listing_exhausted": exhausted,
        "oldest_created_age_h": round(oldest_age_h, 3),
        "complete": complete, "hole": hole,
        "new_grad": sum(1 for e in events if e["kind"] == "grad"),
        "new_excluded": sum(1 for e in events if e["kind"] == "excluded"),
        "unresolved": unresolved,
    })
    return events


# --- network (thin, not unit-tested) ----------------------------------------

def _get_json(url: str) -> object:
    sys.path.insert(0, str(ROOT / "src"))
    from execution.http import ProviderHttpClient, UrllibTransport  # noqa: PLC0415
    from core.rate_limit import RateLimiter  # noqa: PLC0415
    global _CLIENT
    try:
        client = _CLIENT
    except NameError:
        client = _CLIENT = ProviderHttpClient(
            provider="pumpfun-clock", transport=UrllibTransport(),
            # 10/min: GeckoTerminal rate-limits GitHub's shared runner IPs far below
            # its nominal 30/min (measured 2026-09-23). Shared with pump.fun listing calls.
            limiter=RateLimiter(max_requests=10, per_seconds=60.0, name="pumpfun-clock"))
    return client.request("GET", url).json()


def live_list_page(offset: int, limit: int) -> list[dict]:
    data = _get_json(PUMP_LIST.format(offset=offset, limit=limit))
    return data if isinstance(data, list) else []


def lookup_with_retries(
    pools: Sequence[str],
    fetch_batch: Callable[[Sequence[str]], dict[str, float]],
    sleep: Callable[[float], None],
    passes: int = 3,
    backoff_s: float = 60.0,
) -> tuple[dict[str, float], int]:
    """Look up graduation times in batches; retry FAILED batches after a pause.

    Measured 2026-09-23: from GitHub's shared runner IPs GeckoTerminal
    rate-limited so hard that 300 of a poll's coins came back unresolved,
    while the same poll from another IP resolved all of them. Unresolved is
    not lost -- it is retried next poll -- but a backlog that re-forms every
    poll lets cohort coins age out of the window. So a failed batch waits
    `backoff_s` and is tried again, up to `passes` times, within the poll.
    Returns (times, batches still failed after the last pass).
    """
    out: dict[str, float] = {}
    pending = [list(pools[i:i + GECKO_BATCH]) for i in range(0, len(pools), GECKO_BATCH)]
    for attempt in range(passes):
        failed = []
        for batch in pending:
            try:
                out.update(fetch_batch(batch))
            except Exception:  # noqa: BLE001 -- any provider failure = retry, then unresolved
                failed.append(batch)
        pending = failed
        if not pending:
            break
        if attempt < passes - 1:
            sleep(backoff_s)
    return out, len(pending)


def _fetch_batch(batch: Sequence[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    payload = _get_json(GECKO_MULTI.format(addrs=",".join(batch)))
    for p in (payload or {}).get("data", []):
        a = p.get("attributes", {})
        if a.get("address") and a.get("pool_created_at"):
            out[a["address"]] = datetime.fromisoformat(
                a["pool_created_at"].replace("Z", "+00:00")).timestamp()
    return out


def live_lookup(pools: Sequence[str]) -> dict[str, float]:
    """Graduation times by pool. A batch that still fails after retries is
    left OUT, not guessed: its coins come back unresolved and are retried
    next poll while they stay in the window."""
    out, still_failed = lookup_with_retries(pools, _fetch_batch, time.sleep)
    if still_failed:
        print(f"{still_failed} lookup batch(es) failed after retries; left unresolved", file=sys.stderr)
    return out


# --- CLI ---------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--init", action="store_true")
    g.add_argument("--poll", action="store_true")
    g.add_argument("--status", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--file", type=Path, default=CLOCK_FILE)
    a = ap.parse_args(argv)
    now = time.time()

    if a.init:
        if a.file.exists():
            raise ClockError(f"{a.file} already exists; one clock per log. Refusing to re-init.")
        a.file.parent.mkdir(parents=True, exist_ok=True)
        ev = init_event(now)
        append(a.file, [ev])
        print(f"clock_id   {ev['clock_id']}\nt_start    {datetime.fromtimestamp(now, timezone.utc).isoformat()}"
              f"\nrows_now   0\nnext_poll  +{POLL_INTERVAL_H:g}h")
        return 0

    state = load(a.file)
    if a.status:
        print(f"clock_id   {state.clock_id}\nstarted    {datetime.fromtimestamp(state.t_init, timezone.utc).isoformat()}"
              f"\npolls      {state.polls} ({state.holes} with holes)\ncohort     {state.cohort}"
              f"\nexcluded   {state.excluded}")
        return 0

    events = poll(state, live_list_page, live_lookup, now)
    p = events[0]
    print(f"listed {p['listed']}  window {p['oldest_created_age_h']}h  complete={p['complete']}"
          f"  +grad {p['new_grad']}  +excluded {p['new_excluded']}  unresolved {p['unresolved']}")
    if p["hole"]:
        print(f"HOLE recorded: {p['hole']}")
    if a.dry_run:
        print("--dry-run: nothing written")
        return 0
    append(a.file, events)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ClockError as e:
        print(f"refused: {e}", file=sys.stderr)
        sys.exit(2)
