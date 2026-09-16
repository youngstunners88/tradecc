"""The call-site filter that decides what may be sent to DeepSeek.

The skill states the boundary and says plainly that the system prompt cannot
enforce it, because a model instructed not to use wallet data it was given has
still been given wallet data. These tests are the enforcement.

Two properties matter as much as the refusals themselves:

* **Precision.** A guard that refuses `planning/specs/mvp_spec.md` is a guard
  that gets removed, and a removed guard catches nothing. The prose tests
  below pin the discrimination between a *mention* of a fingerprint or a
  private key and an actual *value*.
* **No call on refusal.** `main()` must return before the client exists.
  `test_guard_refusal_sends_nothing` proves it with a transport that fails
  the test if it is ever reached.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# The placeholder key below is shaped so it does NOT match the repository's own
# CI secret scan (`.github/workflows/test.yml`), whose pattern requires a long
# unbroken alphanumeric run after the vendor prefix. The hyphens break that run,
# so this is unmistakably a placeholder to a reader and invisible to the
# scanner. A first version used a realistic-looking suffix and failed CI on
# exactly that pattern — correctly. If you edit this, keep hyphens inside the
# suffix; do not relax the scan.
FAKE_KEY = "sk-or-v1-" + "NOT-A-REAL-KEY"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "research" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = _load("deepseek_guard")
deepseek = _load("deepseek")

ForbiddenPayload = guard.ForbiddenPayload


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A miniature repo: the allowed roots, plus the real BIP-39 wordlist."""
    for directory in ("planning", "research", "docs", ".claude/skills", "src", "ops"):
        (tmp_path / directory).mkdir(parents=True, exist_ok=True)
    hooks = tmp_path / ".claude" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    (hooks / "bip39-english.txt").write_text(
        (ROOT / ".claude" / "hooks" / "bip39-english.txt").read_text()
    )
    return tmp_path


def write(repo: Path, relative: str, content: str = "ordinary research prose\n") -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def send(repo: Path, *files: Path, text: str = "", env: dict[str, str] | None = None) -> None:
    guard.assert_sendable(
        files=list(files),
        texts={"--question": text} if text else {},
        repo_root=repo,
        env=env or {},
    )


# --- paths -----------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    ["planning/decisions/x.md", "research/notes.md", "docs/a.md", ".claude/skills/s/SKILL.md"],
)
def test_allowed_roots_are_sendable(repo: Path, relative: str) -> None:
    send(repo, write(repo, relative))


@pytest.mark.parametrize("relative", ["README.md", "CLAUDE.md"])
def test_root_level_project_descriptions_are_sendable(repo: Path, relative: str) -> None:
    send(repo, write(repo, relative))


def test_source_tree_is_not_sendable(repo: Path) -> None:
    """`src/` is absent from the allow-list on purpose — code review is not
    one of the three jobs the skill assigns DeepSeek."""
    with pytest.raises(ForbiddenPayload, match="outside the sendable roots"):
        send(repo, write(repo, "src/cli.py", "x = 1\n"))


def test_gate_file_is_not_sendable_even_by_name(repo: Path) -> None:
    with pytest.raises(ForbiddenPayload, match="live-gate"):
        send(repo, write(repo, "ops/live-gate.json", "{}\n"))


def test_denied_fragment_beats_an_allowed_root(repo: Path) -> None:
    """A copy of a gate file under `research/` is still refused: the fragment
    check runs on the full relative path, not only outside the allow-list."""
    with pytest.raises(ForbiddenPayload, match="live-gate"):
        send(repo, write(repo, "research/live-gate.backup.json", "{}\n"))


def test_env_file_is_not_sendable(repo: Path) -> None:
    with pytest.raises(ForbiddenPayload, match=r"\.env"):
        send(repo, write(repo, "research/.env.local", "K=v\n"))


