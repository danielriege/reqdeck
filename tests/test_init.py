"""`reqdeck init`, driven with scripted answers.

Each test builds a throwaway project and feeds `python -m reqdeck init` one
answer per line, as a person at the terminal would.
"""

import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent

# Shape 1 with a Node firmware, a Node hardware and a bus interface unit.
SHAPE_1 = [
    "1", "", "", "A B",          # shape, folder, questions file, personas
    "", "", "",                  # TSR, TSSR, ICD
    "y", "y",                    # split testing, headers
    "FWN", "firmware-node", "Node firmware", "y",
    "HWN", "hardware-node", "Node hardware", "n",
    "",                          # no more sub-system units
    "BUS", "icd-bus", "Bus interface", "y",
    "",                          # no more interface units
    "y", "y",                    # copy skills for Claude and Codex
    "y",                         # confirm
]

SHAPE_3 = ["3", "", "", "", "", "n", "n", "y", "y", "y", "y"]

ENV = {**{k: v for k, v in os.environ.items() if k != "REQDECK_ROOT"},
       "PYTHONPATH": str(KIT)}


def snapshot(root: Path) -> dict[str, str]:
    out = {}
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        if p.is_symlink():
            out[rel] = "-> " + os.readlink(p)
        elif p.is_file():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
        else:
            out[rel] = "dir"
    return out


class InitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "my project"   # a space, on purpose
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def init(self, answers: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "reqdeck", "init"],
                              input="\n".join(answers) + "\n", cwd=self.root,
                              capture_output=True, text=True, env=ENV, timeout=60)

    def req(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "reqdeck", *args], cwd=self.root,
                              capture_output=True, text=True, env=ENV)

    def assertNothingWritten(self, before: dict | None = None):
        self.assertEqual(snapshot(self.root), before or {})

    # ------------------------------------------------------------ happy paths

    def test_fresh_project_shape_1(self):
        r = self.init(SHAPE_1)
        self.assertEqual(r.returncode, 0, r.stderr)
        rd = self.root / "docs/requirements"
        for stem in ("stories", "system", "firmware-node", "hardware-node", "icd-bus"):
            self.assertTrue((rd / f"{stem}.csv").exists(), stem)
            self.assertTrue((rd / f"{stem}.toml").exists(), stem)
        self.assertIn('prefixes = ["A", "B"]', (rd / "stories.toml").read_text())
        self.assertIn("code = true", (rd / "firmware-node.toml").read_text())
        self.assertNotIn("code = true", (rd / "hardware-node.toml").read_text())
        self.assertIn("[verification.S]", (self.root / ".reqdeck.toml").read_text())
        self.assertTrue((self.root / "docs/OPEN-QUESTIONS.md").exists())
        for d in (".claude/skills", ".agents/skills"):
            skill = self.root / d / "reqdeck-cli"
            self.assertTrue((skill / "SKILL.md").is_file() and not skill.is_symlink())   # a copy
        self.assertEqual(self.req("check").returncode, 0)
        self.assertIn("TSSR_FWN", self.req("levels").stdout)

    def test_fresh_project_shape_3(self):
        r = self.init(SHAPE_3)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.root / "docs/requirements/requirements.csv").exists())
        self.assertIn("[verification.T]", (self.root / ".reqdeck.toml").read_text())
        self.assertEqual(self.req("add", "REQ", "--statement", "The app shall start.", "--topic", "01",
                                  "--source", "OQ-0101.", "--verification", "T").returncode, 0)
        self.assertEqual(self.req("check").returncode, 0)

    # ------------------------------------------------------------ re-runs and existing files

    def test_second_run_changes_nothing(self):
        self.assertEqual(self.init(SHAPE_1).returncode, 0)
        before = snapshot(self.root)
        r = self.init(SHAPE_1)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already exists", r.stderr)
        self.assertIn("reqdeck unit", r.stderr)
        self.assertNothingWritten(before)

    def test_existing_requirement_file_stops_before_writing(self):
        existing = self.root / "docs/requirements/system.csv"
        existing.parent.mkdir(parents=True)
        existing.write_text("not ours\n")
        before = snapshot(self.root)
        r = self.init(SHAPE_1)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("docs/requirements/system.csv", r.stderr)
        self.assertNothingWritten(before)

    def test_existing_open_questions_is_kept(self):
        q = self.root / "docs/OPEN-QUESTIONS.md"
        q.parent.mkdir(parents=True)
        q.write_text("# Open Questions\n\n## Topic 01 — Ours\n")
        r = self.init(SHAPE_1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(q.read_text(), "# Open Questions\n\n## Topic 01 — Ours\n")
        self.assertNotIn("warning", r.stderr)

    def test_existing_open_questions_in_another_format_warns(self):
        q = self.root / "docs/OPEN-QUESTIONS.md"
        q.parent.mkdir(parents=True)
        q.write_text("# Questions\n\n- what about power?\n")
        r = self.init(SHAPE_1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no\n  '## Topic NN — Title' heading", r.stderr)
        self.assertEqual(q.read_text(), "# Questions\n\n- what about power?\n")

    def test_existing_skill_folder_is_left_alone(self):
        mine = self.root / ".claude/skills/reqdeck-cli"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("mine")
        r = self.init(SHAPE_1)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((mine / "SKILL.md").read_text(), "mine")
        self.assertTrue((self.root / ".claude/skills/reqdeck-method/SKILL.md").is_file())
        self.assertIn("kept the existing .claude/skills/reqdeck-cli", r.stdout)

    # ------------------------------------------------------------ bad input

    def test_invalid_answers_are_asked_again(self):
        answers = ["4", "1", "/abs", "", "", "a", "A B", "", "", "", "y", "y",
                   "F W N", "FWN", "firmware-node", "Node firmware", "y",
                   "FWN",                                 # duplicate code
                   "APP", "firmware-node", "app", "App", "y",  # taken file name
                   "", "", "y", "y", "y"]
        r = self.init(answers)
        self.assertEqual(r.returncode, 0, r.stderr)
        for hint in ("pick 1, 2 or 3", "a relative path", "single capital letters",
                     "letters and digits", "TSSR_FWN is already a unit", "firmware-node is already taken"):
            self.assertIn(hint, r.stderr)
        self.assertTrue((self.root / "docs/requirements/app.csv").exists())

    def test_prefix_clashing_with_a_level_is_asked_again(self):
        answers = ["1", "", "", "A", "", "TSR", "TSSR", "TSR", "ICD"] + SHAPE_1[7:]
        r = self.init(answers)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("must differ from TSR", r.stderr)

    def test_input_ending_early_writes_nothing(self):
        r = self.init(SHAPE_1[:10])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("nothing written", r.stderr)
        self.assertNothingWritten()

    def test_declining_the_summary_writes_nothing(self):
        r = self.init(SHAPE_1[:-1] + ["n"])
        self.assertNotEqual(r.returncode, 0)
        self.assertNothingWritten()

    def test_skills_update_replaces_only_reqdecks_own_copies(self):
        self.assertEqual(self.init(SHAPE_1).returncode, 0)
        ours = self.root / ".claude/skills/reqdeck-cli/SKILL.md"
        ours.write_text(ours.read_text() + "\nstale\n")
        theirs = self.root / ".agents/skills/reqdeck-method"
        for f in theirs.rglob("*"):
            if f.is_file():
                f.unlink()
        (theirs / "SKILL.md").write_text("name: something-else\n")
        r = self.req("skills")
        self.assertIn("kept", r.stdout)
        self.assertIn("stale", ours.read_text())                   # without --update, nothing replaced
        self.req("skills", "--update")
        self.assertNotIn("stale", ours.read_text())                # reqdeck's own copy, refreshed
        self.assertEqual((theirs / "SKILL.md").read_text(), "name: something-else\n")   # not ours

    # ------------------------------------------------------------ failure while writing

    def test_failure_while_writing_rolls_back(self):
        # A read-only requirements folder makes the first unit fail to write.
        rd = self.root / "docs/requirements"
        rd.mkdir(parents=True)
        rd.chmod(0o555)
        try:
            before = snapshot(self.root)
            r = self.init(SHAPE_1)
        finally:
            rd.chmod(0o755)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("removing what this run created", r.stderr)
        self.assertNothingWritten(before)


if __name__ == "__main__":
    unittest.main()
