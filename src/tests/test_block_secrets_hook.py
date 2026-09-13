"""The block-secrets PreToolUse hook must actually block, not just warn.

Held to the same bar as every risk control: a test that only checked the
hook *ran* would be worthless. These invoke the hook exactly as Claude
Code does — JSON on stdin, decision by exit code (2 blocks, 0 allows) —
and assert the decision.

Secret-shaped fixtures are assembled at runtime rather than written as
literals, so this file does not trip the very hook it tests.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "block-secrets.py"

# A base58 string in the 86-90 length band (no 0/O/I/l).
FAKE_BASE58_SECRET = "5" + "Kq9tHz" * 14 + "abc"  # 89 chars

# A genuine BIP-39 test vector, held as separate words so no 12-word
# whitespace-separated run exists in this file.
MNEMONIC_WORDS = [
    "legal", "winner", "thank", "year", "wave", "sausage",
    "worth", "useful", "legal", "winner", "thank", "yellow",
]
FAKE_MNEMONIC = " ".join(MNEMONIC_WORDS)

# Long enough to look like a real value rather than an identifier.
FAKE_KEY_VALUE = "aG9sZHRoaXNpc25vdGFyZWFsa2V5MTIzNDU2"

BLOCKED = 2
ALLOWED = 0


def run(tool_input: dict, tool_name: str = "Write") -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True
    )


# --- it blocks (exit 2) ---

def test_blocks_a_base58_secret_key():
    assert len(FAKE_BASE58_SECRET) in range(86, 91)
    result = run({"file_path": "src/notes.py", "content": f"KEY = '{FAKE_BASE58_SECRET}'"})
    assert result.returncode == BLOCKED
    assert "base58" in result.stdout


def test_blocks_a_labelled_private_key_with_a_real_value():
    result = run({"file_path": "config.py", "content": f'private_key = "{FAKE_KEY_VALUE}"'})
    assert result.returncode == BLOCKED


def test_blocks_a_real_bip39_mnemonic():
    result = run({"file_path": "notes.md", "content": FAKE_MNEMONIC})
    assert result.returncode == BLOCKED
    assert "BIP-39" in result.stdout


def test_blocks_writing_a_dotenv_file():
    result = run({"file_path": "/repo/.env", "content": "HELIUS_API_KEY=abc"})
    assert result.returncode == BLOCKED
    assert ".env" in result.stdout


# --- it allows (exit 0) ---

def test_allows_a_dotenv_example_template():
    result = run({"file_path": "/repo/.env.example", "content": "HELIUS_API_KEY=your-key-here"})
    assert result.returncode == ALLOWED


def test_allows_clean_code():
    content = "def total_cost_usd(size):\n    return size * Decimal('0.002')\n"
    result = run({"file_path": "src/execution/costs.py", "content": content})
    assert result.returncode == ALLOWED


def test_allows_a_reference_to_a_secret_rather_than_the_secret():
    """A redaction test naming `private_key` is not a leak.

    The earlier pattern blocked this, which would have locked the repo
    out of editing the very test that proves secrets get scrubbed.
    """
    content = 'log_and_track("trade.executed", private_key=FAKE_KEY, token="So111")'
    result = run({"file_path": "src/tests/test_telemetry.py", "content": content})
    assert result.returncode == ALLOWED


def test_allows_prose_that_the_shape_only_matcher_used_to_block():
    """Twelve-plus lowercase words are prose far more often than a seed.

    This exact sentence tripped the shape-only regex. It is not a
    mnemonic, because its words are not BIP-39 words.
    """
    content = (
        "written before the harness exists and before any fold has been "
        "scored and the only thing inspected beforehand was trade count"
    )
    result = run({"file_path": "planning/decisions/note.md", "content": content})
    assert result.returncode == ALLOWED


def test_one_non_bip39_word_is_enough_to_clear_a_run():
    """Every word must be a BIP-39 word — this is what kills the noise.

    A real mnemonic with a single word swapped for a non-BIP-39 one
    ("wallet") is not a mnemonic, and must not be treated as one.
    """
    swapped = MNEMONIC_WORDS[:-1] + ["wallet"]
    result = run({"file_path": "notes.md", "content": " ".join(swapped)})
    assert result.returncode == ALLOWED


def test_a_repeated_bip39_word_still_counts_as_a_run():
    """Deliberate: the detector is conservative when every word qualifies.

    Twelve repetitions of "market" is not a valid mnemonic, but it is a
    run of genuine BIP-39 words, so it blocks. Erring toward a refusal
    here is the right direction, and the repo-wide scan shows real
    content does not produce such runs.
    """
    result = run({"file_path": "README.md", "content": " ".join(["market"] * 12)})
    assert result.returncode == BLOCKED


def test_allows_a_solana_mint_address():
    """Mint/pool addresses are 32-44 base58 chars, below the secret floor."""
    content = "SOL_MINT = 'So11111111111111111111111111111111111111112'\n"
    result = run({"file_path": "config.py", "content": content})
    assert result.returncode == ALLOWED


def test_allows_an_edit_payload_via_new_string():
    result = run({"file_path": "src/x.py", "new_string": "x = 1"}, tool_name="Edit")
    assert result.returncode == ALLOWED


# --- it fails open on garbage, never blocking on its own parse error ---

def test_unparseable_stdin_does_not_block():
    result = subprocess.run(
        [sys.executable, str(HOOK)], input="this is not json",
        capture_output=True, text=True,
    )
    assert result.returncode == ALLOWED
