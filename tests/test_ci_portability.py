"""Checks that keep the suite running the same on Linux CI as on a Mac."""
import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def test_node_scripts_go_through_stdin_not_the_command_line():
    """Linux caps one command-line argument at 128 KB (macOS allows far more), and the page tests hand Node whole UI
    bundles: `node -e <script>` fails there with "Argument list too long". Pass the script as input to `node -`."""
    bad = [f"{p.name}:{n}" for p in sorted(TESTS.glob("*.py")) if p.name != Path(__file__).name
           for n, line in enumerate(p.read_text().splitlines(), 1)
           if re.search(r"""(NODE|["']node["'])\s*,\s*["']-e["']""", line)]
    assert not bad, "node -e with an inline script: " + ", ".join(bad)
