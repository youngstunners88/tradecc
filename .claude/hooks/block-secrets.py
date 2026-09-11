#!/usr/bin/env python3
"""PreToolUse hook: refuse any write that could leak a private key or .env.

Claude Code sends JSON on stdin: {"tool_name": "Write", "tool_input": {...}}.
Exit code 2 blocks the tool and shows stdout to the agent; exit 0 allows it.
This is a backstop for CLAUDE.md non-negotiable rule #1, not a substitute
for reviewing what gets written.

Three detectors, each tuned so it cannot fire on ordinary repo content:

1. **base58 secret key** — Solana secret keys base58-encode to ~87-88
   chars. Mint and pool addresses are 32-44 and stay well below the floor,
   so on-chain addresses in config and docs do not trip it.
2. **labelled secret** — "private_key = <value>". Requires a *substantial*
   value after the label, so `private_key=FAKE_KEY` (a reference to a
   secret, as in a redaction test) is not mistaken for the secret itself.
3. **mnemonic phrase** — checked against the real BIP-39 wordlist, not by
   shape. An earlier shape-only version ("12+ lowercase words") matched
   ordinary prose and would have blocked edits to seven tracked files
   including source. A run only counts when *every* word is a genuine
   BIP-39 word, which prose effectively never is.
"""
import json
import re
import sys
from pathlib import Path

WORDLIST_PATH = Path(__file__).with_name("bip39-english.txt")
MIN_MNEMONIC_WORDS = 12

BASE58_SECRET = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{86,90}\b")

# The delimiter must follow the label immediately, and the value must be
# long enough to plausibly *be* a key. WALLET_PRIVATE_KEY_SECRET_REF= does
# not match (the label is followed by "_", not ":"/"="), and a short
# placeholder or identifier does not reach the length floor.
LABELLED_SECRET = re.compile(
    r"(?i)(private[_-]?key|seed[_-]?phrase|secret[_-]?key)"
    r"\s*[:=]\s*[\"']?[A-Za-z0-9+/=_-]{16,}"
)

# Cheap shape prefilter; every match is then confirmed word-by-word against
# the BIP-39 list, which is what makes this precise rather than noisy.
WORD_RUN = re.compile(
    r"\b[a-z]{3,8}(?:\s+[a-z]{3,8}){%d,23}\b" % (MIN_MNEMONIC_WORDS - 1)
)

# Files that must never be written (except *.example templates).
BLOCKED_PATHS = (".env", ".env.", "keypair", "id.json", "wallet.json")


def load_wordlist() -> set[str]:
    try:
        return set(WORDLIST_PATH.read_text().split())
    except OSError:
        return set()


def find_mnemonic(content: str, wordlist: set[str]) -> str | None:
    """A run of >=12 consecutive words that are *all* real BIP-39 words."""
    if not wordlist:
        return None
    for match in WORD_RUN.finditer(content):
        words = match.group(0).split()
        if all(word in wordlist for word in words):
            return match.group(0)
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # Not a recognized payload; a hook must not block on its own
        # parsing failure.
        return 0

    ti = payload.get("tool_input", {}) or {}
    path = str(ti.get("file_path") or "")
    content = ""
    for key in ("content", "new_string", "contents"):
        if key in ti:
            content = str(ti[key])
            break

    reasons = []
    if any(p in path for p in BLOCKED_PATHS) and not path.endswith(".example"):
        reasons.append(f"blocked path '{path}' — .env/key files must never be written")
    elif BASE58_SECRET.search(content):
        reasons.append("content contains a base58 string the length of a secret key")
    elif LABELLED_SECRET.search(content):
        reasons.append("content assigns a value to a private-key/seed-phrase label")
    elif find_mnemonic(content, load_wordlist()):
        reasons.append("content contains a BIP-39 mnemonic phrase")

    if reasons:
        print("BLOCKED by block-secrets hook:\n- " + "\n- ".join(reasons))
        print("\nRule: never hardcode or commit keys (CLAUDE.md non-negotiable #1).")
        print("Load keys from env/secrets manager at runtime only.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
