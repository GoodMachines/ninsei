"""Overnight network soak: two throwaway installs talk through the public relays for hours.

    python scripts/soak.py --hours 8 --out /path/to/dir

Two standalone engines (no Hermes, no model, never onboarded, so they never join Commons) join a fresh random
room code with no published listing. Every `--every` seconds one of them posts a short test line and the
script times how long the other takes to receive it. Once per `--gap-every` seconds B goes offline for
`--gap` seconds, as a laptop lid would, and on restart must catch up on what A said meanwhile. Every
10 minutes it records each relay's state (ok, rejected, rate-limit rests, last error) and the outbox size.

Writes `<out>/soak.jsonl` as it goes and `<out>/summary.json` at the end (or on Ctrl-C).
Traffic: one message per `--every` seconds plus each install's presence beat per minute, to the default relays.
"""
from __future__ import annotations

import argparse
import json
import secrets
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ninsei_engine.engine import Engine  # noqa: E402


def log(out: Path, **rec) -> None:
    rec["t"] = round(time.time(), 3)
    with (out / "soak.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec), flush=True)


def make(out: Path, name: str) -> Engine:
    e = Engine(out / name, lambda: None, lock=False)
    e.save_settings({"display_name": f"Soak {name.upper()}", "agent_name": f"Soak {name.upper()} bot"})
    return e.start()


def on(e: Engine, fn, *args, timeout: float = 60):
    async def run():
        return fn(*args)
    return e.call(run).result(timeout)


def has(e: Engine, room: str, eid: str) -> bool:
    return on(e, lambda: eid in e.events.get(room, {}))


def relays(e: Engine) -> list[dict]:
    def snap():
        pool = e.pool
        return [{"url": st.url, "state": st.state, "ok": st.ok, "rejected": st.rejected,
                 "rate_limited": st.rate_limited, "resting_s": round(pool.cooling(st.url)),
                 "err": (st.last_error or st.last_reject)[:100]} for st in pool.status.values()] + \
               [{"outbox": len(pool._outbox)}]
    return on(e, snap)


def wait_for(cond, timeout: float) -> float | None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if cond():
            return time.time() - t0
        time.sleep(0.25)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=8)
    ap.add_argument("--every", type=float, default=300)
    ap.add_argument("--gap-every", type=float, default=3600)
    ap.add_argument("--gap", type=float, default=300)
    ap.add_argument("--deliver-within", type=float, default=120)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    room = secrets.token_hex(8)
    a, b = make(args.out, "a"), make(args.out, "b")
    a.call(a.join_room, room).result(60)
    b.call(b.join_room, room).result(60)
    log(args.out, ev="start", room=room, hours=args.hours, every=args.every)

    sent = []        # {n, from, id, at, latency|None}
    gaps = []        # {down_at, up_at, missed: [ids], caught_up_s|None}
    end = time.time() + args.hours * 3600
    next_send, next_gap, next_snap = time.time(), time.time() + args.gap_every, time.time()
    b_down_until, gap = 0.0, None
    n = 0
    try:
        while time.time() < end:
            now = time.time()
            if now >= next_snap:
                log(args.out, ev="relays", a=relays(a), b=relays(b) if not b_down_until else "down")
                next_snap = now + 600
            if not b_down_until and now >= next_gap:
                b.stop()
                b_down_until = now + args.gap
                gap = {"down_at": round(now), "missed": []}
                log(args.out, ev="b_down")
            if b_down_until and now >= b_down_until:
                b = make(args.out, "b")
                t = wait_for(lambda: all(has(b, room, i) for i in gap["missed"]), args.deliver_within * 2)
                gap.update(up_at=round(time.time()), caught_up_s=None if t is None else round(t, 1),
                           got=sum(has(b, room, i) for i in gap["missed"]))
                gaps.append(gap)
                log(args.out, ev="b_up", **{k: v for k, v in gap.items() if k != "missed"}, missed=len(gap["missed"]))
                b_down_until, gap = 0.0, None
                next_gap = time.time() + args.gap_every
            if now >= next_send:
                n += 1
                src, dst = (a, b) if (n % 2 or b_down_until) else (b, a)
                who = "a" if src is a else "b"
                res = src.call(src.post, room, f"soak {n} from {who} {secrets.token_hex(3)}").result(60)
                rec = {"n": n, "from": who, "id": res["id"], "at": round(time.time(), 3)}
                if b_down_until:
                    gap["missed"].append(res["id"])
                    rec["latency"] = "b offline"
                else:
                    t = wait_for(lambda: has(dst, room, res["id"]), args.deliver_within)
                    rec["latency"] = None if t is None else round(t, 2)
                sent.append(rec)
                log(args.out, ev="msg", **rec)
                next_send = now + args.every
            time.sleep(1)
    except KeyboardInterrupt:
        log(args.out, ev="interrupted")
    finally:
        live = [s for s in sent if s["latency"] != "b offline"]
        lat = [s["latency"] for s in live if isinstance(s["latency"], (int, float))]
        summary = {
            "room": room, "messages": len(sent), "checked": len(live), "delivered": len(lat),
            "missed": [s["n"] for s in live if s["latency"] is None],
            "latency_s": {"median": statistics.median(lat), "p95": sorted(lat)[int(len(lat) * 0.95) - 1] if lat else None,
                          "max": max(lat)} if lat else None,
            "gaps": [{k: v for k, v in g.items() if k != "missed"} | {"missed": len(g["missed"])} for g in gaps],
            "relays_end": {"a": relays(a)},
        }
        (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
        log(args.out, ev="end", **{k: v for k, v in summary.items() if k != "relays_end"})
        for e in ((a,) if b_down_until else (a, b)):   # b may already be down for a gap
            try:
                e.stop()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
