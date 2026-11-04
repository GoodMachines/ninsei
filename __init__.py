import os
from . import _loader

def register(ctx):
    eng = _loader.load_engine()
    eng.STATE["llm"] = ctx.llm
    eng.STATE["registered_pid"] = os.getpid()
