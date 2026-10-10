"""The reqkit TUI: requirements as documents, with their sections, and the open
questions beside them. Reads through the same model as the CLI and writes
through the same operations.

Needs `textual`, which the CLI does not. The chosen theme and sidebar width
are remembered per user in `$XDG_CONFIG_HOME/reqkit/tui.json`.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from rich.text import Text
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Footer, Header, Input, Label, Markdown, Static, Tree
from textual.widgets.tree import TreeNode

from . import ops, render, themes
from .cli import load_model
from .model import Model, Req

ID_RE = re.compile(r"\b(?:OQ-\d{4}|[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*[_-]\d+)\b")
TARGET_RE = re.compile(r"(?:goto|link)\('(?:reqkit:)?([^']+)'\)")

STATUS_MARK = {"Accepted": ("A", "success"), "Proposed": ("P", "warning"), "Reopened": ("R", "error")}

HELP = """\
# Keys

| | |
|---|---|
| `j` `k` | Down, up — in the tree or the reading pane |
| `h` `l` | Collapse or go to parent, expand or go in; `l` on a requirement moves to the reading pane, `h` there moves back |
| `gg` `G` | First, last |
| `ctrl+d` `ctrl+u` | Half a page down, up |
| `n` `N` | Next, previous requirement or question in the tree |
| `tab` `shift+tab` | In the tree: move to the reading pane. In the reading pane: next, previous link, previewed |
| `enter` `gd` | Follow the selected link — the tree moves there too |
| `K` | Preview the selected link again; `escape` closes the preview |
| `ctrl+o` `[` | Back to where you jumped from |
| `]` | Forward again |
| `/` | Search — a regex over id, title, statement, detail. `enter` returns to the tree, `escape` clears |
| `o` | Only open questions |
| `a` | Accept the highlighted requirement |
| `<` `>` | Narrow or widen the sidebar — or drag the divider |
| `t` | Theme |
| `r` | Reload from disk |
| `q` | Quit |

