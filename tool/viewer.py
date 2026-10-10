"""The reqkit TUI: requirements as documents, with their sections, and the open
questions beside them. Reads through the same model as the CLI and writes
through the same operations.

Needs `textual`, which the CLI does not.
"""

from __future__ import annotations

import re
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, Markdown, Tree
from textual.widgets.tree import TreeNode

from . import ops, render
from .cli import load_model
from .model import Model, Req

STATUS_STYLE = {"Accepted": ("A", "green"), "Proposed": ("P", "yellow"), "Reopened": ("R", "red")}


def _req_label(m: Model, r: Req) -> Text:
    t = Text()
    if m.reviewed(r):
        mark, style = STATUS_STYLE.get(r.status, ("?", "magenta"))
        t.append(f"{mark} ", style=style)
    t.append(r.id, style="bold")
    t.append(f"  {r.label}")
    return t


class Confirm(ModalScreen[bool]):
    DEFAULT_CSS = """
    Confirm { align: center middle; }
    Confirm > Vertical { width: 72; height: auto; padding: 1 2; border: thick $accent; background: $surface; }
    Confirm Horizontal { height: auto; margin-top: 1; }
    Confirm Button { margin-right: 2; }
    """
    BINDINGS = [Binding("escape", "dismiss(False)", "Cancel"), Binding("y", "dismiss(True)", "Yes")]

    def __init__(self, message: str):
        super().__init__()
        self.message = message

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self.message)
            with Horizontal():
                yield Button("Accept", variant="success", id="yes")
                yield Button("Cancel", id="no")

    @on(Button.Pressed)
    def _pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")


