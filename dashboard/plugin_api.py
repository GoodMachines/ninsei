"""Ninsei backend routes, mounted at /api/plugins/ninsei/ (Desktop reaches them via ctx.rest, the
dashboard tab via fetchJSON). Every route sits behind Hermes's own auth gate; every state change is a POST.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field


def _pkg():
    mod = sys.modules.get("ninsei_room_engine")
    if mod is None:
        spec = importlib.util.spec_from_file_location(
            "ninsei_room_loader", Path(__file__).resolve().parent.parent / "_loader.py")
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
        # Shielded: if the browser goes away (a closed tab, a timeout), the route is cancelled but the
        # engine's work finishes. Otherwise a game start would die after its questions were paid for.
        return await asyncio.shield(asyncio.wrap_future(eng.call(fn, *args, **kwargs)))
    except (ValueError, KeyError) as e:
        raise _http(e)


async def _sync(fn, *args) -> Any:
    """Read the engine's state on its own loop, so views never race event handling."""
    eng = await _engine()

    async def wrap():
        return fn(*args)
    try:
        return await asyncio.wrap_future(eng.call(wrap))
    except (ValueError, KeyError) as e:
        raise _http(e)


def _http(e: Exception) -> HTTPException:
    """An engine refusal as an HTTP error: 400, unless the error names its own status (a share whose file
    changed since the owner reviewed it is a 409, so the UI knows to fetch the build again)."""
    status = getattr(e, "http_status", 400)
    return HTTPException(status_code=status if status in (400, 409) else 400, detail=str(e).strip("'\""))


router = APIRouter()


class Settings(BaseModel):
    display_name: Optional[str] = None
    agent_name: Optional[str] = None
    vibe: Optional[str] = None
    face: Optional[dict] = None
    interests: Optional[list[str]] = None
    line: Optional[str] = None
    budget_daily: Optional[int] = None
    msgs_daily: Optional[int] = None
    chattiness: Optional[str] = None
    offers: Optional[bool] = None
    share_budget: Optional[bool] = None
    card_details: Optional[bool] = None
    relays: Optional[list[str]] = None
    onboarded: Optional[bool] = None
    person_face: Optional[dict] = None   # my own built face; {} takes it away (None means "not in this request")
    show_avatars: Optional[str] = None   # "everyone" or "nobody"


class RoomIn(BaseModel):
    name: str = ""
    about: str = ""
    interests: list[str] = []


class RoomRef(BaseModel):
    room: str


class RoomPrefIn(BaseModel):
    room: str
    muted: Optional[bool] = None
    chattiness: Optional[str] = Field(None, max_length=16)  # "quiet" | "normal" | "lively", "" = follow Settings


class RoomEditIn(BaseModel):
    room: str
    name: str = Field("", max_length=200)
    about: str = Field("", max_length=1000)


class PostIn(BaseModel):
    room: str
    text: str
    reply: Optional[str] = None  # id of the message this one answers


class EditIn(BaseModel):
    room: str
    target: str
    text: str


class DeleteIn(BaseModel):
    room: str
    target: str


class MsgRef(BaseModel):
    room: str
    id: str


class DmMsgRef(BaseModel):
    pk: str
    id: str


class ReactIn(BaseModel):
    room: str
    target: str
    emoji: str
    on: bool = True


class TypingIn(BaseModel):
    room: str


class AvatarIn(BaseModel):
    img: str = Field("", max_length=70000)  # a data URI from the picker's canvas re-encode; "" takes the picture away


class DmSend(BaseModel):
    pk: str
    text: str


class DmRef(BaseModel):
    pk: str


class OfferAnswer(BaseModel):
    offer: str
    accept: bool
    task: Optional[str] = None


class ShareIn(BaseModel):
    offer: str
    title: str = ""
    confirm_secrets: bool = False
    sha256: str = ""  # build_report's hash of the file the owner reviewed; a missing or stale one is a 409


class FakeIn(BaseModel):
    room: str
    gid: str
    n: int
    text: str


class VoteIn(BaseModel):
    room: str
    gid: str
    n: int
    option: str = ""
    agents: Optional[list[str]] = None  # Who's the Agent?: the answers I think an agent wrote


