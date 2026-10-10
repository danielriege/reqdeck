"""The TUI, driven headlessly through Textual's pilot. Skipped without textual."""

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import textual  # noqa: F401
except ModuleNotFoundError:
    textual = None

from test_reqkit import Project  # noqa: E402
from tool import ops  # noqa: E402


@unittest.skipIf(textual is None, "textual is not installed")
class TuiTest(unittest.TestCase):
    def setUp(self):
        self.p = Project()
        m = self.p.model()
        ops.add(m, "SR", {"title": "Glow", "statement": "The system shall glow, unlike SR_001.",
                          "satisfies": "A-01", "topic": "01", "source": "OQ-0102.", "verification": "T"})
        ops.add(self.p.model(), "SSR_APP", {"title": "Screen", "statement": "The app shall show it.",
                                            "satisfies": "SR_002", "source": "OQ-0101.", "verification": "T"})
        self.cfg = tempfile.TemporaryDirectory()
        self.env = {k: os.environ.get(k) for k in ("XDG_CONFIG_HOME",)}
        os.environ["XDG_CONFIG_HOME"] = self.cfg.name
        self.cwd = os.getcwd()
        os.chdir(self.p.root)

    def tearDown(self):
        os.chdir(self.cwd)
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.cfg.cleanup()
        self.p.close()

    def run_app(self, steps):
        from tool.viewer import ReqkitApp

        async def go():
            app = ReqkitApp()
            async with app.run_test(size=(160, 48)) as pilot:
                await pilot.pause()
                await steps(app, pilot)
        asyncio.run(go())

    @staticmethod
    def cursor(app):
        return app.query_one("#nav").cursor_node.data

    def test_vim_keys_walk_the_tree(self):
        async def steps(app, pilot):
            await pilot.press("j")                     # STORY level
            await pilot.press("l", "l")                # expand, into the unit
            await pilot.press("l", "l")                # expand the unit, onto its first story
            self.assertEqual(self.cursor(app), ("req", "A-01"))
            await pilot.press("h")                     # back to the unit
            self.assertEqual(self.cursor(app), ("unit", "stories"))
            tree = app.query_one("#nav")
            await pilot.press("G")
            self.assertEqual(tree.cursor_line, tree.last_line)
            await pilot.press("g", "g")
            self.assertEqual(tree.cursor_line, 0)
        self.run_app(steps)

    def test_follow_a_link_and_come_back(self):
        async def steps(app, pilot):
            app.action_goto("SR_002")
            await pilot.pause()
            self.assertEqual(self.cursor(app), ("req", "SR_002"))
            self.assertEqual(app.links, ["A-01", "SSR_APP_001", "SR_001", "OQ-0102"])
            app.query_one("#view").focus()
            await pilot.press("tab")                   # first link, previewed and highlighted
            await pilot.pause()
            self.assertTrue(app.query_one("#peek").display)
            await pilot.press("tab", "tab")            # SR_001, named in the statement
            await pilot.pause()
            self.assertEqual(app.links[app.link_index], "SR_001")
            await pilot.press("g", "d")
            await pilot.pause()
            self.assertEqual(self.cursor(app), ("req", "SR_001"))
            await pilot.press("ctrl+o")
            await pilot.pause()
            self.assertEqual(self.cursor(app), ("req", "SR_002"))
            await pilot.press("right_square_bracket")
            await pilot.pause()
            self.assertEqual(self.cursor(app), ("req", "SR_001"))
        self.run_app(steps)

    def test_link_to_a_question(self):
        async def steps(app, pilot):
            app.action_goto("SR_002")
            await pilot.pause()
            app.action_goto("OQ-0102")
            await pilot.pause()
            self.assertEqual(self.cursor(app), ("question", "OQ-0102"))
        self.run_app(steps)

    def test_hovering_a_link_previews_it(self):
        async def steps(app, pilot):
            app.action_goto("SR_002")
            await pilot.pause()
            peek = app.query_one("#peek")
            head = app.query_one(".chain")              # "Satisfies ↑" then "  A-01  …"
            await pilot.hover(head, offset=(3, 1))
            await pilot.pause()
            self.assertTrue(peek.display)
            self.assertEqual(app.hovering, "A-01")
            await pilot.hover(head, offset=(40, 0))
            await pilot.pause()
            self.assertFalse(peek.display)
        self.run_app(steps)

    def test_document_cursor_steps_through_cards(self):
        async def steps(app, pilot):
            app._move_to(("unit", "system"))
            await pilot.pause()
            app.query_one("#view").focus()
            await pilot.press("tab")
            await pilot.pause()
            self.assertTrue(app.query_one("#card-SR_001").has_class("-selected"))
            await pilot.press("tab")
            await pilot.pause()
            self.assertFalse(app.query_one("#card-SR_001").has_class("-selected"))
            self.assertTrue(app.query_one("#card-SR_002").has_class("-selected"))
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(self.cursor(app), ("req", "SR_002"))
        self.run_app(steps)

    def test_sidebar_resizes_and_theme_is_remembered(self):
        async def steps(app, pilot):
            left = app.query_one("#left")
            before = left.outer_size.width
            await pilot.press("greater_than_sign")
            await pilot.pause()
            self.assertEqual(left.outer_size.width, before + 4)
            app.set_sidebar(80)
            await pilot.pause()
            self.assertEqual(left.outer_size.width, 80)
            app.theme = "dracula"
            await pilot.pause()
        self.run_app(steps)
        import json
        prefs = json.loads(Path(self.cfg.name, "reqkit", "tui.json").read_text())
        self.assertEqual(prefs["theme"], "dracula")

        async def again(app, pilot):
            self.assertEqual(app.theme, "dracula")
        self.run_app(again)

    def test_accept_is_confirmed_and_written(self):
        async def steps(app, pilot):
            app.action_goto("SR_002")
            await pilot.pause()
            await pilot.press("a")
            await pilot.pause()
            await pilot.press("y")
            await pilot.pause()
        self.run_app(steps)
        self.assertEqual(self.p.model().reqs["SR_002"].status, "Accepted")


if __name__ == "__main__":
    unittest.main()
