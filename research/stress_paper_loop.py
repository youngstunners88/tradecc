"""Stress test: drive the paper trader through a long hostile run.

Run with: PYTHONPATH=src .venv/bin/python research/stress_paper_loop.py

Kept in the repo because it found two defects that review and the unit suite
both missed: the tick boundary crashing on any non-ProviderError exception,
and a modelled cost of 38,880% of position size that every risk control
approved. Re-run it after changes to the paper loop, the cost model, or the
risk engine.

Not a unit test — this exercises the loop the 30-day paper run will actually
execute, against providers that misbehave the way real ones do.
"""
import json, random, sys, traceback
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from core.config import RunConfig, RiskConfig, PaperConfig, StrategyConfig, DataConfig
from core.candles import Candle
from core.types import Mode, Quote, Side
from execution.http import ProviderError, TransportError
from paper.session import PaperSessionStore
from paper.trader import PaperTrader
from strategy.registry import build_strategy

TOKEN = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
START = datetime(2026, 9, 1, tzinfo=timezone.utc)

class HostileCandles:
    """Real-ish prices, but the provider fails, flaps, and returns junk."""
    def __init__(self, prices, rng):
        self.prices, self.rng, self.calls = prices, rng, 0
    def fetch_candles(self, pool, interval, limit=1000):
        self.calls += 1
        r = self.rng.random()
        if r < 0.10: raise ProviderError("geckoterminal", "503 Service Unavailable")
        if r < 0.15: raise TransportError("connection reset by peer")
        if r < 0.18: return []                      # empty page
        n = min(len(self.prices), 200)
        out, t = [], START
        for p in self.prices[:n]:
            out.append(Candle(timestamp=t, open=Decimal(str(p)), high=Decimal(str(p)),
                              low=Decimal(str(p)), close=Decimal(str(p)), volume=Decimal("1000")))
            t += timedelta(minutes=15)
        return out

class HostileQuotes:
    """Jupiter-shaped, with outages and extreme-but-legal slippage."""
    def __init__(self, prices, rng):
        self.prices, self.rng, self.i = prices, rng, 0
    def get_quote(self, input_mint, output_mint, amount_atomic, slippage_bps,
                  amount_usd, input_decimals, output_decimals, *, side=Side.BUY):
        r = self.rng.random()
        if r < 0.08: raise ProviderError("jupiter", "429 Too Many Requests")
        if amount_atomic <= 0: raise AssertionError("asked to quote a non-positive amount")
        price = Decimal(str(self.prices[min(self.i, len(self.prices)-1)]))
        self.i += 1
        drift = Decimal(str(round(self.rng.uniform(0.001, 0.04), 4)))  # up to 4%
        worst = price * ((1 - drift) if side is Side.SELL else (1 + drift))
        token = output_mint if side is Side.BUY else input_mint
        return Quote(token_mint=token, side=side, amount_usd=amount_usd,
                     expected_price=price, worst_case_price=worst,
                     fee_usd=Decimal("0"), source="hostile")

def run(seed, prices, ticks=400):
    rng = random.Random(seed)
    d = Path(tempfile.mkdtemp())
    cfg = RunConfig(mode=Mode.PAPER, risk=RiskConfig(), strategy=StrategyConfig(
                        name="momentum", token_mints=(TOKEN,)),
                    data=DataConfig(), paper=PaperConfig(pool_address="pool", quote_mint=USDC),
                    state_dir=d/"state", gate_file=d/"gate.json")
    store = PaperSessionStore(cfg.state_dir)
    trader = PaperTrader(config=cfg, strategy=build_strategy(cfg.strategy),
                         quote_source=HostileQuotes(prices, rng),
                         candle_source=HostileCandles(prices, rng), store=store)
    state = store.load_or_start(TOKEN, "momentum", Decimal("100"), now=START)
    actions, errors, crashes = {}, 0, []
    now = START
    for i in range(ticks):
        now += timedelta(minutes=15)
        try:
            res = trader.run_tick_and_save(state, now=now)
            actions[res.action] = actions.get(res.action, 0) + 1
            if res.error: errors += 1
        except Exception as e:
            crashes.append(f"tick {i}: {type(e).__name__}: {e}")
            if len(crashes) > 3: break
    return state, actions, errors, crashes

SCENARIOS = {
  "flat":        [100.0]*250,
  "crash -70%":  [100.0*(0.9988**i) for i in range(250)],
  "melt-up":     [100.0*(1.0012**i) for i in range(250)],
  "whipsaw":     [100.0*(1+0.06*((-1)**i)) for i in range(250)],
  "near-zero":   [0.00001*(1+0.02*((-1)**i)) for i in range(250)],
  "huge-price":  [1_850_000.0*(1+0.01*((-1)**i)) for i in range(250)],
}

print(f"{'scenario':<12} {'ticks':>6} {'trades':>7} {'net$':>10} {'maxDD%':>8} {'errs':>5}  crashes")
worst = []
for name, prices in SCENARIOS.items():
    try:
        state, actions, errors, crashes = run(7, prices)
        dd = state.max_drawdown_pct
        print(f"{name:<12} {state.ticks:>6} {len(state.trades):>7} {state.net_pnl_usd:>10.4f} "
              f"{dd:>8.2f} {errors:>5}  {crashes[:1] or ''}")
        if crashes: worst.extend(crashes)
    except Exception:
        print(f"{name:<12} SETUP FAILED"); traceback.print_exc()
print()
if worst:
    print("CRASHES:"); [print("  ", c) for c in worst[:10]]
else:
    print("No crashes across any scenario.")
