"""The block-secrets PreToolUse hook must actually block, not just warn.

Held to the same bar as every risk control: a test that only checked the
hook *ran* would be worthless. These invoke the hook exactly as Claude
Code does — JSON on stdin, decision by exit code (2 blocks, 0 allows) —
and assert the decision.

The hook lives in .claude/hooks/ (outside src and outside coverage), but
its job is refusing to let a key reach disk, so its behaviour is pinned.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "block-secrets.py"

# A base58 string in the 86-90 length band (no 0/O/I/l). Assembled here so
# no key-shaped literal sits in the file for the hook itself to flag.
FAKE_BASE58_SECRET = "5" + "Kq9tHz" * 14 + "abc"  # 89 chars, base58 alphabet

BLOCKED = 2
ALLOWED = 0


def run(tool_input: dict, tool_name: str = "Write") -> subprocess.CompletedProcess:
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
    )


# --- it blocks (exit 2) ---

def test_blocks_a_base58_secret_key():
    assert len(FAKE_BASE58_SECRET) in range(86, 91)
    result = run({"file_path": "src/notes.py", "content": f"KEY = '{FAKE_BASE58_SECRET}'"})
    assert result.returncode == BLOCKED
    assert "base58 secret key" in result.stdout


def test_blocks_a_labelled_private_key():
    result = run({"file_path": "config.py", "content": 'private_key = "hunter2"'})
    assert result.returncode == BLOCKED


def test_blocks_a_mnemonic_shaped_phrase():
    phrase = "legal winner thank year wave sausage worth useful legal winner thank yellow"
    result = run({"file_path": "notes.md", "content": phrase})
    assert result.returncode == BLOCKED


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


def test_allows_normal_prose_with_capitals_and_punctuation():
    """Real prose has capitals and punctuation, so it is not a lowercase run."""
    content = (
        "The strategy is gross profitable and net unprofitable here. On 15m "
        "candles it is worse still, with a lower win rate."
    )
    result = run({"file_path": "README.md", "content": content})
    assert result.returncode == ALLOWED


def test_allows_a_solana_mint_address():
    """Mint/pool addresses are 32-44 base58 chars, below the secret floor."""
    content = "SOL_MINT = 'So11111111111111111111111111111111111111112'\n"
    result = run({"file_path": "config.py", "content": content})
    assert result.returncode == ALLOWED


def test_allows_an_edit_payload_via_new_string():
    result = run(
        {"file_path": "src/x.py", "new_string": "x = 1"},
        tool_name="Edit",
    )
    assert result.returncode == ALLOWED


# --- it fails open on garbage, never blocking on its own parse error ---

def test_unparseable_stdin_does_not_block():
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input="this is not json",
        capture_output=True,
        text=True,
    )
    assert result.returncode == ALLOWED
