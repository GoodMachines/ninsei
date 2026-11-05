"""Hearth: rooms where people and their own Hermes agents hang out together.

This is the agent half. It hands `ctx.llm` to the engine, registers a model slot for room chatter,
and adds two tools and a slash command. The engine itself starts only when the Hearth UI asks for it
(see dashboard/plugin_api.py), never at import.
"""
from __future__ import annotations

import json

from . import _loader

STATUS_SCHEMA = {
    "name": "hearth_status",
    "description": (
        "See your Hearth rooms at a glance: room names, unread counts, who is online, your agent's state and "
        "today's room budget, and any offers or drafts waiting for you. It never returns what other people "
        "wrote. Use it when the user asks what's happening in Hearth."),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

SAY_SCHEMA = {
    "name": "hearth_say",
    "description": (
        "Queue a message for one of the user's Hearth rooms, for example 'tell shader club I'm running late'. "
        "It does NOT send: it saves a draft that the user reviews and sends from the Hearth page. Only use it "
        "when the user asked you to say something in a room."),
    "parameters": {
        "type": "object",
        "properties": {
            "room": {"type": "string", "description": "Room name (or id) as listed by hearth_status"},
            "text": {"type": "string", "description": "The message, in the user's voice, under 600 characters"},
        },
        "required": ["room", "text"],
    },
}


def _status(_args=None, **_kw) -> str:
    eng = _loader.load_engine()
    store = eng.peek_store()
    try:
        rooms = store.rooms()
        settings = store.get("settings") or {}
        offers = store.get("offers") or {}
        used = sum(store.budget_used().values())
        out = {
            "rooms": [{"name": m.get("name"), "id": rid} for rid, m in rooms.items()],
            "agent": settings.get("agent_name") or "(not set up yet)",
            "budget": {"used_tokens_today": used, "daily_limit": settings.get("budget_daily", 40000)},
            "offers_waiting_for_you": sum(1 for o in offers.values() if o.get("status") in ("open", "ready")),
            "drafts_waiting_to_send": len(store.drafts()),
            "how_to_open": "Open the Hearth page in Hermes Desktop (sidebar) or the Hearth tab in `hermes dashboard`.",
        }
    finally:
        store.close()
    return json.dumps(out)


def _say(args: dict, **_kw) -> str:
    room_q = str((args or {}).get("room", "")).strip().lower()
    text = str((args or {}).get("text", "")).strip()[:600]
    if not room_q or not text:
        return json.dumps({"error": "room and text are required"})
    eng = _loader.load_engine()
    store = eng.peek_store()
    try:
        rooms = store.rooms()
        match = [rid for rid, m in rooms.items() if rid == room_q or (m.get("name") or "").lower() == room_q] or \
                [rid for rid, m in rooms.items() if room_q in (m.get("name") or "").lower()]
        if not match:
            return json.dumps({"error": f"no Hearth room called {room_q!r}",
                               "rooms": [m.get("name") for m in rooms.values()]})
        oid = store.queue_draft(match[0], text, "hermes chat")
    finally:
        store.close()
    return json.dumps({"queued": True, "draft": oid,
                       "note": "Saved as a draft. The user reviews and sends it from the Hearth page; nothing was posted."})


def _slash(raw: str) -> str:
    data = json.loads(_status())
    if not data["rooms"]:
        return "Hearth: no rooms yet. Open the Hearth page to set up your agent and find a room."
    lines = [f"Hearth · {data['agent']} · {data['budget']['used_tokens_today']:,}/"
             f"{data['budget']['daily_limit']:,} tokens today"]
    lines += [f"  • {r['name']}" for r in data["rooms"]]
    if data["offers_waiting_for_you"]:
        lines.append(f"  {data['offers_waiting_for_you']} offer(s) waiting for you")
    if data["drafts_waiting_to_send"]:
        lines.append(f"  {data['drafts_waiting_to_send']} draft(s) waiting to send")
    return "\n".join(lines)


def register(ctx):
    eng = _loader.load_engine()
    eng.STATE["llm"] = getattr(ctx, "llm", None)  # absent in capability probes
    try:
        ctx.register_auxiliary_task(
            "hearth", display_name="Hearth rooms",
            description="Your agent's chat, offers and game moves in Hearth rooms. Point it at a fast, cheap model.")
    except Exception:  # older hosts: calls fall back to the main model
        pass
    ctx.register_tool(name="hearth_status", toolset="hearth", schema=STATUS_SCHEMA, handler=_status,
                      description="Hearth rooms at a glance", emoji="🔥")
    ctx.register_tool(name="hearth_say", toolset="hearth", schema=SAY_SCHEMA, handler=_say,
                      description="Draft a message for a Hearth room", emoji="🔥")
    ctx.register_command("hearth", _slash, description="Your Hearth rooms, budget and anything waiting for you")
