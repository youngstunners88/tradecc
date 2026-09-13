"""The live-trading validation gate.

`live` mode is locked until every condition in `planning/specs/mvp_spec.md`
is demonstrably met. This module is the enforcement point: it reads the
gate file, checks each condition, and returns a verdict.

Two properties matter more than the individual checks:

1. **It fails closed.** A missing file, malformed JSON, an unreadable
   field, an unexpected exception — all resolve to locked. There is no
   input to this function that produces "unlocked" by accident.
2. **The drawdown threshold must predate the paper run.** A threshold
   chosen after seeing the results is not a gate, it is a rationalisation,
   so a `threshold_set_at` later than `paper_started_at` fails.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from core.config import RunConfig, fingerprint_sections
from core.performance import MIN_POOLED_TRADES
from core.types import finite_decimal

MINIMUM_PAPER_TRADING_DAYS = 30


@dataclass(frozen=True)
class GateResult:
    unlocked: bool
    failures: tuple[str, ...]

    def describe(self) -> str:
        if self.unlocked:
            return "live gate: unlocked"
        return "live gate: LOCKED — " + "; ".join(self.failures)


def evaluate_live_gate(
    gate_file: Path | str, config: RunConfig, now: datetime | None = None
) -> GateResult:
    """Evaluate the live-trading gate. Returns locked on any doubt.

    `config` is required, not optional. The gate binds an approval to the exact
    strategy and limits it was granted against, and it cannot verify that
    binding without knowing what is actually about to run. An optional
    parameter would make the strongest check the easiest one to skip.
    """
    path = Path(gate_file)
    if not path.is_file():
        return GateResult(False, (f"no gate file at {path} — live mode has never been unlocked",))

    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return GateResult(False, (f"gate file unreadable ({exc}) — refusing to infer approval",))

    if not isinstance(raw, dict):
        return GateResult(False, ("gate file must contain a JSON object",))

    failures: list[str] = []
    failures.extend(_check_paper_duration(raw))
    failures.extend(_check_drawdown(raw))
    failures.extend(_check_expectancy(raw))
    failures.extend(_check_trade_count(raw))
    failures.extend(_check_fingerprint(raw, config))
    failures.extend(_check_human_approval(raw))
    return GateResult(not failures, tuple(failures))


def _check_paper_duration(raw: dict[str, Any]) -> list[str]:
    started = _parse_datetime(raw.get("paper_started_at"))
    ended = _parse_datetime(raw.get("paper_ended_at"))
    if started is None:
        return ["paper_started_at missing or not an ISO-8601 timestamp"]
    if ended is None:
        return ["paper_ended_at missing or not an ISO-8601 timestamp"]
    if ended < started:
        return ["paper_ended_at is before paper_started_at"]
    if ended - started < timedelta(days=MINIMUM_PAPER_TRADING_DAYS):
        observed = (ended - started).days
        return [
            f"paper run was {observed} days, needs at least {MINIMUM_PAPER_TRADING_DAYS}"
        ]
    return []


def _check_drawdown(raw: dict[str, Any]) -> list[str]:
    threshold = _parse_decimal(raw.get("max_drawdown_threshold_pct"))
    observed = _parse_decimal(raw.get("observed_max_drawdown_pct"))
    set_at = _parse_datetime(raw.get("threshold_set_at"))
    started = _parse_datetime(raw.get("paper_started_at"))

    failures: list[str] = []
    if threshold is None:
        failures.append("max_drawdown_threshold_pct missing or not a number")
    if observed is None:
        failures.append("observed_max_drawdown_pct missing or not a number")
    if set_at is None:
        failures.append("threshold_set_at missing — cannot prove the threshold predates the run")
    elif started is not None and set_at > started:
        failures.append(
            "threshold_set_at is after paper_started_at: the drawdown threshold was chosen "
            "after the run began, which does not constitute a gate"
        )
    if threshold is not None and observed is not None and observed > threshold:
        failures.append(f"observed drawdown {observed}% exceeds threshold {threshold}%")
    return failures


def _check_expectancy(raw: dict[str, Any]) -> list[str]:
    expectancy = _parse_decimal(raw.get("net_expectancy_usd"))
    if expectancy is None:
        return ["net_expectancy_usd missing or not a number (must be net of fees and slippage)"]
    if expectancy <= 0:
        return [f"net expectancy {expectancy} USD is not positive after fees and slippage"]
    return []


def _check_trade_count(raw: dict[str, Any]) -> list[str]:
    """Positive expectancy on too few trades is not evidence.

    The sweep produced "+$0.47 on 3 trades". Without this check a gate file
    reporting exactly that would unlock live trading.
    """
    value = raw.get("trade_count")
    if isinstance(value, bool) or not isinstance(value, int):
        return ["trade_count missing or not an integer"]
    if value < MIN_POOLED_TRADES:
        return [
            f"paper run produced {value} trades, needs at least {MIN_POOLED_TRADES} "
            "— positive expectancy on fewer is not distinguishable from luck"
        ]
    return []


def _check_fingerprint(raw: dict[str, Any], config: RunConfig) -> list[str]:
    """Bind the approval to the strategy and limits it was granted against.

    Without this, a gate file approved for one strategy unlocks live trading
    for any strategy — including one that was never tested.
    """
    recorded = raw.get("validated_fingerprint")
    if not isinstance(recorded, dict) or not recorded:
        return [
            "validated_fingerprint missing — cannot prove this approval was "
            "granted against the strategy and limits now configured"
        ]
    current = fingerprint_sections(config)
    changed = sorted(
        section
        for section in current
        if recorded.get(section) != current[section]
    )
    unknown = sorted(set(recorded) - set(current))
    failures: list[str] = []
    if changed:
        failures.append(
            "configuration changed since approval — "
            + ", ".join(f"{section!r} differs" for section in changed)
            + ": re-validate and re-approve, or restore the approved values"
        )
    if unknown:
        failures.append(
            f"validated_fingerprint has unrecognised sections {unknown} — "
            "it was written by a different version of this gate"
        )
    return failures


def _check_human_approval(raw: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    approved_by = raw.get("approved_by")
    if not isinstance(approved_by, str) or not approved_by.strip():
        failures.append("approved_by missing — a human must explicitly sign off on live trading")
    if _parse_datetime(raw.get("approved_at")) is None:
        failures.append("approved_at missing or not an ISO-8601 timestamp")
    return failures


def _parse_datetime(value: Any) -> datetime | None:
    """ISO-8601 to an aware UTC datetime, or None.

    Timestamps are normalised to UTC because the checks below compare them to
    each other. A file mixing an aware `paper_started_at` with a naive
    `paper_ended_at` used to raise `TypeError` straight out of this module —
    an uncaught crash where the contract promises "locked". A naive timestamp
    is read as UTC, which is the convention `risk.state` already uses for
    trading days.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_decimal(value: Any) -> Decimal | None:
    """Finite decimals only. `NaN` would raise out of a comparison below and
    `Infinity` would silently satisfy the drawdown check at any observed
    drawdown — both defeat the fail-closed property this module promises."""
    return finite_decimal(value)
