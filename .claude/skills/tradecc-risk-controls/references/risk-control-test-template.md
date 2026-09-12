# Risk Control Test Template

Use this structure when adding tests for any new or modified risk control.

```python
import pytest
from datetime import date, timedelta
# from src.risk import RiskManager  # adjust import

class TestDailyLossCircuitBreaker:
    def test_below_limit_allows_trading(self):
        risk = RiskManager(daily_loss_limit_usd=20.0)
        risk.record_pnl(-10.0)
        assert risk.can_trade() is True

    def test_exactly_at_limit_halts(self):
        risk = RiskManager(daily_loss_limit_usd=20.0)
        risk.record_pnl(-20.0)
        assert risk.can_trade() is False

    def test_over_limit_halts(self):
        risk = RiskManager(daily_loss_limit_usd=20.0)
        risk.record_pnl(-25.0)
        assert risk.can_trade() is False

    def test_new_day_resets(self):
        risk = RiskManager(daily_loss_limit_usd=20.0)
        risk.record_pnl(-25.0)
        assert risk.can_trade() is False
        # Simulate day rollover
        risk._current_day = date.today() + timedelta(days=1)  # or public reset API
        risk.reset_for_new_day()
        assert risk.can_trade() is True

class TestPositionSizeCap:
    def test_within_cap_allowed(self):
        risk = RiskManager(max_position_usd=10.0)
        assert risk.check_position_size(8.0) is True

    def test_over_cap_rejected(self):
        risk = RiskManager(max_position_usd=10.0)
        assert risk.check_position_size(12.0) is False
```

## Principles
- Force the exact breach condition.
- Assert the **behavioral outcome** (`can_trade() is False` or equivalent), not just a log message.
- Keep tests free of network and real keys.
- Cover boundary values (just under, exact, just over).