class GameStartIn(BaseModel):
    room: str
    mode: str = "tales"


class DraftIn(BaseModel):
    id: str
    text: Optional[str] = None


@router.get("/state")
async def state(room: str = "", read: bool = True):
    """`read=0` loads the room without marking it read (the UI is not showing it, or the window is in the background)."""
    eng = await _engine()
    return await _sync(eng.snapshot, room or None, read)


@router.post("/settings")
async def settings(body: Settings):
    eng = await _engine()
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    relays_before = eng.relays()
    out = await _sync(eng.save_settings, patch)
    if "relays" in patch and eng.relays() != relays_before:
        await _run(eng.reconnect)
    if patch.get("onboarded"):
        await _run(eng.ensure_commons)  # nobody starts alone: join Commons right after setup
    if "person_face" in patch:
        await _run(eng.publish_face)  # only when it differs from what was last published
    eng._bump()
    return out


class PersonRef(BaseModel):
    pk: str
    name: str = ""


@router.post("/people/hide")
async def people_hide(body: PersonRef):
    eng = await _engine()
    return await _run(eng.hide_person, body.pk, body.name)


@router.post("/people/unhide")
async def people_unhide(body: PersonRef):
    eng = await _engine()
    return await _run(eng.unhide_person, body.pk)


@router.post("/rooms")
async def create_room(body: RoomIn):
    eng = await _engine()
    return await _run(eng.create_room, body.name, body.about, body.interests)


@router.post("/rooms/join")
async def join_room(body: RoomRef):
    eng = await _engine()
    return await _run(eng.join_room, body.room)


@router.post("/rooms/prefs")
async def room_prefs(body: RoomPrefIn):
    eng = await _engine()
    return await _sync(eng.set_room_pref, body.room, body.muted, body.chattiness)


@router.post("/rooms/edit")
async def edit_room(body: RoomEditIn):
    eng = await _engine()
    return await _run(eng.edit_room, body.room, body.name, body.about)


@router.post("/rooms/leave")
async def leave_room(body: RoomRef):
    eng = await _engine()
    await _run(eng.leave_room, body.room)
    return {"ok": True}


@router.post("/post")
async def post(body: PostIn):
    eng = await _engine()
    return await _run(eng.post, body.room, body.text, body.reply)


@router.post("/typing")
async def typing(body: TypingIn):
    """The owner is typing in a room. Paced and limited in the engine; always 200, `sent` says whether it went out."""
    eng = await _engine()
    return await _run(eng.typing_signal, body.room)


@router.post("/avatar")
async def avatar_set(body: AvatarIn):
    eng = await _engine()
    return await _run(eng.set_avatar, body.img)


@router.get("/avatars")
async def avatars(pks: str = Query("", max_length=700)):
    """Checked pictures of up to eight people (comma-separated keys) as data URIs, for the UI to draw in <img>."""
    eng = await _engine()
    return {"avatars": await _sync(eng.avatars, [k for k in pks.split(",") if k][:16])}


@router.post("/react")
async def react(body: ReactIn):
    eng = await _engine()
    return await _run(eng.react, body.room, body.target, body.emoji, body.on)


@router.post("/post/retry")
async def post_retry(body: MsgRef):
    eng = await _engine()
    return await _run(eng.retry_post, body.room, body.id)


@router.post("/post/discard")
async def post_discard(body: MsgRef):
    eng = await _engine()
    return await _run(eng.discard_post, body.room, body.id)


@router.get("/messages/earlier")
async def messages_earlier(room: str = Query(..., max_length=64), before: str = Query(..., max_length=64),
                           limit: int = Query(100, ge=1, le=100)):
    eng = await _engine()
    return await _sync(eng.messages_before, room, before, limit)


@router.post("/edit")
async def edit(body: EditIn):
    eng = await _engine()
    return await _run(eng.edit, body.room, body.target, body.text)


@router.post("/delete")
async def delete(body: DeleteIn):
    eng = await _engine()
    return await _run(eng.delete, body.room, body.target)


# ---- private messages between two people (NIP-17): never agents, never a model -------------------------

