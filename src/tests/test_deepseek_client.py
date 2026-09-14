"""The DeepSeek delegation client: what it sends, what it costs, when it stops.

The expensive failure mode for an LLM call is not an exception — it is a
retry storm, because every attempt is billable and a long reasoning call over
a megabyte of context is not cheap. `test_at_most_one_retry` is the test that
matters most here.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from execution.http import HttpResponse, ProviderError

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "research" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


deepseek = _load("deepseek")


class RecordingTransport:
    """Returns a canned completion and remembers every request made."""

    def __init__(self, status: int = 200, content: str = "a draft") -> None:
        self.status = status
        self.content = content
        self.requests: list[dict] = []

    def request(self, method, url, *, headers=None, body=None, timeout=15.0):
        self.requests.append(
            {"method": method, "url": url, "headers": headers or {}, "body": body}
        )
        payload = {
            "choices": [{"message": {"content": self.content}}],
            "usage": {"prompt_tokens": 1200, "completion_tokens": 400},
        }
        return HttpResponse(self.status, json.dumps(payload).encode(), {})


def call(transport, **overrides):
    kwargs = dict(
        system="boundary",
        user="question",
        model=deepseek.MODEL_ALIAS,
        max_tokens=4000,
        seed=17,
        api_key="sk-or-v1-testkey0123456789",
        transport=transport,
    )
    kwargs.update(overrides)
    return deepseek.call(**kwargs)


def test_posts_a_bounded_request_to_the_chat_endpoint() -> None:
    transport = RecordingTransport()
    content, usage = call(transport)

    assert content == "a draft"
    assert usage.prompt_tokens == 1200 and usage.completion_tokens == 400

    (request,) = transport.requests
    assert request["method"] == "POST"
    assert request["url"] == "https://openrouter.ai/api/v1/chat/completions"

    sent = json.loads(request["body"])
    assert sent["model"] == deepseek.MODEL_ALIAS
    assert sent["max_tokens"] == 4000, "every call must be bounded"
    assert sent["seed"] == 17
    assert [m["role"] for m in sent["messages"]] == ["system", "user"]


def test_the_key_travels_in_a_header_and_never_in_the_url_or_prompt() -> None:
    transport = RecordingTransport()
    key = "sk-or-v1-testkey0123456789"
    call(transport, api_key=key)

    (request,) = transport.requests
    assert request["headers"]["Authorization"] == f"Bearer {key}"
    assert key not in request["url"]
    assert key not in request["body"].decode()


def test_at_most_one_retry() -> None:
    """Two attempts total. Every attempt is billable, so the general provider
    default of three is the wrong policy for a model call."""

    class AlwaysFailing(RecordingTransport):
        def request(self, *args, **kwargs):
            self.requests.append({})
            return HttpResponse(503, b"{}", {})

    transport = AlwaysFailing()
    with pytest.raises(ProviderError):
        deepseek.call(
            system="s",
            user="u",
            model=deepseek.MODEL_ALIAS,
            max_tokens=100,
            seed=None,
            api_key="k",
            transport=transport,
        )
    assert len(transport.requests) == deepseek.MAX_ATTEMPTS == 2


def test_an_empty_completion_is_an_error_not_an_empty_draft() -> None:
    """A blank file written with a provenance header looks like a reviewed
    artifact with nothing in it. Fail instead."""
    with pytest.raises(RuntimeError, match="empty completion"):
        call(RecordingTransport(content="   "))


def test_seed_is_omitted_when_not_requested() -> None:
    transport = RecordingTransport()
    call(transport, seed=None)
    assert "seed" not in json.loads(transport.requests[0]["body"])


# --- cost ------------------------------------------------------------------


def test_cost_is_computed_from_the_response_not_an_estimate() -> None:
    usage = deepseek.Usage(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert usage.cost_usd(deepseek.MODEL_ALIAS) == Decimal("1.60") + Decimal("3.20")
    assert usage.cost_usd(deepseek.MODEL_PIN) == Decimal("0.579") + Decimal("1.738")


def test_the_pin_is_cheaper_than_the_floating_alias() -> None:
    """Pins the reason the skill recommends `--pin` for anything citable: it
    is the same weights at roughly a third of the price."""
    usage = deepseek.Usage(prompt_tokens=500_000, completion_tokens=50_000)
    assert usage.cost_usd(deepseek.MODEL_PIN) < usage.cost_usd(deepseek.MODEL_ALIAS) / 2


def test_unknown_model_reports_no_cost_rather_than_a_wrong_one() -> None:
    assert deepseek.Usage(1, 1).cost_usd("deepseek/some-future-model") is None


# --- provenance ------------------------------------------------------------


def test_written_output_is_marked_unreviewed() -> None:
    """The header is written at creation time so an artifact cannot reach the
    repository unmarked by someone forgetting to add it afterwards."""
    from datetime import date

    header = deepseek.provenance_header(deepseek.MODEL_PIN, [], date(2026, 9, 14))
    assert "DeepSeek-assisted" in header
    assert deepseek.MODEL_PIN in header
    assert "Not yet reviewed" in header


def test_provenance_cites_the_sources_the_model_was_given() -> None:
    from datetime import date

    header = deepseek.provenance_header(
        deepseek.MODEL_ALIAS, [ROOT / "planning" / "CONTEXT.md"], date(2026, 9, 14)
    )
    assert "planning/CONTEXT.md" in header


# --- main: the guard runs before the client exists -------------------------


def test_guard_refusal_sends_nothing(capsys, monkeypatch) -> None:
    def explode(**_kwargs):
        raise AssertionError("a call was made despite a guard refusal")

    monkeypatch.setattr(deepseek, "call", explode)
    code = deepseek.main(
        ["--task", "freeform", "--question", "q", "--file", str(ROOT / "src" / "cli.py")]
    )
    assert code == 2
    assert "outside the sendable roots" in capsys.readouterr().err


def test_dry_run_costs_the_call_without_making_it(capsys, monkeypatch) -> None:
    def explode(**_kwargs):
        raise AssertionError("a call was made during a dry run")

    monkeypatch.setattr(deepseek, "call", explode)
    code = deepseek.main(["--task", "edge-viability", "--question", "q", "--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "nothing sent" in out and "cost:" in out


def test_a_missing_key_is_a_clear_refusal_not_a_traceback(capsys, monkeypatch) -> None:
    monkeypatch.delenv(deepseek.API_KEY_ENV, raising=False)

    def explode(**_kwargs):
        raise AssertionError("a call was made without a key")

    monkeypatch.setattr(deepseek, "call", explode)
    code = deepseek.main(["--task", "freeform", "--question", "q"])
    assert code == 1
    assert "environment variable only" in capsys.readouterr().err


def test_a_failed_call_degrades_to_no_draft(capsys, monkeypatch) -> None:
    """Best-effort infrastructure: a failure prints and exits, it does not
    propagate a traceback into whatever invoked it."""
    monkeypatch.setenv(deepseek.API_KEY_ENV, "sk-or-v1-testkey0123456789")

    def fail(**_kwargs):
        raise RuntimeError("provider is down")

    monkeypatch.setattr(deepseek, "call", fail)
    code = deepseek.main(["--task", "freeform", "--question", "q"])
    assert code == 1
    assert "no draft generated" in capsys.readouterr().err


# --- reasoning-model failure modes -----------------------------------------


class TruncatedTransport:
    """What a reasoning model actually returns when the budget runs out: a
    length-truncated choice with empty content, HTTP 200, no error."""

    def __init__(self, reasoning_tokens: int = 5980) -> None:
        self.reasoning_tokens = reasoning_tokens

    def request(self, method, url, *, headers=None, body=None, timeout=15.0):
        payload = {
            "choices": [{"message": {"content": "", "reasoning": "..."}, "finish_reason": "length"}],
            "usage": {
                "prompt_tokens": 3000,
                "completion_tokens": 6000,
                "completion_tokens_details": {"reasoning_tokens": self.reasoning_tokens},
            },
        }
        return HttpResponse(200, json.dumps(payload).encode(), {})


def test_budget_exhausted_by_reasoning_is_named_not_generic() -> None:
    """Found by running it. Diagnosed as "empty completion" this costs an
    afternoon; named, it costs one retry with a bigger ceiling."""
    with pytest.raises(RuntimeError, match="output budget exhausted") as excinfo:
        call(TruncatedTransport(), max_tokens=6000)
    message = str(excinfo.value)
    assert "reasoning" in message and "--max-tokens" in message and "6,000" in message


def test_reasoning_tokens_are_reported_not_added() -> None:
    """They are billed inside `completion_tokens`. Adding them would overstate
    every cost this tool prints."""
    usage = deepseek.Usage(prompt_tokens=10, completion_tokens=100, reasoning_tokens=80)
    expected = deepseek.Usage(prompt_tokens=10, completion_tokens=100).cost_usd(deepseek.MODEL_PIN)
    assert usage.cost_usd(deepseek.MODEL_PIN) == expected


def test_the_providers_own_cost_beats_the_local_price_table() -> None:
    """The table is a snapshot and goes stale silently; OpenRouter reports
    what it actually charged."""
    usage = deepseek.Usage(
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        reported_cost=Decimal("0.4242"),
    )
    assert usage.cost_usd(deepseek.MODEL_ALIAS) == Decimal("0.4242")


def test_reported_cost_is_captured_from_the_response() -> None:
    class CostedTransport(RecordingTransport):
        def request(self, method, url, *, headers=None, body=None, timeout=15.0):
            payload = {
                "choices": [{"message": {"content": "draft"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 200,
                    "completion_tokens_details": {"reasoning_tokens": 150},
                    "cost": 0.0001122,
                },
            }
            return HttpResponse(200, json.dumps(payload).encode(), {})

    _, usage = call(CostedTransport())
    assert usage.reported_cost == Decimal("0.0001122")
    assert usage.reasoning_tokens == 150
