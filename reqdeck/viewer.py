"""The reqdeck TUI: requirements as documents, with their sections, and the open
questions beside them. Reads through the same model as the CLI and writes
through the same operations.

Needs `textual`, which the CLI does not. The chosen theme and sidebar width
are remembered per user in `$XDG_CONFIG_HOME/reqdeck/tui.json`, and the seconds
between reloads read from it: `"reload": 30` by default, `0` for never.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
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
from textual.widgets import Input, Label, Markdown, OptionList, Static, Tree
from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode

from . import editor, ops, render, themes
from .cli import load_model
from .model import Model, Req

ID_RE = re.compile(r"\b(?:OQ-\d{4}|[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*[_-]\d+)\b")
TARGET_RE = re.compile(r"(?:goto|link)\('(?:reqdeck:)?([^']+)'\)")

#: Status letter in the tree, and the theme role that colours it.
STATUS_MARK = {"Accepted": ("A", "accepted"), "Proposed": ("P", "proposed"), "Reopened": ("R", "reopened")}
#: Progress mark in the tree, and the theme role that colours it.
PROGRESS_MARK = {"Done": ("✓", "accepted"), "Untested": ("◑", "proposed"), "Partial": ("◔", "proposed"),
                 "Not implemented": ("○", "reopened"), "Unsatisfied": ("✗", "reopened")}

HELP = """\
# Keys

The tree always has the cursor; the reading pane shows what it highlights.

| | |
|---|---|
| `j` `k` | Down, up |
| `h` `l` | Collapse or go to the parent, expand or go in |
| `gg` `G` | First, last |
| `n` `N` | Next, previous requirement or question — the search results, while searching |
| `tab` `shift+tab` | Next, previous link in the reading pane, previewed beside it |
| `enter` `gd` | Follow the selected link — the tree moves there too. A code or test reference opens in the editor. With no link selected, `enter` opens or closes the node |
| `escape` | Drop the selected link and its preview; again, clear the search |
| `K` | Show the selected link's preview again |
| `ctrl+o` `[` | Back to where you jumped from |
| `]` | Forward again |
| `ctrl+d` `ctrl+u` | Scroll the reading pane half a page; `ctrl+e` `ctrl+y` a line |
| `/` | Search — a regex over id, title, statement, detail. `enter` returns to the tree |
| `o` | Only open questions |
| `a` | Accept the highlighted requirement |
| `<` `>` | Narrow or widen the sidebar — or drag the divider |
| `t` | Theme — previewed as you move, `enter` keeps it |
| `r` | Reload from disk — it also does so every 30 seconds |
| `q` | Quit |

Every requirement and question ID in the reading pane is a link, and so is every code
and test reference. Hover one for a preview, click it to go there.

# Marks

Beside each requirement in the tree: its review status, then how far it is built — judged
over it and everything that satisfies it, from the links and the `@REQ_REF` markers.

| | |
|---|---|
| `A` `P` `R` | Accepted, Proposed, Reopened |
| `✓` | Done — coded, and tested where its verification asks, and so is everything beneath it |
| `◑` | Untested — the code is there, a test its verification asks for is not |
| `◔` | Partial — some of what is beneath it is built, not all |
| `○` | Not implemented — code is expected, and none names it |
| `✗` | Unsatisfied — a lower level exists to satisfy it, and nothing does |
"""


# --------------------------------------------------------------------- prefs

def _prefs_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "reqdeck" / "tui.json"


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
        Binding("d", "d", show=False),
        # The reading pane is never focused: the tree drives it.
        Binding("tab", "app.cycle_link(1)", show=False),
        Binding("shift+tab", "app.cycle_link(-1)", show=False),
        Binding("enter", "app.follow_or_toggle", show=False),
        Binding("K", "app.peek_link", show=False),
        Binding("escape", "app.escape", show=False),
        Binding("ctrl+d", "app.scroll_view(0.5)", show=False),
        Binding("ctrl+u", "app.scroll_view(-0.5)", show=False),
        Binding("ctrl+e", "app.scroll_view(1)", show=False),
        Binding("ctrl+y", "app.scroll_view(-1)", show=False),
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

    def action_last(self) -> None:
        self.cursor_line = self.last_line

    def action_g(self) -> None:
        if self._g.second():
            self.cursor_line = 0

    def action_d(self) -> None:
        """`gd` follows the selected link, as go-to-definition does in nvim."""
        if self._g.pending():
            self.app.action_follow_link()


class ReadingPane(VerticalScroll):
    """Shows what the tree has highlighted. Never focused — the tree drives it,
    and its links are stepped through from there."""

    can_focus = False


class Divider(Widget):
    """The bar between sidebar and reading pane. Drag it to resize."""

    DEFAULT_CSS = """
    Divider { width: 1; height: 1fr; color: $rk-border-active; text-opacity: 0%; }
    Divider:hover, Divider.-dragging { text-opacity: 100%; }
    """

    def render(self) -> str:
        return "\n".join("┃" * 1 for _ in range(max(1, self.size.height)))

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
    Confirm { align: center middle; background: transparent; }
    Confirm > Vertical { width: 72; height: auto; padding: 1 2; border: round $rk-border-active;
                         border-title-color: $rk-title; background: transparent; }
    Confirm Label { color: $rk-foreground; }
    Confirm .hint { margin-top: 1; color: $rk-muted; }
    """
    BINDINGS = [Binding("escape,n", "dismiss(False)", "Cancel"), Binding("y,enter", "dismiss(True)", "Yes")]

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical() as box:
            box.border_title = "Accept"
            yield Label(self.message)
            yield Static(Content.assemble(("Accept: ", "$rk-muted"), ("y", "bold $rk-keys"),
                                          ("  |  Cancel: ", "$rk-muted"), ("n", "bold $rk-keys")),
                         classes="hint")


