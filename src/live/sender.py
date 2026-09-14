"""Stage 6d — the only path from signed bytes to the chain.

Everything before this point refuses by default and produces evidence:
`RiskEngine.approve` owns sizing, slippage, the breaker and the gate;
`HeliusRpcClient.simulate_transaction` answers what would happen;
`live.preflight.authorize_send` issues a `SendAuthorization` bound to the
digest of the exact bytes that were simulated; `live.signing` turns those
bytes into a signature. This module is where all of it is finally checked
against each other, once, immediately before transmitting.

The problem this module exists to solve is subtle and worth stating plainly.
**The authorisation is issued against UNSIGNED bytes** — simulation runs with
`sigVerify: false` on an unsigned transaction — but what gets sent is SIGNED,
and therefore has a different digest. A naive check would compare the
authorisation to the signed bytes, find they differ, and either fail always or
be "fixed" by dropping the check. So the sender proves the relationship
instead:

1. the authorisation matches the unsigned bytes the signer says it started from,
2. the signed transaction's message is byte-identical to that unsigned message,
   parsed independently rather than taken on the signer's word, and
3. the signature over that message actually verifies.

Together those say: *the thing about to be transmitted is a correctly signed
instance of precisely the transaction that was simulated and authorised.*

Everything here fails closed. There is no argument, no configuration and no
provider response that produces a send by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol

from core.config import RiskConfig
from core.logging import get_logger
from core.telemetry import log_and_track
from core.types import digest_of
from live.preflight import SendAuthorization
from live.signing import SignedTransaction

logger = get_logger("tradecc.live.sender")

# An authorisation older than this describes chain state the transaction will
# never meet — Solana blockhashes expire after ~150 slots (~60s). Deliberately
# tighter than that: the gap between authorising and transmitting should be
# milliseconds, and anything near a minute means something stalled.
MAX_AUTHORIZATION_AGE = timedelta(seconds=30)


class TransactionSubmitter(Protocol):
    """The transmit capability. `HeliusTransactionSubmitter` is the real one."""

    def send_transaction(self, transaction_base64: str) -> str: ...

    def get_balance_sol(self, pubkey: str) -> Decimal: ...


@dataclass(frozen=True)
class SendResult:
    """Either a signature or the reasons there is none. Never both."""

    signature: str | None
    refusals: tuple[str, ...] = ()

    @property
    def sent(self) -> bool:
        return self.signature is not None

    def describe(self) -> str:
        if self.sent:
            return f"sent {self.signature}"
        return "send REFUSED — " + "; ".join(self.refusals)


@dataclass
class TransactionSender:
    """Checks every precondition together, then transmits at most once."""

    submitter: TransactionSubmitter
    risk: RiskConfig
    _spent: set[str] = field(default_factory=set)

    def send(
        self,
        signed: SignedTransaction,
        authorization: SendAuthorization | None,
        *,
        now: datetime | None = None,
    ) -> SendResult:
        moment = now or datetime.now(timezone.utc)
        refusals = self._refusals(signed, authorization, moment)
        if refusals:
            log_and_track(
                "live.send_refused",
                reasons=list(refusals),
                public_key=signed.public_key,
            )
            return SendResult(signature=None, refusals=tuple(refusals))

        # Marked spent BEFORE transmitting. If the provider call raises after
        # the bytes reached the cluster, a retry would double-send; treating an
        # attempt as spent means the worst case is a missed confirmation we can
        # look up, rather than a second transaction we cannot take back.
        assert authorization is not None  # guaranteed by _refusals
        self._spent.add(authorization.transaction_digest)

        import base64

        signature = self.submitter.send_transaction(
            base64.b64encode(signed.signed_bytes).decode()
        )
        log_and_track(
            "live.transaction_sent",
            tx_signature=signature,
            size_usd=authorization.size_usd,
            public_key=signed.public_key,
        )
        return SendResult(signature=signature)

    def _refusals(
        self,
        signed: SignedTransaction,
        authorization: SendAuthorization | None,
        now: datetime,
    ) -> list[str]:
        if authorization is None:
            # First and alone, because every later check reads the
            # authorisation. No authorisation is the ordinary state.
            return [
                "no send authorisation — preflight must issue one against a "
                "simulated transaction before anything can be sent"
            ]

        refusals: list[str] = []

        if authorization.transaction_digest in self._spent:
            refusals.append(
                "this authorisation has already been used — it permits exactly "
                "one send, and re-sending is how one trade becomes two"
            )

        age = now - authorization.authorized_at
        if age < timedelta(0):
            refusals.append(
                "authorisation is timestamped in the future — refusing to reason about it"
            )
        elif age > MAX_AUTHORIZATION_AGE:
            refusals.append(
                f"authorisation is {age.total_seconds():.0f}s old, limit is "
                f"{MAX_AUTHORIZATION_AGE.total_seconds():.0f}s — re-simulate and re-authorise"
            )

        if not authorization.authorizes(signed.unsigned_bytes):
            refusals.append(
                "authorisation does not match the transaction that was signed — "
                "the simulated bytes and the signed bytes are different transactions"
            )

        refusals.extend(self._verify_signature_covers_authorized_message(signed))
        refusals.extend(self._check_hot_wallet_balance(signed.public_key))
        return refusals

    def _verify_signature_covers_authorized_message(
        self, signed: SignedTransaction
    ) -> list[str]:
        """Re-derive the relationship rather than trusting the signer.

        `SignedTransaction` carries both halves because the signer says they
        correspond. This checks it: a buggy or substituted signer that returned
        a signature over different bytes would pass every digest comparison
        above, because those compare the authorisation to the *unsigned* half
        it also supplied.
        """
        try:
            from solders.transaction import VersionedTransaction

            unsigned = VersionedTransaction.from_bytes(signed.unsigned_bytes)
            transmitted = VersionedTransaction.from_bytes(signed.signed_bytes)
        except Exception as exc:  # noqa: BLE001 - library errors vary by version
            return [
                f"transaction bytes did not parse ({type(exc).__name__}) — "
                "refusing to send something we cannot read"
            ]

        if bytes(transmitted.message) != bytes(unsigned.message):
            return [
                "the signed transaction carries a different message than the one "
                "simulated and authorised — refusing to send it"
            ]

        results = transmitted.verify_with_results()
        if not results or not all(results):
            return [
                "the transaction's signature does not verify against its own "
                "message — refusing to spend a send on bytes the cluster will reject"
            ]
        return []

    def _check_hot_wallet_balance(self, public_key: str) -> list[str]:
        """CLAUDE.md rule 2, enforced approximately but usefully.

        Nothing can prove a wallet is "dedicated". What it can do is notice
        that the wallet holds more than a throwaway should, which is the
        observable consequence of pointing this at a main wallet by mistake.

        A balance lookup that fails is a refusal, not a pass: not knowing the
        balance is not the same as knowing it is small.
        """
        try:
            balance = self.submitter.get_balance_sol(public_key)
        except Exception as exc:  # noqa: BLE001 - any provider failure is a refusal
            return [
                f"could not read the wallet balance ({type(exc).__name__}) — "
                "refusing to send from a wallet whose size is unknown"
            ]

        if balance > self.risk.max_hot_wallet_sol:
            return [
                f"wallet holds {balance} SOL, above the {self.risk.max_hot_wallet_sol} "
                "SOL hot-wallet ceiling — this bot must run on a dedicated wallet "
                "funded only with capital you can afford to lose (CLAUDE.md rule 2). "
                "Move the excess out, or raise risk.max_hot_wallet_sol deliberately."
            ]
        return []
