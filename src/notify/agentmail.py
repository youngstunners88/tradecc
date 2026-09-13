"""AgentMail delivery for TradeCC alerts.

Built on the project's own `ProviderHttpClient` rather than a mail SDK: the
same rate limiting, retry and backoff every other provider gets, and no new
third-party dependency on a money-adjacent codebase. The `UrllibTransport`
reasoning applies unchanged — a smaller supply-chain surface is worth more
than nicer ergonomics.

The API key is sent in a header and never in the URL, so `redacted_url` is
simply the URL. It is registered with the logger's secret list at bootstrap,
so a key that somehow reached a log line would be masked there too.
"""

from __future__ import annotations

import json
from typing import Any

from core.alerts import Alert
from core.logging import get_logger
from core.rate_limit import RateLimiter
from execution.http import ProviderHttpClient, HttpTransport, UrllibTransport

logger = get_logger("tradecc.notify.agentmail")

DEFAULT_BASE_URL = "https://api.agentmail.to"
DEFAULT_MAX_REQUESTS_PER_MINUTE = 20


class AgentMailSink:
    """Sends one alert as one email.

    Deliberately not batched. The `agent-mail-alerts` skill asks for batching
    on *repeating* events like slippage rejections, where three emails say
    nothing three emails' worth. Gate transitions are not that: each one is a
    distinct state change, they are rare by construction, and a steady gate
    sends nothing at all. Batching them would only delay the one email that
    matters.
    """

    def __init__(
        self,
        api_key: str,
        sender: str,
        recipient: str,
        base_url: str = DEFAULT_BASE_URL,
        transport: HttpTransport | None = None,
        client: ProviderHttpClient | None = None,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("AgentMail base URL must use https")
        self._api_key = api_key
        self._sender = sender
        self._recipient = recipient
        self._base_url = base_url.rstrip("/")
        self._client = client or ProviderHttpClient(
            provider="agentmail",
            transport=transport or UrllibTransport(),
            limiter=RateLimiter(DEFAULT_MAX_REQUESTS_PER_MINUTE),
        )

    def send(self, alert: Alert) -> None:
        payload: dict[str, Any] = {
            "from": self._sender,
            "to": [self._recipient],
            "subject": alert.subject,
            "text": alert.body,
        }
        url = f"{self._base_url}/v0/inboxes/{self._sender}/messages/send"
        self._client.request(
            "POST",
            url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            body=json.dumps(payload).encode(),
        )
        logger.info("alert_sent", extra={"event_name": alert.event, "provider": "agentmail"})


def build_sink_from_env(env: dict[str, str]) -> AgentMailSink | None:
    """Construct the sink if the environment carries a full configuration.

    All three of key, sender and recipient are required. A partial
    configuration returns None and logs it rather than half-building a client
    that fails on first send — the point of failure should be startup, where
    someone is looking, not the moment an unlock needs announcing.
    """
    api_key = env.get("AGENTMAIL_API_KEY")
    sender = env.get("AGENTMAIL_FROM")
    recipient = env.get("AGENTMAIL_TO")
    if api_key and sender and recipient:
        return AgentMailSink(
            api_key,
            sender,
            recipient,
            base_url=env.get("AGENTMAIL_BASE_URL", DEFAULT_BASE_URL),
        )
    if api_key or sender or recipient:
        missing = [
            name
            for name, value in (
                ("AGENTMAIL_API_KEY", api_key),
                ("AGENTMAIL_FROM", sender),
                ("AGENTMAIL_TO", recipient),
            )
            if not value
        ]
        logger.warning("alerts_partially_configured", extra={"missing": missing})
    return None
