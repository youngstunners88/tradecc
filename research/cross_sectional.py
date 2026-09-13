"""Cross-sectional momentum backtest.

Implements `planning/decisions/2026-09-12-cross-sectional-momentum-protocol.md`
literally. Rank a small universe by trailing return, hold the top N
equally weighted out of $10 total, rebalance weekly, and compare against
two mandatory benchmarks.

**All six grid combinations are reported.** The grid is deliberately tiny
(3 lookbacks x 2 hold sizes), which makes reporting every one of them
cheaper than selecting a winner — and reporting every one is what makes
selection bias impossible here. There is no "best" row to quote.

Point-in-time: a rebalance at bar i ranks on closes[i-L..i] and fills at
bar i's close. Nothing after i is read. Analysis tool, not part of the bot.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.config import load_config  # noqa: E402
from execution.candle_cache import CandleCache  # noqa: E402
from core.performance import MIN_POOLED_TRADES  # noqa: E402
from execution.costs import CostModel  # noqa: E402

# Fixed in the decision record.
LOOKBACKS = [7, 14, 30]
TOP_NS = [1, 2]
REBALANCE_EVERY = 7
TOTAL_CAPITAL = Decimal("10")
FOLDS = 3
UNIVERSE_FILE = Path("research/.universe.json")
INTERVAL = "1d"
HUNDRED = Decimal(100)


@dataclass
class Holding:
    symbol: str
    entry_price: Decimal
    size_usd: Decimal


@dataclass
class Outcome:
    net: Decimal = Decimal(0)
    trades: int = 0
    fees: Decimal = Decimal(0)
    gross: Decimal = Decimal(0)


@dataclass
class Book:
    """Positions, costs and realised P&L for one run over one window."""

    model: CostModel
    adverse: Decimal
    funded: set[str] = field(default_factory=set)
    holdings: dict[str, Holding] = field(default_factory=dict)
    out: Outcome = field(default_factory=Outcome)

    def _cost(self, size: Decimal, symbol: str, sol_price: Decimal) -> Decimal:
        fresh = symbol not in self.funded
        self.funded.add(symbol)
        return self.model.estimate(
            size, creates_token_account=fresh, sol_price_usd=sol_price
        ).total_usd

    def buy(self, symbol: str, price: Decimal, size: Decimal, sol_price: Decimal) -> None:
        fee = self._cost(size, symbol, sol_price)
        self.out.fees += fee
        self.out.net -= fee
        # Buys fill above the close; sells below it. Always adverse.
        self.holdings[symbol] = Holding(
            symbol, price * (Decimal(1) + self.adverse), size
        )

    def sell(self, symbol: str, price: Decimal, sol_price: Decimal) -> None:
        held = self.holdings.pop(symbol)
        exit_price = price * (Decimal(1) - self.adverse)
        gross = held.size_usd * (exit_price - held.entry_price) / held.entry_price
        fee = self._cost(held.size_usd, symbol, sol_price)
        self.out.gross += gross
        self.out.fees += fee
        self.out.net += gross - fee
        self.out.trades += 1


def load_universe(config) -> tuple[list[str], list, dict[str, list[Decimal]]]:
    """Aligned closes across the universe, on the timestamps they all share."""
    entries = json.loads(UNIVERSE_FILE.read_text())
    cache = CandleCache(config.data.cache_dir)
    by_symbol = {e["symbol"]: cache.load(e["pool"], INTERVAL) for e in entries}

    common = set.intersection(*({c.timestamp for c in s} for s in by_symbol.values()))
    stamps = sorted(common)
    closes = {
        sym: [next(c.close for c in series if c.timestamp == t) for t in stamps]
        for sym, series in by_symbol.items()
    }
    return sorted(by_symbol), stamps, closes


def run_strategy(
    model: CostModel,
    adverse: Decimal,
    symbols: list[str],
    closes: dict[str, list[Decimal]],
    lo: int,
    hi: int,
    lookback: int,
    top_n: int,
) -> Outcome:
    """One (lookback, top_n) run over the window [lo, hi)."""
    book = Book(model=model, adverse=adverse)
    size = TOTAL_CAPITAL / Decimal(top_n)

    for i in range(lo, hi):
        if i < lookback or (i - lo) % REBALANCE_EVERY:
            continue
        sol = closes["SOL"][i]
        ranked = sorted(
            symbols,
            key=lambda s: (closes[s][i] - closes[s][i - lookback]) / closes[s][i - lookback],
            reverse=True,
        )
        target = set(ranked[:top_n])
        for symbol in list(book.holdings):
            if symbol not in target:
                book.sell(symbol, closes[symbol][i], sol)
        for symbol in target:
            if symbol not in book.holdings:
                book.buy(symbol, closes[symbol][i], size, sol)

    # Close everything on the final bar so all P&L is realised and the
    # comparison against buy-and-hold is like-for-like.
    last = hi - 1
    for symbol in list(book.holdings):
        book.sell(symbol, closes[symbol][last], closes["SOL"][last])
    return book.out


def buy_and_hold(
    model: CostModel,
    adverse: Decimal,
    basket: list[str],
    closes: dict[str, list[Decimal]],
    lo: int,
    hi: int,
) -> Outcome:
    """Buy each name at `lo`, sell at `hi-1`. Capital split across the basket."""
    book = Book(model=model, adverse=adverse)
    size = TOTAL_CAPITAL / Decimal(len(basket))
    last = hi - 1
    for symbol in basket:
        book.buy(symbol, closes[symbol][lo], size, closes["SOL"][lo])
    for symbol in basket:
        book.sell(symbol, closes[symbol][last], closes["SOL"][last])
    return book.out


def fold_bounds(n: int, folds: int) -> list[tuple[int, int]]:
    size = n // folds
    bounds = [(i * size, (i + 1) * size) for i in range(folds)]
    bounds[-1] = (bounds[-1][0], n)
    return bounds


def main() -> int:
    config = load_config("config.backtest.yaml", env={})
    model = CostModel(config.costs)
    adverse = config.backtest.total_adverse_pct / HUNDRED
    symbols, stamps, closes = load_universe(config)
    bounds = fold_bounds(len(stamps), FOLDS)

    print("CROSS-SECTIONAL MOMENTUM — all six grid combinations")
    print("Protocol: planning/decisions/2026-09-12-cross-sectional-momentum-protocol.md")
    print(f"Universe: {symbols}")
    print(f"Aligned window: {stamps[0].date()} -> {stamps[-1].date()} "
          f"({len(stamps)} common daily bars)")
    print(f"Capital ${TOTAL_CAPITAL} total, rebalance every {REBALANCE_EVERY}d, "
          f"adverse {config.backtest.total_adverse_pct}%/side\n")

    # Benchmarks, pooled across the same folds the strategy is scored on.
    sol_folds = [buy_and_hold(model, adverse, ["SOL"], closes, lo, hi) for lo, hi in bounds]
    basket_folds = [buy_and_hold(model, adverse, symbols, closes, lo, hi) for lo, hi in bounds]
    sol_pooled = sum((f.net for f in sol_folds), Decimal(0))
    basket_pooled = sum((f.net for f in basket_folds), Decimal(0))

    print("BENCHMARKS (pooled across the same 3 folds)")
    print(f"  buy-and-hold SOL          net {sol_pooled:+8.4f}   "
          f"folds {[f'{f.net:+.2f}' for f in sol_folds]}")
    print(f"  equal-weight basket ({len(symbols)})    net {basket_pooled:+8.4f}   "
          f"folds {[f'{f.net:+.2f}' for f in basket_folds]}")
    print(f"    (basket pays {len(symbols)}x the fixed costs on "
          f"${TOTAL_CAPITAL/len(symbols):.2f} positions — fees "
          f"{sum((f.fees for f in basket_folds), Decimal(0)):.4f})\n")

    print(f"{'L':>3}{'N':>3}  {'fold nets':<28}{'pooled':>9}{'trades':>7}"
          f"{'fees':>8}   verdict")
    print("-" * 84)
    for lookback in LOOKBACKS:
        for top_n in TOP_NS:
            outs = [
                run_strategy(model, adverse, symbols, closes, lo, hi, lookback, top_n)
                for lo, hi in bounds
            ]
            pooled = sum((o.net for o in outs), Decimal(0))
            trades = sum(o.trades for o in outs)
            fees = sum((o.fees for o in outs), Decimal(0))
            positive = sum(1 for o in outs if o.net > 0)
            biggest = max((o.net for o in outs), default=Decimal(0))

            checks = {
                "majority": positive >= 2,
                "pooled>0": pooled > 0,
                "spread": pooled > 0 and biggest <= pooled * Decimal("0.60"),
                "trades": trades >= MIN_POOLED_TRADES,
                "beats SOL": pooled > sol_pooled,
                "beats basket": pooled > basket_pooled,
            }
            failed = [k for k, ok in checks.items() if not ok]
            verdict = "PASS" if not failed else "fail: " + ",".join(failed)
            nets = " ".join(f"{o.net:+7.3f}" for o in outs)
            print(f"{lookback:>3}{top_n:>3}  {nets:<28}{pooled:>9.4f}{trades:>7}"
                  f"{fees:>8.4f}   {verdict}")

    print("\nAll six combinations shown — there is no selected winner, which is")
    print("what makes selection bias impossible here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