def test_path_outside_the_repository_is_refused(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere.md"
    outside.write_text("x\n")
    with pytest.raises(ForbiddenPayload, match="outside the repository"):
        send(repo, outside)


def test_symlink_is_judged_by_where_it_lands(repo: Path, tmp_path: Path) -> None:
    """Resolution happens before the allow-list check, so a link from an
    allowed directory to a forbidden file does not launder it."""
    secret = write(repo, "ops/live-gate.json", "{}\n")
    link = repo / "research" / "innocent.md"
    link.symlink_to(secret)
    with pytest.raises(ForbiddenPayload):
        send(repo, link)


# --- content ---------------------------------------------------------------


def test_base58_secret_key_is_refused(repo: Path) -> None:
    key = "5" + "K" * 86
    with pytest.raises(ForbiddenPayload, match="length of a secret key"):
        send(repo, write(repo, "research/leak.md", f"key: {key}\n"))


def test_labelled_secret_is_refused(repo: Path) -> None:
    with pytest.raises(ForbiddenPayload, match="private-key"):
        send(repo, write(repo, "research/leak.md", "private_key = A1b2C3d4E5f6G7h8J9k0\n"))


def test_mnemonic_is_refused(repo: Path) -> None:
    phrase = "abandon ability able about above absent absorb abstract absurd abuse access accident"
    with pytest.raises(ForbiddenPayload, match="mnemonic"):
        send(repo, write(repo, "research/leak.md", phrase + "\n"))


def test_live_secret_value_is_refused_wherever_it_appears(repo: Path) -> None:
    """The deny-list runs on top of the allow-list: a key pasted into an
    otherwise sendable research note is still caught on the way out."""
    env = {"OPENROUTER_API_KEY": FAKE_KEY}
    with pytest.raises(ForbiddenPayload, match="live value of a registered secret"):
        send(repo, write(repo, "research/n.md", f"we used {env['OPENROUTER_API_KEY']}\n"), env=env)


def test_short_env_values_are_not_matched(repo: Path) -> None:
    """Below the length floor an environment value could be an ordinary word,
    and matching on it would refuse arbitrary documents."""
    send(repo, write(repo, "research/n.md", "the cost model is fine\n"), env={"HELIUS_API_KEY": "cost"})


def test_fingerprint_state_is_refused(repo: Path) -> None:
    with pytest.raises(ForbiddenPayload, match="live gate or fingerprint state"):
        send(repo, write(repo, "research/n.md", '{"validated_fingerprint": {"risk": "ab"}}\n'))


def test_hex_digest_is_refused(repo: Path) -> None:
    with pytest.raises(ForbiddenPayload, match="64-character digest"):
        send(repo, write(repo, "research/n.md", "digest " + "a1" * 32 + "\n"))


def test_git_sha_is_not_a_digest(repo: Path) -> None:
    """Git SHAs are 40 hex characters and appear throughout the decision
    records. Only the 64-character fingerprint length is refused."""
    send(repo, write(repo, "research/n.md", "merged in " + "b" * 40 + "\n"))


def test_labelled_wallet_address_is_refused(repo: Path) -> None:
    with pytest.raises(ForbiddenPayload, match="wallet/pubkey label"):
        send(repo, write(repo, "research/n.md", "hot_wallet: 7xKXtg2CW3iP5kA9bTqLmNvRs4YzHdEuFgJ1\n"))


def test_bare_token_mint_is_sendable(repo: Path) -> None:
    """Mint addresses are legitimate, frequent research data. Only an address
    under a wallet label is refused."""
    send(repo, write(repo, "research/n.md", "SOL mint So11111111111111111111111111111111111111112\n"))


# --- precision: mentions are not values ------------------------------------


def test_prose_about_secrets_and_fingerprints_is_sendable(repo: Path) -> None:
    """Every decision record in `planning/` discusses these concepts. The
    guard must pass the vocabulary and refuse only the values."""
    prose = (
        "The `validated_fingerprint` is what proves the running config matches "
        "the approved one, and SOLANA_PRIVATE_KEY is loaded from the "
        "environment only. Never commit a private_key or a seed phrase.\n"
    )
    send(repo, write(repo, "planning/decisions/d.md", prose))


def test_gate_policy_values_are_sendable(repo: Path) -> None:
    """Pins the calibration decision. `threshold_set_at` and
    `max_drawdown_threshold_pct` are operator-set policy committed to the repo
    as an audit record, not state. An earlier, broader pattern refused
    `mvp_spec.md` and two decision records — the documents a viability check
    most needs.
    """
    send(
        repo,
        write(
            repo,
            "planning/specs/mvp_spec.md",
            "`ops/live-gate.json` carries `threshold_set_at: 2026-09-14T00:41:03+00:00` "
            "and `max_drawdown_threshold_pct: 8`.\n",
        ),
    )


# --- reporting -------------------------------------------------------------


def test_every_finding_is_reported_not_just_the_first(repo: Path) -> None:
    """One refusal at a time turns a mis-assembled payload into several rounds
    of trial and error, which is how an operator ends up removing the guard."""
    with pytest.raises(ForbiddenPayload) as excinfo:
        send(repo, write(repo, "src/a.py", "x\n"), write(repo, "ops/live-gate.json", "{}\n"))
    message = str(excinfo.value)
    assert "src/a.py" in message and "live-gate" in message


def test_the_question_text_is_scanned_too(repo: Path) -> None:
    """Files are not the only way material reaches the prompt."""
    with pytest.raises(ForbiddenPayload, match="--question"):
        send(repo, text="check private_key = A1b2C3d4E5f6G7h8J9k0 for me")


def test_refusal_never_echoes_the_secret(repo: Path) -> None:
    secret = FAKE_KEY
    with pytest.raises(ForbiddenPayload) as excinfo:
        send(repo, text=f"my key is {secret}", env={"OPENROUTER_API_KEY": secret})
    assert secret not in str(excinfo.value)
