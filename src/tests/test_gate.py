"""The live gate must fail closed. No input should unlock it by accident."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.gate import evaluate_live_gate

VALID_GATE = {
    "paper_started_at": "2026-01-01T00:00:00+00:00",
    "paper_ended_at": "2026-02-15T00:00:00+00:00",
    "threshold_set_at": "2025-12-28T00:00:00+00:00",
    "max_drawdown_threshold_pct": 15,
    "observed_max_drawdown_pct": 8.4,
    "net_expectancy_usd": 1.25,
    "trade_count": 12,
    "approved_by": "chris",
    "approved_at": "2026-02-16T09:00:00+00:00",
}


def gate_payload(config, **overrides) -> dict:
    """A satisfied gate for a specific config.

    The fingerprint binds an approval to what it was granted against, so a
    valid gate file cannot be written without knowing the config it approves.
    """
    from core.config import fingerprint_sections

    return {**VALID_GATE, "validated_fingerprint": fingerprint_sections(config), **overrides}


def write_gate(path: Path, config=None, **overrides) -> Path:
    data = {**VALID_GATE, **overrides}
    if config is not None and "validated_fingerprint" not in overrides:
        from core.config import fingerprint_sections

        data["validated_fingerprint"] = fingerprint_sections(config)
    for key, value in list(data.items()):
        if value is None:
            del data[key]
    path.write_text(json.dumps(data))
    return path


def test_fully_satisfied_gate_unlocks(tmp_path, run_config):
    result = evaluate_live_gate(write_gate(tmp_path / "gate.json", run_config), run_config)

    assert result.unlocked


def test_missing_file_is_locked(tmp_path, run_config):
    result = evaluate_live_gate(tmp_path / "nope.json", run_config)

    assert not result.unlocked
    assert "never been unlocked" in result.describe()


def test_malformed_json_is_locked(tmp_path, run_config):
    path = tmp_path / "gate.json"
    path.write_text("{ not json at all")

    assert not evaluate_live_gate(path, run_config).unlocked


def test_non_object_json_is_locked(tmp_path, run_config):
    path = tmp_path / "gate.json"
    path.write_text("[1, 2, 3]")

    assert not evaluate_live_gate(path, run_config).unlocked


def test_empty_object_is_locked(tmp_path, run_config):
    path = tmp_path / "gate.json"
    path.write_text("{}")

    assert not evaluate_live_gate(path, run_config).unlocked


def test_short_paper_run_is_locked(tmp_path, run_config):
    result = evaluate_live_gate(
        write_gate(tmp_path / "gate.json", run_config, paper_ended_at="2026-01-20T00:00:00+00:00"),
        run_config,
    )

    assert not result.unlocked
    assert "needs at least 30" in result.describe()


def test_drawdown_over_threshold_is_locked(tmp_path, run_config):
    result = evaluate_live_gate(
        write_gate(tmp_path / "gate.json", run_config, observed_max_drawdown_pct=22.5),
        run_config,
    )

    assert not result.unlocked
    assert "exceeds threshold" in result.describe()


def test_threshold_set_after_run_started_is_locked(tmp_path, run_config):
    """A threshold picked after seeing results is not a gate."""
    result = evaluate_live_gate(
        write_gate(tmp_path / "gate.json", run_config, threshold_set_at="2026-02-01T00:00:00+00:00"),
        run_config,
    )

    assert not result.unlocked
    assert "does not constitute a gate" in result.describe()


@pytest.mark.parametrize("expectancy", [0, -0.5, -12])
def test_non_positive_expectancy_is_locked(tmp_path, run_config, expectancy):
    result = evaluate_live_gate(
        write_gate(tmp_path / "gate.json", run_config, net_expectancy_usd=expectancy),
        run_config,
    )

    assert not result.unlocked
    assert "not positive" in result.describe()


@pytest.mark.parametrize("field", ["approved_by", "approved_at"])
def test_missing_human_approval_is_locked(tmp_path, run_config, field):
    result = evaluate_live_gate(write_gate(tmp_path / "gate.json", run_config, **{field: None}), run_config)

    assert not result.unlocked


def test_blank_approver_is_locked(tmp_path, run_config):
    result = evaluate_live_gate(write_gate(tmp_path / "gate.json", run_config, approved_by="   "), run_config)

    assert not result.unlocked


@pytest.mark.parametrize(
    "field",
    ["paper_started_at", "paper_ended_at", "max_drawdown_threshold_pct", "net_expectancy_usd"],
)
def test_any_missing_required_field_is_locked(tmp_path, run_config, field):
    result = evaluate_live_gate(write_gate(tmp_path / "gate.json", run_config, **{field: None}), run_config)

    assert not result.unlocked


def test_all_failures_are_reported_together(tmp_path, run_config):
    result = evaluate_live_gate(
        write_gate(
            tmp_path / "gate.json",
            run_config,
            paper_ended_at="2026-01-05T00:00:00+00:00",
            net_expectancy_usd=-3,
            approved_by=None,
        ),
        run_config,
    )

    assert not result.unlocked
    assert len(result.failures) >= 3


# --- Non-finite numbers and mixed-awareness timestamps.
#
# All four inputs below used to defeat the fail-closed contract: two by
# raising an uncaught exception out of the module, two by quietly unlocking.
# json.loads parses the bare literals NaN/Infinity by default, so none of
# these requires a hand-crafted parser to produce.


def test_infinite_drawdown_threshold_does_not_unlock(tmp_path, run_config):
    """Infinity as a threshold satisfied `observed > threshold` at any
    observed drawdown — a 99% drawdown passed a gate that claimed to cap it."""
    path = tmp_path / "gate.json"
    path.write_text(
        json.dumps({**gate_payload(run_config), "observed_max_drawdown_pct": 99}).replace(
            '"max_drawdown_threshold_pct": 15', '"max_drawdown_threshold_pct": Infinity'
        )
    )
    result = evaluate_live_gate(path, run_config)
    assert not result.unlocked
    assert any("max_drawdown_threshold_pct" in f for f in result.failures)


def test_nan_expectancy_is_locked_not_a_crash(tmp_path, run_config):
    """Decimal('NaN') raises InvalidOperation from `expectancy <= 0`."""
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(gate_payload(run_config)).replace('"net_expectancy_usd": 1.25',
                                                   '"net_expectancy_usd": NaN'))
    result = evaluate_live_gate(path, run_config)
    assert not result.unlocked
    assert any("net_expectancy_usd" in f for f in result.failures)


def test_infinite_expectancy_does_not_unlock(tmp_path, run_config):
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(gate_payload(run_config)).replace('"net_expectancy_usd": 1.25',
                                                   '"net_expectancy_usd": Infinity'))
    assert not evaluate_live_gate(path, run_config).unlocked


def test_mixed_naive_and_aware_timestamps_do_not_crash(tmp_path, run_config):
    """A naive paper_ended_at against an aware paper_started_at raised
    TypeError straight out of the module. Naive is now read as UTC."""
    result = evaluate_live_gate(
        write_gate(tmp_path / "gate.json", run_config, paper_ended_at="2026-02-15T00:00:00"),
        run_config,
    )
    assert isinstance(result.unlocked, bool)
    assert result.unlocked, result.failures


def test_naive_timestamps_throughout_still_evaluate(tmp_path, run_config):
    result = evaluate_live_gate(
        write_gate(
            tmp_path / "gate.json",
            run_config,
            paper_started_at="2026-01-01T00:00:00",
            paper_ended_at="2026-02-15T00:00:00",
            threshold_set_at="2025-12-28T00:00:00",
            approved_at="2026-02-16T09:00:00",
        ),
        run_config,
    )
    assert result.unlocked, result.failures


def test_boolean_is_not_a_number(tmp_path, run_config):
    """JSON `true` must not become Decimal(1) and satisfy a numeric check."""
    result = evaluate_live_gate(write_gate(tmp_path / "gate.json", run_config, net_expectancy_usd=True), run_config)
    assert not result.unlocked


# --- Trade-count floor and the approval binding.


def test_expectancy_on_too_few_trades_does_not_unlock(tmp_path, run_config):
    """The sweep produced "+$0.47 on 3 trades". Without a sample-size floor a
    gate file reporting exactly that would unlock live trading."""
    from core.performance import MIN_POOLED_TRADES

    result = evaluate_live_gate(
        write_gate(tmp_path / "gate.json", run_config, trade_count=3), run_config
    )
    assert not result.unlocked
    assert f"at least {MIN_POOLED_TRADES}" in result.describe()


def test_the_floor_has_exactly_one_definition():
    """The gate and the research harnesses must apply the same number.

    It was a bare 12 in three places plus a separate MIN_POOLED_TRADES in
    cross_sectional.py. Checked at source level because importing the
    harnesses needs research/ on sys.path, which the test suite does not add.
    """
    from core.performance import MIN_POOLED_TRADES

    assert MIN_POOLED_TRADES == 12

    root = Path(__file__).resolve().parents[2]
    for harness in ("research/walk_forward.py", "research/cross_sectional.py"):
        source = (root / harness).read_text()
        assert "MIN_POOLED_TRADES" in source, harness
        assert "from core.performance import" in source, harness
        assert "MIN_POOLED_TRADES = " not in source, f"{harness} redefines the floor"
        assert ">= 12" not in source, f"{harness} restates the floor as a literal"


@pytest.mark.parametrize("bad", [None, "12", 11, True, 11.9])
def test_trade_count_must_be_an_integer_at_or_above_the_floor(tmp_path, run_config, bad):
    result = evaluate_live_gate(
        write_gate(tmp_path / "gate.json", run_config, trade_count=bad), run_config
    )
    assert not result.unlocked


def test_missing_fingerprint_does_not_unlock(tmp_path, run_config):
    """An approval that cannot prove what it approved is not an approval."""
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(VALID_GATE))  # no validated_fingerprint
    result = evaluate_live_gate(path, run_config)
    assert not result.unlocked
    assert "validated_fingerprint missing" in result.describe()


@pytest.mark.parametrize(
    "section,mutate",
    [
        ("risk", {"risk": {"position_size_usd": "50", "position_size_override_ack": True}}),
        ("strategy", {"strategy": {"name": "momentum", "params": {"fast_ema": 7}}}),
        ("costs", {"costs": {"jito_tip_lamports": 99_999}}),
        ("execution_assumptions", {"backtest": {"execution_slippage_pct": "0.75"}}),
    ],
)
def test_changing_any_bound_section_relocks_and_names_it(tmp_path, run_config, section, mutate):
    """A gate approved against one configuration must not unlock a different
    one — and the failure has to say which part moved, or it is undebuggable."""
    from core.config import BacktestConfig, CostsConfig, RiskConfig, StrategyConfig

    approved = write_gate(tmp_path / "gate.json", run_config)
    builders = {
        "risk": RiskConfig,
        "strategy": StrategyConfig,
        "costs": CostsConfig,
        "backtest": BacktestConfig,
    }
    key, values = next(iter(mutate.items()))
    changed = run_config.model_copy(update={key: builders[key](**values)})

    result = evaluate_live_gate(approved, changed)

    assert not result.unlocked
    assert f"{section!r} differs" in result.describe()
    assert "re-validate and re-approve" in result.describe()


@pytest.mark.parametrize("ignored", ["state_dir", "gate_file"])
def test_excluded_fields_do_not_relock_the_gate(tmp_path, run_config, ignored):
    """Paths do not change what was validated. A gate that fails on a machine
    move gets worked around, which is worse than one that does not fire."""
    approved = write_gate(tmp_path / "gate.json", run_config)
    moved = run_config.model_copy(update={ignored: tmp_path / "elsewhere"})

    assert evaluate_live_gate(approved, moved).unlocked


def test_unknown_fingerprint_sections_relock(tmp_path, run_config):
    """A gate file written by a different version of this gate is not trusted."""
    from core.config import fingerprint_sections

    result = evaluate_live_gate(
        write_gate(
            tmp_path / "gate.json",
            run_config,
            validated_fingerprint={**fingerprint_sections(run_config), "wat": "x"},
        ),
        run_config,
    )
    assert not result.unlocked
    assert "unrecognised sections" in result.describe()
