"""Measure the cost inputs that were previously guessed.

Three of the cost model's numbers describe the market rather than the
code, so they are wrong the moment they are hardcoded:

- **SOL price** — multiplies every SOL-denominated cost. The config
  default said 200 while SOL traded near 102.
- **Price impact** — the real cost of depth at our size. The backtest
  assumed 0.3% per side; measurement put it near zero for SOL/USDC at
  $5-$200, because the pool is deep and our size is tiny.
- **Jito tip** — modelled as zero, which it never is.

This prints what to put in config. It does not write config itself: a
tool that silently rewrites its own cost assumptions is the shape of
thing that quietly flatters a backtest.

    PYTHONPATH=src python research/calibrate_costs.py --size-usd 10

Kept in research/ because it is an analysis tool, not part of the bot.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_config  # noqa: E402

SOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
JUPITER = "https://lite-api.jup.ag"
JITO_TIP_FLOOR = "https://bundles.jito.wtf/api/v1/bundles/tip_floor"
LAMPORTS_PER_SOL = Decimal("1000000000")
# GeckoTerminal rejects urllib's default UA, and Jupiter is stricter than
# it looks too. Same header the production transport sends.
HEADERS = {"User-Agent": "tradecc/0.1", "Accept": "application/json"}


def fetch(url: str):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as handle:
        return json.loads(handle.read().decode())


def sol_price_usd() -> Decimal:
    payload = fetch(f"{JUPITER}/price/v3?ids={SOL_MINT}")
    return Decimal(str(payload[SOL_MINT]["usdPrice"]))


def price_impact_pct(lamports: int, slippage_bps: int) -> tuple[Decimal, int]:
    """Measured impact, and how many hops the route needed."""
    url = (
        f"{JUPITER}/swap/v1/quote?inputMint={SOL_MINT}&outputMint={USDC_MINT}"
        f"&amount={lamports}&slippageBps={slippage_bps}"
    )
    payload = fetch(url)
    impact = Decimal(str(payload.get("priceImpactPct", "0"))) * Decimal(100)
    return impact, len(payload.get("routePlan", []))


def jito_tip_lamports() -> dict[str, int]:
    rows = fetch(JITO_TIP_FLOOR)
    row = rows[0]
    return {
        key.replace("landed_tips_", ""): int(
            (Decimal(str(value)) * LAMPORTS_PER_SOL).to_integral_value()
        )
        for key, value in row.items()
        if key.startswith("landed_tips_")
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.backtest.yaml")
    parser.add_argument("--size-usd", type=Decimal, default=None)
    parser.add_argument("--slippage-bps", type=int, default=None)
    args = parser.parse_args()

    config = load_config(args.config, env={})
    size_usd = args.size_usd or config.risk.position_size_usd
    slippage_bps = args.slippage_bps or int(config.risk.max_slippage_pct * 100)

    price = sol_price_usd()
    print(f"SOL price          : ${price:.2f}")
    print(f"  config says      : ${config.costs.sol_price_usd}")
    drift = (price - config.costs.sol_price_usd) / config.costs.sol_price_usd * 100
    print(f"  config drift     : {drift:+.1f}%  <- multiplies every SOL cost\n")

    lamports = int((size_usd / price * LAMPORTS_PER_SOL).to_integral_value())
    print(f"Price impact at ${size_usd} ({lamports} lamports, {slippage_bps} bps):")
    impact, hops = price_impact_pct(lamports, slippage_bps)
    print(f"  measured impact  : {impact:.4f}%   ({hops} hop(s))")
    print(f"  backtest assumes : {config.backtest.price_impact_pct}%")
    print("  NOTE: impact is not the gap to otherAmountThreshold. That gap is")
    print("        the slippage tolerance requested, not a cost incurred.\n")

    tips = jito_tip_lamports()
    print("Jito landed tips (lamports):")
    for key in sorted(tips, key=lambda k: tips[k]):
        usd = Decimal(tips[key]) / LAMPORTS_PER_SOL * price
        print(f"  {key:<32} {tips[key]:>10,}  (${usd:.5f})")
    print(f"  config uses      : {config.costs.jito_tip_lamports:,} lamports")
    print("\nPessimistic default is the 75th percentile: tips are a bidding")
    print("market, and the median is what clears on a quiet block.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
