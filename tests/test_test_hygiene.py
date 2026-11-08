"""Keeps flaky waits out of the suite.

A test that sleeps a fixed time and then asserts a count or a state passes on an idle machine and fails on a
busy one (2026-11-06: four such failures at load 11 to 20). Wait for the condition instead: `wait_for`,
`until`, `quiet` (an engine has no reaction in flight) or `settle` (a bare engine's tasks have all finished).
A fixed wait that is genuinely about the clock, such as getting a later created_at second, says why on the
same line with `# fixed-wait-ok: <reason>`."""
import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent

FIXED_WAIT = re.compile(r"\b(?:asyncio|aio)\.sleep\(\s*(?:0*[1-9][\d.]*|0?\.\d*[1-9]\d*)\s*\)"
                        r"|\btime\.sleep\("
                        r"|\bsettle\([^)]*,\s*[\d.]+\s*\)")  # the old settle(e, secs) was a fixed sleep too
CONDITION_WAIT = re.compile(r"\b(?:wait_for|until|quiet|settle|req)\(")
ALLOW = "# fixed-wait-ok:"
LOOKAHEAD = 4  # code lines after the wait


def fixed_waits_before_asserts(source: str) -> list[tuple[int, str]]:
    """(line number, line) for each fixed wait followed by an assert before any condition wait."""
    lines = source.splitlines()
    found = []
    for i, line in enumerate(lines):
        if not FIXED_WAIT.search(line) or ALLOW in line:
            continue
        seen = 0
        for nxt in lines[i + 1:]:
            code = nxt.strip()
            if not code or code.startswith("#"):
                continue
            if re.match(r"(async\s+)?def\s", code) or CONDITION_WAIT.search(code):
                break
            if code.startswith("assert"):
                found.append((i + 1, line.strip()))
                break
            seen += 1
            if seen >= LOOKAHEAD:
                break
    return found


def test_no_test_asserts_right_after_a_fixed_sleep():
    offenders = [f"{f.name}:{n}: {line}" for f in sorted(TESTS.glob("*.py")) if f.name != Path(__file__).name
                 for n, line in fixed_waits_before_asserts(f.read_text())]
    assert not offenders, ("a fixed sleep followed by an assert races a loaded machine; wait for the condition "
                           f"(wait_for/until/quiet/settle) or mark the line '{ALLOW} <reason>':\n" + "\n".join(offenders))


def test_the_scan_catches_the_patterns_that_flaked():
    # test_hostile.py::test_one_stranger_can_trigger_only_a_few_replies, before the fix
    old = '''
    for i in range(2):
        await e._on_event(own_person_event(e, {"t": "msg", "text": "hi"}), "relay")
        await settle(e, 0.1)
    assert llm.calls.count("ninsei.reply") == STRANGER_REPLIES + 2
'''
    assert [n for n, _ in fixed_waits_before_asserts(old)] == [4]
    # test_engine.py::test_open_question_from_owner_one_agent_answers, before the fix
    old = '''
    await asyncio.sleep(0.5)
    # Only Maya's own agent treats an open question from its owner as a cue
    assert llms["Maya"].calls.count("ninsei.reply") == 1
'''
    assert [n for n, _ in fixed_waits_before_asserts(old)] == [2]
    ok = '''
    await asyncio.sleep(0.1)
    assert await wait_for(lambda: done)
    await asyncio.sleep(0)
    assert x
    await asyncio.sleep(1.05)  # fixed-wait-ok: a later created_at second
    assert g["gid"] == "real"
'''
    assert fixed_waits_before_asserts(ok) == []


# A websockets or asyncio test server's close() only schedules the shutdown. A test that returns without
# awaiting wait_closed() leaves the server's tasks for the garbage collector, which prints "Task was destroyed
# but it is pending" or an unraisable-exception warning after the loop has closed (2026-11-08, twice).
SERVER_BIND = re.compile(r"^\s*(\w+)(?:\s*,\s*\w+)?\s*=\s*await\s+(?:serve|_server|relay_holding|"
                         r"asyncio\.start_server)\(")
CLOSE_WINDOW = 4  # code lines after close() that may hold the wait


def unawaited_server_closes(source: str) -> list[tuple[int, str]]:
    """(line number, line) for each close() of a test server with no wait_closed() on it soon after."""
    lines = source.splitlines()
    names = {m.group(1) for line in lines if (m := SERVER_BIND.match(line))}
    names |= {"self._server"} if "self._server = await serve(" in source else set()
    found = []
    for i, line in enumerate(lines):
        code = line.strip()
        for name in names:
            if code != f"{name}.close()":
                continue
            after = [n.strip() for n in lines[i + 1:] if n.strip() and not n.strip().startswith("#")]
            if not any(f"{name}.wait_closed()" in n for n in after[:CLOSE_WINDOW]):
                found.append((i + 1, code))
    return found


def test_every_test_server_is_awaited_after_close():
    offenders = [f"{f.name}:{n}: {line}" for f in sorted(TESTS.glob("*.py")) if f.name != Path(__file__).name
                 for n, line in unawaited_server_closes(f.read_text())]
    assert not offenders, ("await the server's wait_closed() right after close(), or its tasks outlive the "
                           "event loop:\n" + "\n".join(offenders))


def test_the_server_scan_catches_a_close_with_no_wait():
    old = '''
    srv, url = await _server(handler)
    try:
        pass
    finally:
        await pool.stop()
        srv.close()
'''
    assert [n for n, _ in unawaited_server_closes(old)] == [7]
    ok = old + "        await asyncio.wait_for(srv.wait_closed(), 5)\n"
    assert unawaited_server_closes(ok) == []
    pair = '''
    sa, ua = await _server(a)
    sb, ub = await _server(b)
    sa.close()
    await asyncio.wait_for(sa.wait_closed(), 5)
    sb.close()
'''
    assert [n for n, _ in unawaited_server_closes(pair)] == [6]
