"""Detect live-gate state changes and alert on them.

`evaluate_live_gate` answers "is live trading allowed right now?". It is
stateless, so nothing in the system could previously notice that the answer had
*changed* — and the change is the alertable event. An unlock that nobody is
told about is a bot that could start trading real money while the operator is
asleep; a re-lock that nobody is told about is a bot whose approval evaporated
mid-run.

Four transitions are alerted:

| Transition | Why it matters |
|---|---|
| `first_observation` | No prior record. The state is new information by definition, and staying silent would mean the very first unlock goes unannounced. |
| `unlocked` | locked → unlocked. Live trading just became possible. |
| `relocked` | unlocked → locked. Something that was approved no longer is. |
| `failures_changed` | still locked, but for different reasons — where a fingerprint mismatch first appears. |

A steady gate is silent: no transition, no email. That is the whole
rate-limiting story, and it is better than a time window because it cannot
suppress a genuine change that happens to arrive during a quiet period.

**This module cannot make the gate more permissive.** It reads a `GateResult`
and never constructs or modifies one. `observe()` returns the transition it
detected and nothing else; no caller can route a decision through it.

**Corruption fails noisy, not closed.** An unreadable snapshot is treated as "no
prior state", which alerts. This is the opposite of `risk.state`, deliberately:
there, a deleted file could clear a halt, so corruption had to mean halted.
Here the worst case of a lost snapshot is one redundant email, while the worst
case of trusting it is silence about a real unlock. Noise is the safe direction,
so there is no checksum to defend.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.alerts import Alert, Alerts, get_alerts
from core.gate import GateResult

SNAPSHOT_FILENAME = "live-gate-last-seen.json"

FIRST_OBSERVATION = "first_observation"
UNLOCKED = "unlocked"
RELOCKED = "relocked"
FAILURES_CHANGED = "failures_changed"


@dataclass(frozen=True)
class GateSnapshot:
    unlocked: bool
    failures: tuple[str, ...]
    observed_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "unlocked": self.unlocked,
            "failures": list(self.failures),
            "observed_at": self.observed_at.isoformat(),
        }

    @staticmethod
    def from_dict(raw: dict[str, object]) -> GateSnapshot:
        failures = raw["failures"]
        if not isinstance(failures, list) or not all(isinstance(f, str) for f in failures):
            raise ValueError("failures must be a list of strings")
        observed_at = datetime.fromisoformat(str(raw["observed_at"]))
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        return GateSnapshot(
            unlocked=bool(raw["unlocked"]),
            failures=tuple(failures),
            observed_at=observed_at.astimezone(timezone.utc),
        )


@dataclass(frozen=True)
class GateTransition:
    kind: str
    current: GateSnapshot
    previous: GateSnapshot | None
    fingerprint_mismatch: bool

    @property
    def is_urgent(self) -> bool:
        """Whether this needs attention now rather than at the next glance.

        An unlock means real money can move. A re-lock means an approval that
        was relied on is gone. A fingerprint mismatch means the approval on
        file was granted against a different bot. Everything else is a change
        in *why* a locked gate is locked, which is worth recording but is not
        an emergency.
        """
        return (
            self.kind in (UNLOCKED, RELOCKED)
            or self.fingerprint_mismatch
        )

    def subject(self) -> str:
        state = "UNLOCKED" if self.current.unlocked else "LOCKED"
        headline = {
            UNLOCKED: "live gate UNLOCKED — live trading is now possible",
            RELOCKED: "live gate RE-LOCKED — a previously granted approval no longer holds",
            FAILURES_CHANGED: f"live gate still {state}, for different reasons",
            FIRST_OBSERVATION: f"live gate is {state} (first observation on this host)",
        }[self.kind]
        prefix = "[TradeCC] "
        if self.fingerprint_mismatch:
            return f"{prefix}FINGERPRINT MISMATCH — {headline}"
        return f"{prefix}{headline}"

    def body(self) -> str:
        lines = [
            self.subject().removeprefix("[TradeCC] "),
            "",
            f"Observed at: {self.current.observed_at.isoformat()}",
            f"Gate state:  {'UNLOCKED' if self.current.unlocked else 'LOCKED'}",
        ]
        if self.previous is not None:
            lines.append(
                f"Previously:  {'UNLOCKED' if self.previous.unlocked else 'LOCKED'} "
                f"(as of {self.previous.observed_at.isoformat()})"
            )
        else:
            lines.append("Previously:  no recorded state on this host")

        if self.fingerprint_mismatch:
            lines += [
                "",
                "The approval on file was granted against a different configuration.",
                "Either restore the approved values or re-validate and re-approve.",
                "This is the one gate failure that can appear after an approval",
                "that previously passed, so it is called out separately.",
            ]

        lines += ["", "Current failures:"]
        if self.current.failures:
            lines += [f"  - {failure}" for failure in self.current.failures]
        else:
            lines.append("  (none — every gate condition is satisfied)")

        resolved = tuple(
            f for f in (self.previous.failures if self.previous else ()) 
            if f not in self.current.failures
        )
        if resolved:
            lines += ["", "No longer failing:"]
            lines += [f"  - {failure}" for failure in resolved]

        lines += [
            "",
            "This email reports a gate state change only. It is not an",
            "instruction to trade, and nothing has been sent on chain.",
        ]
        return "\n".join(lines)


class GateWatcher:
    """Remembers the last gate verdict seen on this host."""

    def __init__(self, state_dir: Path | str, alerts: Alerts | None = None) -> None:
        self._path = Path(state_dir) / SNAPSHOT_FILENAME
        self._alerts = alerts

    @property
    def path(self) -> Path:
        return self._path

    def _alerter(self) -> Alerts:
        # Resolved per call rather than at construction so a watcher built
        # before `configure_alerts()` still uses the configured sink.
        return self._alerts if self._alerts is not None else get_alerts()

    def load(self) -> GateSnapshot | None:
        if not self._path.is_file():
            return None
        try:
            return GateSnapshot.from_dict(json.loads(self._path.read_text()))
        except (json.JSONDecodeError, OSError, KeyError, ValueError, TypeError):
            # Unreadable means "unknown", which alerts. See the module docstring
            # for why noisy is the safe direction here.
            return None

    def save(self, snapshot: GateSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(snapshot.to_dict(), indent=2))
        os.replace(tmp, self._path)

    def observe(
        self, result: GateResult, now: datetime | None = None
    ) -> GateTransition | None:
        """Compare this verdict to the last one and alert if it changed.

        The snapshot advances only when there is nothing left to deliver. If a
        configured sink fails, the old snapshot stays on disk so the next
        evaluation detects the same transition again and retries the alert —
        an alert that failed to send is not an alert that happened.
        """
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        current = GateSnapshot(
            unlocked=result.unlocked,
            failures=tuple(result.failures),
            observed_at=moment.astimezone(timezone.utc),
        )
        previous = self.load()
        transition = _classify(previous, current, result.fingerprint_mismatch)

        if transition is None:
            return None

        delivered = self._alerter().send(
            Alert(transition.subject(), transition.body(), "gate.state_changed"),
            transition=transition.kind,
            unlocked=current.unlocked,
            fingerprint_mismatch=transition.fingerprint_mismatch,
            urgent=transition.is_urgent,
            failure_count=len(current.failures),
        )
        if delivered:
            self.save(current)
        return transition


def _classify(
    previous: GateSnapshot | None, current: GateSnapshot, fingerprint_mismatch: bool
) -> GateTransition | None:
    if previous is None:
        kind: str | None = FIRST_OBSERVATION
    elif previous.unlocked != current.unlocked:
        kind = UNLOCKED if current.unlocked else RELOCKED
    elif previous.failures != current.failures:
        kind = FAILURES_CHANGED
    else:
        kind = None

    if kind is None:
        return None
    return GateTransition(
        kind=kind,
        current=current,
        previous=previous,
        fingerprint_mismatch=fingerprint_mismatch,
    )
