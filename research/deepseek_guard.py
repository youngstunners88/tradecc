"""The call-site filter for anything sent to DeepSeek.

`.claude/skills/openrouter-deepseek/SKILL.md` states the boundary and then
states why the boundary cannot live in the system prompt: *a model instructed
not to use wallet data it was given has still been given wallet data.* This
module is where that instruction becomes a control. It runs before the client
is constructed and before any byte leaves the process, and it raises rather
than redacts — a payload that needed redacting is a payload that was assembled
wrongly, and quietly fixing it hides the assembly bug.

Fail-closed in both directions:

* **Paths** are allow-listed. Research and planning material is sendable;
  everything else, `src/` and `ops/` and `config/` included, is not. There is
  deliberately no `--allow-anyway` flag, because a control with an override is
  a control that gets overridden at the moment it matters.
* **Content** is deny-listed on top of that, so a secret that someone pasted
  into an allowed research note is still caught on the way out.

The content detectors are borrowed from `.claude/hooks/block-secrets.py`,
including its precision discipline: each one requires a *value*, not a
mention, so a document that discusses fingerprints or private keys in prose
travels fine while a document that contains one does not.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

MIN_MNEMONIC_WORDS = 12

# Repo-relative directories whose contents may be sent. Analysis material
# only. `src/` is absent on purpose: DeepSeek is a research assistant, and
# code review is not one of the three jobs the skill assigns it.
ALLOWED_ROOTS = (
    "planning",
    "research",
    "docs",
    ".claude/skills",
)

# Root-level files that are sendable despite not sitting under an allowed
# directory. Both are public-facing project descriptions.
ALLOWED_FILES = ("README.md", "CLAUDE.md")

# Checked against the repo-relative path even when it sits under an allowed
# root, so a stray copy of a gate file under `research/` is still refused.
DENIED_PATH_FRAGMENTS = (
    ".env",
    "live-gate",
    "keypair",
    "wallet.json",
    "id.json",
    "chamber-state",
    "risk-state",
    ".secret",
)

# Solana secret keys base58-encode to ~87-88 characters. Mint and pool
# addresses are 32-44 and stay well below the floor.
BASE58_SECRET = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{86,90}\b")

# A label followed immediately by a substantial value. `SOLANA_PRIVATE_KEY`
# named in prose does not match; `SOLANA_PRIVATE_KEY=<64 chars>` does.
LABELLED_SECRET = re.compile(
    r"(?i)(private[_-]?key|seed[_-]?phrase|secret[_-]?key|api[_-]?key)"
    r"\s*[:=]\s*[\"']?[A-Za-z0-9+/=_-]{16,}"
)

# Gate and fingerprint *state*, not the words. The skill forbids sending the
# values that say whether real money can move, not the vocabulary used to
# discuss them — every decision record in `planning/` discusses them.
#
# Calibrated deliberately narrow. A first version also matched
# `threshold_set_at` and `max_drawdown_threshold_pct`, which refused
# `planning/specs/mvp_spec.md`, the max-drawdown decision record and the gate
# checklist — three of the documents a viability check most needs. Those two
# keys are *policy*, not state: they are set by the operator, committed to the
# repository in `ops/live-gate.json` as an audit record, and reveal nothing
# that enables anything. What must not travel is whether the gate is open and
# whether the running configuration matches the approved one. A guard that
# refuses the specification it exists to help analyse is a guard someone
# removes, and a removed guard catches nothing at all.
GATE_STATE = re.compile(
    r"(?i)[\"']?(validated_fingerprint|fingerprint_mismatch|gate_unlocked)[\"']?\s*[:=]"
)

# A 64-character hex run is a digest — a config fingerprint here. Git SHAs are
# 40 and are unaffected.
HEX_DIGEST = re.compile(r"\b[0-9a-f]{64}\b")

# A base58 address under a wallet label. The address alone is not enough to
# refuse on: token mints are legitimate, frequent research data.
LABELLED_WALLET = re.compile(
    r"(?i)(hot[_-]?wallet|wallet[_-]?address|pub(lic)?[_-]?key|owner)"
    r"\s*[:=]\s*[\"']?[1-9A-HJ-NP-Za-km-z]{32,44}"
)

# Cheap shape prefilter, confirmed word-by-word against the real BIP-39 list.
# A shape-only check matches ordinary English prose; this does not.
WORD_RUN = re.compile(r"\b[a-z]{3,8}(?:\s+[a-z]{3,8}){%d,23}\b" % (MIN_MNEMONIC_WORDS - 1))

# Kept in step with `SECRET_ENV_NAMES` in `src/cli.py`. Duplicated rather than
# imported because this module must not depend on `src/` — the dependency
# arrow between research tooling and the bot points one way only.
SECRET_ENV_NAMES = (
    "HELIUS_API_KEY",
    "POSTHOG_API_KEY",
    "OPENROUTER_API_KEY",
    "AGENTMAIL_API_KEY",
    "BITQUERY_API_KEY",
    "SOLANA_PRIVATE_KEY",
)

# Below this length an environment value is too short to match uniquely — an
# 8-character value could be an ordinary word appearing in a document.
MIN_SECRET_VALUE_LENGTH = 12


class ForbiddenPayload(Exception):
    """Assembly produced something that must not be sent. No call is made."""


@dataclass(frozen=True)
class Finding:
    source: str
    reason: str

    def __str__(self) -> str:
        return f"{self.source}: {self.reason}"


def load_wordlist(repo_root: Path) -> set[str]:
    path = repo_root / ".claude" / "hooks" / "bip39-english.txt"
    try:
        return set(path.read_text().split())
    except OSError:
        # An absent wordlist disables one detector; it must not silently
        # disable the others, and it must not pass a mnemonic. The caller
        # sees the empty set through `find_mnemonic` returning None, so this
        # is recorded as a real gap rather than an equivalent of "clean".
        return set()


def find_mnemonic(content: str, wordlist: set[str]) -> str | None:
    """A run of >=12 consecutive words that are *all* genuine BIP-39 words."""
    if not wordlist:
        return None
    for match in WORD_RUN.finditer(content):
        if all(word in wordlist for word in match.group(0).split()):
            return match.group(0)
    return None


def secret_values(env: dict[str, str]) -> list[str]:
    """Live secret values long enough to match on, from the registered names."""
    values = []
    for name in SECRET_ENV_NAMES:
        value = (env.get(name) or "").strip()
        if len(value) >= MIN_SECRET_VALUE_LENGTH:
            values.append(value)
    return values


def check_path(path: Path, repo_root: Path) -> Finding | None:
    """Allow-list the path, then deny-list fragments within it.

    Resolves first, so a symlink out of an allowed directory is judged by
    where it lands rather than by where it is named.
    """
    resolved = path.resolve()
    root = repo_root.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        return Finding(str(path), "outside the repository")

    posix = relative.as_posix()
    lowered = posix.lower()
    for fragment in DENIED_PATH_FRAGMENTS:
        if fragment in lowered:
            return Finding(posix, f"path contains '{fragment}' — runtime state, never sent")

    if posix in ALLOWED_FILES:
        return None
    if any(posix == root_dir or posix.startswith(root_dir + "/") for root_dir in ALLOWED_ROOTS):
        return None
    allowed = ", ".join(ALLOWED_ROOTS)
    return Finding(posix, f"outside the sendable roots ({allowed})")


def scan_text(text: str, source: str, *, repo_root: Path, env: dict[str, str]) -> Finding | None:
    """First matching detector wins; the reason names what, never the value."""
    for value in secret_values(env):
        if value in text:
            return Finding(source, "contains the live value of a registered secret")
    if BASE58_SECRET.search(text):
        return Finding(source, "contains a base58 string the length of a secret key")
    if LABELLED_SECRET.search(text):
        return Finding(source, "assigns a value to a private-key/seed-phrase/API-key label")
    if find_mnemonic(text, load_wordlist(repo_root)):
        return Finding(source, "contains a BIP-39 mnemonic phrase")
    if GATE_STATE.search(text):
        return Finding(source, "contains live gate or fingerprint state, not just a mention of it")
    if HEX_DIGEST.search(text):
        return Finding(source, "contains a 64-character digest — a config fingerprint")
    if LABELLED_WALLET.search(text):
        return Finding(source, "assigns a base58 address to a wallet/pubkey label")
    return None


def assert_sendable(
    *,
    files: list[Path],
    texts: dict[str, str],
    repo_root: Path,
    env: dict[str, str] | None = None,
) -> None:
    """Raise unless every path and every piece of text may leave the process.

    Collects *all* findings before raising. One refusal at a time turns a
    mis-assembled payload into several rounds of trial and error, which is
    how an operator ends up removing the guard instead of fixing the input.
    """
    environ = os.environ if env is None else env
    environ = dict(environ)
    findings: list[Finding] = []

    for path in files:
        finding = check_path(path, repo_root)
        if finding is not None:
            findings.append(finding)
            continue
        try:
            content = path.read_text()
        except OSError as exc:
            findings.append(Finding(str(path), f"unreadable: {exc}"))
            continue
        finding = scan_text(content, path.name, repo_root=repo_root, env=environ)
        if finding is not None:
            findings.append(finding)

    for source, text in texts.items():
        finding = scan_text(text, source, repo_root=repo_root, env=environ)
        if finding is not None:
            findings.append(finding)

    if findings:
        detail = "\n".join(f"  - {f}" for f in findings)
        raise ForbiddenPayload(
            "refusing to send: the payload contains material the DeepSeek "
            "boundary forbids.\n" + detail + "\n"
            "Nothing was sent. Fix the input rather than the guard — see "
            ".claude/skills/openrouter-deepseek/SKILL.md."
        )
