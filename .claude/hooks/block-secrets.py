#!/usr/bin/env python3
"""PreToolUse hook: refuse any write that could leak a private key or .env.

Claude Code sends JSON on stdin: {"tool_name": "Write", "tool_input": {...}}.
Exit code 2 blocks the tool and shows stdout to the agent; exit 0 allows it.
This is a backstop for CLAUDE.md non-negotiable rule #1, not a substitute
for reviewing what gets written.

Detection is deliberately conservative in one direction (better to block a
false positive than leak a key) and its known weak spot is documented on
the MNEMONIC pattern below.
"""
import json
import re
import sys

# --- base58 secret key: Solana secret keys base58-encode to ~87-88 chars.
# Mint/pool addresses are 32-44 chars and stay well below the floor, so
# this does not fire on ordinary on-chain addresses in config or docs.
BASE58_SECRET = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{86,90}\b")

# --- labelled secret: "private_key =", "seed-phrase:", "secretKey:".
# Requires the delimiter immediately after the label, so an identifier like
# WALLET_PRIVATE_KEY_SECRET_REF= (label followed by "_", not ":"/"=") does
# not match — that name is a *reference* to a secret, not the secret.
LABELLED_SECRET = re.compile(
    r"(?i)(private[_-]?key|seed[_-]?phrase|secret[_-]?key)\s*[:=]"
)

# --- mnemonic phrase: 12-24 space-separated lowercase words.
#
# FALSE-POSITIVE WARNING (read before trusting a block from this pattern):
# BIP-39 mnemonics are 12/24 lowercase words, but so is a run of ordinary
# lowercase English prose with no capitals or punctuation between the words.
# A markdown sentence like "the strategy is gross profitable and net
# unprofitable here on the range it was tuned on" can trip this. The words
# are bounded to 3-8 chars (BIP-39's word-length range) to shed the most
# common technical-prose false positives — long words like "significance"
# or "parameters" break a run — but it is still the least precise of the
# three patterns. If it blocks a legitimate write, that is this pattern,
# not a real secret; tighten or narrow it rather than being mystified.
MNEMONIC = re.compile(r"\b(?:[a-z]{3,8}\s+){11,23}[a-z]{3,8}\b")

PATTERNS = [
    ("base58 secret key", BASE58_SECRET),
    ("labelled private key / seed phrase", LABELLED_SECRET),
    ("mnemonic-shaped phrase (see false-positive note in hook)", MNEMONIC),
]

# Files that must never be written (except *.example templates).
BLOCKED_PATHS = (".env", ".env.", "keypair", "id.json", "wallet.json")


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
    for label, pattern in PATTERNS:
        if pattern.search(content):
            reasons.append(f"content matches {label}")
            break

    if reasons:
        print("BLOCKED by block-secrets hook:\n- " + "\n- ".join(reasons))
        print("\nRule: never hardcode or commit keys (CLAUDE.md non-negotiable #1).")
        print("Load keys from env/secrets manager at runtime only.")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
