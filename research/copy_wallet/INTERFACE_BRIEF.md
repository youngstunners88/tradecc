# Interface brief — what an implementer needs from `src/`, without reading `src/`

**Why this file exists.** `.claude/skills/openrouter-deepseek` deliberately
keeps `src/` off the list of material that may be sent to DeepSeek. The
copy-wallet work order needs DeepSeek to implement against real interfaces
anyway. Extending the allow-list to "just a few source files" would be the
first step in dissolving a control that currently has no exceptions, so
instead the interfaces are transcribed here, by hand, into a file that lives
in `research/` and is sendable by the ordinary rules.

Transcribed 2026-09-16 from `main` at `369d4ef`. **If `src/` changes, this
file goes stale silently** — re-check it against the tree before relying on
it, the same way `references/models.md` is re-checked against the live
catalogue.

---

## 1. The strategy protocol — and the problem it creates

```python
# src/strategy/base.py
@runtime_checkable
class Strategy(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def minimum_candles(self) -> int: ...
    def generate(self, token_mint: str, candles: Sequence[Candle]) -> Signal: ...
```

The module docstring states the contract that matters more than the
signature:

> A strategy is a **pure function of closed candles**: same candles in, same
> signal out, no I/O, no clock, no randomness.

**A copy strategy has a problem here, and it must be solved deliberately.**
Copying needs *source wallet fills*, which are neither candles nor pure — a
naive implementation fetches them inside `generate()`. That would make the
strategy non-replayable, and a non-replayable strategy makes the backtest
measure something other than what would run. The whole validation gate rests
on that property.

**The required resolution:** the fill log is **frozen and injected at
construction time**, never fetched at tick time.

```python
class CopyStrategy:
    def __init__(self, fills: Sequence[SourceFill], lag_seconds: int = 60) -> None:
        # `fills` is already sorted, already filtered to the allowlist, and
        # already complete for the replay window. No network, no clock.
        ...

    def generate(self, token_mint: str, candles: Sequence[Candle]) -> Signal:
        # `candles[-1].timestamp` is the only notion of "now" available.
        # Eligible fills are those with fill.timestamp + lag <= that value.
        # Nothing later may be consulted — that is the look-ahead boundary.
        ...
```

`generate()` stays pure: same fills, same candles, same signal. The I/O
happens once, before the run, in `research/copy_wallet/`.

**The lag is a look-ahead control, not a latency model.** It is applied by
comparing timestamps inside `generate()`, so it is enforced in the backtest
and in paper identically. An implementation that applies lag only when
fetching has not applied it at all.

## 2. Types you will emit and receive

```python
# src/core/types.py — all frozen dataclasses, all money is Decimal
class SignalType(str, Enum):
    BUY = "buy"; SELL = "sell"; HOLD = "hold"

@dataclass(frozen=True)
class Candle:
    timestamp: datetime   # bar OPEN time, timezone-aware UTC (enforced in __post_init__)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

@dataclass(frozen=True)
class Signal:
    type: SignalType
    token_mint: str
    price: Decimal
    timestamp: datetime
    strategy: str                                  # your NAME constant
    metadata: dict[str, str] = field(...)          # str -> str ONLY
```

`Signal` **carries no size**. Sizing is `risk/`'s job and a strategy that
tries to express size is reaching outside its boundary. Put the source
wallet address and the source fill timestamp in `metadata` (as strings) so a
signal can be traced back to the fill that caused it.

## 3. Registration

```python
# src/strategy/registry.py
_BUILDERS: dict[str, Callable[[dict[str, Any]], Strategy]] = {
    MOMENTUM: MomentumStrategy.from_params,
}
```

Add exactly one entry, `"copy": CopyStrategy.from_params`, and one module.
`build_strategy` raises `ValueError` on an unknown name — a typo must never
fall back to a default, because something with real money behind it would
then run what nobody asked for. Follow that: `from_params` validates its own
params and raises on anything unrecognised.

```python
# src/core/config.py
class StrategyConfig(StrictModel):
    name: str = "momentum"
    params: dict[str, Any] = Field(default_factory=dict)   # each strategy validates its own
    token_mints: tuple[str, ...] = ()
```

`StrictModel` **rejects unknown keys**. Match that in your own config
objects: an unrecognised key is an error, never an ignored field.

## 4. Costs

`src/execution/costs.py` exposes `CostModel`, `TradeCosts`, and
`sol_price_from_close(token_mint, close) -> Decimal | None`. **Do not
re-implement any of it and do not hardcode a SOL price** — a hardcoded `$200`
shipped here once and was wrong by 2x within days; the measured mean over the
1h window was `$87.53`. Take the price from each bar's own close, as the
backtest runner does.

The recurring cost per round trip is about **$0.0127**, which is 0.127% of a
$10 position and 0.254% of a $5 one. That is the hurdle a copy signal must
clear *before* it is interesting. ATA rent is a refundable deposit — a
capital lockup, not a cost — so it belongs in the write-up, not in the
hurdle.

## 5. Things that will get a diff rejected

- Any import of `solders`, or any function named `send`/`sign`, anywhere in
  what you write. Execution and signing already exist and are gated.
- `float` anywhere money is represented. `Decimal` throughout.
- Reading any key from anywhere but `os.environ`.
- A network call inside `generate()`, or anything that consults the wall
  clock inside it.
- Touching `src/core/gate.py` or `ops/live-gate.json`.
