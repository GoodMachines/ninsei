"""Hearth backend routes, mounted at /api/plugins/hearth/ (Desktop reaches them via ctx.rest, the
dashboard tab via fetchJSON). Every route sits behind Hermes's own auth gate; every state change is a POST.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


def _pkg():
    mod = sys.modules.get("hearth_room_engine")
    if mod is None:
        spec = importlib.util.spec_from_file_location(
            "hearth_room_loader", Path(__file__).resolve().parent.parent / "_loader.py")
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)
        mod = loader.load_engine()
    return mod


async def _engine():
    pkg = _pkg()
    try:
        return await asyncio.to_thread(pkg.get_engine)
    except Exception as e:  # EngineLocked or a broken data dir: tell the UI plainly
        raise HTTPException(status_code=409, detail=str(e))


async def _run(fn, *args, **kwargs) -> Any:
    eng = await _engine()
    try:
        return await asyncio.wrap_future(eng.call(fn, *args, **kwargs))
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e).strip("'\""))


async def _sync(fn, *args) -> Any:
    """Read the engine's state on its own loop, so views never race event handling."""
    eng = await _engine()

    async def wrap():
        return fn(*args)
    try:
        return await asyncio.wrap_future(eng.call(wrap))
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e).strip("'\""))


router = APIRouter()


class Settings(BaseModel):
    display_name: Optional[str] = None
    agent_name: Optional[str] = None
    vibe: Optional[str] = None
    face: Optional[dict] = None
    interests: Optional[list[str]] = None
    line: Optional[str] = None
    budget_daily: Optional[int] = None
    chattiness: Optional[str] = None
    offers: Optional[bool] = None
    share_budget: Optional[bool] = None
    relays: Optional[list[str]] = None
    onboarded: Optional[bool] = None


class RoomIn(BaseModel):
    name: str = ""
    about: str = ""
    interests: list[str] = []


class RoomRef(BaseModel):
    room: str


class PostIn(BaseModel):
    room: str
    text: str


class OfferAnswer(BaseModel):
    offer: str
    accept: bool
    task: Optional[str] = None


class ShareIn(BaseModel):
    offer: str
    title: str = ""


class FakeIn(BaseModel):
    room: str
    gid: str
    n: int
    text: str


class VoteIn(BaseModel):
    room: str
    gid: str
    n: int
    option: str


class DraftIn(BaseModel):
    id: str
    text: Optional[str] = None


@router.get("/state")
async def state(room: str = ""):
    eng = await _engine()
    return await _sync(eng.snapshot, room or None)


@router.post("/settings")
async def settings(body: Settings):
    eng = await _engine()
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    relays_before = eng.relays()
    out = await _sync(eng.save_settings, patch)
    if "relays" in patch and eng.relays() != relays_before:
        await _run(eng.reconnect)
    eng._bump()
    return out


@router.post("/rooms")
async def create_room(body: RoomIn):
    eng = await _engine()
    return await _run(eng.create_room, body.name, body.about, body.interests)


@router.post("/rooms/join")
async def join_room(body: RoomRef):
    eng = await _engine()
    return await _run(eng.join_room, body.room)


@router.post("/rooms/leave")
async def leave_room(body: RoomRef):
    eng = await _engine()
    await _run(eng.leave_room, body.room)
    return {"ok": True}


@router.post("/post")
async def post(body: PostIn):
    eng = await _engine()
    return await _run(eng.post, body.room, body.text)


@router.post("/lobby/refresh")
async def lobby():
    eng = await _engine()
    return await _run(eng.refresh_lobby)


@router.get("/card/preview")
async def card_preview():
    eng = await _engine()
    return await _sync(eng.card_content)


@router.post("/card/publish")
async def card_publish():
    eng = await _engine()
    return await _run(eng.publish_card)


@router.post("/offers/answer")
async def offer_answer(body: OfferAnswer):
    eng = await _engine()
    return await _run(eng.answer_offer, body.offer, body.accept, body.task)


@router.get("/offers/build")
async def offer_build(offer: str):
    eng = await _engine()
    try:
        html = await asyncio.to_thread(eng.read_build, offer)
    except (OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"html": html, "bytes": len(html.encode())}


@router.post("/offers/share")
async def offer_share(body: ShareIn):
    eng = await _engine()
    return await _run(eng.share_build, body.offer, body.title)


@router.get("/share")
async def share(room: str, id: str):
    eng = await _engine()
    return {"html": await _sync(eng.share_html, room, id)}


@router.post("/game/start")
async def game_start(body: RoomRef):
    eng = await _engine()
    return await _run(eng.start_tales, body.room)


@router.post("/game/fake")
async def game_fake(body: FakeIn):
    eng = await _engine()
    await _run(eng.submit_fake, body.room, body.gid, body.n, body.text)
    return {"ok": True}


@router.post("/game/vote")
async def game_vote(body: VoteIn):
    eng = await _engine()
    await _run(eng.submit_vote, body.room, body.gid, body.n, body.option)
    return {"ok": True}


@router.post("/drafts/send")
async def draft_send(body: DraftIn):
    eng = await _engine()
    await _run(eng.send_draft, body.id, body.text)
    return {"ok": True}


@router.post("/drafts/discard")
async def draft_discard(body: DraftIn):
    eng = await _engine()
    await _run(eng.discard_draft, body.id)
    return {"ok": True}


@router.post("/relays/reconnect")
async def relays_reconnect():
    eng = await _engine()
    await _run(eng.reconnect)
    return {"ok": True}
