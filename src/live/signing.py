"""Stage 6c — turning an authorised transaction into a signed one.

This is the only module in the project that touches a private key, and it is
written to keep that surface as small as possible:

- **The key is loaded from an environment variable and nowhere else.** Not a
  file, not a config value, not an argument. CLAUDE.md rule 1 says a key is
  never hardcoded or committed; the way that rule gets broken in practice is a
  helpful "just point it at keypair.json", so this module refuses a value that
  looks like a path rather than reading one.
- **The key is registered with the logger before anything else can see it**, so
  a stray log line or traceback carrying it is masked.
- **No error message ever contains key material**, including the "this did not
  parse" ones. A malformed key is reported by length and shape only.
- **`SignedTransaction` carries no key**, and the signer exposes no method that
  returns one.

Signing deliberately does NOT decide whether to send. It takes bytes that
something else already authorised and returns bytes; the refusal logic lives in
`live.preflight` and the send gate in `live.sender`. A signer that also decided
would be a second place where "should we?" is answered, and the two would
eventually disagree.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from core.logging import get_logger, register_secret

logger = get_logger("tradecc.live.signing")

PRIVATE_KEY_ENV = "SOLANA_PRIVATE_KEY"
SECRET_KEY_LENGTH = 64


class SigningError(Exception):
    """Key material or transaction bytes that cannot be used.

    Never carries the offending value — that is the whole point of a dedicated
    exception here rather than letting a library's own message propagate.
    """


@dataclass(frozen=True)
class SignedTransaction:
    """A signed transaction and the exact unsigned bytes it came from.

    Both halves travel together because the send gate needs to prove they
    correspond: the authorisation was issued against the *simulated* (unsigned)
    bytes, and signing changes the bytes. Carrying the origin lets the sender
    check the relationship instead of trusting that signing was faithful.
    """

    signed_bytes: bytes
    unsigned_bytes: bytes
    public_key: str


class Signer(Protocol):
    @property
    def public_key(self) -> str: ...

    def sign(self, unsigned_bytes: bytes) -> SignedTransaction: ...


class SoldersSigner:
    """The real signer. Holds a keypair; exposes no way to read it back."""

    def __init__(self, keypair: Any) -> None:
        self._keypair = keypair

    @property
    def public_key(self) -> str:
        return str(self._keypair.pubkey())

    def sign(self, unsigned_bytes: bytes) -> SignedTransaction:
        from solders.transaction import VersionedTransaction

        if not unsigned_bytes:
            raise SigningError("refusing to sign empty transaction bytes")
        try:
            unsigned = VersionedTransaction.from_bytes(unsigned_bytes)
        except Exception as exc:  # noqa: BLE001 - library errors vary by version
            raise SigningError(
                f"transaction bytes did not parse as a versioned transaction "
                f"({type(exc).__name__}); refusing to sign something we cannot read"
            ) from exc

        signed = VersionedTransaction(unsigned.message, [self._keypair])

        # The signature must cover exactly the message that was simulated. If
        # rebuilding changed a single byte of it, the authorisation issued
        # against the simulated bytes would no longer describe what we send.
        if bytes(signed.message) != bytes(unsigned.message):
            raise SigningError(
                "signing altered the transaction message — refusing to produce "
                "a transaction that was never simulated"
            )

        logger.info(
            "transaction_signed",
            extra={"public_key": self.public_key, "bytes": len(bytes(signed))},
        )
        return SignedTransaction(
            signed_bytes=bytes(signed),
            unsigned_bytes=unsigned_bytes,
            public_key=self.public_key,
        )


def _decode_secret(raw: str) -> bytes:
    """Accept the two formats a Solana key is normally handed out in.

    Errors describe shape, never content.
    """
    text = raw.strip()

    if text.startswith("["):
        try:
            values = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SigningError(
                f"{PRIVATE_KEY_ENV} looked like a JSON array but did not parse"
            ) from exc
        if (
            not isinstance(values, list)
            or len(values) != SECRET_KEY_LENGTH
            or not all(isinstance(v, int) and 0 <= v <= 255 for v in values)
        ):
            raise SigningError(
                f"{PRIVATE_KEY_ENV} as JSON must be {SECRET_KEY_LENGTH} integers "
                f"in 0..255; got {len(values) if isinstance(values, list) else 'not a list'}"
            )
        return bytes(values)

    try:
        from solders.keypair import Keypair

        return bytes(Keypair.from_base58_string(text))
    except SigningError:
        raise
    except Exception as exc:  # noqa: BLE001 - library errors vary by version
        raise SigningError(
            f"{PRIVATE_KEY_ENV} is {len(text)} characters and parsed as neither a "
            f"base58 keypair nor a {SECRET_KEY_LENGTH}-integer JSON array"
        ) from exc


def load_signer_from_env(env: dict[str, str]) -> SoldersSigner | None:
    """Build a signer from the environment, or None when no key is set.

    Returning None rather than raising is deliberate: paper and backtest runs
    have no key and must not be broken by its absence. Refusing to *send*
    without a signer is the sender's job, and it does refuse.
    """
    raw = env.get(PRIVATE_KEY_ENV)
    if not raw or not raw.strip():
        return None

    # Registered before any parsing, so a parse failure cannot log it.
    register_secret(raw.strip())

    if _looks_like_a_path(raw.strip()):
        raise SigningError(
            f"{PRIVATE_KEY_ENV} looks like a file path. This project never reads "
            "a key from a file — a path is how a key ends up committed. Export "
            "the key material itself into the variable instead."
        )

    secret = _decode_secret(raw.strip())
    from solders.keypair import Keypair

    keypair = Keypair.from_bytes(secret)
    logger.info("signer_loaded", extra={"public_key": str(keypair.pubkey())})
    return SoldersSigner(keypair)


def _looks_like_a_path(value: str) -> bool:
    return (
        value.startswith(("/", "./", "../", "~"))
        or value.endswith((".json", ".key", ".pem", ".txt"))
        or "\\" in value
    )
