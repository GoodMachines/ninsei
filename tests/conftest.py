import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The repo root is itself the Hermes plugin package (its __init__.py uses relative imports), so pytest
# would treat the root as a Package and try to import that __init__.py on its own, which fails.
# Skip that import for the repo root only.
from _pytest import python as _pt_python  # noqa: E402

_orig_setup = _pt_python.Package.setup


def _setup(self):
    if Path(str(self.path)).resolve() == ROOT:
        return
    return _orig_setup(self)


_pt_python.Package.setup = _setup

# tests import the relay helper as a plain module
_tests = str(Path(__file__).resolve().parent)
if _tests not in sys.path:
    sys.path.insert(0, _tests)


# No test may reach a real relay. A test once passed relays=[] (meaning "offline"), fell through to the
# public defaults, and every suite run joined the real Commons as "Maya" and "Ada" with fresh keys.
# Patch the one place the engine dials out and refuse anything that isn't this machine.
import pytest  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402

_LOCAL = {"127.0.0.1", "localhost", "::1"}


@pytest.fixture(autouse=True)
def _no_public_relays(monkeypatch):
    from ninsei_engine import relays as _relays
    real = _relays.websockets.connect

    tried = []

    def guarded(url, *a, **k):
        host = urlsplit(str(url)).hostname or ""
        if host not in _LOCAL:
            tried.append(str(url))
            raise OSError("tests never open public relays")  # the pool's retry loop swallows this...
        return real(url, *a, **k)
    monkeypatch.setattr(_relays.websockets, "connect", guarded)
    yield
    assert not tried, f"a test tried to open public relays: {sorted(set(tried))}"  # ...so fail here


# Engines start with "the owner is away" (no page has said it is open), and the default away_mode answers only
# when named. Most tests are about a room with its owner at the screen, so engines start that way here; a test
# about being away sets `_last_open_at = _last_focused_at = 0.0` itself.
@pytest.fixture(autouse=True)
def _owner_at_the_screen(monkeypatch):
    import time as _time
    from ninsei_engine import engine as _engine
    real = _engine.Engine.__init__

    def init(self, *a, **k):
        real(self, *a, **k)
        self._last_open_at = self._last_focused_at = _time.time()
    monkeypatch.setattr(_engine.Engine, "__init__", init)
    yield
