#!/usr/bin/env bash
# Lightweight static security scan for tradecc source.
#
# Scope, deliberately narrow: this looks for structural violations of the
# non-negotiable rules — an unsimulated send, a hard-coded live mode, a risky
# dependency name. It does NOT try to detect secrets by shape.
#
# Secret detection lives in `.claude/hooks/block-secrets.py`, which matches
# candidate word runs against the real BIP-39 wordlist and is wired as a
# PreToolUse hook in `.claude/settings.json`. That approach was chosen after a
# shape-only regex false-positived on seven tracked files. Do not reintroduce a
# shape regex here — it would duplicate the hook badly and train the reader to
# ignore CRITICAL.
set -euo pipefail

REPO_ROOT="${1:-.}"
cd "$REPO_ROOT"

echo "=== tradecc Static Security Scan ==="
echo "Target: $(pwd)"
echo

CRITICAL=0
HIGH=0

# scan <pattern> <message> <severity>
#
# CRITICAL and HIGH count toward the exit status. INFO is genuinely
# informational and counts toward nothing — an INFO that escalated to HIGH was
# the original version's bug, and it made every clean run look dirty.
scan() {
  local pattern="$1" msg="$2" severity="$3" hits
  hits=$(grep -rniE "$pattern" --include="*.py" \
    --exclude-dir=.git --exclude-dir=.venv --exclude-dir=venv \
    --exclude-dir=__pycache__ . 2>/dev/null | head -10 || true)
  [[ -z "$hits" ]] && return 0
  echo "[$severity] $msg"
  echo "$hits" | sed 's/^/  /'
  echo
  case "$severity" in
    CRITICAL) CRITICAL=$((CRITICAL + 1)) ;;
    HIGH) HIGH=$((HIGH + 1)) ;;
  esac
}

echo "--- Key handling ---"
scan "Keypair\.from_(base58|bytes|seed|secret)" \
  "Keypair construction found — verify the source is env/secrets manager only" "HIGH"

echo "--- Transaction safety ---"
scan "send_transaction|send_raw_transaction" \
  "send_transaction found — every send must be preceded by a successful simulation" "HIGH"

scan "simulate_transaction" \
  "simulate_transaction present — verify it gates every send" "INFO"

echo "--- Mode gating ---"
scan "BOT_MODE[[:space:]]*=[[:space:]]*['\"]live['\"]" \
  "Hard-coded live mode — live must stay behind the validation gate" "CRITICAL"

echo "--- Dependency names ---"
scan "^[[:space:]]*(import|from)[[:space:]]+solana_py\b" \
  "Import of a known typosquat package name" "CRITICAL"

echo "=== Summary ==="
echo "Critical findings: $CRITICAL"
echo "High findings:     $HIGH"
if [[ $CRITICAL -gt 0 ]]; then
  echo "ACTION REQUIRED: resolve CRITICAL items before any capital is at risk."
  exit 1
fi
if [[ $HIGH -gt 0 ]]; then
  echo "Review HIGH items carefully."
fi
echo "No critical findings."
