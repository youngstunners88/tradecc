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
  elif [[ -f pyproject.toml ]] && grep -qi "$pkg" pyproject.toml 2>/dev/null; then
    echo "OK: $pkg referenced in pyproject.toml"
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
echo "--- Quick source scan for hard-coded secrets (heuristic) ---"
# Very basic patterns — not a full secret scanner
grep -rniE "(private[_-]?key|seed[_-]?phrase|secret[_-]?key|api[_-]?key).*=.*['\"][a-zA-Z0-9+/]{20,}" \
  --include="*.py" --include="*.env*" --include="*.yaml" --include="*.yml" \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv --exclude-dir=__pycache__ \
  . 2>/dev/null | head -20 || echo "No obvious hard-coded long secrets found by heuristic."

echo
echo "=== Audit complete. Review any CRITICAL findings before continuing. ==="