class ReqkitApp(App):
    TITLE = "reqkit"
    CSS = """
    #left { width: 45%; min-width: 40; }
    #nav { height: 1fr; }
    #search { margin: 0 0 1 0; }
    #view { padding: 0 2; }
    """
    BINDINGS = [
        Binding("/", "search", "Search"),
        Binding("escape", "clear", "Clear search", show=False),
        Binding("a", "accept", "Accept"),
        Binding("o", "toggle_open", "Open questions only"),
        Binding("r", "reload", "Reload"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, script: Path | None = None):
        super().__init__()
        self.script = script
        self.m: Model = load_model(script)
        self.query_text = ""
        self.open_only = False
        self.sub_title = str(self.m.cfg.root)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left"):
                yield Input(placeholder="Search — regex over id, title, statement, detail", id="search")
                yield Tree("reqkit", id="nav")
            with VerticalScroll(id="view"):
                yield Markdown(id="doc")
        yield Footer()

    def on_mount(self) -> None:
        self.rebuild()
        self.query_one("#nav", Tree).focus()

    # ------------------------------------------------------------- the tree

    def _matches(self, *texts: str) -> bool:
        if not self.query_text:
            return True
        try:
            pat = re.compile(self.query_text, re.I)
        except re.error:
            return any(self.query_text.lower() in t.lower() for t in texts)
        return any(pat.search(t) for t in texts)

    def rebuild(self) -> None:
        m = self.m
        tree = self.query_one("#nav", Tree)
        tree.clear()
        tree.show_root = False
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
            label = Text.assemble((t, "bold"), f"  {title}  ", (f"{n_open} open", "red" if n_open else "dim"))
            t_node = q_root.add(label, data=("topic", t), expand=searching or self.open_only)
            for q in qs:
                mark = ("open ", "red") if q.open else ("done ", "dim")
                t_node.add_leaf(Text.assemble(mark, (q.id, "bold"), f"  {q.title}"), data=("question", q.id))

    def _add_document(self, u_node: TreeNode, unit) -> None:
        stack: list[tuple[int, TreeNode]] = [(0, u_node)]
        searching = bool(self.query_text)
        for e in self.m.document(unit):
            if e["type"] == "section":
                while stack and stack[-1][0] >= e["depth"]:
                    stack.pop()
                s = e["section"]
                node = stack[-1][1].add(Text.assemble((e["number"], "bold cyan"), f" {s.title}"),
                                        data=("section", (unit.stem, s.key)), expand=searching)
                stack.append((e["depth"], node))
            else:
                r: Req = e["req"]
                if self._matches(r.id, r.title, r.statement, r.rationale, r.detail):
                    stack[-1][1].add_leaf(_req_label(self.m, r), data=("req", r.id))
        if searching:
            self._drop_empty_sections(u_node)

    def _drop_empty_sections(self, node: TreeNode) -> None:
        for child in list(node.children):
            if child.data and child.data[0] == "section":
                self._drop_empty_sections(child)
                if not child.children:
                    child.remove()

    # ------------------------------------------------------------- the view

    @on(Tree.NodeHighlighted)
    def _highlighted(self, event: Tree.NodeHighlighted) -> None:
        self.show(event.node.data)

    def show(self, data) -> None:
        if not data:
            return
        m = self.m
        kind, key = data
        md = ""
        if kind == "req" and key in m.reqs:
            md = render.requirement(m, m.reqs[key], chain=True)
        elif kind == "unit":
            md = render.document(m, m.unit(key))
        elif kind == "section":
            stem, skey = key
            u = m.unit(stem)
            s = u.section(skey)
            num = u.numbering()[skey]
            parts = [f"# {num} {s.title}", "", s.description, ""]
            parts += [render.requirement(m, r, heading="###")
                      for r in sorted(m.reqs.values(), key=m.sort_key)
                      if r.unit == stem and (r.section == skey or r.section.startswith(skey + "."))]
            md = "\n".join(parts)
        elif kind == "level":
            lv = m.cfg.level(key)
            rows = "\n".join(
                f"| {u.title} | {', '.join(u.prefixes)} | {sum(1 for r in m.reqs.values() if r.unit == u.stem)} "
                f"| `{m.cfg.rel(u.csv_path)}` |" for u in m.units if u.level == key)
            md = (f"# {lv.kind} — {lv.title}\n\nSatisfies: {', '.join(lv.satisfies) or 'top level'}\n\n"
                  f"| Unit | Prefix | Requirements | File |\n|---|---|---|---|\n{rows}\n")
        elif kind == "topic":
            qs = [q for q in m.questions if q.topic == key]
            rows = "\n".join(f"| {q.id} | {'**open**' if q.open else 'answered'} | {q.title} |" for q in qs)
            n_reqs = sum(1 for r in m.reqs.values() if key in r.topics)
            md = (f"# Topic {key} — {m.topics.get(key, '')}\n\n{n_reqs} requirement(s) name this topic.\n\n"
                  f"| | | |\n|---|---|---|\n{rows}\n")
        elif kind == "question":
            q = next(q for q in m.questions if q.id == key)
            md = render.question(q, m.topics.get(q.topic, ""))
        self.query_one("#doc", Markdown).update(md)
        self.query_one("#view", VerticalScroll).scroll_home(animate=False)

    # ------------------------------------------------------------- actions

    @on(Input.Changed, "#search")
    def _search(self, event: Input.Changed) -> None:
        self.query_text = event.value.strip()
        self.rebuild()

    @on(Input.Submitted, "#search")
    def _submitted(self, event: Input.Submitted) -> None:
        self.query_one("#nav", Tree).focus()

    def action_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_clear(self) -> None:
        inp = self.query_one("#search", Input)
        inp.value = ""
        self.query_one("#nav", Tree).focus()

    def action_toggle_open(self) -> None:
        self.open_only = not self.open_only
        self.rebuild()

    def action_reload(self) -> None:
        self.m = load_model(self.script)
        self.rebuild()
        self.notify("Reloaded")

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
            node.set_label(_req_label(self.m, r))
            self.show(node.data)
            self.notify(f"{r.id} accepted")

        self.push_screen(Confirm(f"Accept {r.id} — {r.label}?\n\nYou have read it and agree with it."), done)


def main(script: Path | None = None) -> int:
    ReqkitApp(script).run()
    return 0
