"""Ninsei engine package. One engine per Hermes process, created lazily on first UI request."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("ninsei")

STATE: dict[str, Any] = {"llm": None}
_engine = None
_engine_error: Optional[str] = None
_lock = threading.Lock()
_last_push = [0.0]


def data_dir() -> Path:
    from plugins.plugin_storage import plugin_data_dir  # documented per-plugin, per-profile data root
    return Path(plugin_data_dir("ninsei"))


def db_path_if_present() -> Optional[Path]:
    """The store's path when Ninsei has data in the active profile, else None. Passive: it never
    creates the data folder (plugin_data_dir does), so status displays can call it freely."""
    try:
        from hermes_constants import get_hermes_home
        path = Path(get_hermes_home()) / "plugin-data" / "ninsei" / "ninsei.db"
    except Exception:
        return None
    return path if path.is_file() else None


def _push(version: int) -> None:
    """Tell the Desktop half something changed (it re-fetches). Throttled; polling covers misses."""
    now = time.monotonic()
    if now - _last_push[0] < 0.15:
        return
    _last_push[0] = now
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event
        broadcast_plugin_event("ninsei", "changed", {"v": version})
    except Exception:
        pass


def get_engine():
    """Start (once) and return this process's engine. Raises EngineLocked if another process owns it."""
    global _engine, _engine_error
    with _lock:
        if _engine is None:
            from .engine import Engine
            eng = Engine(data_dir(), lambda: STATE["llm"], notify=_push)
            eng.start()
            _engine = eng
        return _engine


def peek_store():
    """Read-only-ish store access for tools running in processes that don't host the engine."""
    from .store import Store
    return Store(data_dir() / "ninsei.db")
