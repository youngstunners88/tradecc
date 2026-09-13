"""Out-of-band alerting for events the user must learn about without looking.

Structured logs and PostHog answer "what happened?" after the fact. An alert
answers "you need to know this now, even though you are not watching." The
`agent-mail-alerts` skill names the live-gate transitions as one of the events
that qualifies, and until now nothing in the codebase could send one.

Three properties this module commits to:

1. **Disabled by default.** With no sink configured, alerting is a no-op that
   still writes the structured log line. An unconfigured bot behaves exactly as
   it did before, so a missing API key degrades to local-only observability
   rather than to a crash mid-session.
2. **Redacted on the way out.** Bodies are assembled from `redact()`-ed context,
   the same path the logger uses, so an alert cannot carry something the log
   would have masked.
3. **It never raises into a caller.** A mail provider being down is not a reason
   to stop managing a position. Delivery failure is reported through the return
   value instead, and the caller decides what that means — `gate_watch` uses it
   to retry the alert on the next evaluation rather than losing it.

The transport lives outside `core` on purpose: `core` is the bottom layer and
must not import `execution`. `notify.agentmail` builds the real sink and
`cli._bootstrap` injects it, so the composition happens above both.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from core.logging import get_logger, redact

logger = get_logger("tradecc.alerts")


@dataclass(frozen=True)
class Alert:
    """One thing worth interrupting someone for."""

    subject: str
    body: str
    event: str


class AlertSink(Protocol):
    """Where an alert goes. `AgentMailSink` is the real one; tests use a fake."""

    def send(self, alert: Alert) -> None: ...


class Alerts:
    def __init__(self, sink: AlertSink | None = None) -> None:
        self._sink = sink

    @property
    def enabled(self) -> bool:
        return self._sink is not None

    def send(self, alert: Alert, **context: Any) -> bool:
        """Log the alert, then deliver it if a sink is configured.

        Returns True when there is nothing left to retry — either the sink
        accepted it, or alerting is switched off entirely and the log line is
        the whole story. Returns False only when a configured sink *failed*,
        which is the one case where the alert still needs to go out.

        The asymmetry is deliberate. Treating "no sink configured" as a failure
        would make an unconfigured bot retry forever; treating a delivery error
        as success would silently drop the alert the skill calls the most
        important one in the system.
        """
        payload = redact({"subject": alert.subject, "body": alert.body, **context})
        logger.warning(alert.event, extra=payload)

        if self._sink is None:
            return True

        try:
            self._sink.send(Alert(payload["subject"], payload["body"], alert.event))
        except Exception as exc:  # noqa: BLE001 - alerting must not raise
            logger.error(
                "alert_delivery_failed",
                extra={"event_name": alert.event, "error": str(exc)},
            )
            return False
        return True


_alerts = Alerts()


def configure_alerts(sink: AlertSink | None = None) -> Alerts:
    """Install the process-wide alerter.

    No environment sniffing here — the caller supplies the sink or there
    isn't one. `core` cannot construct an AgentMail client without importing
    `execution`, and inverting that layering to save one argument is the
    trade that put `SimulationOutcome` in the wrong module once already.
    """
    global _alerts
    _alerts = Alerts(sink)
    return _alerts


def get_alerts() -> Alerts:
    return _alerts


def alerts_configured(env: dict[str, str] | None = None) -> bool:
    """Whether the environment carries enough to build a real sink."""
    environ = os.environ if env is None else env
    return all(
        environ.get(name)
        for name in ("AGENTMAIL_API_KEY", "AGENTMAIL_FROM", "AGENTMAIL_TO")
    )
