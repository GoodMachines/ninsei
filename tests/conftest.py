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
