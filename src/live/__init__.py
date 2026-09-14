"""Stage 6 — live execution.

Built refusal-first: this package contains the preconditions for sending a
transaction before it contains any ability to send one. That order is
deliberate. A send path written first and guarded afterwards has its guards
bolted on; a send path written inside its guards cannot exist without them.
"""
