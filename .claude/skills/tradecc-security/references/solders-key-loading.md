# Safe Key Loading with solders (tradecc)

## Rules

- Load the keypair **once** at process start from a secrets manager or injected environment variable.
- Never persist the `Keypair` object longer than necessary.
- Never log, print, or include the key (or its bytes/seed) in exceptions, metrics, or debug dumps.
- Prefer a dedicated hot wallet funded only with capital that can be lost.
- The value in `.env.example` must always be a placeholder / secret reference name, never a real key.

## Recommended Pattern

```python
import os
from solders.keypair import Keypair
from solders.pubkey import Pubkey

def load_hot_wallet() -> Keypair:
    """
    Load the bot's dedicated hot wallet.
    Expects WALLET_PRIVATE_KEY_SECRET_REF to contain either:
      - base58-encoded secret key, or
      - JSON array of 64 bytes (Solana CLI style)
    Adjust parsing to match the exact format chosen for the secrets manager.
    """
    raw = os.environ.get("WALLET_PRIVATE_KEY_SECRET_REF")
    if not raw:
        raise RuntimeError(
            "WALLET_PRIVATE_KEY_SECRET_REF is not set. "
            "Load the key only from a secrets manager or runtime-injected env."
        )

    raw = raw.strip()

    # Example: base58 secret key
    try:
        return Keypair.from_base58_string(raw)
    except Exception:
        pass

    # Example: JSON byte array "[1,2,3,...,64]"
    try:
        import json
        secret_bytes = bytes(json.loads(raw))
        return Keypair.from_bytes(secret_bytes)
    except Exception as e:
        raise RuntimeError("Unable to parse wallet secret") from e


def get_public_key(kp: Keypair) -> Pubkey:
    return kp.pubkey()
```

## Anti-Patterns (reject these)

```python
# NEVER
keypair = Keypair.from_base58_string("ActualSecretKeyHere...")  # hard-coded
print(f"Using key: {keypair}")                                 # logging
logging.info("seed", seed=seed_phrase)                         # sensitive log
open(".wallet", "w").write(secret)                             # writing to disk in repo
```

## Testing Guidance

- Unit tests must **never** contain real private keys.
- Use `Keypair()` (random) or a fixed test-only keypair generated in the test setup and discarded.
- Prefer mocking the load function rather than loading a real secret in CI.

## Rotation

If compromise is suspected:
1. Immediately stop the bot.
2. Generate a new dedicated keypair.
3. Transfer remaining funds from the old wallet (if any) using a one-off secure process.
4. Update the secret in the secrets manager / runtime env.
5. Record the incident in `ops/incident-logs/`.
