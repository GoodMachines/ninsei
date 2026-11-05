"""The optional second cap: "Hearth may use at most N% of my Nous plan per day".

How it works. The first model call after local midnight snapshots the remaining plan dollars (stored
in the kv table). The day's cap is snapshot x N%. Every Nous-billed call adds its dollar cost to a
running total. When the total reaches the cap, `preflight` raises BudgetExhausted, the same exception
the token budget raises, so the agent rests and posts the one canned notice.

Where the numbers come from, all through Hermes (Hearth never touches auth.json, tokens or .env):
  * remaining plan dollars: `agent.billing_usage.build_usage_model()`, the same shared model behind the
    `billing.state` RPC's `usage` block, called in-process. It fails open (no login, no plan, a window
    plan, a transport error, an older Hermes without the module -> unavailable) and the cap does nothing.
  * cost of one call: `result.usage.cost_usd` if the host sets it, else Hermes's own price table
    (`agent.usage_pricing.estimate_usage_cost`), else a flat fallback rate so a call is never free.
    Only calls Hermes routed to the `nous` provider count; Hearth calls billed elsewhere cost the plan nothing.

The token budget is separate and always applies.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from decimal import Decimal
from typing import Any, Callable, Optional

from .brain import BudgetExhausted
from .store import Store, today

log = logging.getLogger("hearth")

FALLBACK_USD_PER_MTOK = 10.0   # used only when neither the host nor the price table knows the model
NOUS_NAMES = ("nous", "nous-portal", "nousresearch")   # the provider profile name and its aliases
RETRY_AFTER = 60.0             # seconds to wait before asking the portal again after a failed read


def hermes_remaining_usd() -> Optional[float]:
    """Remaining plan dollars from Hermes's own usage model, or None when there is no Nous plan to read."""
    try:
        from agent.billing_usage import build_usage_model
        m = build_usage_model(timeout=8.0)
    except Exception as e:  # older Hermes, not logged in, anything: fail open
        log.debug("hearth: plan read unavailable: %s", e)
        return None
    if not getattr(m, "available", False):
        return None
    bar = getattr(m, "plan_bar", None)
    val = bar.remaining_usd if bar is not None else getattr(m, "subscription_remaining_usd", None)
    return float(val) if isinstance(val, (int, float)) and val >= 0 else None


def hermes_call_cost(res: Any) -> tuple[float, str]:
    """(dollars this call took from the Nous plan, basis). Basis is reported | estimated | fallback | not-nous."""
    if str(getattr(res, "provider", "") or "").lower() not in NOUS_NAMES:
        return 0.0, "not-nous"
    u = getattr(res, "usage", None)
    reported = getattr(u, "cost_usd", None)
    if isinstance(reported, (int, float)) and reported >= 0:
        return float(reported), "reported"
    try:
        from agent.usage_pricing import CanonicalUsage, estimate_usage_cost
        cost = estimate_usage_cost(
            getattr(res, "model", "") or "",
            CanonicalUsage(input_tokens=int(getattr(u, "input_tokens", 0) or 0),
                           output_tokens=int(getattr(u, "output_tokens", 0) or 0),
                           cache_read_tokens=int(getattr(u, "cache_read_tokens", 0) or 0),
                           cache_write_tokens=int(getattr(u, "cache_write_tokens", 0) or 0)),
            provider="nous")
        if cost.amount_usd is not None:
            return float(cost.amount_usd if isinstance(cost.amount_usd, Decimal) else Decimal(str(cost.amount_usd))), "estimated"
    except Exception as e:
        log.debug("hearth: price lookup failed: %s", e)
    tokens = int(getattr(u, "total_tokens", 0) or 0)
    return tokens * FALLBACK_USD_PER_MTOK / 1_000_000, "fallback"


class PlanCap:
    def __init__(self, store: Store, pct_getter: Callable[[], int], *,
                 source: Optional[Callable[[], Optional[float]]] = None,
                 cost: Optional[Callable[[Any], tuple[float, str]]] = None):
        self.store = store
        self._pct = pct_getter
        self._source = source or hermes_remaining_usd
        self._cost = cost or hermes_call_cost
        self._lock = threading.Lock()        # snapshot fetch (may block on the network, run in a thread)
        self._spend_lock = threading.Lock()  # spend total (never blocks, safe on the event loop)
        self._retry_at = 0.0
        self._checked = False
        self._basis = ""

    # --- reads that never touch the network ---------------------------------------------------------
    def snapshot(self) -> Optional[dict]:
        snap = self.store.get("plan_snapshot")
        return snap if snap and snap.get("day") == today() else None

    def used_usd(self) -> float:
        row = self.store.get("plan_spent") or {}
        return float(row.get("usd", 0.0)) if row.get("day") == today() else 0.0

    def cap_usd(self) -> Optional[float]:
        pct, snap = int(self._pct()), self.snapshot()
        return round(snap["remaining_usd"] * pct / 100, 6) if pct and snap else None

    def exhausted(self) -> bool:
        cap = self.cap_usd()
        return cap is not None and self.used_usd() >= cap

    def view(self) -> dict:
        pct, snap = int(self._pct()), self.snapshot()
        cap = self.cap_usd()
        return {"plan_pct": pct, "available": snap is not None, "checked": self._checked or snap is not None,
                "plan_cap_usd": round(cap, 4) if cap is not None else None,
                "plan_used_usd": round(self.used_usd(), 4), "plan_snapshot_usd": round(snap["remaining_usd"], 4) if snap else None,
                "cost_basis": self._basis}

    # --- the parts that may block (run in a thread) -------------------------------------------------
    def ensure_snapshot(self) -> Optional[dict]:
        with self._lock:
            snap = self.snapshot()
            if snap or time.monotonic() < self._retry_at:
                return snap
            try:
                remaining = self._source()
            except Exception as e:
                log.debug("hearth: plan source failed: %s", e)
                remaining = None
            self._checked = True
            if remaining is None:
                self._retry_at = time.monotonic() + RETRY_AFTER
                return None
            snap = {"day": today(), "remaining_usd": float(remaining), "at": time.time()}
            self.store.set("plan_snapshot", snap)
            return snap

    async def probe(self) -> None:
        if int(self._pct()):
            await asyncio.to_thread(self.ensure_snapshot)

    async def preflight(self) -> None:
        """Called before every room model call. Does nothing when off or unavailable."""
        if not int(self._pct()):
            return
        await asyncio.to_thread(self.ensure_snapshot)
        if self.exhausted():
            raise BudgetExhausted()

    def record(self, res: Any) -> None:
        """Add one finished call's dollars to today's total (only while the cap is on and readable)."""
        if not int(self._pct()) or self.snapshot() is None:
            return
        try:
            usd, basis = self._cost(res)
        except Exception as e:
            log.debug("hearth: cost failed: %s", e)
            return
        with self._spend_lock:
            self.store.set("plan_spent", {"day": today(), "usd": self.used_usd() + max(0.0, usd)})
            self._basis = basis
