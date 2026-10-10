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
    async def settle(app, pilot):
        """Until the link preview has been placed — it is found and drawn in a worker."""
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()

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
            await pilot.press("tab")                   # A-01 links nowhere: the tree keeps the cursor
            self.assertEqual(app.focused.id, "nav")
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
            await pilot.press("tab")                   # first link, previewed and highlighted
            await self.settle(app, pilot)
            # Reading order: the statement, the source, then the chain.
            self.assertEqual(app.links, ["SR_001", "OQ-0102", "A-01", "SSR_APP_001"])
            self.assertTrue(app.query_one("#peek").display)
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

    def test_tab_preview_opens_where_a_hover_would(self):
        async def steps(app, pilot):
            app.action_goto("SR_002")
            await pilot.pause()
            for _ in range(3):                         # onto A-01, in the chain
                await pilot.press("tab")
                await self.settle(app, pilot)
            self.assertEqual(app.links[app.link_index], "A-01")
            by_key = tuple(app.query_one("#peek").styles.offset)
            x, y = app._locate("A-01")
            await pilot.press("escape")
            await pilot.hover(None, offset=(x, y))
            await pilot.pause()
            self.assertEqual(app.hovering, "A-01")
            self.assertEqual(tuple(app.query_one("#peek").styles.offset), by_key)
        self.run_app(steps)

    def test_preview_never_covers_its_link(self):
        from tool.viewer import ReqkitApp

        async def go():
            app = ReqkitApp()
            async with app.run_test(size=(120, 24)) as pilot:   # short, so some must flip above
                await pilot.pause()
                app.action_goto("SR_002")
                await pilot.pause()
                for _ in range(len(app._ensure_links())):
                    await pilot.press("tab")
                    await self.settle(app, pilot)
                    target = app.links[app.link_index]
                    cell = app._locate(target)
                    self.assertIsNotNone(cell, target)
                    peek = app.query_one("#peek").region
                    self.assertFalse(peek.contains(*cell), f"{target} at {cell} under {peek}")
        asyncio.run(go())

    def test_code_references_preview_and_open_in_the_editor(self):
        self.p.write("src/screen.h", "#pragma once\n// @REQ_REF(SSR_APP_001) shows it\nvoid show(void);\n")
        self.p.write("tests/screen_test.c", "// @REQ_REF(SSR_APP_001) shows it\nTEST(Screen, Shows) {}\n")
        (self.p.root / ".reqkit.toml").write_text(
            (self.p.root / ".reqkit.toml").read_text() + '\n[editor]\ncommand = "nvim +{line} {file}"\n')
        ran = []

        async def steps(app, pilot):
            import contextlib
            from unittest import mock
            app.action_goto("SSR_APP_001")
            await pilot.pause()
            await pilot.press("tab")
            await self.settle(app, pilot)
            # The source names OQ-0101; then the chain; then code and test.
            self.assertEqual(app.links, ["OQ-0101", "SR_002", "ref:src/screen.h:2",
                                         "ref:tests/screen_test.c:1"])
            await pilot.press("tab", "tab")
            await self.settle(app, pilot)
            peek = app.query_one("#peek")
            self.assertTrue(peek.display)
            self.assertIn("void show(void);", str(peek.content))
            refs = str(app.query(".chain").last().content)
            self.assertIn("void show(void);", refs)            # the origin, not the description
            self.assertNotIn("shows it", refs)
            self.assertIn("enter opens in nvim", str(peek.border_title))
            with mock.patch("tool.viewer.subprocess.run", side_effect=lambda argv, **kw: ran.append(argv)), \
                    mock.patch.object(type(app), "suspend", lambda self: contextlib.nullcontext()):
                await pilot.press("enter")
                await pilot.pause()
            self.assertEqual(ran, [["nvim", "+2", "src/screen.h"]])
            self.assertEqual(self.cursor(app), ("req", "SSR_APP_001"))   # still there after the reload
        self.run_app(steps)

    def test_escape_drops_the_link_then_the_search_and_enter_toggles(self):
        async def steps(app, pilot):
            app.action_goto("SR_002")
            await pilot.pause()
            view = app.query_one("#view")
            await pilot.press("tab")
            await self.settle(app, pilot)
            self.assertTrue(view.has_class("-linking"))
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(app.link_index, -1)
            self.assertFalse(view.has_class("-linking"))
            self.assertFalse(app.query_one("#peek").display)
            self.assertEqual(self.cursor(app), ("req", "SR_002"))
            await pilot.press("slash", *"Glow", "enter")
            await pilot.pause()
            self.assertEqual(app.query_text, "Glow")
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(app.query_text, "")
            tree = app.query_one("#nav")
            tree.cursor_line = 0                       # "Requirements", expanded
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertFalse(tree.cursor_node.is_expanded)
            self.assertEqual(app.focused.id, "nav")
        self.run_app(steps)

    def test_document_cursor_steps_through_cards(self):
        async def steps(app, pilot):
            app._move_to(("unit", "system"))
            await pilot.pause()
            await pilot.press("tab")
            await self.settle(app, pilot)
            self.assertTrue(app.query_one("#card-SR_001").has_class("-selected"))
            await pilot.press("tab")
            await self.settle(app, pilot)
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

    def test_every_bundled_theme_is_complete(self):
        from tool import themes
        palettes = themes.load_all()
        self.assertGreaterEqual(len(palettes), 19)
        for p in palettes.values():
            self.assertEqual(set(p.colors), set(themes.ROLES), p.name)
            self.assertIn("rk-border-active", p.theme().variables)

    def test_a_broken_user_theme_is_named(self):
        from tool import themes
        bad = Path(self.cfg.name, "reqkit", "themes")
        bad.mkdir(parents=True)
        (bad / "mine.toml").write_text('extends = "nord"\n[colors]\nforeground = "#ffffff"\n')
        with self.assertRaises(themes.ThemeError) as e:
            themes.load_all()
        self.assertIn("mine.toml: missing", str(e.exception))

    def test_theme_picker_previews_and_escape_reverts(self):
        async def steps(app, pilot):
            app.theme = "dracula"
            await pilot.press("t")
            await pilot.pause()
            await pilot.press("j")
            await pilot.pause()
            self.assertNotEqual(app.theme, "dracula")
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(app.theme, "dracula")
            await pilot.press("t")
            await pilot.pause()
            await pilot.press("j", "enter")
            await pilot.pause()
            self.assertNotEqual(app.theme, "dracula")
        self.run_app(steps)

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
