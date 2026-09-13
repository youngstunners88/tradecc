# Jupiter + MEV + Slippage Notes for tradecc

## Slippage

- Always set an explicit `slippageBps` (or equivalent) on every quote request.
- Default recommendation for liquid pairs in this bot: 50–100 bps (0.5–1%).
- After simulation (or after quote), compute effective price and reject if it exceeds the configured cap.
- Small position sizes ($5–$10) still need protection — low-liquidity tokens can move far.

## MEV / Sandwich Protection

Jupiter options (as of current docs):
- **Ultra Mode**: Built-in MEV protection via private transaction submission. Prefer this when available for the bot’s size and latency needs.
- **Manual Mode**: No built-in MEV protection. Requires tighter slippage and awareness that the tx is more exposed.

Additional mitigations:
- Prefer Jito bundles or other private relay paths when constructing and sending transactions yourself.
- Keep trade sizes small relative to pool liquidity.
- Avoid predictable, large, or repeated patterns that make sandwiching profitable.
- Validity / expiry timestamps on instructions where the program supports them.

## Practical Rules for tradecc

1. Quote → Simulate → (effective slippage check) → Send.
2. Never send a transaction that failed simulation.
3. Log the quote, the simulation result summary, and the final execution price for every trade.
4. If using Jupiter Ultra, document which protection features are active in the execution module comments.
5. Treat any path that skips the simulation gate as a Critical security finding.

## Common Failure Modes

- Setting slippage too high “so trades go through” → open sandwich risk.
- Relying only on Jupiter’s displayed price impact without post-simulation verification.
- Broadcasting on public RPCs without private submission for sizeable or time-sensitive trades.
- Ignoring failed simulations and retrying with the same (now stale) parameters.
