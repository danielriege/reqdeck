"""reqkit's own tests. Standard library only: python3 -m unittest discover tests"""

import contextlib
import io
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tool import config, ops, store  # noqa: E402
from tool.cli import main  # noqa: E402
from tool.model import Model  # noqa: E402

CONFIG = """\
requirements = "reqs"
questions = "OPEN-QUESTIONS.md"

[[levels]]
kind = "STORY"
reviewed = false
traced = false
separator = "-"
digits = 2

[[levels]]
kind = "SR"
satisfies = ["STORY"]
topic = true
traced = false

[[levels]]
kind = "SSR"
satisfies = ["SR"]

[markers]
declaration_extensions = [".h", ".swift"]
interface_suffixes = ["_interface"]
"""

QUESTIONS = """\
# Open Questions

## Topic 01 — Scope

### OQ-0101 — Who is it for
**Question:** Who?
**Answer:** Collectors.
**Blocks:** —

### OQ-0102 — How many
**Question:** How many?
**Answer:**
**Blocks:** —
"""


class Project:
    """A throwaway project with one unit per level."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / ".reqkit.toml").write_text(CONFIG)
        (self.root / "OPEN-QUESTIONS.md").write_text(QUESTIONS)
        rd = self.root / "reqs"
        store.create_unit(rd, "stories", "STORY", ["A"], "Stories", False, store.STORY_COLUMNS)
        store.create_unit(rd, "system", "SR", ["SR"], "System", False, store.STANDARD)
        store.create_unit(rd, "app", "SSR", ["SSR_APP"], "App", True,
                          [c for c in store.STANDARD if c != "topic"])
        self.write("reqs/stories.csv", """\
            id,section,statement
            A-01,,"As a collector, I want lights."
            """)
        self.write("reqs/system.csv", """\
            id,section,title,statement,rationale,satisfies,topic,source,verification,status,security
            SR_001,,Lights,The system shall light.,,A-01,01,OQ-0101.,T,Accepted,
            """)

    def write(self, rel: str, text: str) -> None:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(text))

    def model(self) -> Model:
        return Model.load(config.load(self.root))

    def run(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                code = main(list(argv))
        finally:
            os.chdir(cwd)
        return code, out.getvalue()

    def close(self):
        self.tmp.cleanup()


class Base(unittest.TestCase):
    def setUp(self):
        self.p = Project()

    def tearDown(self):
        self.p.close()


class TestAdd(Base):
    def test_allocates_next_id_and_writes_proposed(self):
        m = self.p.model()
        rid, _, line = ops.add(m, "SSR_APP", {"title": "Screen", "statement": "The app shall show.",
                                              "satisfies": "SR_001", "source": "OQ-0101.",
                                              "verification": "t"})
        self.assertEqual(rid, "SSR_APP_001")
        self.assertEqual(line, 2)
        r = self.p.model().reqs[rid]
        self.assertEqual((r.status, r.verification), ("Proposed", "T"))
        rid2, _, _ = ops.add(self.p.model(), "SSR_APP", {"statement": "Again.", "satisfies": "SR_001",
                                                         "source": "x", "verification": "T"})
        self.assertEqual(rid2, "SSR_APP_002")

    def test_cannot_set_status(self):
        rid, _, _ = ops.add(self.p.model(), "SSR_APP", {"statement": "S.", "source": "x",
                                                        "verification": "T", "status": "Accepted"})
        self.assertEqual(self.p.model().reqs[rid].status, "Proposed")

    def test_story_ids_follow_the_level_format(self):
        rid, _, _ = ops.add(self.p.model(), "A", {"statement": "As a builder, I want more."})
        self.assertEqual(rid, "A-02")

    def test_refuses_unknown_prefix_and_wrong_level_link(self):
        with self.assertRaises(ops.OpError):
            ops.add(self.p.model(), "SSR_NEW", {"statement": "S.", "source": "x", "verification": "T"})
        with self.assertRaises(ops.OpError):
            ops.add(self.p.model(), "SSR_APP", {"statement": "S.", "source": "x", "verification": "T",
                                                "satisfies": "A-01"})

    def test_topic_required_where_the_level_says(self):
        with self.assertRaises(ops.OpError):
            ops.add(self.p.model(), "SR", {"statement": "S.", "source": "x", "verification": "T"})


class TestEdit(Base):
    def test_editing_accepted_reopens_it(self):
        changed, reopened = ops.edit(self.p.model(), "SR_001", {"statement": "The system shall glow."})
        self.assertEqual((changed, reopened), (["statement"], True))
        self.assertEqual(self.p.model().reqs["SR_001"].status, "Reopened")

    def test_status_is_not_editable(self):
        with self.assertRaises(ops.OpError):
            ops.edit(self.p.model(), "SR_001", {"status": "Proposed"})


class TestCheck(Base):
    def problems(self):
        return self.p.model().problems()

    def test_clean_project_passes(self):
        self.assertEqual(self.problems(), [])
        self.assertEqual(self.p.run("check")[0], 0)

    def test_duplicate_id_and_bad_prefix(self):
        self.p.write("reqs/app.csv", """\
            id,section,title,statement,rationale,satisfies,source,verification,status,security
            SR_001,,Dup,The app shall.,,SR_001,x,T,Proposed,
            SSR_APP_01,,Short,The app shall.,,SR_001,x,T,Proposed,
            """)
        ps = "\n".join(self.problems())
        self.assertIn("duplicate id SR_001", ps)
        self.assertIn("SSR_APP_01: expected SSR_APP_ and 3 digits", ps)

    def test_wrong_level_link_and_undeclared_section(self):
        self.p.write("reqs/app.csv", """\
            id,section,title,statement,rationale,satisfies,source,verification,status,security
            SSR_APP_001,nowhere,Skip,The app shall.,,A-01,x,T,Proposed,
            """)
        ps = "\n".join(self.problems())
        self.assertIn("satisfies A-01, a STORY; a SSR satisfies SR", ps)
        self.assertIn("section 'nowhere' is not declared", ps)

    def test_non_canonical_csv(self):
        path = self.p.root / "reqs/system.csv"
        path.write_text(path.read_text().replace("The system shall light.", '"The system shall light."'))
        self.assertTrue(any("canonical" in p for p in self.problems()))
        self.p.run("fmt")
        self.assertEqual(self.problems(), [])

    def test_detail_for_a_requirement_elsewhere(self):
        self.p.write("reqs/app.details.md", "## SR_001\n\nA table.\n")
        self.assertTrue(any("detail for SR_001" in p for p in self.problems()))

    def test_marker_rules(self):
        ops.add(self.p.model(), "SSR_APP", {"statement": "S.", "satisfies": "SR_001", "source": "x",
                                            "verification": "T"})
        self.p.write("src/screen.h", "// @REQ_REF(SSR_APP_001) shows the screen\n")
        self.p.write("src/screen.c", "// @REQ_REF(SSR_APP_001) restated\n")
        self.p.write("src/screen_interface.h", "// @REQ_REF(SSR_APP_001) declared\n")
        self.p.write("src/two.h", "// @REQ_REF(SSR_APP_001, SR_001) both\n")
        self.p.write("src/bare.h", "// @REQ_REF(SSR_APP_001)\n")
        self.p.write("src/top.h", "// @REQ_REF(SR_001) the system level\n")
        self.p.write("src/doc.h", "// a marker reads @REQ_REF(<ID>) description\n")
        ps = "\n".join(self.problems())
        self.assertIn("screen.c:1: @REQ_REF(SSR_APP_001) is in an implementation file", ps)
        self.assertIn("screen_interface.h:1: @REQ_REF(SSR_APP_001) is on an interface", ps)
        self.assertIn("two.h:1: @REQ_REF names 2 requirements", ps)
        self.assertIn("bare.h:1: @REQ_REF(SSR_APP_001) has no description", ps)
        self.assertIn("top.h:1: @REQ_REF(SR_001) names a SR", ps)
        self.assertNotIn("doc.h", ps)
        self.assertNotIn("screen.h:", ps)


class TestTrace(Base):
    def setUp(self):
        super().setUp()
        ops.add(self.p.model(), "SSR_APP", {"statement": "S.", "satisfies": "SR_001", "source": "x",
                                            "verification": "T"})

    def test_untraced_until_code_and_test_name_it(self):
        self.assertEqual(self.p.run("trace", "SSR_APP_001")[0], 1)
        self.p.write("src/screen.swift", "// @REQ_REF(SSR_APP_001) shows the screen\n")
        self.p.write("tests/screen_test.swift", "// @REQ_REF(SSR_APP_001) shows the screen\n")
        self.assertEqual(self.p.run("trace", "SSR_APP_001")[0], 0)

    def test_a_test_below_covers_the_level_above(self):
        self.p.write("tests/screen_test.swift", "// @REQ_REF(SSR_APP_001) shows the screen\n")
        m = self.p.model()
        self.assertEqual([r.id for r in m.covering_refs("SR_001")], ["SSR_APP_001"])
        self.assertNotIn("SR_001", m.gaps()["untested"])


class TestDocument(Base):
    def test_sections_are_numbered_by_declaration_order(self):
        toml = self.p.root / "reqs/system.toml"
        toml.write_text(toml.read_text() + textwrap.dedent("""
            [[sections]]
            key = "power"
            title = "Power"

            [[sections]]
            key = "power.bus"
            title = "Bus supply"

            [[sections]]
            key = "light"
            title = "Light"
            """))
        ops.edit(self.p.model(), "SR_001", {"section": "power.bus"})
        m = self.p.model()
        doc = m.document(m.unit("system"))
        self.assertEqual([(e.get("number"), e["type"]) for e in doc],
                         [("1", "section"), ("1.1", "section"), (None, "req"), ("2", "section")])
        self.assertEqual(doc[2]["req"].id, "SR_001")


class TestEditor(unittest.TestCase):
    def setUp(self):
        self.env = {k: os.environ.pop(k, None) for k in ("VISUAL", "EDITOR")}

    def tearDown(self):
        for k, v in self.env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)

    def test_presets_from_the_environment(self):
        from tool.config import Editor
        from tool.editor import command
        os.environ["EDITOR"] = "nvim"
        self.assertEqual(command(Editor(), "a b.h", 7), (["nvim", "+7", "a b.h"], True))
        os.environ["VISUAL"] = "code"
        self.assertEqual(command(Editor(), "x.swift", 3), (["code", "--goto", "x.swift:3"], False))
        os.environ["VISUAL"] = "/opt/bin/nvim -u NONE"
        self.assertEqual(command(Editor(), "x.h", 3)[0], ["/opt/bin/nvim", "-u", "NONE", "+3", "x.h"])

    def test_the_project_command_wins(self):
        from tool.config import Editor
        from tool.editor import command
        os.environ["EDITOR"] = "nvim"
        self.assertEqual(command(Editor(command="zed {file}:{line}"), "x.c", 9), (["zed", "x.c:9"], False))
        self.assertEqual(command(Editor(command="myed {file}", suspend=True), "x.c", 9), (["myed", "x.c"], True))

    def test_editor_table_is_read_from_the_config(self):
        p = Project()
        try:
            (p.root / ".reqkit.toml").write_text(CONFIG + '\n[editor]\ncommand = "code --goto {file}:{line}"\n')
            self.assertEqual(config.load(p.root).editor.command, "code --goto {file}:{line}")
            (p.root / ".reqkit.toml").write_text(CONFIG + '\n[editor]\ncmd = "x"\n')
            with self.assertRaises(config.ConfigError):
                config.load(p.root)
        finally:
            p.close()


class TestOrigin(Base):
    def test_what_a_marker_is_attached_to(self):
        from tool.render import origin
        self.p.write("src/pwm.h", "/**\n * @file pwm.h\n * @REQ_REF(SSR_APP_001) x\n */\n#pragma once\n")
        self.p.write("src/A.swift", "/// Keeps them.\n///\n/// @REQ_REF(SSR_APP_001) x\nfinal class A {\n}\n")
        self.p.write("test/t.cpp", "/**\n * @test It works.\n *\n * @REQ_REF(SSR_APP_001) x\n */\n"
                                   "TEST_F(PwmTest, Works)\n{\n}\n")
        self.assertEqual(origin(self.p.root, "src/pwm.h", 3), "file header")
        self.assertEqual(origin(self.p.root, "src/A.swift", 3), "final class A")
        self.assertEqual(origin(self.p.root, "test/t.cpp", 4), "TEST_F(PwmTest, Works)")


class TestQuestions(Base):
    def test_open_and_answered(self):
        m = self.p.model()
        self.assertEqual(m.topics, {"01": "Scope"})
        self.assertEqual([(q.id, q.open) for q in m.questions], [("OQ-0101", False), ("OQ-0102", True)])


if __name__ == "__main__":
    unittest.main()
