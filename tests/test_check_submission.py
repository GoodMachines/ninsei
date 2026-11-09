"""The pre-PR check refuses a draft that Hermes's catalog validator would call OK."""
import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("check_submission", ROOT / "scripts/check_submission.py")
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)


def on_main() -> str:
    """A commit that is on origin/main and holds docs/media/banner.png."""
    return subprocess.run(["git", "-C", str(ROOT), "log", "-1", "--format=%H", "origin/main", "--",
                           "docs/media/banner.png"], capture_output=True, text=True).stdout.strip()


def entry(sha: str, pin: str = None) -> str:
    pin = pin or sha
    return (f'name: ninsei\nsha: "{sha}"\n'
            f"image: https://raw.githubusercontent.com/GoodMachines/ninsei/{pin}/docs/media/banner.png\n")


def pr(sha: str) -> str:
    return f"# Add Ninsei\n\n- Repo: https://github.com/GoodMachines/ninsei, pinned at `{sha}`\n"


def test_the_files_as_they_stand_are_ready_exactly_when_no_marker_is_left():
    # pinned on 2026-11-08; until the video link and the go, the draft markers keep them not ready
    y, pr_ = (ROOT / "submission/ninsei.yaml").read_text(), (ROOT / "submission/catalog-pr.md").read_text()
    found = cs.problems(y, pr_)
    if any(m in y + pr_ for m in cs.LEFTOVERS):
        assert found and all("still contains" in p for p in found), found   # only markers, the pin itself is fine
    else:
        assert found == []


def test_placeholders_are_each_caught():
    zeros = "0" * 40
    found = cs.problems(entry(zeros), pr(zeros))
    assert "sha is still the all-zeros placeholder" in found
    found = cs.problems(entry(zeros, pin="<sha>"), pr("<sha>"))
    assert any("still contains '<sha>'" in p for p in found)
    assert any("pinned to '<sha>'" in p for p in found)
    assert any("not 40" in p for p in cs.problems("sha: 0\n", pr("x")))


def test_a_pinned_entry_passes_and_a_missing_file_does_not():
    sha = on_main()
    assert len(sha) == 40, "origin/main has no banner commit to test against"
    assert cs.problems(entry(sha), pr(sha)) == []
    gone = entry(sha).replace("banner.png", "nope.png")
    assert any("does not exist" in p for p in cs.problems(gone, pr(sha)))
    other = "f" * 40
    assert any("not a commit" in p for p in cs.problems(entry(other), pr(other)))
    draft = "<!-- DRAFT PR description. NOT submitted. -->\n" + pr(sha)
    assert any("'DRAFT'" in p for p in cs.problems(entry(sha), draft))


def on_media() -> str:
    return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "origin/media"], capture_output=True, text=True).stdout.strip()


def test_screenshots_pin_to_the_media_branch_not_the_plugin_sha():
    sha, media = on_main(), on_media()
    assert len(media) == 40, "origin/media is missing; fetch it"
    shot = f"  - https://raw.githubusercontent.com/GoodMachines/ninsei/{media}/catalog/room.png\n"
    assert cs.problems(entry(sha) + shot, pr(sha)) == []
    assert any("does not exist" in p for p in cs.problems(entry(sha) + shot.replace("room.png", "nope.png"), pr(sha)))
    assert any("not on origin/media" in p for p in cs.problems(entry(sha) + shot.replace(media, sha), pr(sha)))
    assert any("not a full media commit" in p for p in cs.problems(entry(sha) + shot.replace(media, "media"), pr(sha)))
