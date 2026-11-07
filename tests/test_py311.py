"""Hermes supports Python 3.11 (`requires-python = ">=3.11"`), so every file Ninsei ships must load there.

Python 3.12 (PEP 701) relaxed f-strings, and `ast.parse(feature_version=(3, 11))` does not catch the difference:
an `r'\\s+'` inside an f-string's braces compiled on 3.12 and broke the import on 3.11 (engine.py, 2026-11-07).
This test walks every f-string with the tokenizer and refuses what 3.11 can't parse. When a 3.11 interpreter is
on the machine, it also compiles every file with it."""
import io
import os
import shutil
import subprocess
import sys
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FILES = sorted(p for p in ROOT.rglob("*.py") if not any(part.startswith(".") or part in ("__pycache__", "node_modules")
                                                         for part in p.relative_to(ROOT).parts))


def _quote(tok: str) -> str:
    body = tok.lstrip("rRbBuUfF")
    return body[:3] if body[:3] in ('"""', "'''") else body[:1]


def _clashes(inner: str, outer: str) -> bool:
    """3.11 ends the outer f-string at the first copy of its own quote, even inside the braces."""
    return inner == outer if len(outer) == 3 else inner[:1] == outer


def py311_problems(src: str) -> list:
    """(line, why) for each f-string expression 3.11 rejects: a backslash, a comment, or a nested string that
    reuses an enclosing f-string's quote."""
    if sys.version_info < (3, 12):
        return []   # the 3.11 tokenizer has no FSTRING_* tokens; the compile check below covers this case
    out, stack = [], []   # stack: one [quote, brace depth] per open f-string
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        inside = bool(stack) and stack[-1][1] > 0
        if tok.type == tokenize.FSTRING_START:
            q = _quote(tok.string)
            if inside and any(_clashes(q, s[0]) for s in stack):
                out.append((tok.start[0], "nested f-string reuses the outer quote"))
            if inside and "\\" in tok.string:
                out.append((tok.start[0], "backslash in an f-string expression"))
            stack.append([q, 0])
            continue
        if not stack:
            continue
        if tok.type == tokenize.FSTRING_END:
            stack.pop()
            continue
        if tok.type == tokenize.OP and tok.string == "{":
            stack[-1][1] += 1
        elif tok.type == tokenize.OP and tok.string == "}":
            stack[-1][1] -= 1
        elif inside and tok.type != tokenize.FSTRING_MIDDLE:
            if "\\" in tok.string:
                out.append((tok.start[0], "backslash in an f-string expression"))
            if tok.type == tokenize.COMMENT:
                out.append((tok.start[0], "comment in an f-string expression"))
            if tok.type == tokenize.STRING and any(_clashes(_quote(tok.string), s[0]) for s in stack):
                out.append((tok.start[0], "nested string reuses the outer quote"))
    return out


@pytest.mark.skipif(sys.version_info < (3, 12), reason="needs the 3.12 tokenizer")
def test_the_check_catches_what_broke_on_311():
    bad = 'x = [f"> {re.sub(r\'[^\\\\w]\', \'\', n)}" for n in names]\n'
    assert [why for _, why in py311_problems(bad)] == ["backslash in an f-string expression"]
    assert py311_problems('x = f"{d["k"]}"\n')                       # same quote inside the braces
    assert py311_problems("x = f\"{d['k']}\" + f'''{d[\"k\"]}'''\n") == []   # fine on 3.11
    assert py311_problems('x = f"{a!r:>{w}} \\n"\n') == []          # a backslash in the literal part is fine


@pytest.mark.skipif(sys.version_info < (3, 12), reason="needs the 3.12 tokenizer")
def test_every_file_parses_on_python_311():
    problems = [f"{p.relative_to(ROOT)}:{line}: {why}" for p in FILES for line, why in py311_problems(p.read_text())]
    assert not problems, "Python 3.11 can't parse these (Hermes supports 3.11):\n" + "\n".join(problems)


def _py311():
    for cand in (os.environ.get("NINSEI_PY311", ""), shutil.which("python3.11") or "",
                 str(Path.home() / ".hermes/hermes-agent/venv/bin/python")):
        if cand and Path(cand).is_file():
            try:
                v = subprocess.run([cand, "-c", "import sys; print(sys.version_info[:2] == (3, 11))"],
                                   capture_output=True, text=True, timeout=20).stdout.strip()
            except Exception:
                continue
            if v == "True":
                return cand
    return None


def test_every_file_compiles_with_a_real_python_311_when_one_is_here():
    py = _py311()
    if not py:
        pytest.skip("no Python 3.11 on this machine (set NINSEI_PY311 to one)")
    code = ("import sys\nbad=[]\nfor f in sys.argv[1:]:\n    try: compile(open(f).read(), f, 'exec')\n"
            "    except SyntaxError as e: bad.append(f'{f}:{e.lineno}: {e.msg}')\nprint('\\n'.join(bad))")
    out = subprocess.run([py, "-c", code, *map(str, FILES)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0 and not out.stdout.strip(), out.stdout + out.stderr