Every requirement and question ID in the reading pane is a link — in the fields, the
statement, the detail tables. Hover one for a preview, click it to go there.
"""


# --------------------------------------------------------------------- prefs

def _prefs_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "reqkit" / "tui.json"


def load_prefs() -> dict:
    try:
        return json.loads(_prefs_path().read_text())
    except (OSError, ValueError):
        return {}


def save_prefs(prefs: dict) -> None:
    try:
        p = _prefs_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(prefs, indent=2))
    except OSError:
        pass


# ------------------------------------------------------------------- widgets

class GPrefix:
    """`gg` as two presses of `g` within a second."""

    def __init__(self):
        self._last = 0.0

    def second(self) -> bool:
        now = time.monotonic()
        hit = now - self._last < 1.0
        self._last = 0.0 if hit else now
        return hit

    def pending(self) -> bool:
        """A `g` pressed within the last second, consumed."""
        hit = time.monotonic() - self._last < 1.0
        self._last = 0.0
        return hit


class VimTree(Tree):
    BINDINGS = [
        Binding("j", "cursor_down", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("h", "vim_left", show=False),
        Binding("l", "vim_right", show=False),
        Binding("G", "last", show=False),
        Binding("g", "g", show=False),
        Binding("ctrl+d", "half(1)", show=False),
        Binding("ctrl+u", "half(-1)", show=False),
    ]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._g = GPrefix()

    def action_vim_left(self) -> None:
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
        elif node.parent is not None and node.parent is not self.root:
            self.action_cursor_parent()

    def action_vim_right(self) -> None:
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand and not node.is_expanded:
            node.expand()
        elif node.children:
            self.action_cursor_down()      # an expanded node's first child is the next line
        else:
            self.app.query_one("#view").focus()

    def action_last(self) -> None:
        self.cursor_line = self.last_line

    def action_g(self) -> None:
        if self._g.second():
            self.cursor_line = 0

    def action_half(self, direction: int) -> None:
        self.cursor_line = max(0, min(self.last_line, self.cursor_line + direction * max(1, self.size.height // 2)))


class VimScroll(VerticalScroll):
    BINDINGS = [
        Binding("j", "scroll_down", show=False),
        Binding("k", "scroll_up", show=False),
        Binding("h", "back", show=False),
        Binding("escape", "escape", show=False),
        Binding("tab", "app.cycle_link(1)", show=False),
        Binding("shift+tab", "app.cycle_link(-1)", show=False),
        Binding("enter", "app.follow_link", show=False),
        Binding("d", "d", show=False),
        Binding("K", "app.peek_link", show=False),
        Binding("G", "scroll_end", show=False),
        Binding("g", "g", show=False),
        Binding("ctrl+d", "half(1)", show=False),
        Binding("ctrl+u", "half(-1)", show=False),
    ]

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._g = GPrefix()

    def action_back(self) -> None:
        self.app.hide_peek()
        self.app.query_one("#nav").focus()

    def action_escape(self) -> None:
        if not self.app.hide_peek():
            self.action_back()

    def action_g(self) -> None:
        if self._g.second():
            self.scroll_home(animate=False)

    def action_d(self) -> None:
        """`gd` follows the selected link, as go-to-definition does in nvim."""
        if self._g.pending():
            self.app.action_follow_link()

    def action_half(self, direction: int) -> None:
        self.scroll_relative(y=direction * max(1, self.size.height // 2), animate=False)


class Divider(Widget):
    """The bar between sidebar and reading pane. Drag it to resize."""

    DEFAULT_CSS = """
    Divider { width: 1; height: 1fr; background: $panel; }
    Divider:hover, Divider.-dragging { background: $accent; }
    """

    def render(self) -> str:
        return ""

    def on_mouse_down(self, event: events.MouseDown) -> None:
        self.capture_mouse()
        self.add_class("-dragging")
        event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.has_class("-dragging"):
            self.app.set_sidebar(event.screen_x)

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self.has_class("-dragging"):
            self.release_mouse()
            self.remove_class("-dragging")
            self.app.remember()


class Confirm(ModalScreen[bool]):
    DEFAULT_CSS = """
    Confirm { align: center middle; }
    Confirm > Vertical { width: 72; height: auto; padding: 1 2; border: thick $accent; background: $surface; }
    Confirm Horizontal { height: auto; margin-top: 1; }
    Confirm Button { margin-right: 2; }
    """
    BINDINGS = [Binding("escape,n", "dismiss(False)", "Cancel"), Binding("y", "dismiss(True)", "Yes")]

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.message)
            with Horizontal():
                yield Button("Accept  y", variant="success", id="yes")
                yield Button("Cancel  n", id="no")

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


# --------------------------------------------------------------------- cards

def _status_chip(status: str) -> Content:
    _, colour = STATUS_MARK.get(status, ("?", "secondary"))
    return Content.assemble((f" {status} ", f"bold $background on ${colour}"))


def _link(rid: str, sel: str = "") -> tuple[str, str]:
    """A clickable ID; the one under the keyboard link cursor is drawn reversed."""
    style = "bold reverse $accent" if rid == sel else "bold $primary underline"
    return rid, f"{style} @click=app.goto('{rid}')"


def _field(label: str, *value) -> Horizontal:
    """A label and its value side by side, the value wrapping under itself."""
    return Horizontal(Static(label, classes="flabel"), Static(Content.assemble(*value), classes="fvalue"),
                      classes="frow")


INLINE = re.compile(r"\*\*(.+?)\*\*|(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|`([^`]+)`")


def _inline(text: str, style: str) -> list[tuple[str, str]]:
    """Inline markdown — bold, italic, code — as styled segments."""
    out, pos = [], 0
    for mm in INLINE.finditer(text):
        if mm.start() > pos:
            out.append((text[pos:mm.start()], style))
        bold, italic, code = mm.groups()
        if bold is not None:
            out.append((bold, f"{style} bold".strip()))
        elif italic is not None:
            out.append((italic, f"{style} italic".strip()))
        else:
            out.append((code, f"{style} $accent".strip()))
        pos = mm.end()
    if pos < len(text):
        out.append((text[pos:], style))
    return out


def linked(m: Model, text: str, style: str = "", sel: str = "") -> list:
    """`text` as Content parts: inline markdown rendered, every known ID a link."""
    parts: list = []
    for seg, st in _inline(text, style):
        pos = 0
        for mm in ID_RE.finditer(seg):
            if not m.knows(mm.group(0)):
                continue
            if mm.start() > pos:
                parts.append((seg[pos:mm.start()], st))
            parts.append(_link(mm.group(0), sel))
            pos = mm.end()
        if pos < len(seg):
            parts.append((seg[pos:], st))
    return parts


def linked_md(m: Model, text: str, sel: str = "") -> str:
    """Markdown with every known ID outside code spans turned into a link."""
    def link(mm: re.Match) -> str:
        rid = mm.group(0)
        if not m.knows(rid):
            return rid
        return f"[**▸ {rid}**](reqkit:{rid})" if rid == sel else f"[{rid}](reqkit:{rid})"

    out = []
    for i, chunk in enumerate(text.split("`")):
        if i % 2 == 0:
            chunk = ID_RE.sub(link, chunk)
        out.append(chunk)
    return "`".join(out)


def md(text: str, classes: str) -> Markdown:
    return Markdown(text, classes=classes, open_links=False)


def requirement_card(m: Model, r: Req, full: bool, sel: str = "") -> Vertical:
    """One requirement, formatted. `full` adds the chain and references."""
    parts: list[Widget] = []
    head = [_link(r.id) if not full else (r.id, "bold $primary")]
    if r.title:
        head += ["  ", (r.title, "bold")]
    if m.reviewed(r) and r.status:
        head += ["  ", _status_chip(r.status)]
    if r.security:
        head += ["  ", (" security ", "bold $background on $accent")]
    parts.append(Static(Content.assemble(*head), classes="card-head"))
    parts.append(md(linked_md(m, r.statement, sel), "statement"))
    if r.detail:
        parts.append(md(linked_md(m, r.detail, sel), "detail"))

    rows: list[Widget] = []
    if r.rationale:
        rows.append(_field("Rationale", *linked(m, r.rationale, "$text-muted italic", sel)))
    if r.satisfies and not full:
        links: list = []
        for i, t in enumerate(r.satisfies):
            links += ([", "] if i else []) + [_link(t, sel)]
        rows.append(_field("Satisfies", *links))
    if r.topics:
        rows.append(_field("Topic", ", ".join(f"{t} · {m.topics.get(t, '?')}" for t in r.topics)))
    if r.source:
        rows.append(_field("Source", *linked(m, r.source, sel=sel)))
    if r.verification:
        v = m.cfg.verification.get(r.verification)
        rows.append(_field("Verification", (r.verification, "bold $secondary"),
                           f" — {v.name}" if v else ""))
    if r.section and full:
        u = m.unit(r.unit)
        s = u.section(r.section) if u else None
        if s:
            rows.append(_field("Section", f"{u.numbering()[s.key]} {s.title}"))
    for k, v in r.extra.items():
        rows.append(_field(k.capitalize(), *linked(m, v, sel=sel)))
    if rows:
        parts.append(Vertical(*rows, classes="fields"))

    if full:
        def chain(title: str, ids: list[str], empty: str) -> Static:
            lines = [Content.assemble((title, "bold $accent"))]
            for t in ids:
                label = m.reqs[t].label if t in m.reqs else "(undefined)"
                lines.append(Content.assemble("  ", _link(t, sel), "  ", (label, "$text-muted")))
            if not ids:
                lines.append(Content.assemble(("  " + empty, "$text-muted italic")))
            return Static(Content("\n").join(lines), classes="chain")

        parts.append(chain("Satisfies ↑", r.satisfies, "nothing — top level or orphan"))
        parts.append(chain("Satisfied by ↓", m.satisfied_by.get(r.id, []), "nothing yet"))
        refs = m.refs_for(r.id)
        lines = [Content.assemble(("References", "bold $accent"))]
        for x in refs:
            kind = ("test", "bold $success") if x.is_test else ("code", "bold $secondary")
            lines.append(Content.assemble("  ", kind, "  ", (f"{x.file}:{x.line}", "$primary"),
                                          "  ", (x.note, "$text-muted")))
        if not refs:
            lines.append(Content.assemble(("  none", "$text-muted italic")))
        parts.append(Static(Content("\n").join(lines), classes="chain"))
        parts.append(Static(Content.assemble((f"{r.file}:{r.line}", "$text-muted")), classes="where"))
    return Vertical(*parts, classes="card full" if full else "card", id=f"card-{r.id}")


def heading(text: str, level: int = 1) -> Static:
    return Static(Content.assemble((text, "bold")), classes=f"heading h{min(level, 3)}")


# ----------------------------------------------------------------------- app

class ReqkitApp(App):
    TITLE = "reqkit"
    CSS = """
    #left { width: 60; }
    #nav { height: 1fr; background: $surface; }
    #search { margin: 0 0 1 0; }
    #view { padding: 0 2; background: $background; }
    #view:focus { background-tint: $foreground 3%; }

    .heading { margin: 1 0 1 0; padding: 0 1; color: $foreground; }
    .heading.h1 { background: $primary 20%; border-left: wide $primary; }
    .heading.h2 { border-bottom: solid $accent; color: $accent; }
    .heading.h3 { color: $accent; }

    .card { height: auto; margin: 0 0 1 0; padding: 1 2; background: $surface;
            border-left: wide $primary 60%; }
    .card.full { margin-top: 1; }
    .card.-selected { border-left: wide $accent; background: $accent 12%; }
    .card-head { height: auto; }
    .card Markdown { margin: 0; padding: 0; background: transparent; }
    .card .statement { margin: 1 0 0 0; padding: 0 1; border-left: outer $accent;
                       text-style: bold; }
    .card .detail { margin: 1 0 0 0; }
    .card .fields { margin: 1 0 0 0; height: auto; }
    .frow { height: auto; }
    .flabel { width: 14; text-style: bold; color: $text-muted; }
    .fvalue { width: 1fr; }
    .card .statement MarkdownParagraph { margin: 0; }
    .card .chain { margin: 1 0 0 0; height: auto; }
    .card .where { margin: 1 0 0 0; }
    .prose { margin: 0 0 1 0; padding: 0; background: transparent; }
    .page { height: auto; }

    Screen { layers: default overlay; }
    #peek { layer: overlay; position: absolute; display: none; width: 66; height: auto;
            max-height: 18; padding: 0 1; background: $panel; border: round $accent;
            border-title-color: $accent; }
    """
    BINDINGS = [
        Binding("slash", "search", "Search"),
        Binding("escape", "clear", "Clear search", show=False),
        Binding("a", "accept", "Accept"),
        Binding("o", "toggle_open", "Open questions"),
        Binding("t", "change_theme", "Theme"),
        Binding("question_mark", "help", "Keys"),
        Binding("r", "reload", "Reload", show=False),
        Binding("n", "next_match(1)", show=False),
        Binding("N", "next_match(-1)", show=False),
        Binding("ctrl+o,left_square_bracket", "history_back", show=False),
        Binding("right_square_bracket", "history_forward", show=False),
        Binding("less_than_sign", "resize(-4)", show=False),
        Binding("greater_than_sign", "resize(4)", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, script: Path | None = None):
        super().__init__()
        self.script = script
        self.m: Model = load_model(script)
        self.query_text = ""
        self.open_only = False
        self.nodes: dict[str, TreeNode] = {}
        self.links: list[str] = []
        self.shown: tuple | None = None
        self.link_index = -1
        self.hovering = ""
        self.back: list[tuple] = []
        self.forward: list[tuple] = []
        self.prefs = load_prefs()
        self.sub_title = str(self.m.cfg.root)
        for t in themes.THEMES:
            self.register_theme(t)
        wanted = self.prefs.get("theme", themes.DEFAULT)
        self.theme = wanted if wanted in self.available_themes else themes.DEFAULT

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left"):
                yield Input(placeholder="/ search — regex over id, title, statement, detail", id="search")
                yield VimTree("reqkit", id="nav")
            yield Divider()
            yield VimScroll(id="view")
        yield Footer()
        yield Static(id="peek")

    def on_mount(self) -> None:
        if "sidebar" in self.prefs:
            self.query_one("#left").styles.width = int(self.prefs["sidebar"])
        self.theme_changed_signal.subscribe(self, self._theme_changed)
        self.rebuild()
        tree = self.query_one("#nav", Tree)
        tree.focus()
        tree.cursor_line = 0
        self.show(("help", None))

    # ------------------------------------------------------------- layout and prefs

    def set_sidebar(self, width: int) -> None:
        width = max(24, min(width, self.size.width - 30))
        self.query_one("#left").styles.width = width

    def action_resize(self, delta: int) -> None:
        self.set_sidebar(self.query_one("#left").outer_size.width + delta)
        self.remember()

    def remember(self) -> None:
        self.prefs["sidebar"] = self.query_one("#left").outer_size.width
        self.prefs["theme"] = self.theme
        save_prefs(self.prefs)

    def _theme_changed(self, _theme) -> None:
        self.remember()
        self.relabel()

    def colour(self, name: str) -> str:
        t = self.current_theme
        return getattr(t, name, None) or t.primary

    # ------------------------------------------------------------- the tree

    def _matches(self, *texts: str) -> bool:
        if not self.query_text:
            return True
        try:
            pat = re.compile(self.query_text, re.I)
        except re.error:
            return any(self.query_text.lower() in t.lower() for t in texts)
        return any(pat.search(t) for t in texts)

    def _req_label(self, r: Req) -> Text:
        t = Text()
        if self.m.reviewed(r):
            mark, colour = STATUS_MARK.get(r.status, ("?", "secondary"))
            t.append(f"{mark} ", style=f"bold {self.colour(colour)}")
        t.append(r.id, style=f"bold {self.colour('primary')}")
        t.append(f"  {r.label}")
        return t

    def _topic_label(self, t: str, title: str, n_open: int) -> Text:
        return Text.assemble((t, "bold"), f"  {title}  ",
                             (f"{n_open} open", self.colour("error") if n_open else "dim"))

    def _question_label(self, q) -> Text:
        mark = ("open ", self.colour("error")) if q.open else ("done ", "dim")
        return Text.assemble(mark, (q.id, "bold"), f"  {q.title}")

    def relabel(self) -> None:
        """Recolour every label for the current theme, keeping the cursor where it is."""
        tree = self.query_one("#nav", Tree)
        by_topic = {}
        for q in self.m.questions:
            by_topic.setdefault(q.topic, []).append(q)

        def walk(node: TreeNode) -> None:
            for child in node.children:
                kind, key = child.data or (None, None)
                if kind == "req" and key in self.m.reqs:
                    child.set_label(self._req_label(self.m.reqs[key]))
                elif kind == "question":
                    child.set_label(self._question_label(next(q for q in self.m.questions if q.id == key)))
                elif kind == "topic":
                    child.set_label(self._topic_label(key, self.m.topics.get(key, ""),
                                                      sum(1 for q in by_topic.get(key, []) if q.open)))
                walk(child)

        walk(tree.root)

    def rebuild(self) -> None:
        m = self.m
        tree = self.query_one("#nav", Tree)
        tree.clear()
        tree.show_root = False
        self.nodes = {}
        searching = bool(self.query_text)

        reqs_root = tree.root.add("Requirements", data=("root", None), expand=True)
        for lv in m.cfg.levels:
            units = [u for u in m.units if u.level == lv.kind]
            if not units:
                continue
            lv_node = reqs_root.add(Text.assemble((lv.kind, "bold"), f"  {lv.title}"),
                                    data=("level", lv.kind), expand=searching)
            for u in units:
                u_node = lv_node.add(Text.assemble((u.title, "bold"), f"  {', '.join(u.prefixes)}"),
                                     data=("unit", u.stem), expand=searching)
                self._add_document(u_node, u)
                if searching and not u_node.children:
                    u_node.remove()
            if searching and not lv_node.children:
                lv_node.remove()

        q_root = tree.root.add("Open questions", data=("root", None), expand=searching or self.open_only)
        by_topic: dict[str, list] = {}
        for q in m.questions:
            by_topic.setdefault(q.topic, []).append(q)
        for t, title in sorted(m.topics.items()):
            qs = [q for q in by_topic.get(t, [])
                  if (q.open or not self.open_only) and self._matches(q.id, q.title, q.question, q.answer)]
            if not qs and (searching or self.open_only):
                continue
            n_open = sum(1 for q in by_topic.get(t, []) if q.open)
            t_node = q_root.add(self._topic_label(t, title, n_open), data=("topic", t),
                                expand=searching or self.open_only)
            for q in qs:
                self.nodes[q.id] = t_node.add_leaf(self._question_label(q), data=("question", q.id))

    def _add_document(self, u_node: TreeNode, unit) -> None:
        stack: list[tuple[int, TreeNode]] = [(0, u_node)]
        searching = bool(self.query_text)
        for e in self.m.document(unit):
            if e["type"] == "section":
                while stack and stack[-1][0] >= e["depth"]:
                    stack.pop()
                s = e["section"]
                node = stack[-1][1].add(
                    Text.assemble((e["number"], f"bold {self.colour('accent')}"), f" {s.title}"),
                    data=("section", (unit.stem, s.key)), expand=searching)
                stack.append((e["depth"], node))
            else:
                r: Req = e["req"]
                if self._matches(r.id, r.title, r.statement, r.rationale, r.detail):
                    self.nodes[r.id] = stack[-1][1].add_leaf(self._req_label(r), data=("req", r.id))
        if searching:
            self._drop_empty_sections(u_node)

    def _drop_empty_sections(self, node: TreeNode) -> None:
        for child in list(node.children):
            if child.data and child.data[0] == "section":
                self._drop_empty_sections(child)
                if not child.children:
                    child.remove()

    # ------------------------------------------------------------- the reading pane

    @on(Tree.NodeHighlighted)
    def _highlighted(self, event: Tree.NodeHighlighted) -> None:
        self.show(event.node.data)

    def _widgets_for(self, data, sel: str = "") -> list[Widget]:
        m = self.m
        kind, key = data
        if kind == "help":
            return [Markdown(HELP, classes="prose")]
        if kind == "req" and key in m.reqs:
            return [requirement_card(m, m.reqs[key], full=True, sel=sel)]
        if kind == "unit":
            u = m.unit(key)
            out: list[Widget] = [heading(u.title, 1)]
            if u.description:
                out.append(Markdown(u.description, classes="prose"))
            for e in m.document(u):
                if e["type"] == "section":
                    s = e["section"]
                    out.append(heading(f"{e['number']}  {s.title}", e["depth"] + 1))
                    if s.description:
                        out.append(Markdown(s.description, classes="prose"))
                else:
                    out.append(requirement_card(m, e["req"], full=False))
            return out
        if kind == "section":
            stem, skey = key
            u = m.unit(stem)
            s = u.section(skey)
            out = [heading(f"{u.numbering()[skey]}  {s.title}", 1)]
            if s.description:
                out.append(Markdown(s.description, classes="prose"))
            out += [requirement_card(m, r, full=False)
                    for r in sorted(m.reqs.values(), key=m.sort_key)
                    if r.unit == stem and (r.section == skey or r.section.startswith(skey + "."))]
            return out
        if kind == "level":
            lv = m.cfg.level(key)
            rows = "\n".join(
                f"| {u.title} | `{', '.join(u.prefixes)}` | {sum(1 for r in m.reqs.values() if r.unit == u.stem)} "
                f"| `{m.cfg.rel(u.csv_path)}` |" for u in m.units if u.level == key)
            return [heading(f"{lv.kind} — {lv.title}", 1),
                    Markdown(f"Satisfies: **{', '.join(lv.satisfies) or 'top level'}**\n\n"
                             f"| Unit | Prefix | Requirements | File |\n|---|---|---|---|\n{rows}\n",
                             classes="prose")]
        if kind == "topic":
            qs = [q for q in m.questions if q.topic == key]
            rows = "\n".join(f"| {linked_md(m, q.id, sel)} | {'**open**' if q.open else 'answered'} | {q.title} |"
                             for q in qs)
            n_reqs = sum(1 for r in m.reqs.values() if key in r.topics)
            return [heading(f"Topic {key} — {m.topics.get(key, '')}", 1),
                    md(f"{n_reqs} requirement(s) name this topic.\n\n"
                       f"| Question | | |\n|---|---|---|\n{rows}\n", "prose")]
        if kind == "question":
            q = next(q for q in m.questions if q.id == key)
            chip = (" open ", "bold $background on $error") if q.open else \
                (" answered ", "bold $background on $success")
            head = Static(Content.assemble((q.id, "bold $primary"), "  ", (q.title, "bold"), "  ", chip,
                                           "\n", (f"Topic {q.topic} — {m.topics.get(q.topic, '')}",
                                                  "$text-muted")), classes="card-head")
            body = render.question(q, m.topics.get(q.topic, "")).split("\n", 4)[-1]
            return [Vertical(head, md(linked_md(m, body, sel), "detail"), classes="card full")]
        return []

    def show(self, data, sel: str = "") -> None:
        """Render `data` in the reading pane. With `sel`, the same view again with
        that link under the cursor, scrolled where it was."""
        if not data:
            return
        widgets = self._widgets_for(data, sel)
        if not widgets:
            return
        view = self.query_one("#view", VimScroll)
        scroll = view.scroll_y
        if not sel:
            self.hide_peek()
            self.shown = data
            self.links = self._links_for(data)
            self.link_index = -1
        # A fresh page per view: the old one is removed asynchronously, and its
        # cards share IDs with the new one's.
        old = list(view.query(".page"))
        with self.batch_update():
            for page in old:
                page.remove()
            view.mount(Vertical(*widgets, classes="page"))
        if sel:
            self.call_after_refresh(view.scroll_to, y=scroll, animate=False)
        else:
            view.scroll_home(animate=False)

    # ------------------------------------------------------------- actions

    @on(Input.Changed, "#search")
    def _search(self, event: Input.Changed) -> None:
        self.query_text = event.value.strip()
        self.rebuild()

    @on(Input.Submitted, "#search")
    def _submitted(self, event: Input.Submitted) -> None:
        self.query_one("#nav", Tree).focus()
        self.action_next_match(1)

    def action_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_clear(self) -> None:
        self.query_one("#search", Input).value = ""
        self.query_one("#nav", Tree).focus()

    def action_toggle_open(self) -> None:
        self.open_only = not self.open_only
        self.rebuild()

    def action_help(self) -> None:
        self.show(("help", None))

    def action_reload(self) -> None:
        self.m = load_model(self.script)
        self.rebuild()
        self.notify("Reloaded")

    def action_next_match(self, direction: int) -> None:
        tree = self.query_one("#nav", Tree)
        line = tree.cursor_line
        while 0 <= (line := line + direction) <= tree.last_line:
            node = tree.get_node_at_line(line)
            if node is not None and node.data and node.data[0] in ("req", "question"):
                tree.cursor_line = line
                return

    # ------------------------------------------------------------- links

    def _ids_in(self, *texts: str) -> list[str]:
        return [mm.group(0) for t in texts for mm in ID_RE.finditer(t or "") if self.m.knows(mm.group(0))]

    def _links_for(self, data) -> list[str]:
        m = self.m
        kind, key = data
        ids: list[str] = []
        if kind == "req" and key in m.reqs:
            r = m.reqs[key]
            ids = r.satisfies + m.satisfied_by.get(key, []) + self._ids_in(
                r.statement, r.detail, r.rationale, r.source, *r.extra.values())
        elif kind in ("unit", "section"):
            stem = key if kind == "unit" else key[0]
            for r in sorted(m.reqs.values(), key=m.sort_key):
                if r.unit == stem and (kind == "unit" or r.section == key[1]
                                       or r.section.startswith(key[1] + ".")):
                    ids.append(r.id)
        elif kind == "question":
            q = m.question(key)
            ids = self._ids_in(q.question, q.answer, q.blocks) if q else []
        elif kind == "topic":
            ids = [q.id for q in m.questions if q.topic == key]
        return [i for i in dict.fromkeys(ids) if i != key]

    def preview(self, target: str) -> Content:
        m = self.m
        if target in m.reqs:
            r = m.reqs[target]
            head = [(r.id, "bold $primary")]
            if r.title:
                head += ["  ", (r.title, "bold")]
            if m.reviewed(r) and r.status:
                head += ["  ", _status_chip(r.status)]
            lines = [Content.assemble(*head), Content(""), Content(r.statement)]
            if r.satisfies:
                lines.append(Content.assemble(("Satisfies  ", "bold $text-muted"), ", ".join(r.satisfies)))
            if r.verification:
                lines.append(Content.assemble(("Verified   ", "bold $text-muted"), r.verification))
            return Content("\n").join(lines)
        q = m.question(target)
        if q:
            chip = (" open ", "bold $background on $error") if q.open else \
                (" answered ", "bold $background on $success")
            answer = q.answer if len(q.answer) < 400 else q.answer[:399] + "…"
            lines = [Content.assemble((q.id, "bold $primary"), "  ", (q.title, "bold"), "  ", chip),
                     Content(""), Content(q.question)]
            if answer:
                lines += [Content(""), Content.assemble((answer, "$text-muted"))]
            return Content("\n").join(lines)
        return Content(target)

    def show_peek(self, target: str, x: int, y: int, title: str = "") -> None:
        peek = self.query_one("#peek", Static)
        peek.update(self.preview(target))
        peek.border_title = title
        width = 66
        x = max(0, min(x, self.size.width - width - 1))
        y = max(1, min(y, self.size.height - 8))
        peek.styles.offset = (x, y)
        peek.display = True

    def hide_peek(self) -> bool:
        peek = self.query_one("#peek", Static)
        shown = bool(peek.display)
        peek.display = False
        self.hovering = ""
        return shown

    def on_mouse_move(self, event: events.MouseMove) -> None:
        action = event.style.meta.get("@click", "") if event.style else ""
        mm = TARGET_RE.search(action) if action else None
        target = mm.group(1) if mm else ""
        if target and self.m.knows(target):
            if target != self.hovering:
                self.show_peek(target, event.screen_x + 2, event.screen_y + 1)
                self.hovering = target
        elif self.hovering:
            self.hide_peek()

    @on(Markdown.LinkClicked)
    def _markdown_link(self, event: Markdown.LinkClicked) -> None:
        if event.href.startswith("reqkit:"):
            event.stop()
            self.action_goto(event.href.removeprefix("reqkit:"))

    def action_cycle_link(self, direction: int) -> None:
        if not self.links:
            self.notify("Nothing here links anywhere.")
            return
        self.link_index = (self.link_index + direction) % len(self.links)
        target = self.links[self.link_index]
        kind = self.shown[0] if self.shown else ""
        if kind in ("unit", "section"):
            # A document: the cursor is on whole cards, so no re-render is needed.
            for card in self.query(".card.-selected"):
                card.remove_class("-selected")
            try:
                card = self.query(f"#card-{target}").last()
                card.add_class("-selected")
                card.scroll_visible(animate=False, top=True)
            except Exception:
                pass
        else:
            self.show(self.shown, sel=target)
        self.call_after_refresh(self.action_peek_link)

    def action_peek_link(self) -> None:
        if not self.links:
            return
        if self.link_index < 0:
            self.link_index = 0
        view = self.query_one("#view").region
        self.show_peek(self.links[self.link_index], view.x + max(2, view.width - 68),
                       view.y + max(1, view.height - 14),
                       f" link {self.link_index + 1}/{len(self.links)} · enter to follow ")

    def action_follow_link(self) -> None:
        if 0 <= self.link_index < len(self.links):
            self.action_goto(self.links[self.link_index])
        elif self.links:
            self.action_cycle_link(1)

    # ------------------------------------------------------------- jumping and history

    def _node_for(self, data) -> TreeNode | None:
        kind, key = data
        if kind in ("req", "question"):
            return self.nodes.get(key)
        stack = [self.query_one("#nav", Tree).root]
        while stack:
            node = stack.pop()
            if node.data == data:
                return node
            stack.extend(node.children)
        return None

    def _move_to(self, data) -> bool:
        node = self._node_for(data)
        if node is None and (self.query_text or self.open_only):
            self.query_one("#search", Input).value = ""
            self.query_text = ""
            self.open_only = False
            self.rebuild()
            node = self._node_for(data)
        if node is None:
            return False
        parent = node.parent
        while parent is not None:
            parent.expand()
            parent = parent.parent
        tree = self.query_one("#nav", Tree)
        self.call_after_refresh(tree.move_cursor, node)
        return True

    def action_goto(self, target: str) -> None:
        kind = "req" if target in self.m.reqs else "question"
        here = self.query_one("#nav", Tree).cursor_node
        if self._move_to((kind, target)):
            if here is not None and here.data and here.data != (kind, target):
                self.back.append(here.data)
                self.forward.clear()
        else:
            self.notify(f"{target} is not in the tree.", severity="warning")

    def _step(self, source: list, dest: list) -> None:
        here = self.query_one("#nav", Tree).cursor_node
        while source:
            data = source.pop()
            if self._move_to(data):
                if here is not None and here.data:
                    dest.append(here.data)
                return
        self.notify("Nothing further back." if source is self.back else "Nothing further forward.")

    def action_history_back(self) -> None:
        if not self.back:
            self.notify("Nothing further back.")
            return
        self._step(self.back, self.forward)

    def action_history_forward(self) -> None:
        if not self.forward:
            self.notify("Nothing further forward.")
            return
        self._step(self.forward, self.back)

    def action_accept(self) -> None:
        node = self.query_one("#nav", Tree).cursor_node
        if not node or not node.data or node.data[0] != "req":
            self.notify("Highlight a requirement to accept it.", severity="warning")
            return
        r = self.m.reqs[node.data[1]]
        if not self.m.reviewed(r):
            self.notify(f"{r.id} carries no review status.", severity="warning")
            return
        if r.status == "Accepted":
            self.notify(f"{r.id} is already accepted.")
            return

        def done(yes: bool | None) -> None:
            if not yes:
                return
            try:
                ops.accept(self.m, r.id)
            except ops.OpError as e:
                self.notify(str(e), severity="error")
                return
            r.status = "Accepted"
            node.set_label(self._req_label(r))
            self.show(node.data)
            self.notify(f"{r.id} accepted")

        self.push_screen(Confirm(f"Accept {r.id} — {r.label}?\n\nYou have read it and agree with it."), done)


def main(script: Path | None = None) -> int:
    ReqkitApp(script).run()
    return 0
