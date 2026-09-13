"""Feasibility probe for copy-trading — run BEFORE any protocol is written.

Copy-trading is the only named, untested signal source left after
`planning/decisions/2026-09-12-kill-ema-rsi-momentum.md` closed the momentum
path. The lesson that paid for itself twice (regime-detection, cross-sectional
momentum) is to establish whether a hypothesis is *testable on available data*
before fixing a protocol around it. This probe answers four questions and
stops:

  Q1 How far back does wallet trade history reach on infrastructure we have?
  Q2 Are transaction bodies (not just signatures) retrievable at that depth?
  Q3 What sustained throughput can we get, i.e. what does a wallet-year cost
     in wall-clock time?
  Q4 What edge must a copied trade clear to be worth copying at $5-$10?

It deliberately does NOT score wallets, propose a universe, or backtest
anything. Those need a pre-registered decision record. This only measures
whether such a record could be honoured.

No API keys required and none used: `HELIUS_API_KEY` is not set in this
environment, and `https://mainnet.helius-rpc.com` returns `Unauthorized`
without one, so the probe uses the public RPC endpoint. That is a measurement
of the *free path* specifically.

Read-only. Touches no production path, imports only the existing cost model.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_config  # noqa: E402
from execution.costs import CostModel  # noqa: E402

RPC = "https://api.mainnet-beta.solana.com"
# A continuously active mainnet address, used only to characterise what the
# endpoint serves. Nothing about this address is a trading recommendation and
# it is not a copy-trading candidate.
PROBE_ADDRESS = "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"
SIG_PAGES = 6
THROUGHPUT_SAMPLE = 12
SIZES = [Decimal("5"), Decimal("10"), Decimal("25"), Decimal("100")]
SOL_PRICE = Decimal("101.79")  # the live close measured 2026-09-12


def rpc(method: str, params: list, tries: int = 4) -> tuple[dict, int]:
    """JSON-RPC with backoff on 429. Returns (payload, retries_used)."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    for attempt in range(tries):
        request = urllib.request.Request(
            RPC, data=body.encode(), headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=40) as handle:
                return json.loads(handle.read().decode()), attempt
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                time.sleep(1.0 + attempt)
                continue
            raise
    return {"error": {"message": "rate limited after retries"}}, tries


def q1_history_depth() -> list[dict]:
    """How far back signatures reach, and how many are available."""
    print("Q1 — signature history depth (free public RPC)")
    before, rows_total, oldest, page = None, 0, None, 0
    last_page: list[dict] = []
    while page < SIG_PAGES:
        params: dict = {"limit": 1000}
        if before:
            params["before"] = before
        payload, _ = rpc("getSignaturesForAddress", [PROBE_ADDRESS, params])
        rows = payload.get("result") or []
        if not rows:
            break
        last_page = rows
        rows_total += len(rows)
        before = rows[-1]["signature"]
        oldest = rows[-1].get("blockTime")
        page += 1
        stamp = datetime.fromtimestamp(oldest, timezone.utc) if oldest else None
        print(f"  page {page}: {len(rows):>4} sigs, oldest {stamp.date() if stamp else '?'}")
        time.sleep(1.0)
    if oldest:
        days = (datetime.now(timezone.utc) - datetime.fromtimestamp(oldest, timezone.utc)).days
        print(f"  -> {rows_total} signatures, {days} days of reach\n")
    return last_page


def q2_body_retrievable(rows: list[dict]) -> None:
    """Are transaction bodies still served at depth, and are swaps derivable?"""
    print("Q2 — transaction bodies at depth")
    if not rows:
        print("  no signatures to test\n")
        return
    target = rows[-1]
    payload, _ = rpc(
        "getTransaction",
        [target["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}],
    )
    stamp = datetime.fromtimestamp(target["blockTime"], timezone.utc).date()
    if payload.get("error"):
        print(f"  {stamp}: ERROR {payload['error'].get('message')}\n")
        return
    if payload.get("result") is None:
        print(f"  {stamp}: NULL — body pruned at this depth\n")
        return
    meta = payload["result"]["meta"]
    pre = len(meta.get("preTokenBalances") or [])
    post = len(meta.get("postTokenBalances") or [])
    print(f"  {stamp}: body retrieved. token balances {pre} pre / {post} post")
    print("  -> swap legs (mint in/out, amounts) derivable from balance deltas\n")


def q3_throughput(rows: list[dict]) -> None:
    """Sustained getTransaction rate, which sets the cost of a wallet-year."""
    print(f"Q3 — sustained throughput ({THROUGHPUT_SAMPLE} bodies)")
    sample = rows[:THROUGHPUT_SAMPLE]
    ok, retries, start = 0, 0, time.time()
    for row in sample:
        payload, used = rpc(
            "getTransaction",
            [row["signature"], {"maxSupportedTransactionVersion": 0, "encoding": "jsonParsed"}],
        )
        retries += used
        if payload.get("result"):
            ok += 1
    elapsed = time.time() - start
    rate = ok / elapsed if elapsed else 0
    print(f"  {ok}/{len(sample)} in {elapsed:.1f}s -> {rate:.2f} tx/s, {retries} rate-limit retries")
    if rate:
        print(f"  -> one wallet-year (~6000 tx) ≈ {6000 / rate / 3600:.1f} h;"
              f" 10 wallets ≈ {10 * 6000 / rate / 3600:.0f} h\n")


def q4_cost_hurdle() -> None:
    """What must a copied trade beat, per round trip, to be worth copying?"""
    config = load_config("config.backtest.yaml", env={})
    model = CostModel(config.costs)
    adverse = config.backtest.total_adverse_pct * 2  # both sides

    print("Q4 — hurdle per round trip, at the calibrated cost model")
    print("  Recurring costs only. ATA rent is a refundable rent-exempt deposit")
    print("  charged once per mint, NOT a fee — counting it as one overstates")
    print("  the hurdle several-fold (see costs.py TradeCosts.recurring_usd).")
    print(f"\n  {'size':>6} {'recurring RT':>13} {'fee %':>8} {'adverse %':>10} {'HURDLE':>8}")
    for size in SIZES:
        entry = model.estimate(size, creates_token_account=True, sol_price_usd=SOL_PRICE)
        exit_ = model.estimate(size, creates_token_account=False, sol_price_usd=SOL_PRICE)
        recurring = entry.recurring_usd + exit_.recurring_usd
        fee_pct = recurring / size * 100
        print(f"  ${size:>5} {recurring:>13.4f} {fee_pct:>7.2f}% {adverse:>9.2f}% "
              f"{fee_pct + adverse:>7.2f}%")
    rent = model.estimate(SIZES[1], creates_token_account=True, sol_price_usd=SOL_PRICE)
    print(f"\n  ATA rent, once per mint: ${rent.account_rent_usd:.4f}, recoverable on close.")
    print(f"  At $10 of capital that is {rent.account_rent_usd / Decimal(10) * 100:.1f}% "
          "locked up per distinct mint held.\n")


def main() -> int:
    print("COPY-TRADING FEASIBILITY PROBE — 2026-09-12")
    print("Measures whether the hypothesis is testable. Scores no wallets.\n")
    rows = q1_history_depth()
    q2_body_retrievable(rows)
    q3_throughput(rows)
    q4_cost_hurdle()
    print("No wallet was scored, ranked, or recommended. Any test of copy-trading")
    print("needs a pre-registered decision record first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
