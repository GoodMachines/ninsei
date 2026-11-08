"""`start_tales` returns at once and writes the questions in a task. Most tests want the old shape: the
call that comes back with the game started (or raises why it could not). `started` is that."""
import asyncio
import time


async def started(engine, room, *args, timeout=30.0, **kwargs):
    """Call engine.start_tales and wait for the background start to finish: {"gid"} on success, ValueError
    carrying the owner-facing text when it failed."""
    await engine.start_tales(room, *args, **kwargs)
    end = time.time() + timeout
    while room in engine._starting_games:
        assert time.time() < end, "the game start never finished"
        await asyncio.sleep(0.01)
    err = engine._start_errors.pop(room, None)
    if err:
        raise ValueError(err["text"])
    return {"gid": next(gid for gid, g in engine._host_games.items() if g["room"] == room)}
