"""Strategy lookup by name.

Adding v0.2's copy-trading strategy means adding one entry here and one
module — nothing in `execution/` or `risk/` changes, which is the whole
point of keeping the strategy boundary narrow.
"""

from __future__ import annotations

from typing import Any, Callable

from core.config import StrategyConfig
from strategy.base import Strategy
from strategy.strategy_momentum import NAME as MOMENTUM, MomentumStrategy

_BUILDERS: dict[str, Callable[[dict[str, Any]], Strategy]] = {
    MOMENTUM: MomentumStrategy.from_params,
}


def available_strategies() -> tuple[str, ...]:
    return tuple(sorted(_BUILDERS))


def build_strategy(config: StrategyConfig) -> Strategy:
    """Build the configured strategy, failing loudly on an unknown name.

    A typo'd strategy name must not silently fall back to a default — that
    would run something the operator did not ask for, with real money
    eventually behind it.
    """
    builder = _BUILDERS.get(config.name)
    if builder is None:
        raise ValueError(
            f"unknown strategy {config.name!r}; available: {', '.join(available_strategies())}"
        )
    return builder(dict(config.params))