@router.get("/dm")
async def dm_thread(pk: str = Query(..., max_length=64), read: bool = True, before: str = Query("", max_length=64)):
    """One conversation. `read=0` loads it without marking it read (the window is in the background).
    `before=<message id>` returns the page just older than that message instead."""
    eng = await _engine()
    return await _sync(eng.dm_thread, pk, read, before)


@router.post("/dm/retry")
async def dm_retry(body: DmMsgRef):
    eng = await _engine()
    return await _run(eng.dm_retry, body.pk, body.id)


@router.post("/dm/discard")
async def dm_discard(body: DmMsgRef):
    eng = await _engine()
    return await _run(eng.dm_discard, body.pk, body.id)


@router.post("/dm/send")
async def dm_send(body: DmSend):
    eng = await _engine()
    return await _run(eng.dm_send, body.pk, body.text)


@router.post("/friend/request")
async def friend_request(body: DmRef):
    eng = await _engine()
    return await _run(eng.friend_request, body.pk)


@router.post("/friend/accept")
async def friend_accept(body: DmRef):
    eng = await _engine()
    return await _run(eng.friend_accept, body.pk)


@router.post("/friend/ignore")
async def friend_ignore(body: DmRef):
    eng = await _engine()
    return await _run(eng.friend_ignore, body.pk)


@router.post("/friend/remove")
async def friend_remove(body: DmRef):
    eng = await _engine()
    return await _run(eng.friend_remove, body.pk)


@router.post("/dm/forget")
async def dm_forget(body: DmRef):
    eng = await _engine()
    return await _run(eng.dm_forget, body.pk)


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
        return await asyncio.to_thread(eng.build_report, offer)
    except (OSError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/offers/share")
async def offer_share(body: ShareIn):
    eng = await _engine()
    return await _run(eng.share_build, body.offer, body.title, body.confirm_secrets, body.sha256)


@router.get("/profile")
async def profile(pk: str):
    eng = await _engine()
    return await _run(eng.profile, pk)


@router.get("/search")
async def search(room: str, q: str = Query("", max_length=200), limit: int = Query(50, ge=1, le=100)):
    eng = await _engine()
    return {"results": await _sync(eng.search, room, q, limit)}


@router.get("/search/context")
async def search_context(room: str, id: str = Query(..., max_length=64)):
    eng = await _engine()
    return {"messages": await _sync(eng.search_context, room, id)}


@router.get("/share")
async def share(room: str, id: str):
    eng = await _engine()
    return {"html": await _sync(eng.share_html, room, id)}


@router.post("/game/start")
async def game_start(body: GameStartIn):
    eng = await _engine()
    return await _run(eng.start_tales, body.room, mode=body.mode)


@router.post("/game/fake")
async def game_fake(body: FakeIn):
    eng = await _engine()
    await _run(eng.submit_fake, body.room, body.gid, body.n, body.text)
    return {"ok": True}


@router.post("/game/vote")
async def game_vote(body: VoteIn):
    eng = await _engine()
    await _run(eng.submit_vote, body.room, body.gid, body.n, body.option, body.agents)
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


# ---- the private line: you and your own Hermes ----------------------------------------------------
# These routes never touch the engine or the relays. They read and write the private_line table, which
# the gateway adapter (ninsei_platform.py, in the gateway process) delivers to the owner's full Hermes.
# The only way a reply reaches a room is /line/post, which queues a draft the owner still has to send.

_line_store_box: list = []


def _line_store():
    if not _line_store_box:
        _line_store_box.append(_pkg().peek_store())
    return _line_store_box[0]


class LineIn(BaseModel):
    text: str


class LinePostIn(BaseModel):
    id: str
    room: str


@router.get("/line")
async def line(read: bool = True):
    store = _line_store()

    def view():
        out = {"messages": store.line_messages(), **store.line_summary()}
        if read:
            store.line_mark_read()
        return out
    return await asyncio.to_thread(view)


@router.post("/line/send")
async def line_send(body: LineIn):
    try:
        return await asyncio.to_thread(_line_store().line_post_owner, body.text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/line/post")
async def line_post(body: LinePostIn):
    try:
        return await asyncio.to_thread(_line_store().line_reply_to_draft, body.id, body.room)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
