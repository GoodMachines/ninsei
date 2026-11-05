"""The optional Nous plan cap, with a stubbed billing source (no Hermes, no network)."""
import pytest

from xenia_engine import plan as plan_mod
from xenia_engine.brain import BudgetExhausted
from xenia_engine.engine import Engine
from xenia_engine.plan import hermes_call_cost


class Usage:
    def __init__(self, total=50, cost_usd=None):
        self.total_tokens, self.input_tokens, self.output_tokens, self.cost_usd = total, total // 2, total // 2, cost_usd


class Result:
    def __init__(self, provider="nous", model="m", usage=None):
        self.text, self.provider, self.model, self.usage = "ok", provider, model, usage or Usage()


class StubLLM:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, max_tokens=None, purpose=None, task=None, **_):
        self.calls += 1
        return Result()


class Billing:
    """Stubbed billing source and per-call price."""

    def __init__(self, remaining=100.0, cost=1.0):
        self.remaining, self.cost, self.reads = remaining, cost, 0

    def source(self):
        self.reads += 1
        return self.remaining

    def price(self, res):
        return self.cost, "reported"


def make(tmp_path, billing, pct=10):
    llm = StubLLM()
    e = Engine(tmp_path / "e", lambda: llm, relays=[], lock=False, plan_source=billing.source, plan_cost=billing.price)
    e.save_settings({"plan_pct": pct})
    return e, llm


async def call(e):
    return await e.brain._complete("chat", [{"role": "user", "content": "hi"}], 20, "reply")


def test_plan_pct_is_validated(tmp_path):
    e, _ = make(tmp_path, Billing(), pct=0)
    assert e.settings()["plan_pct"] == 0
    assert e.save_settings({"plan_pct": 250})["plan_pct"] == 100
    assert e.save_settings({"plan_pct": -5})["plan_pct"] == 0
    assert e.save_settings({"plan_pct": "12"})["plan_pct"] == 12
    assert e.save_settings({"plan_pct": "junk"})["plan_pct"] == 12   # bad input keeps the old value


async def test_snapshot_once_per_day_and_cap_math(tmp_path, monkeypatch):
    billing = Billing(remaining=80.0)
    e, _ = make(tmp_path, billing, pct=10)
    await call(e)
    await call(e)
    assert billing.reads == 1                                # one snapshot, not one per call
    v = e.budget_view()
    assert v["available"] and v["plan_pct"] == 10
    assert v["plan_cap_usd"] == pytest.approx(8.0)           # 80 x 10%
    assert v["plan_used_usd"] == pytest.approx(2.0)
    # first call after the next local midnight snapshots what is left then, and spend starts over
    monkeypatch.setattr(plan_mod, "today", lambda: "2099-01-01")
    billing.remaining = 40.0
    assert e.plan.snapshot() is None
    await call(e)
    assert billing.reads == 2
    assert e.plan.cap_usd() == pytest.approx(4.0)
    assert e.plan.used_usd() == pytest.approx(1.0)


async def test_blocks_over_the_cap_like_the_token_budget(tmp_path):
    billing = Billing(remaining=20.0, cost=1.0)              # cap 2.0
    e, llm = make(tmp_path, billing, pct=10)
    await call(e)
    await call(e)
    assert e.plan.exhausted() and e._budget_left() == 0
    before = llm.calls
    with pytest.raises(BudgetExhausted):                     # the exception the rest-notice path already handles
        await call(e)
    assert llm.calls == before                               # refused before the model was called
    assert e.budget_view()["pct"] == 1.0


async def test_does_nothing_when_unavailable(tmp_path):
    billing = Billing(remaining=None)
    e, llm = make(tmp_path, billing, pct=10)
    for _ in range(3):
        await call(e)
    assert llm.calls == 3
    v = e.budget_view()
    assert v["available"] is False and v["checked"] is True
    assert v["plan_cap_usd"] is None and v["plan_used_usd"] == 0
    assert billing.reads == 1                                # a failed read is retried after a minute, not per call


async def test_source_that_raises_is_unavailable(tmp_path):
    billing = Billing()
    billing.source = lambda: (_ for _ in ()).throw(RuntimeError("transport"))
    e, llm = make(tmp_path, billing, pct=10)
    await call(e)
    assert llm.calls == 1 and not e.budget_view()["available"]


async def test_off_by_default_never_reads_billing(tmp_path):
    billing = Billing()
    e, _ = make(tmp_path, billing, pct=0)
    assert Engine.settings(e)["plan_pct"] == 0
    await call(e)
    assert billing.reads == 0 and e.budget_view()["plan_cap_usd"] is None


async def test_token_budget_still_applies_with_the_cap_on(tmp_path):
    billing = Billing(remaining=1000.0, cost=0.0)            # the plan cap never trips
    e, llm = make(tmp_path, billing, pct=50)
    e.save_settings({"budget_daily": 10})
    with pytest.raises(BudgetExhausted):
        await call(e)
    assert llm.calls == 0


def test_only_nous_calls_cost_plan_dollars():
    assert hermes_call_cost(Result(provider="openai-codex")) == (0.0, "not-nous")
    assert hermes_call_cost(Result(provider="nous", usage=Usage(1000, cost_usd=0.5))) == (0.5, "reported")
    usd, basis = hermes_call_cost(Result(provider="nous", model="no-such-model", usage=Usage(1_000_000)))
    assert basis in ("estimated", "fallback") and usd >= 0