class ThemePicker(ModalScreen[str | None]):
    """Every theme with a colour suite, applied live as the cursor moves."""

    DEFAULT_CSS = """
    ThemePicker { align: center middle; background: transparent; }
    ThemePicker OptionList { width: 44; height: auto; max-height: 80%; padding: 0 1;
                             border: round $rk-border-active; border-title-color: $rk-title;
                             background: transparent; color: $rk-foreground; }
    ThemePicker OptionList > .option-list--option-highlighted {
        background: $rk-selection; color: $rk-foreground; text-style: bold; }
    """
    BINDINGS = [Binding("escape,q", "cancel", show=False), Binding("j", "down", show=False),
                Binding("k", "up", show=False)]

    def __init__(self, palettes: dict, current: str):
        super().__init__()
        self.palettes = palettes
        self.original = current

    def compose(self) -> ComposeResult:
        names = sorted(self.palettes, key=lambda n: self.palettes[n].title.lower())
        opts = OptionList(*[Option(self.palettes[n].title, id=n) for n in names])
        opts.border_title = "Theme"
        yield opts

    def on_mount(self) -> None:
        opts = self.query_one(OptionList)
        opts.highlighted = opts.get_option_index(self.original) if self.original in self.palettes else 0
        opts.focus()

    @on(OptionList.OptionHighlighted)
    def _preview(self, event: OptionList.OptionHighlighted) -> None:
        self.app.theme = event.option.id

    @on(OptionList.OptionSelected)
    def _chosen(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_down(self) -> None:
        self.query_one(OptionList).action_cursor_down()

    def action_up(self) -> None:
        self.query_one(OptionList).action_cursor_up()

    def action_cancel(self) -> None:
        self.app.theme = self.original
        self.dismiss(None)


# --------------------------------------------------------------------- cards

def _status_chip(status: str) -> Content:
    _, role = STATUS_MARK.get(status, ("?", "muted"))
    return Content.assemble((f"● {status}", f"bold $rk-{role}"))


def _progress_chip(state: str) -> Content:
    mark, role = PROGRESS_MARK.get(state, ("?", "muted"))
    return Content.assemble((f"{mark} {state}", f"bold $rk-{role}"))


def _link(rid: str, sel: str = "") -> tuple[str, str]:
    """A clickable ID; the one under the keyboard link cursor is drawn reversed."""
    style = "bold $rk-link-active on $rk-selection" if rid == sel else "$rk-link underline"
    return rid, f"{style} @click=app.goto('{rid}')"


def _ref_link(file: str, line: int, sel: str = "") -> tuple[str, str]:
    """A code or test reference, which opens in the editor when followed."""
    target = f"ref:{file}:{line}"
    style = "bold $rk-link-active on $rk-selection" if target == sel else "$rk-link underline"
    shown = f"{Path(file).name}:{line}"     # the full path is in the preview
    if "'" in file:
        return shown, "$rk-link"
    return shown, f"{style} @click=app.goto('{target}')"


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
            out.append((code, f"{style} $rk-code".strip()))
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
        return f"[**▸ {rid}**](reqdeck:{rid})" if rid == sel else f"[{rid}](reqdeck:{rid})"

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
    head = [(r.id, f"bold $rk-id @click=app.goto('{r.id}')") if not full else (r.id, "bold $rk-id")]
    if r.title:
        head += ["  ", (r.title, "bold $rk-foreground")]
    if m.reviewed(r) and r.status:
        head += ["  ", _status_chip(r.status)]
    if m.progress(r.id).state:
        head += ["  ", _progress_chip(m.progress(r.id).state)]
    if r.security:
        head += ["  ", ("◆ security", "bold $rk-security")]
    parts.append(Static(Content.assemble(*head), classes="card-head"))
    parts.append(Static(Content.assemble(*linked(m, r.statement, "bold", sel)), classes="statement"))
    if r.detail:
        parts.append(md(linked_md(m, r.detail, sel), "detail"))

    rows: list[Widget] = []
    if r.rationale:
        rows.append(_field("Rationale", *linked(m, r.rationale, "$rk-muted italic", sel)))
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
        rows.append(_field("Verification", (r.verification, "bold $rk-heading"),
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
            lines = [Content.assemble((title, "bold $rk-heading"))]
            for t in ids:
                label = m.reqs[t].label if t in m.reqs else "(undefined)"
                lines.append(Content.assemble("  ", _link(t, sel), "  ", (label, "$rk-foreground")))
            if not ids:
                lines.append(Content.assemble(("  " + empty, "$rk-muted italic")))
            return Static(Content("\n").join(lines), classes="chain")

        parts.append(chain("Satisfies ↑", r.satisfies, "nothing — top level or orphan"))
        parts.append(chain("Satisfied by ↓", m.satisfied_by.get(r.id, []), "nothing yet"))
        refs = m.refs_for(r.id)
        lines = [Content.assemble(("References", "bold $rk-heading"))]
        for x in refs:
            kind = ("test", "bold $rk-accepted") if x.is_test else ("code", "bold $rk-id")
            lines.append(Content.assemble("  ", kind, "  ", _ref_link(x.file, x.line, sel),
                                          "  ", (render.origin(m.cfg.root, x.file, x.line), "$rk-muted")))
        if not refs:
            lines.append(Content.assemble(("  none", "$rk-muted italic")))
        parts.append(Static(Content("\n").join(lines), classes="chain"))
        parts.append(Static(Content.assemble((f"{r.file}:{r.line}", "$rk-muted")), classes="where"))
    return Vertical(*parts, classes="card full" if full else "card", id=f"card-{r.id}")


def heading(text: str, level: int = 1) -> Static:
    return Static(Content.assemble((text, "bold")), classes=f"heading h{min(level, 3)}")


# ----------------------------------------------------------------------- app

class ReqdeckApp(App):
    TITLE = "reqdeck"
    CSS = """
    Screen { background: transparent; layers: default overlay; }
    * { scrollbar-background: transparent; scrollbar-background-hover: transparent;
        scrollbar-background-active: transparent; scrollbar-color: $rk-selection;
        scrollbar-color-hover: $rk-muted; scrollbar-color-active: $rk-border-active;
        scrollbar-corner-color: transparent; scrollbar-size-vertical: 1; }
    #main { height: 1fr; background: transparent; }

    .panel { border: round $rk-border; border-title-color: $rk-border; border-title-style: bold;
             border-subtitle-color: $rk-muted; background: transparent; }
    #left { width: 60; padding: 0; }
    #left.-searching { border: round $rk-border-search; }
    #view { width: 1fr; padding: 0 1; }

    #search { height: 1; border: none; padding: 0 1; margin: 0 0 1 0; background: transparent;
              color: $rk-foreground; }
    #search:focus { background-tint: transparent; }
    #search > .input--placeholder { color: $rk-muted; }
    #search > .input--cursor { background: $rk-foreground; color: $rk-selection; }

    Tree { background: transparent; color: $rk-foreground; overflow-x: hidden; }
    Tree:focus { background-tint: transparent; }
    Tree > .tree--guides, Tree > .tree--guides-hover { color: $rk-border; }
    Tree > .tree--guides-selected { color: $rk-border-active; }
    Tree > .tree--cursor { background: transparent; text-style: bold; }
    Tree:focus > .tree--cursor { background: $rk-selection; color: $rk-foreground; text-style: none; }
    Tree:focus > .tree--guides { color: $rk-border; }
    Tree:focus > .tree--guides-selected { color: $rk-border-active; }
    Tree > .tree--highlight-line { background: transparent; }

    .heading { margin: 1 0; color: $rk-heading; }
    .heading.h1 { color: $rk-title; border-bottom: solid $rk-border; }
    .heading.h3 { margin: 0 0 1 0; }

    .card { height: auto; margin: 0 0 1 0; padding: 0 1; background: transparent;
            border: round $rk-border; }
    .card.full { border: none; padding: 0; margin-top: 1; }
    .card.-selected { border: round $rk-link-active; }
    .card-head { height: auto; }
    .card .statement { margin: 1 0 0 0; padding: 0 1; border-left: outer $rk-statement-bar;
                       text-style: bold; }
    .skeleton { margin: 1 0 0 0; }
    .card .detail { margin: 1 0 0 0; }
    .card .fields { margin: 1 0 0 0; height: auto; }
    .frow { height: auto; }
    .flabel { width: 14; color: $rk-muted; }
    .fvalue { width: 1fr; color: $rk-foreground; }
    .card .chain { margin: 1 0 0 0; height: auto; }
    .card .where { margin: 1 0 0 0; }
    .prose { margin: 0 0 1 0; }
    .page { height: auto; }

    Markdown { margin: 0; padding: 0; background: transparent; color: $rk-foreground;
               link-color: $rk-link; link-background: transparent; link-style: underline;
               link-color-hover: $rk-link-active; link-background-hover: transparent;
               link-style-hover: bold underline; }
    Markdown MarkdownBlock > .code_inline { background: transparent !important; color: $rk-code !important; }
    Markdown MarkdownBlock > .strong { color: $rk-foreground; }
    MarkdownTable { background: transparent !important; }
    MarkdownTableContent > .header { color: $rk-table-header; text-style: bold; }
    MarkdownTableContent > .markdown-table--lines { color: $rk-border; }
    MarkdownBullet { color: $rk-muted; }
    MarkdownFence { background: transparent !important; color: $rk-code; }
    MarkdownBlockQuote { background: transparent; border-left: outer $rk-border; }
    MarkdownH1, MarkdownH2, MarkdownH3 { color: $rk-heading; background: transparent; }

    #peek { layer: overlay; position: absolute; display: none; width: 66; height: auto;
            max-height: 18; padding: 0 1; background: transparent; color: $rk-foreground;
            border: round $rk-link-active; border-title-color: $rk-link-active; }
    #keys { dock: bottom; height: 1; padding: 0 1; background: transparent; }

    Toast { background: transparent; border: round $rk-border-active; color: $rk-foreground; }
    .toast--title { color: $rk-title; }
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
    #: Seconds between reloads from disk, unless `tui.json` names its own; 0 is never.
    RELOAD_EVERY = 30
    #: Frames of the spinner drawn while a reload runs, as lazygit's.
    SPINNER = "|/-\\"
    #: The spinner stays up at least this long, so a fast reload is still seen.
    SPIN_AT_LEAST = 0.5

    def __init__(self):
        # ansi_color leaves the terminal's own background unpainted: with it
        # off Textual fills every cell.
        super().__init__(ansi_color=True)
        self.m: Model = load_model()
        self.query_text = ""
        self.open_only = False
        self.nodes: dict[str, TreeNode] = {}
        self.links: list[str] | None = []
        self.shown: tuple | None = None
        #: Bumped by every new view, so a fill still running for an old one stops.
        self._token = 0
        #: The reading pane holds the real view, not its skeleton.
        self._filled = False
        self.link_index = -1
        self.hovering = ""
        self.back: list[tuple] = []
        self.forward: list[tuple] = []
        #: The spinner's frame while a reload runs; None when none does.
        self._spin: int | None = None
        #: The last reload's error, so a file left broken is reported once.
        self._reload_error = ""
        self.prefs = load_prefs()
        self.palettes = themes.load_all()
        for p in self.palettes.values():
            self.register_theme(p.theme())
        wanted = self.prefs.get("theme", themes.DEFAULT)
        self.theme = wanted if wanted in self.palettes else themes.DEFAULT

    def get_theme_variable_defaults(self) -> dict[str, str]:
        """Every role, so the stylesheet parses before a theme is applied."""
        palettes = getattr(self, "palettes", None) or themes.load_all()
        fallback = palettes.get(themes.DEFAULT) or next(iter(palettes.values()))
        return {f"rk-{k.replace('_', '-')}": v for k, v in fallback.colors.items()}

    def compose(self) -> ComposeResult:
        with Horizontal(id="main"):
            with Vertical(id="left", classes="panel") as left:
                left.border_title = "Requirements"
                left.border_subtitle = self.m.cfg.root.name
                yield Input(placeholder="/ search — regex over id, title, statement, detail", id="search")
                yield VimTree("reqdeck", id="nav")
            yield Divider()
            view = ReadingPane(id="view", classes="panel")
            view.border_title = "Keys"
            yield view
        yield Static(id="keys")
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
        self.refresh_keys()
        self.run_worker(self._warm_origins, thread=True, group="warm")
        try:
            every = float(self.prefs.get("reload", self.RELOAD_EVERY))
        except (TypeError, ValueError):
            every = self.RELOAD_EVERY
        if every > 0:
            self.set_interval(every, self.reload)

    def _warm_origins(self) -> None:
        """What every reference is attached to, read in a thread at start, so a
        requirement with references is as quick to show as one without."""
        root = self.m.cfg.root
        for ref in list(self.m.refs):
            render.origin(root, ref.file, ref.line)

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
        self.relabel()
        self.refresh_keys()

    def colour(self, role: str) -> str:
        """A role's colour in the current theme, for Rich text that cannot name a variable."""
        p = self.palettes.get(self.theme) or self.palettes[themes.DEFAULT]
        return p.colors[role]

    def action_change_theme(self) -> None:
        def done(name: str | None) -> None:
            if name:
                self.theme = name
                self.remember()
        self.push_screen(ThemePicker(self.palettes, self.theme), done)

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        self.refresh_keys()

    def refresh_keys(self) -> None:
        """The one line of `Action: key` hints — only those that do something here."""
        try:
            bar = self.query_one("#keys", Static)
            tree = self.query_one("#nav", Tree)
            view = self.query_one("#view", ReadingPane)
            peek = self.query_one("#peek", Static)
        except Exception:
            return
        node = tree.cursor_node
        data = node.data if node is not None else None
        in_questions = False
        while node is not None:
            if node.data and node.data[0] == "qroot":
                in_questions = True
            node = node.parent
        pairs = [("Search", "/")]
        if self._ensure_links():
            pairs.append(("Next link", "tab"))
        if peek.display and 0 <= self.link_index < len(self.links or []):
            ref = self.links[self.link_index].startswith("ref:")
            pairs.append(("Open in editor" if ref else "Follow", "enter"))
        if self.back:
            pairs.append(("Back", "ctrl+o"))
        if self.forward:
            pairs.append(("Forward", "]"))
        if view.max_scroll_y > 0:
            pairs.append(("Scroll", "ctrl+d/u"))
        if in_questions:
            pairs.append(("All questions" if self.open_only else "Only open questions", "o"))
        if data and data[0] == "req" and data[1] in self.m.reqs:
            r = self.m.reqs[data[1]]
            if self.m.reviewed(r) and r.status != "Accepted":
                pairs.append(("Accept", "a"))
        pairs += [("Theme", "t"), ("Keys", "?"), ("Quit", "q")]
        parts: list = []
        for i, (action, key) in enumerate(pairs):
            if i:
                parts.append(("  |  ", "$rk-muted"))
            parts += [(f"{action}: ", "$rk-muted"), (key, "bold $rk-keys")]
        if self._spin is not None:
            frame = self.SPINNER[self._spin % len(self.SPINNER)]
            parts = [(f"Reloading {frame}", "bold $rk-link-active"), "    "] + parts
        line = Content.assemble(*parts)
        if str(line) != str(bar.content):           # a repaint only when it changed
            bar.update(line)

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
            mark, role = STATUS_MARK.get(r.status, ("?", "muted"))
            t.append(f"{mark} ", style=f"bold {self.colour(role)}")
        state = self.m.progress(r.id).state
        if state:
            mark, role = PROGRESS_MARK[state]
            t.append(f"{mark} ", style=f"bold {self.colour(role)}")
        else:
            t.append("  ")
        t.append(r.id, style=self.colour("id"))
        t.append(f"  {r.label}")
        return t

    def _topic_label(self, t: str, title: str, n_open: int) -> Text:
        return Text.assemble((t, f"bold {self.colour('heading')}"), f"  {title}  ",
                             (f"{n_open} open", self.colour("open") if n_open else self.colour("muted")))

    def _question_label(self, q) -> Text:
        mark = ("open ", self.colour("open")) if q.open else ("done ", self.colour("muted"))
        return Text.assemble(mark, (q.id, self.colour("id")), f"  {q.title}")

    def relabel(self) -> None:
        """Recolour every label for the current theme, keeping the cursor where it is."""
        tree = self.query_one("#nav", Tree)
        here = tree.cursor_node.data if tree.cursor_node else None
        self.rebuild()
        if here:
            node = self._node_for(here)
            if node is not None:
                parent = node.parent
                while parent is not None:
                    parent.expand()
                    parent = parent.parent
                self.call_after_refresh(tree.move_cursor, node)

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
            lv_node = reqs_root.add(Text.assemble((lv.kind, f"bold {self.colour('title')}"), f"  {lv.title}"),
                                    data=("level", lv.kind), expand=searching)
            for u in units:
                u_node = lv_node.add(Text.assemble((u.title, "bold"),
                                                   (f"  {', '.join(u.prefixes)}", self.colour("muted"))),
                                     data=("unit", u.stem), expand=searching)
                self._add_document(u_node, u)
                if searching and not u_node.children:
                    u_node.remove()
            if searching and not lv_node.children:
                lv_node.remove()

        q_root = tree.root.add("Open questions", data=("qroot", None), expand=searching or self.open_only)
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
                    Text.assemble((e["number"], f"bold {self.colour('heading')}"), f" {s.title}"),
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
        if event.node.data == self.shown:
            return              # the tree rebuilt under a view it already shows
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
            def done(u) -> str:
                states = [m.progress(r.id).state for r in m.reqs.values() if r.unit == u.stem]
                asked = [st for st in states if st]
                return f"{asked.count('Done')}/{len(asked)}" if asked else "—"
            rows = "\n".join(
                f"| {u.title} | `{', '.join(u.prefixes)}` | {sum(1 for r in m.reqs.values() if r.unit == u.stem)} "
                f"| {done(u)} | `{m.cfg.rel(u.csv_path)}` |" for u in m.units if u.level == key)
            return [heading(f"{lv.kind} — {lv.title}", 1),
                    Markdown(f"Satisfies: **{', '.join(lv.satisfies) or 'top level'}**\n\n"
                             f"| Unit | Prefix | Requirements | Done | File |\n|---|---|---|---|---|\n{rows}\n",
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
            chip = ("● open", "bold $rk-open") if q.open else ("● answered", "bold $rk-answered")
            head = Static(Content.assemble((q.id, "bold $rk-id"), "  ", (q.title, "bold"), "  ", chip,
                                           "\n", (f"Topic {q.topic} — {m.topics.get(q.topic, '')}",
                                                  "$rk-muted")), classes="card-head")
            body = render.question(q, m.topics.get(q.topic, "")).split("\n", 4)[-1]
            return [Vertical(head, md(linked_md(m, body, sel), "detail"), classes="card full")]
        return []

    def _title_for(self, data) -> str:
        m = self.m
        kind, key = data
        if kind == "req" and key in m.reqs:
            return f"{key} — {m.reqs[key].label}"
        if kind == "unit":
            return m.unit(key).title
        if kind == "section":
            u = m.unit(key[0])
            return f"{u.title} · {u.numbering()[key[1]]} {u.section(key[1]).title}"
        if kind == "level":
            return f"{key} — {m.cfg.level(key).title}"
        if kind == "topic":
            return f"Topic {key} — {m.topics.get(key, '')}"
        if kind == "question":
            return key
        return "Keys"

    CONTENT_KINDS = ("req", "unit", "section", "level", "topic", "question", "help")
    #: How long the cursor must rest before a view is filled.
    FILL_DELAY = 0.08

    def show(self, data, sel: str = "", keep: bool = False) -> None:
        """Show `data` in the reading pane.

        A new view appears as a skeleton at once and is filled in a worker once
        the cursor rests, so moving quickly through the tree draws only skeletons.
        With `sel` or `keep` it is the same view again — `sel` the link under the
        cursor — rebuilt at once, scrolled where it was."""
        if not data or data[0] not in self.CONTENT_KINDS:
            return
        view = self.query_one("#view", ReadingPane)
        title = self._title_for(data)
        if view.border_title != title:
            view.border_title = title
        if sel or keep:
            self._replace(self._widgets_for(data, sel))
            if sel:
                # The link preview restores this, in order with revealing the link.
                self._restore_scroll = view.scroll_y
            else:
                self.call_after_refresh(view.scroll_to, y=view.scroll_y, animate=False)
            return
        self.hide_peek()
        self.shown = data
        self.links = None
        self.link_index = -1
        self._filled = False
        self._token += 1
        if self._cheap(data):
            # Nothing slow to draw: no Markdown, no document. Shown at once.
            self.workers.cancel_group(self, "render")
            self._replace(self._widgets_for(data))
            view.scroll_home(animate=False)
            # Its links are read off the page, which is mounted by the next frame.
            self.call_after_refresh(self._mark_filled, self._token)
            return
        top, bars = self._skeleton(data)
        current = view.query(".page")
        if current and current.last().has_class("skeleton-page") and len(current.last().children) == 2:
            # Moving on from a skeleton: rewrite its header in place, nothing to lay out.
            current.last().children[0].update(top.content)
        else:
            self._replace([top, bars]).add_class("skeleton-page")
            view.scroll_home(animate=False)
        self.run_worker(self._fill(data, self._token), exclusive=True, group="render")
        self.refresh_keys()

    def _mark_filled(self, token: int) -> None:
        if token == self._token:
            self._filled = True
            self.refresh_keys()

    def _cheap(self, data) -> bool:
        """A view with nothing slow to lay out: a requirement without a detail table,
        whose references' origins are already known."""
        kind, key = data
        if kind != "req" or key not in self.m.reqs or self.m.reqs[key].detail:
            return False
        root = self.m.cfg.root
        return all(render.origin_cached(root, x.file, x.line) for x in self.m.refs_for(key))

    def _replace(self, widgets: list[Widget]) -> Widget:
        """A fresh page holding `widgets`: the old one is removed asynchronously,
        and its cards share IDs with the new one's."""
        view = self.query_one("#view", ReadingPane)
        page = Vertical(*widgets, classes="page")
        with self.batch_update():
            for old in list(view.query(".page")):
                old.remove()
            view.mount(page)
        return page

    def _skeleton(self, data) -> list[Widget]:
        """What a view looks like before it is filled: its header, and grey bars."""
        m = self.m
        kind, key = data
        if kind == "req" and key in m.reqs:
            r = m.reqs[key]
            head = [(r.id, "bold $rk-id")] + (["  ", (r.title, "bold $rk-foreground")] if r.title else [])
            if m.reviewed(r) and r.status:
                head += ["  ", _status_chip(r.status)]
            if m.progress(r.id).state:
                head += ["  ", _progress_chip(m.progress(r.id).state)]
        else:
            head = [(self._title_for(data), "bold $rk-heading")]
        top = Static(Content.assemble(*head), classes="card-head")
        bars = [58, 44, 0, 70, 66, 52, 0, 24, 30, 28, 0, 36, 40]
        lines = Content("\n").join(Content.assemble(("▆" * w, "$rk-selection")) for w in bars)
        return [top, Static(lines, classes="skeleton")]

    async def _fill(self, data, token: int) -> None:
        await asyncio.sleep(self.FILL_DELAY)        # only once the cursor rests
        if token != self._token:
            return
        if data[0] == "req" and data[1] in self.m.reqs:
            # File reads — what each reference is attached to — off the main thread.
            refs = self.m.refs_for(data[1])
            await asyncio.to_thread(lambda: [render.origin(self.m.cfg.root, x.file, x.line) for x in refs])
        widgets = self._widgets_for(data)
        if token != self._token or not widgets:
            return
        page = self._replace([])
        # A screenful at once, then the rest a batch a frame.
        batches = [widgets[:6]] + [widgets[i:i + 12] for i in range(6, len(widgets), 12)]
        for batch in batches:
            await page.mount_all(batch)
            await asyncio.sleep(0)
            if token != self._token:
                return
        if data[0] in ("unit", "section"):
            self.links = self._links_for(data)
        self._filled = True
        self.refresh_keys()
        self.call_after_refresh(self.refresh_keys)  # again once laid out: whether it scrolls

    # ------------------------------------------------------------- actions

    @on(Input.Changed, "#search")
    def _search(self, event: Input.Changed) -> None:
        self.query_text = event.value.strip()
        self.query_one("#left").set_class(bool(self.query_text), "-searching")
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
        self.refresh_keys()

    def action_help(self) -> None:
        self.show(("help", None))

    def action_reload(self) -> None:
        self.reload(say=True)

    def reload(self, say: bool = False) -> None:
        """Read the model from disk again, in a thread, with the spinner up meanwhile.
        A dialog defers it: the next one comes soon enough."""
        if self._spin is not None or len(self.screen_stack) > 1:
            return
        self._spin = 0
        self.refresh_keys()
        self.run_worker(self._reload(say), exclusive=True, group="reload")

    async def _reload(self, say: bool) -> None:
        start = time.monotonic()
        ticker = self.set_interval(0.1, self._spin_on)
        try:
            m, error = await asyncio.to_thread(load_model), ""
        except Exception as e:      # a broken config or file, maybe half written
            m, error = None, str(e)
        await asyncio.sleep(max(0.0, self.SPIN_AT_LEAST - (time.monotonic() - start)))
        ticker.stop()
        self._spin = None
        self.refresh_keys()
        if error:
            if say or error != self._reload_error:
                self.notify(error, title="Reload failed", severity="error")
            self._reload_error = error
            return
        self._reload_error = ""
        if len(self.screen_stack) == 1 and not self._same(m, self.m):
            self.m = m
            self.drop_link()
            self.relabel()          # rebuilds the tree, keeping the cursor where it was
            here = self.shown
            if here and (here[0] == "help" or self._node_for(here) is not None):
                # Redrawn from the new model, scrolled where it was.
                self.links = self._links_for(here) if here[0] in ("unit", "section") else None
                self.show(here, keep=True)
            else:
                self.call_after_refresh(self._show_cursor)     # it is gone
        if say:
            self.notify("Reloaded")

    def _show_cursor(self) -> None:
        node = self.query_one("#nav", Tree).cursor_node
        if node is not None:
            self.show(node.data)

    def _spin_on(self) -> None:
        if self._spin is not None:
            self._spin += 1
            self.refresh_keys()

    @staticmethod
    def _same(a: Model, b: Model) -> bool:
        """Nothing on disk changed between two loads, so nothing need be redrawn."""
        def facts(m: Model) -> tuple:
            return m.cfg, m.units, m.reqs, m.refs, m.topics, m.questions, m.load_problems
        return facts(a) == facts(b)

    def action_next_match(self, direction: int) -> None:
        tree = self.query_one("#nav", Tree)
        line = tree.cursor_line
        while 0 <= (line := line + direction) <= tree.last_line:
            node = tree.get_node_at_line(line)
            if node is not None and node.data and node.data[0] in ("req", "question"):
                tree.cursor_line = line
                return

    # ------------------------------------------------------------- links

    def _links_for(self, data) -> list[str]:
        """A document's cards, in order: the link cursor steps through whole requirements."""
        m = self.m
        kind, key = data
        stem = key if kind == "unit" else key[0]
        return [r.id for r in sorted(m.reqs.values(), key=m.sort_key)
                if r.unit == stem and (kind == "unit" or r.section == key[1]
                                       or r.section.startswith(key[1] + "."))]

    def known(self, target: str) -> bool:
        """A requirement, a question, or a source line that exists."""
        if target.startswith("ref:"):
            file, _, _line = target[4:].rpartition(":")
            return (self.m.cfg.root / file).is_file()
        return self.m.knows(target)

    @staticmethod
    def split_ref(target: str) -> tuple[str, int]:
        file, _, line = target[4:].rpartition(":")
        return file, int(line)

    def _ref_preview(self, target: str) -> Content:
        from rich.style import Style
        from rich.syntax import Syntax
        from rich.text import Span

        file, line = self.split_ref(target)
        rows = render.excerpt(self.m.cfg.root, file, line)
        ref = next((x for x in self.m.refs if x.file == file and x.line == line), None)
        kind = ("test", "bold $rk-accepted") if ref and ref.is_test else ("code", "bold $rk-id")
        head = [Content.assemble(kind, "  ", (f"{file}:{line}", "bold $rk-link"), "  ",
                                 (render.origin(self.m.cfg.root, file, line), "$rk-muted")),
                Content("")]
        if not rows:
            return Content("\n").join(head + [Content.assemble(("unreadable", "$rk-reopened"))])
        style = self.theme if self.theme in ("dracula", "nord", "monokai", "gruvbox-dark",
                                             "solarized-dark", "solarized-light", "one-dark") else \
            ("monokai" if self.current_theme.dark else "default")
        code = Syntax("\n".join(text for _, text in rows), Syntax.guess_lexer(file),
                      theme=style).highlight("\n".join(text for _, text in rows))
        # The theme's token colours, without its background: nothing here paints one.
        code.style = ""
        code.spans[:] = [Span(sp.start, sp.end, Style(color=sp.style.color, bold=sp.style.bold,
                                                      italic=sp.style.italic))
                         for sp in code.spans if isinstance(sp.style, Style)]
        body = []
        for (n, _), text in zip(rows, code.split("\n", allow_blank=True)):
            text.truncate(66 - 4 - 8, overflow="ellipsis")      # the gutter stays a gutter
            mark = (f"{n:>5} ▶ ", "bold $rk-link-active") if n == line else (f"{n:>5} │ ", "$rk-muted")
            body.append(Content.assemble(mark, Content.from_rich_text(text)))
        return Content("\n").join(head + body)

    def preview(self, target: str) -> Content:
        if target.startswith("ref:"):
            return self._ref_preview(target)
        m = self.m
        if target in m.reqs:
            r = m.reqs[target]
            head = [(r.id, "bold $rk-id")]
            if r.title:
                head += ["  ", (r.title, "bold")]
            if m.reviewed(r) and r.status:
                head += ["  ", _status_chip(r.status)]
            if m.progress(r.id).state:
                head += ["  ", _progress_chip(m.progress(r.id).state)]
            lines = [Content.assemble(*head), Content(""), Content(r.statement)]
            if r.satisfies:
                lines.append(Content.assemble(("Satisfies  ", "$rk-muted"), ", ".join(r.satisfies)))
            if r.verification:
                lines.append(Content.assemble(("Verified   ", "$rk-muted"), r.verification))
            return Content("\n").join(lines)
        q = m.question(target)
        if q:
            chip = ("● open", "bold $rk-open") if q.open else ("● answered", "bold $rk-answered")
            answer = q.answer if len(q.answer) < 400 else q.answer[:399] + "…"
            lines = [Content.assemble((q.id, "bold $rk-id"), "  ", (q.title, "bold"), "  ", chip),
                     Content(""), Content(q.question)]
            if answer:
                lines += [Content(""), Content.assemble((answer, "$rk-muted"))]
            return Content("\n").join(lines)
        return Content(target)

    def show_peek(self, target: str, cell: tuple[int, int] | None, title: str = "") -> None:
        """The preview of `target`, beside the cell its link is drawn in.

        Below the link where it fits, above where it does not — never over it,
        as nvim places a hover. With no cell, in the reading pane's corner."""
        peek = self.query_one("#peek", Static)
        content = self.preview(target)
        peek.update(content)
        peek.border_title = title
        width = 66
        # The height it will be drawn at: border 2, padding 2, at most 18 rows.
        height = min(18, peek.get_content_height(self.size, self.size, width - 4) + 2)
        bottom = self.size.height - 1                     # the hint line
        if cell is None:
            view = self.query_one("#view").region
            x, y = view.right - width - 2, view.bottom - height - 1
        else:
            x = cell[0] + 2
            y = cell[1] + 1 if cell[1] + 1 + height <= bottom else cell[1] - height
        peek.styles.offset = (max(0, min(x, self.size.width - width - 1)), max(0, y))
        peek.display = True
        self.refresh_keys()

    def hide_peek(self) -> bool:
        # A preview still being placed would reappear after this.
        if any(w.group == "peek" and w.is_running for w in self.workers):
            self.workers.cancel_group(self, "peek")
        peek = self.query_one("#peek", Static)
        shown = bool(peek.display)
        peek.display = False
        self.hovering = ""
        if shown:
            self.refresh_keys()
        return shown

    def on_mouse_move(self, event: events.MouseMove) -> None:
        action = event.style.meta.get("@click", "") if event.style else ""
        mm = TARGET_RE.search(action) if action else None
        target = mm.group(1) if mm else ""
        if target and self.known(target):
            if target != self.hovering:
                self.show_peek(target, (event.screen_x, event.screen_y))
                self.hovering = target
        elif self.hovering:
            self.hide_peek()

    @on(Markdown.LinkClicked)
    def _markdown_link(self, event: Markdown.LinkClicked) -> None:
        if event.href.startswith("reqdeck:"):
            event.stop()
            self.action_goto(event.href.removeprefix("reqdeck:"))

    def _page(self) -> Widget | None:
        pages = list(self.query_one("#view").query(".page"))
        return pages[-1] if pages else None

    @staticmethod
    def _targets_in(w: Widget) -> list[str]:
        """Link targets a widget draws, in order."""
        if isinstance(w, Markdown):
            return re.findall(r"\(reqdeck:([^)\s]+)\)", w.source)
        if isinstance(w, Static) and isinstance(w.content, Content):
            spans = sorted(w.content.spans, key=lambda sp: sp.start)
            return [mm.group(1) for sp in spans if (mm := TARGET_RE.search(str(sp.style)))]
        return []

    def _ensure_links(self) -> list[str]:
        if not self._filled:
            return []
        if self.links is None:
            page = self._page()
            own = self.shown[1] if self.shown else None
            found = [t for w in (page.query("*") if page else []) for t in self._targets_in(w)]
            self.links = [t for t in dict.fromkeys(found) if t != own and self.known(t)]
        return self.links

    def _holder(self, target: str) -> Widget | None:
        """The first widget on the page that draws a link to `target`."""
        page = self._page()
        for w in page.query("*") if page else []:
            if target in self._targets_in(w):
                return w
        return None

    def _locate(self, target: str) -> tuple[int, int] | None:
        """The screen cell the link to `target` is drawn in, if it is in view."""
        view = self.query_one("#view")
        w = self._holder(target)
        if w is None:
            return None
        area = w.region.intersection(view.region.shrink((1, 1, 1, 1)))
        for y in range(area.y, area.bottom):
            for x in range(area.x, area.right):
                mm = TARGET_RE.search(str(self.screen.get_style_at(x, y).meta.get("@click", "")))
                if mm and mm.group(1) == target:
                    return x, y
        return None

    def action_cycle_link(self, direction: int) -> None:
        links = self._ensure_links()
        if not links:
            self.notify("Nothing here links anywhere.")
            return
        self.link_index = (self.link_index + direction) % len(links)
        target = links[self.link_index]
        # The last preview may cover the next link, which then cannot be found on screen.
        self.hide_peek()
        self.query_one("#view").add_class("-linking")
        kind = self.shown[0] if self.shown else ""
        if kind in ("unit", "section"):
            # A document: the cursor is on whole cards, so no re-render is needed.
            for card in self.query(".card.-selected"):
                card.remove_class("-selected")
            try:
                card = self.query(f"#card-{target}").last()
                card.add_class("-selected")
                card.scroll_visible(animate=False, top=True)
                self.query_one("#view").add_class("-linking")
            except Exception:
                pass
            self.action_peek_link()
        else:
            self.show(self.shown, sel=target)
            self.action_peek_link(reveal=True)

    def action_peek_link(self, reveal: bool = False) -> None:
        """Preview the selected link beside it — in a worker, since the page may
        not be drawn yet and the link may first have to be scrolled to. A newer
        `tab` cancels an older one still looking."""
        links = self._ensure_links()
        if not links:
            return
        if self.link_index < 0:
            self.link_index = 0
        self.run_worker(self._peek(links[self.link_index], reveal), exclusive=True, group="peek")

    async def _frame(self) -> None:
        await asyncio.sleep(0.02)

    async def _still(self, view: Widget) -> None:
        """Until the pane has stopped scrolling: scroll_visible lands a frame or two late."""
        last = None
        for _ in range(10):
            await self._frame()
            if view.scroll_y == last:
                return
            last = view.scroll_y

    async def _peek(self, target: str, reveal: bool) -> None:
        links = self.links or []
        verb = f"enter opens in {editor.command(self.m.cfg.editor, 'x', 1)[0][0].rsplit('/', 1)[-1]}" \
            if target.startswith("ref:") else "enter to follow"
        title = f" link {self.link_index + 1}/{len(links)} · {verb} "
        view = self.query_one("#view", ReadingPane)
        spot = None
        if self.shown and self.shown[0] in ("unit", "section"):
            await self._frame()
            try:
                card = self.query(f"#card-{target}").last().region
                spot = (card.x + 2, card.y + 1)     # the ID in the card's head, as a hover sees it
            except Exception:
                pass
        else:
            holder = None
            for _ in range(15):                     # the page mounted, laid out and drawn
                holder = self._holder(target)
                if holder is not None and holder.region.height:
                    break
                await self._frame()
            if holder is not None:
                if reveal:
                    view.scroll_to(y=getattr(self, "_restore_scroll", 0), animate=False)
                    await self._still(view)
                    holder.scroll_visible(animate=False)
                    await self._still(view)
                for _ in range(40):                 # down through a tall widget, a page at a time
                    spot = self._locate(target)
                    if spot is not None:
                        break
                    await self._frame()
                    spot = self._locate(target)
                    if spot is not None or not reveal:
                        break
                    inside = holder.region.bottom > view.region.bottom - 1
                    if not inside or view.scroll_y >= view.max_scroll_y:
                        break
                    view.scroll_relative(y=max(1, view.size.height - 2), animate=False)
                    await self._still(view)
        self.show_peek(target, spot, title)

    def open_in_editor(self, file: str, line: int) -> None:
        """`file` at `line` in the configured editor. A terminal editor gets the
        terminal until it exits; a windowed one is launched and left running."""
        argv, terminal = editor.command(self.m.cfg.editor, file, line)
        self.hide_peek()
        try:
            if terminal:
                with self.suspend():
                    subprocess.run(argv, cwd=self.m.cfg.root)
                self.reload()
            else:
                subprocess.Popen(argv, cwd=self.m.cfg.root, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
        except Exception as e:   # a missing editor, or no terminal to hand over
            self.notify(f"Could not run {argv[0]}: {e}", severity="error")

    def action_follow_or_toggle(self) -> None:
        """`enter`: follow the selected link, or with none selected open or close the node."""
        if self.link_index >= 0:
            self.action_follow_link()
            return
        tree = self.query_one("#nav", Tree)
        node = tree.cursor_node
        if node is not None and node.allow_expand:
            node.toggle()

    def drop_link(self) -> bool:
        """Clear the link cursor and its preview. Whether there was one."""
        if self.link_index < 0 and not self.hide_peek():
            return False
        self.hide_peek()
        had = self.link_index >= 0
        self.link_index = -1
        view = self.query_one("#view")
        view.remove_class("-linking")
        for card in self.query(".card.-selected"):
            card.remove_class("-selected")
        if had and self.shown and self.shown[0] not in ("unit", "section"):
            self.show(self.shown, keep=True)
        return True

    def action_escape(self) -> None:
        if not self.drop_link():
            self.action_clear()

    def action_scroll_view(self, pages: float) -> None:
        view = self.query_one("#view")
        lines = int(pages * max(1, view.size.height)) if abs(pages) < 1 else int(pages)
        view.scroll_relative(y=lines, animate=False)

    def action_follow_link(self) -> None:
        self._ensure_links()
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
        if target.startswith("ref:"):
            self.open_in_editor(*self.split_ref(target))
            return
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
            self.refresh_keys()
            self.notify(f"{r.id} accepted")

        self.push_screen(Confirm(f"Accept {r.id} — {r.label}?\n\nYou have read it and agree with it."), done)


def main() -> int:
    ReqdeckApp().run()
    return 0
