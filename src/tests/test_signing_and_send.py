"""Stage 6c/6d — signing, and the single path to the chain.

This is the most safety-critical code in the project: it is the only place
that holds a private key and the only place that can move real money. Every
refusal below is exercised, and the suite is written so that removing any one
check fails at least one test.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.config import RiskConfig
from core.logging import REDACTED
from core.types import digest_of
from live.preflight import SendAuthorization
from live.sender import MAX_AUTHORIZATION_AGE, SendResult, TransactionSender
from live.signing import (
    PRIVATE_KEY_ENV,
    SignedTransaction,
    SigningError,
    SoldersSigner,
    load_signer_from_env,
)

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def a_keypair():
    from solders.keypair import Keypair

    return Keypair()


def an_unsigned_transaction(keypair, payload: bytes = b"\x01") -> bytes:
    """A structurally real v0 transaction with an empty signature slot."""
    from solders.hash import Hash
    from solders.instruction import AccountMeta, Instruction
    from solders.message import MessageV0
    from solders.pubkey import Pubkey
    from solders.signature import Signature
    from solders.transaction import VersionedTransaction

    ix = Instruction(
        Pubkey.new_unique(), payload, [AccountMeta(keypair.pubkey(), True, True)]
    )
    message = MessageV0.try_compile(keypair.pubkey(), [ix], [], Hash.default())
    return bytes(VersionedTransaction.populate(message, [Signature.default()]))


class FakeSubmitter:
    def __init__(self, balance: str = "0.5", fail_balance: bool = False) -> None:
        self.balance = Decimal(balance)
        self.fail_balance = fail_balance
        self.sent: list[str] = []

    def send_transaction(self, transaction_base64: str) -> str:
        self.sent.append(transaction_base64)
        return "5" + "x" * 86

    def get_balance_sol(self, pubkey: str) -> Decimal:
        if self.fail_balance:
            raise RuntimeError("rpc down")
        return self.balance


def sender(submitter=None, **risk_kwargs) -> TransactionSender:
    return TransactionSender(
        submitter=submitter or FakeSubmitter(), risk=RiskConfig(**risk_kwargs)
    )


def signed_and_authorized(keypair=None, at=NOW):
    kp = keypair or a_keypair()
    unsigned = an_unsigned_transaction(kp)
    signed = SoldersSigner(kp).sign(unsigned)
    auth = SendAuthorization(
        transaction_digest=digest_of(unsigned), authorized_at=at, size_usd="10"
    )
    return signed, auth


# --- 6c: signing ---------------------------------------------------------


def test_signing_preserves_the_simulated_message():
    """The authorisation is issued against the simulated message. If signing
    changed it, the thing sent would be a transaction nobody simulated."""
    from solders.transaction import VersionedTransaction

    kp = a_keypair()
    unsigned = an_unsigned_transaction(kp)
    signed = SoldersSigner(kp).sign(unsigned)

    assert bytes(VersionedTransaction.from_bytes(signed.signed_bytes).message) == bytes(
        VersionedTransaction.from_bytes(unsigned).message
    )
    assert signed.unsigned_bytes == unsigned


def test_a_signed_transaction_carries_no_key_material():
    kp = a_keypair()
    signed = SoldersSigner(kp).sign(an_unsigned_transaction(kp))

    assert bytes(kp) not in signed.signed_bytes
    assert not any("key" in f and f != "public_key" for f in vars(signed))


def test_the_signer_exposes_no_way_to_read_the_key_back():
    surface = {n for n in dir(SoldersSigner) if not n.startswith("_")}
    assert surface == {"public_key", "sign"}


@pytest.mark.parametrize("garbage", [b"", b"not a transaction", b"\x00" * 8])
def test_unparseable_bytes_are_refused_rather_than_signed(garbage):
    with pytest.raises(SigningError):
        SoldersSigner(a_keypair()).sign(garbage)


# --- 6c: key loading -----------------------------------------------------


def test_no_key_in_the_environment_yields_no_signer():
    """Paper and backtest runs have no key and must not break."""
    assert load_signer_from_env({}) is None
    assert load_signer_from_env({PRIVATE_KEY_ENV: "   "}) is None


def test_a_json_array_key_loads():
    kp = a_keypair()
    signer = load_signer_from_env({PRIVATE_KEY_ENV: json.dumps(list(bytes(kp)))})
    assert signer is not None
    assert signer.public_key == str(kp.pubkey())


def test_a_base58_key_loads():
    kp = a_keypair()
    signer = load_signer_from_env({PRIVATE_KEY_ENV: str(kp)})
    assert signer is not None
    assert signer.public_key == str(kp.pubkey())


@pytest.mark.parametrize(
    "path",
    ["/home/user/keypair.json", "./key.json", "~/.config/solana/id.json", "wallet.key"],
)
def test_a_file_path_is_refused(path):
    """A path is how a key ends up committed. CLAUDE.md rule 1."""
    with pytest.raises(SigningError, match="file path"):
        load_signer_from_env({PRIVATE_KEY_ENV: path})


@pytest.mark.parametrize("bad", ["[1,2,3]", "[]", "not-base58-at-all!!!", "[999]*64"])
def test_malformed_key_material_never_appears_in_the_error(bad):
    with pytest.raises(SigningError) as excinfo:
        load_signer_from_env({PRIVATE_KEY_ENV: bad})
    assert bad not in str(excinfo.value)


def test_the_key_is_registered_as_a_secret_before_parsing(caplog):
    """Registered first, so even a parse failure cannot log it."""
    import logging

    from core.logging import redact

    secret = str(a_keypair())
    load_signer_from_env({PRIVATE_KEY_ENV: secret})
    assert REDACTED in redact({"note": f"key was {secret}"})["note"]
    del logging, caplog


# --- 6d: the send gate ---------------------------------------------------


def test_a_fully_authorized_send_transmits_once():
    submitter = FakeSubmitter()
    signed, auth = signed_and_authorized()

    result = sender(submitter).send(signed, auth, now=NOW)

    assert result.sent
    assert result.signature
    assert len(submitter.sent) == 1
    assert base64.b64decode(submitter.sent[0]) == signed.signed_bytes


def test_no_authorization_refuses():
    submitter = FakeSubmitter()
    signed, _ = signed_and_authorized()

    result = sender(submitter).send(signed, None, now=NOW)

    assert not result.sent
    assert submitter.sent == []
    assert "no send authorisation" in result.describe()


def test_an_authorization_for_different_bytes_refuses():
    """The core guarantee: a transaction that differs from the simulated one
    has no authorisation, because the token it would need was never issued."""
    submitter = FakeSubmitter()
    signed, _ = signed_and_authorized()
    foreign = SendAuthorization(
        transaction_digest=digest_of(b"some other transaction"),
        authorized_at=NOW,
        size_usd="10",
    )

    result = sender(submitter).send(signed, foreign, now=NOW)

    assert not result.sent
    assert submitter.sent == []
    assert "different transactions" in result.describe()


def test_a_signature_over_different_bytes_refuses():
    """A signer that returned a signature over a substituted message would
    satisfy every digest check, because it supplies both halves. This catches
    it by re-deriving the relationship."""
    kp = a_keypair()
    authorized_unsigned = an_unsigned_transaction(kp, payload=b"\x01")
    other_signed = SoldersSigner(kp).sign(an_unsigned_transaction(kp, payload=b"\x02"))

    substituted = SignedTransaction(
        signed_bytes=other_signed.signed_bytes,
        unsigned_bytes=authorized_unsigned,
        public_key=other_signed.public_key,
    )
    auth = SendAuthorization(
        transaction_digest=digest_of(authorized_unsigned),
        authorized_at=NOW,
        size_usd="10",
    )

    submitter = FakeSubmitter()
    result = sender(submitter).send(substituted, auth, now=NOW)

    assert not result.sent
    assert submitter.sent == []
    assert "different message" in result.describe()


def test_an_unsigned_transaction_refuses():
    """Empty signature slots must not reach the cluster."""
    kp = a_keypair()
    unsigned = an_unsigned_transaction(kp)
    never_signed = SignedTransaction(
        signed_bytes=unsigned, unsigned_bytes=unsigned, public_key=str(kp.pubkey())
    )
    auth = SendAuthorization(digest_of(unsigned), NOW, "10")

    submitter = FakeSubmitter()
    result = sender(submitter).send(never_signed, auth, now=NOW)

    assert not result.sent
    assert "does not verify" in result.describe()


def test_the_same_authorization_cannot_be_used_twice():
    """Re-sending is how one trade becomes two."""
    submitter = FakeSubmitter()
    s = sender(submitter)
    signed, auth = signed_and_authorized()

    assert s.send(signed, auth, now=NOW).sent
    second = s.send(signed, auth, now=NOW)

    assert not second.sent
    assert len(submitter.sent) == 1
    assert "already been used" in second.describe()


def test_a_stale_authorization_refuses():
    submitter = FakeSubmitter()
    signed, auth = signed_and_authorized()
    late = NOW + MAX_AUTHORIZATION_AGE + timedelta(seconds=1)

    result = sender(submitter).send(signed, auth, now=late)

    assert not result.sent
    assert submitter.sent == []
    assert "old, limit is" in result.describe()


def test_an_authorization_from_the_future_refuses():
    submitter = FakeSubmitter()
    signed, auth = signed_and_authorized(at=NOW + timedelta(minutes=5))

    result = sender(submitter).send(signed, auth, now=NOW)

    assert not result.sent
    assert "timestamped in the future" in result.describe()


def test_a_wallet_above_the_hot_ceiling_refuses():
    """CLAUDE.md rule 2 — a dedicated hot wallet, never the main one."""
    submitter = FakeSubmitter(balance="25")
    signed, auth = signed_and_authorized()

    result = sender(submitter).send(signed, auth, now=NOW)

    assert not result.sent
    assert submitter.sent == []
    assert "hot-wallet ceiling" in result.describe()


def test_an_unreadable_balance_refuses_rather_than_assuming_it_is_small():
    submitter = FakeSubmitter(fail_balance=True)
    signed, auth = signed_and_authorized()

    result = sender(submitter).send(signed, auth, now=NOW)

    assert not result.sent
    assert submitter.sent == []
    assert "whose size is unknown" in result.describe()


def test_every_refusal_reason_is_reported_together():
    """Fixing one must not reveal the next at send time."""
    submitter = FakeSubmitter(balance="25")
    signed, _ = signed_and_authorized()
    wrong_and_stale = SendAuthorization(
        transaction_digest=digest_of(b"other"),
        authorized_at=NOW - timedelta(minutes=10),
        size_usd="10",
    )

    result = sender(submitter).send(signed, wrong_and_stale, now=NOW)

    assert not result.sent
    assert len(result.refusals) >= 3


def test_a_refused_send_does_not_consume_the_authorization():
    """A refusal must be recoverable: fix the cause and the token still works."""
    signed, auth = signed_and_authorized()
    submitter = FakeSubmitter(balance="25")
    s = TransactionSender(submitter=submitter, risk=RiskConfig())

    assert not s.send(signed, auth, now=NOW).sent
    submitter.balance = Decimal("0.5")

    assert s.send(signed, auth, now=NOW).sent


def test_send_result_never_reports_both_a_signature_and_refusals():
    assert SendResult(signature="sig").sent
    assert not SendResult(signature=None, refusals=("nope",)).sent
