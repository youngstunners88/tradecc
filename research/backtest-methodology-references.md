# Reference Notes: freqtrade & jesse-ai → backtest methodology maturity check

Not dependencies. Both are CEX-focused (ccxt-based) and cannot execute
Solana DEX trades, so neither is installed or run. This is a maturity
bar to check our hand-built walk-forward harness against, not code to
import.

## Why this is worth reading
`freqtrade` is the most established open-source crypto trading bot,
with years of community-hardened backtesting tooling. `jesse-ai/jesse`
is a smaller but well-regarded Python framework with a clean strategy
interface and backtest metrics reporting. Both have solved the
walk-forward / overfitting problem at more scale and for longer than
this project has — worth checking their approach against our own
`research/walk_forward.py`, built from scratch this week.

## What to check our harness against
1. **Hyperopt-style parameter search discipline.** freqtrade's hyperopt
   separates the search space definition from the evaluation loss
   function explicitly, and warns loudly about overfitting when a
   search finds a narrow optimum. Our Phase B already produced exactly
   that signature (a different "winning" parameter set per fold, several
   noise-shaped) — worth confirming our decision-rule language
   (concentration check, trade-count floor) is at least as strict as
   freqtrade's standard guidance, not looser.
2. **Walk-forward window construction.** Both frameworks support
   rolling and expanding windows as configurable, well-tested options.
   Our expanding-window, 3-fold choice was justified by measured trade
   counts (see `2026-09-10-walk-forward-validation.md`) — that reasoning
   holds regardless of what these frameworks default to, but it's worth
   a quick sanity check that we're not missing an edge case they
   specifically guard against (e.g., warmup period leaking across fold
   boundaries).
3. **Baseline comparisons.** Both frameworks report strategy P&L against
   a buy-and-hold baseline by default, not just against a "no signal"
   baseline. Our `backtest.md` command already includes this
   requirement — confirm it's actually being run and reported, not just
   specified.

## What NOT to borrow
- Do not adopt ccxt or any CEX-exchange integration — irrelevant to a
  Solana DEX bot.
- Do not adopt either framework's live-trading execution layer — our
  own execution stack (Helius + Jupiter, already built and tested) is
  the one to extend, not replace.
- Do not treat "freqtrade has more features" as a reason to expand
  scope — the comparison here is methodology rigor only, not feature
  parity.
