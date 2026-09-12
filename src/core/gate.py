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


def evaluate_live_gate(gate_file: Path | str, now: datetime | None = None) -> GateResult:
    """Evaluate the live-trading gate. Returns locked on any doubt."""
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
