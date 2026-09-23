"""A validation clock that reports honestly, including when it has not started.

Extracted from Hydra's paper run (2026-09-23), where four independent failures
each kept the clock at zero and NONE of them raised an error:

  1. No caller existed. `package.json` advertised four scripts; none of the
     four files was ever written. Every library was green and unused.
  2. The store was a dict, so every restart silently reset the run.
  3. The gate's evidence was a boolean the caller handed in.
  4. The status tool mis-parsed its own arguments and reported NOT STARTED
     over a clock that was running.

All four are ABSENCES. This module makes three of them raise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

__all__ = [
    "MIN_RESOLVED_DEFAULT",
    "ClockError",
    "ClockStatus",
    "Decision",
    "status_of",
    "verify_not_restarted",
    "blockers",
]

SECONDS_PER_DAY = 86_400.0

# Derived, not chosen: n >= (1.96 / (2 * tolerance))^2 for a ten-point
# tolerance gives 97. Twenty flawless outcomes look like proof and are not.
MIN_RESOLVED_DEFAULT = 97


class ClockError(RuntimeError):
    pass


@dataclass(frozen=True)
class Decision:
    """One recorded prediction. `outcome` is None until reality reports back."""

    id: str
    at: float
    outcome: bool | None = None

    @property
    def resolved(self) -> bool:
        return self.outcome is not None


@dataclass(frozen=True)
class ClockStatus:
    started_at: float | None
    now: float
    elapsed_days: float
    required_days: float
    decisions: int
    resolved: int
    min_resolved: int

    @property
    def started(self) -> bool:
        return self.started_at is not None

    @property
    def days_satisfied(self) -> bool:
        return self.started and self.elapsed_days >= self.required_days

    @property
    def sample_satisfied(self) -> bool:
        return self.resolved >= self.min_resolved

    @property
    def satisfied(self) -> bool:
        """Both conditions. Never one standing in for the other.

        Shortening the calendar is the tempting move and it does not work: it
        moves `days_satisfied` while leaving `sample_satisfied` exactly where
        it was, because a shorter window does not produce more outcomes.
        """
        return self.days_satisfied and self.sample_satisfied


def status_of(
    decisions: Sequence[Decision],
    *,
    required_days: float,
    now: float,
    min_resolved: int = MIN_RESOLVED_DEFAULT,
) -> ClockStatus:
    """Derive the clock from the decisions themselves.

    The start is the timestamp of the EARLIEST decision, never a stored
    `started_at` field. A hand-written start date asserts that a run happened;
    the oldest decision is evidence one did. They differ exactly when it
    matters -- when someone wants the clock to have started before the work.
    """
    if not (required_days > 0):
        raise ClockError(
            f"required_days must be positive; got {required_days}. A zero-day "
            "minimum is not a gate."
        )
    if min_resolved < 1:
        raise ClockError(
            f"min_resolved must be at least 1; got {min_resolved}. A gate that "
            "accepts zero outcomes passes vacuously, which is how an empty "
            "check goes unnoticed."
        )
    if not decisions:
        return ClockStatus(None, now, 0.0, required_days, 0, 0, min_resolved)

    started_at = min(d.at for d in decisions)
    if started_at > now:
        raise ClockError(
            f"the earliest decision is at {started_at}, later than now ({now}). "
            "A clock running backwards means the clock source and the decision "
            "source disagree; fix that before trusting any elapsed figure."
        )
    return ClockStatus(
        started_at=started_at,
        now=now,
        elapsed_days=(now - started_at) / SECONDS_PER_DAY,
        required_days=required_days,
        decisions=len(decisions),
        resolved=sum(1 for d in decisions if d.resolved),
        min_resolved=min_resolved,
    )


def verify_not_restarted(before: ClockStatus, after: ClockStatus) -> None:
    """Prove durability: run the system twice, compare, and raise if it reset.

    This is the step people skip, and skipping it is why a volatile store
    survives review. ONE run cannot distinguish a durable store from a
    dictionary -- both look identical. Two runs across separate processes can.

    `after` must carry MORE decisions and the SAME start. A moved start means
    the store did not persist; an unchanged count means nothing was written.
    """
    if not before.started:
        raise ClockError(
            "the 'before' clock had not started, so this comparison cannot "
            "show anything. Record a decision first."
        )
    if not after.started:
        raise ClockError(
            "the clock reports NOT STARTED after a run that recorded "
            "decisions. Either the store is volatile or the status tool is "
            "reading the wrong place -- both have happened."
        )
    if after.started_at != before.started_at:
        raise ClockError(
            f"the clock RESTARTED: {before.started_at} -> {after.started_at}. "
            "The store is not durable across processes. A run measured in days "
            "spans restarts, so this clock would never reach its threshold."
        )
    if after.decisions <= before.decisions:
        raise ClockError(
            f"decision count did not grow ({before.decisions} -> "
            f"{after.decisions}). The second run wrote nothing, so this proves "
            "persistence of an empty file, not of the journal."
        )


def blockers(status: ClockStatus) -> list[str]:
    """What is actually in the way, listed separately.

    Two conditions that fail for different reasons at different times. A
    single 'not ready' hides which one is binding, and the wrong one gets
    'fixed'.
    """
    if not status.started:
        return [
            "the clock has NOT STARTED: no decisions recorded. Check that an "
            "entry point exists and actually calls the function that writes "
            "evidence -- an advertised script whose file is missing is the "
            "most common cause."
        ]
    out: list[str] = []
    if not status.days_satisfied:
        out.append(
            f"{status.required_days - status.elapsed_days:.2f} more days of elapsed time"
        )
    if not status.sample_satisfied:
        out.append(f"{status.min_resolved - status.resolved} more RESOLVED outcomes")
    return out
