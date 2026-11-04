import asyncio, importlib.util, os, sys
from pathlib import Path
from fastapi import APIRouter

def _engine():
    mod = sys.modules.get("hearth_room_engine")
    if mod is None:
        spec = importlib.util.spec_from_file_location("hearth_room_loader", Path(__file__).resolve().parent.parent / "_loader.py")
        loader = importlib.util.module_from_spec(spec); spec.loader.exec_module(loader)
        mod = loader.load_engine()
    return mod

router = APIRouter()

@router.get("/debug")
async def debug():
    eng = _engine(); eng.STATE["api_pid"] = os.getpid()
    return {k: (str(v) if k == "llm" else v) for k, v in eng.STATE.items()} | {"pid": os.getpid()}

@router.get("/llmtest")
async def llmtest():
    eng = _engine(); llm = eng.STATE["llm"]
    if llm is None:
        return {"error": "no llm"}
    r = await asyncio.to_thread(llm.complete, messages=[{"role": "user", "content": "Say hi in 3 words."}], max_tokens=20, purpose="hearth.probe")
    return {"text": r.text, "model": r.model, "usage": str(r.usage)}
