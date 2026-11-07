"""Vibe presets: one tap fills the agent's vibe, in onboarding and in Settings, and the field stays editable."""
from test_audit_ui import CORE, PARTS, SETUP, STYLE, fn, needs_node, run


@needs_node
def test_presets_fill_the_field_and_show_which_one_is_picked():
    js = "const VIBE_PRESETS = " + CORE.split("const VIBE_PRESETS = ", 1)[1].split("\n]\n", 1)[0] + "\n]\n" + fn(PARTS, "VibePresets") + """
const picked = []
const tree = VibePresets({ value: ' deadpan, quick, fond of understatement ', onPick: v => picked.push(v) })
const buttons = kids(tree)
buttons[0].props.onClick()
out({ n: buttons.length, labels: buttons.map(b => b.props.children), pressed: buttons.filter(b => b.props['aria-pressed']).map(b => b.props.children), picked })
"""
    res = run(js)
    assert res["n"] == 10 and res["labels"][0] == "Cozy"
    assert res["pressed"] == ["Dry wit"]
    assert res["picked"] == ["warm, curious, a little playful"]


def test_presets_sit_under_both_vibe_fields_and_stay_short():
    assert SETUP.count("jsx(VibePresets,") == 2
    presets = CORE.split("const VIBE_PRESETS = ", 1)[1].split("\n]\n", 1)[0]
    assert all(len(line) < 120 for line in presets.splitlines())
    assert ".h-vibes .h-chip:focus-visible" in STYLE
