#!/usr/bin/env bash
# Dependency security audit helper for tradecc (Solana Python trading bot)
# Usage: run from repo root or pass path to requirements / pyproject
set -euo pipefail

REPO_ROOT="${1:-.}"
cd "$REPO_ROOT"

echo "=== tradecc Dependency Security Audit ==="
echo "Repo: $(pwd)"
echo

# Preferred safe packages
SAFE_SOLANA_PKGS=("solana" "solders" "anchorpy")
DANGEROUS_NAMES=("solana-py" "solana_py" "solders-py" "jupiter-python-sdk" "solana-helper" "solana-wallet")

echo "--- Checking for known risky / typosquat package names ---"
if [[ -f requirements.txt ]]; then
  for bad in "${DANGEROUS_NAMES[@]}"; do
    if grep -qiE "^${bad}([=<>]|$)" requirements.txt 2>/dev/null; then
      echo "CRITICAL: Found potentially dangerous package name: $bad"
      echo "  Prefer official 'solana' + 'solders'. Historical typosquats have stolen keys."
    fi
  done
fi

if [[ -f pyproject.toml ]]; then
  for bad in "${DANGEROUS_NAMES[@]}"; do
    if grep -qi "$bad" pyproject.toml 2>/dev/null; then
      echo "CRITICAL: Found potentially dangerous package reference: $bad in pyproject.toml"
    fi
  done
fi

echo
echo "--- Preferred packages present? ---"
for pkg in "${SAFE_SOLANA_PKGS[@]}"; do
  if [[ -f requirements.txt ]] && grep -qiE "^${pkg}([=<>]|$)" requirements.txt 2>/dev/null; then
    echo "OK: $pkg listed in requirements.txt"
  elif [[ -f pyproject.toml ]] && \
       grep -qiE "^[[:space:]]*[\"']${pkg}[\"'>=<~!]" pyproject.toml 2>/dev/null; then
    # Must look like a declared dependency entry, not any mention of the word.
    # A bare substring match reported "OK: solana referenced in pyproject.toml"
    # off the project *description* line, which is false reassurance in a
    # security script — it claims the official package is declared when it is
    # not declared at all.
    echo "OK: $pkg declared in pyproject.toml"
  else
    echo "NOTE: $pkg not obviously declared (may be transitive or not yet added)"
  fi
done

echo
echo "--- Running pip audit (if available) ---"
if command -v pip-audit >/dev/null 2>&1; then
  if [[ -f requirements.txt ]]; then
    pip-audit -r requirements.txt || true
  else
    pip-audit || true
  fi
elif command -v safety >/dev/null 2>&1; then
  safety check || true
else
  echo "pip-audit / safety not installed. Install with:"
  echo "  pip install pip-audit"
  echo "Then re-run this script."
fi

echo
echo "--- Secret scanning ---"
# Deliberately not done here. A heuristic shape regex lived at this spot and was
# removed: the same pattern in static-security-scan.sh matched a loop variable
# named `key` and block-secrets.py's own refusal messages, i.e. false positives
# on a clean repo. Secret detection belongs to `.claude/hooks/block-secrets.py`,
# which matches candidate word runs against the real BIP-39 wordlist and is
# wired as a PreToolUse hook in `.claude/settings.json`. Do not reintroduce a
# shape regex here.
echo "Handled by .claude/hooks/block-secrets.py (BIP-39 wordlist, PreToolUse)."
echo "This script does not duplicate it."

echo
echo "=== Audit complete. Advisory only — this script never fails a build. ==="
echo "Review anything printed above before adding a dependency that touches"
echo "wallets or the network."
# Advisory by design: findings here are for a human to read, not a gate. The
# gate is the test suite, the CI secret scan, and the validation gate itself.
exit 0
