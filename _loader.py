"""Load the xenia_engine package once per process under a private module name."""
import importlib.util, sys
from pathlib import Path

ENGINE_MODULE = "xenia_room_engine"

def load_engine():
    mod = sys.modules.get(ENGINE_MODULE)
    if mod is not None:
        return mod
    pkg_dir = Path(__file__).resolve().parent / "xenia_engine"
    spec = importlib.util.spec_from_file_location(
        ENGINE_MODULE, pkg_dir / "__init__.py", submodule_search_locations=[str(pkg_dir)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[ENGINE_MODULE] = mod
    spec.loader.exec_module(mod)
    return mod
