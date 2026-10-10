"""The `reqdeck` command line. Logic lives in the model; this file only asks and prints.

Every command takes --json for machine-readable output.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from . import __version__, config, ops, render, store
from .config import STATUS
from .markers import Ref
from .model import Model, Req, split

BOLD, DIM, RED, RESET = "\033[1m", "\033[2m", "\033[31m", "\033[0m"

EDITABLE = ops.EDITABLE


def _c(s: str, code: str) -> str:
    return s if not sys.stdout.isatty() else f"{code}{s}{RESET}"


def _err(msg: str) -> int:
    print(msg, file=sys.stderr)
    return 1


def _label(m: Model, rid: str) -> str:
    r = m.reqs.get(rid)
    return f"{rid} — {r.label}" if r else f"{rid} {_c('(undefined)', DIM)}"


def _print_branch(m: Model, rid: str, direction: str, prefix: str = "", seen=None):
    seen = seen if seen is not None else set()
    nxt = m.reqs[rid].satisfies if direction == "up" else m.satisfied_by.get(rid, [])
    nxt = [n for n in nxt if n not in seen] if direction == "up" else nxt
    for i, child in enumerate(nxt):
        last = i == len(nxt) - 1
        print(f"{prefix}{'└─ ' if last else '├─ '}{_label(m, child)}")
        if child in m.reqs and child not in seen:
            seen.add(child)
            _print_branch(m, child, direction, prefix + ("   " if last else "│  "), seen)


def _find(m: Model, rid: str) -> Req | None:
    r = m.reqs.get(rid) or m.reqs.get(rid.upper())
    if r is None:
        print(f"No such requirement: {rid}", file=sys.stderr)
        near = sorted(k for k in m.reqs if rid.upper() in k.upper())
        if near:
            print("Did you mean: " + ", ".join(near[:8]), file=sys.stderr)
    return r


# --------------------------------------------------------------------- queries

def cmd_get(m: Model, args) -> int:
    r = _find(m, args.id)
    if r is None:
        return 1
    rid = r.id
    refs = m.refs_for(rid)
    if args.json:
        print(json.dumps({
            **r.to_dict(),
            "topic_titles": {t: m.topics.get(t, "") for t in r.topics},
            "satisfies_transitive": m.up(rid),
            "satisfied_by": m.satisfied_by.get(rid, []),
            "satisfied_by_transitive": m.down(rid),
            "code_refs": [asdict(x) for x in refs if not x.is_test],
            "test_refs": [asdict(x) for x in refs if x.is_test],
            "covering_test_refs": [asdict(x) for x in m.covering_refs(rid) if x.is_test],
        }, indent=2))
        return 0

    print(_c(f"{r.id} — {r.label}", BOLD))
    print(f"{_c(r.file + ':' + str(r.line), DIM)}\n")
    if r.statement:
        print(f"  {r.statement}")
    if r.detail:
        print("\n" + "\n".join("  " + ln for ln in r.detail.splitlines()))
    if r.rationale:
        print(f"\n  {_c('Rationale:', DIM)} {r.rationale}")
    if r.source:
        print(f"  {_c('Source:', DIM)} {r.source}")
    if r.topics:
        print(f"  {_c('Topic:', DIM)} " + ", ".join(f"{t} {m.topics.get(t, '?')}" for t in r.topics))
    if r.verification:
        v = m.cfg.verification.get(r.verification)
        print(f"  {_c('Verification:', DIM)} {r.verification} — {v.name if v else '?'}")
    if r.status:
        print(f"  {_c('Status:', DIM)} {r.status}")
    if r.security:
        print(f"  {_c('Security relevant:', DIM)} {r.security}")
    for k, v in r.extra.items():
        print(f"  {_c(k.capitalize() + ':', DIM)} {v}")

    print(f"\n{_c('Satisfies (up)', BOLD)}")
    if r.satisfies:
        _print_branch(m, rid, "up")
    else:
        lv = m.cfg.level(r.kind)
        print(f"  {_c('nothing — orphan' if lv and lv.satisfies else 'top level', DIM)}")
    print(f"\n{_c('Satisfied by (down)', BOLD)}")
    if m.satisfied_by.get(rid):
        _print_branch(m, rid, "down")
    else:
        print(f"  {_c('nothing yet', DIM)}")

    def _ref_line(x: Ref) -> str:
        return f"  {x.file}:{x.line}" + (f"  {_c(x.note, DIM)}" if x.note else "")

    code = [x for x in refs if not x.is_test]
    test = [x for x in refs if x.is_test]
    cover = [x for x in m.covering_refs(rid) if x.is_test and x.id != rid]
    print(f"\n{_c('Code', BOLD)}")
    print("\n".join(_ref_line(x) for x in code) or f"  {_c('none', DIM)}")
    print(f"\n{_c('Tests', BOLD)}")
    print("\n".join(_ref_line(x) for x in test) or f"  {_c('none', DIM)}")
    if cover:
        print(f"  {_c('via children:', DIM)}")
        for x in cover:
            print(f"    {x.file}:{x.line} {_c('(' + x.id + ')', DIM)}")
    return 0


def _print_reqs(m: Model, rs: list[Req], long: bool, noun=("requirement", "requirements")) -> None:
    for r in rs:
        v = f"[{r.verification}]" if r.verification else "[ ]"
        t = f"{'/'.join(r.topics):<5}" if r.topics else "  -  "
        st = r.status[0] if r.status else "-"
        print(f"{v} {t} {st} {_c(r.id, BOLD):<28} {r.label}")
        if long and r.statement and r.statement != r.label:
            print(f"        {_c(r.statement, DIM)}\n")
    sys.stdout.flush()
    print(f"{len(rs)} {noun[0] if len(rs) == 1 else noun[1]}", file=sys.stderr)


def cmd_search(m: Model, args) -> int:
    pat = re.compile(args.query, re.I)
    hits = [r for r in m.reqs.values()
            if any(pat.search(s) for s in (r.id, r.title, r.statement, r.rationale, r.detail))]
    hits.sort(key=m.sort_key)
    if args.json:
        print(json.dumps([r.to_dict() for r in hits], indent=2))
        return 0
    _print_reqs(m, hits, args.long, ("match", "matches"))
    return 0


def cmd_list(m: Model, args) -> int:
    rs = list(m.reqs.values())
    if args.kind:
        rs = [r for r in rs if r.kind.upper() == args.kind.upper()]
    if args.unit:
        u = m.unit(args.unit)
        if u is None:
            # A bare unit code, as in TSSR_FWN's FWN.
            rs = [r for r in rs if r.prefix.upper().endswith("_" + args.unit.upper())]
        else:
            rs = [r for r in rs if r.unit == u.stem]
    if args.verification:
        rs = [r for r in rs if r.verification == args.verification.upper()]
    if args.status:
        rs = [r for r in rs if r.status == args.status.capitalize()]
    if args.topic:
        want = args.topic.zfill(2)
        rs = [r for r in rs if want in r.topics]
    if args.section:
        rs = [r for r in rs if r.section == args.section or r.section.startswith(args.section + ".")]
    if args.security:
        rs = [r for r in rs if r.security == "Yes"]
    rs.sort(key=m.sort_key)
    if args.json:
        print(json.dumps([r.to_dict() for r in rs], indent=2))
        return 0
    _print_reqs(m, rs, args.long)
    return 0


def cmd_tree(m: Model, args) -> int:
    r = _find(m, args.id)
    if r is None:
        return 1
    if args.json:
        print(json.dumps({"id": r.id, "up": m.up(r.id), "down": m.down(r.id)}, indent=2))
        return 0
    if not args.down:
        print(_c("Satisfies (up)", BOLD))
        print(f"  {_label(m, r.id)}")
        _print_branch(m, r.id, "up", "  ")
    if not args.up:
        print(_c("\nSatisfied by (down)", BOLD))
        print(f"  {_label(m, r.id)}")
        _print_branch(m, r.id, "down", "  ")
    return 0


GAP_LABELS = [
    ("dangling", "Satisfies a requirement that does not exist", True),
    ("orphans", "No satisfies link — traces to nothing", False),
    ("unsatisfied", "Nothing satisfies it yet", False),
    ("untested", "Verification is automated, but no test references it or its children", False),
    ("uncoded", "Implemented in software, but no code reference", False),
    ("not_accepted", "Not yet accepted — awaiting review by the user", False),
]


def cmd_coverage(m: Model, args) -> int:
    g = m.gaps()
    if args.json:
        print(json.dumps(g, indent=2))
        return 0
    counts = ", ".join(f"{sum(1 for r in m.reqs.values() if r.kind == lv.kind)} {lv.kind}"
                       for lv in m.cfg.levels)
    print(_c(f"{len(m.reqs)} requirements  ({counts})", BOLD))
    print(f"{len(m.refs)} @REQ_REF marker(s) in source\n")
    clean = True
    for key, label, hard in GAP_LABELS:
        items = g[key]
        if not items:
            continue
        clean = False
        print(f"{'!!' if hard else '  '} {_c(label, BOLD)}  ({len(items)})")
        for it in items:
            if isinstance(it, dict):
                print(f"     {it['id']} -> {it['missing']}")
            else:
                print(f"     {it:<28} {m.reqs[it].label}")
        print()
    if clean:
        print("No gaps.")
    return 0


def cmd_trace(m: Model, args) -> int:
    """Is each named requirement actually referenced from source and test?

    The per-requirement form of `coverage`, for gating one change rather than
    surveying the whole tree — a change claiming to implement something should
    be the thing that makes it traced.
    """
    problems: list[str] = []
    results: list[dict] = []
    for rid in args.ids:
        r = m.reqs.get(rid)
        if r is None:
            problems.append(f"{rid}: no such requirement")
            continue
        if not m.traced(r):
            below = ", ".join(m.satisfied_by.get(rid, [])) or "nothing yet"
            problems.append(f"{rid}: is a {r.kind}, which no code references directly — "
                            f"name what satisfies it instead ({below})")
            continue
        code = [x for x in m.refs_for(rid) if not x.is_test]
        test = [x for x in m.covering_refs(rid) if x.is_test]
        needs_code = m.code_bearing(rid)
        needs_test = m.automated(r)
        if needs_code and not code:
            problems.append(f"{rid}: no code reference — put @REQ_REF({rid}) on what implements it")
        if needs_test and not test:
            problems.append(f"{rid}: verification is {r.verification}, so a test must name it — "
                            f"add @REQ_REF({rid}) to the test function")
        results.append({"id": rid, "verification": r.verification, "status": r.status,
                        "code_refs": [asdict(x) for x in code],
                        "test_refs": [asdict(x) for x in test],
                        "needs_code": needs_code, "needs_test": needs_test})
    if args.json:
        print(json.dumps({"ok": not problems, "problems": problems, "requirements": results}, indent=2))
        return 1 if problems else 0
    for res in results:
        marks = [f"{len(res['code_refs'])} code" if res["needs_code"] else "code n/a",
                 f"{len(res['test_refs'])} test" if res["needs_test"]
                 else f"test n/a ({res['verification']})"]
        print(f"  {res['id']:<16} {', '.join(marks)}")
    for prob in problems:
        print(_c(f"  {prob}", RED))
    if problems:
        print(f"\n{len(problems)} untraced")
        return 1
    print(f"\n{len(results)} traced")
    return 0


def cmd_check(m: Model, args) -> int:
    problems = m.problems()
    if args.json:
        print(json.dumps({"ok": not problems, "problems": problems,
                          "status": m.status_tally()}, indent=2))
        return 1 if problems else 0
    for p in problems:
        print(p)
    print(f"\n{len(problems)} problem(s)" if problems else "OK")
    _print_maturity(m)
    return 1 if problems else 0


def _print_maturity(m: Model) -> None:
    """Status tally. Informational — never fails the check.

    Everything starts Proposed, so failing on it would make check useless as a
    gate. Full maturity is every requirement Accepted, linked, and referenced
    from code and tests; this is the acceptance third of that."""
    counts = m.status_tally()
    total = sum(counts.values())
    if not total:
        return
    bits = [f"{counts[k]} {k.lower()}" for k in ("Accepted", "Proposed", "Reopened") if counts[k]]
    if counts["missing"]:
        bits.append(f"{counts['missing']} without a status")
    print(f"Status: {', '.join(bits)} of {total} — {100 * counts['Accepted'] // total}% accepted")


def cmd_topics(m: Model, args) -> int:
    reqs = {t: [] for t in m.topics}
    for r in m.reqs.values():
        for t in r.topics:
            reqs.setdefault(t, []).append(r.id)
    qs: dict[str, list] = {t: [] for t in m.topics}
    for q in m.questions:
        qs.setdefault(q.topic, []).append(q)
    if args.json:
        print(json.dumps({t: {"title": m.topics.get(t, ""),
                              "open": [q.id for q in qs.get(t, []) if q.open],
                              "answered": [q.id for q in qs.get(t, []) if not q.open],
                              "requirements": sorted(reqs.get(t, []))}
                          for t in sorted(set(reqs) | set(qs))}, indent=2))
        return 0
    print(_c(f"  {'':2}  {'':<32} {'open':>5} {'done':>5} {'reqs':>5}", DIM))
    for t, title in sorted(m.topics.items()):
        n_open = sum(1 for q in qs.get(t, []) if q.open)
        n_done = len(qs.get(t, [])) - n_open
        n = len(reqs.get(t, []))
        print(f"  {_c(t, BOLD)}  {title:<32} {n_open:>5} {n_done:>5} {n:>5}")
    return 0


def cmd_questions(m: Model, args) -> int:
    qs = m.questions
    if args.topic:
        qs = [q for q in qs if q.topic == args.topic.zfill(2)]
    if args.open:
        qs = [q for q in qs if q.open]
    if args.answered:
        qs = [q for q in qs if not q.open]
    if args.json:
        print(json.dumps([{**asdict(q), "open": q.open} for q in qs], indent=2))
        return 0
    for q in qs:
        mark = _c("open", RED) if q.open else _c("done", DIM)
        print(f"{mark}  {_c(q.id, BOLD)}  {q.title}")
        if args.long and q.question:
            print(f"         {_c(q.question, DIM)}\n")
    sys.stdout.flush()
    print(f"{len(qs)} question" + ("" if len(qs) == 1 else "s"), file=sys.stderr)
    return 0


def cmd_verification(m: Model, args) -> int:
    if args.json:
        print(json.dumps({k: {"name": v.name, "definition": v.definition, "automated": v.automated}
                          for k, v in m.cfg.verification.items()}, indent=2))
        return 0
    for k, v in m.cfg.verification.items():
        auto = _c(" (automated)", DIM) if v.automated else ""
        print(f"{_c(k, BOLD)} — {_c(v.name, BOLD)}{auto}\n  {v.definition}\n")
    return 0


def cmd_levels(m: Model, args) -> int:
    if args.json:
        print(json.dumps([{**asdict(lv), "units": [u.stem for u in m.units if u.level == lv.kind]}
                          for lv in m.cfg.levels], indent=2))
        return 0
    for lv in m.cfg.levels:
        up = ", ".join(lv.satisfies) or "top level"
        print(f"{_c(lv.kind, BOLD)} — {lv.title}  {_c('satisfies ' + up, DIM)}")
        for u in (u for u in m.units if u.level == lv.kind):
            n = sum(1 for r in m.reqs.values() if r.unit == u.stem)
            print(f"    {', '.join(u.prefixes):<14} {u.title:<36} {n:>4}  {_c(m.cfg.rel(u.csv_path), DIM)}")
    return 0


# ------------------------------------------------------------------- documents

def cmd_doc(m: Model, args) -> int:
    unit = m.unit(args.unit)
    if unit is None:
        return _err(f"No unit {args.unit!r}. `reqdeck levels` lists them.")
    if args.json:
        entries = []
        for e in m.document(unit):
            if e["type"] == "section":
                s = e["section"]
                entries.append({"type": "section", "depth": e["depth"], "number": e["number"],
                                "key": s.key, "title": s.title, "description": s.description})
            else:
                entries.append({"type": "req", "depth": e["depth"], **e["req"].to_dict()})
        print(json.dumps({"unit": unit.stem, "title": unit.title, "entries": entries}, indent=2))
        return 0
    if args.markdown:
        sys.stdout.write(render.document(m, unit))
        return 0
    print(_c(unit.title, BOLD))
    if unit.description:
        print(_c(unit.description, DIM))
    for e in m.document(unit):
        if e["type"] == "section":
            ind = "  " * (e["depth"] - 1)
            print(f"\n{ind}{_c(e['number'] + ' ' + e['section'].title, BOLD)}")
        else:
            r = e["req"]
            ind = "  " * e["depth"]
            print(f"{ind}{_c(r.id, BOLD)} {r.label}")
    return 0


# --------------------------------------------------------------------- writing

def cmd_add(m: Model, args) -> int:
    fields = {"title": args.title, "statement": args.statement, "rationale": args.rationale,
              "satisfies": args.satisfies, "topic": args.topic, "source": args.source,
              "verification": args.verification or "", "security": "yes" if args.security else "",
              "section": args.section}
    for k, v in args.field or []:
        fields[k] = v
    try:
        rid, rel, line = ops.add(m, args.prefix, fields)
    except ops.OpError as e:
        return _err(str(e))
    if args.json:
        print(json.dumps({"id": rid, "file": rel, "line": line}, indent=2))
    else:
        print(f"{_c(rid, BOLD)} added to {rel}:{line}")
        lv = m.cfg.level(m.unit(args.prefix).level)
        if not lv or lv.reviewed:
            print(_c("Status is Proposed. Only the user marks a requirement Accepted.", DIM))
    return 0


def cmd_edit(m: Model, args) -> int:
    r = _find(m, args.id)
    if r is None:
        return 1
    changes = {k: getattr(args, k) for k in EDITABLE if getattr(args, k) is not None}
    for k, v in args.field or []:
        changes[k] = v
    try:
        changed, reopened = ops.edit(m, r.id, changes)
    except ops.OpError as e:
        return _err(str(e))
    if args.json:
        print(json.dumps({"id": r.id, "changed": changed, "reopened": reopened}, indent=2))
    else:
        print(f"{_c(r.id, BOLD)} updated: {', '.join(changed)}")
        if reopened:
            print(_c("It was Accepted, so it is now Reopened and needs the user's review again. "
                     "Say what changed in source.", DIM))
    return 0


def cmd_fmt(m: Model, args) -> int:
    changed = []
    for u in m.units:
        try:
            rows = store.read_rows(u)
        except store.StoreError as e:
            return _err(str(e))
        if not store.is_canonical(u, rows):
            store.write_rows(u, [r.values for r in rows])
            changed.append(m.cfg.rel(u.csv_path))
    if args.json:
        print(json.dumps({"rewritten": changed}, indent=2))
    else:
        print("\n".join(f"rewrote {c}" for c in changed) or "Already canonical.")
    return 0


def cmd_unit(m: Model, args) -> int:
    lv = m.cfg.level(args.level)
    if lv is None:
        return _err(f"No level {args.level!r} in .reqdeck.toml — one of "
                    f"{', '.join(x.kind for x in m.cfg.levels)}")
    prefixes = split(args.prefix)
    for p in prefixes:
        if m.unit(p):
            return _err(f"{p} is already a unit.")
    if args.columns:
        columns = ["id"] + [c for c in split(args.columns) if c != "id"]
    elif not lv.reviewed:
        columns = list(store.STORY_COLUMNS)
    else:
        columns = [c for c in store.STANDARD if lv.topic or c != "topic"]
    try:
        u = store.create_unit(m.cfg.requirements, args.file, lv.kind, prefixes,
                              args.title, args.code, columns)
    except store.StoreError as e:
        return _err(str(e))
    if args.json:
        print(json.dumps({"unit": u.stem, "csv": m.cfg.rel(u.csv_path),
                          "toml": m.cfg.rel(u.toml_path)}, indent=2))
    else:
        print(f"Created {m.cfg.rel(u.csv_path)} and {m.cfg.rel(u.toml_path)}")
    return 0


# ------------------------------------------------------------------------ links

def _repo_slug(root: Path) -> str:
    try:
        url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
    mm = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    return mm.group(1) if mm else ""


def cmd_url(m: Model, args) -> int:
    """A link to where a requirement is written, for pasting into an issue.

    Rows are only ever appended, so a row's line number is as stable as its ID
    and the link can name it directly."""
    repo = _repo_slug(m.cfg.root)
    out = []
    for rid in args.ids:
        r = m.reqs.get(rid)
        if r is None:
            return _err(f"no such requirement: {rid}")
        url = f"https://github.com/{repo}/blob/{args.ref}/{r.file}?plain=1#L{r.line}" if repo else ""
        out.append({"id": rid, "title": r.title, "url": url, "markdown": f"[{rid}]({url})"})
    if args.json:
        print(json.dumps(out, indent=2))
        return 0
    for o in out:
        print(o["markdown"] if args.markdown else o["url"])
    return 0


# ------------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reqdeck", description="Requirements, open questions and traceability.")
    p.add_argument("--version", action="version", version=f"reqdeck {__version__}")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="set this directory up as a reqdeck project, asking as it goes")
    sub.add_parser("tui", help="browse the requirements and open questions")
    sk = sub.add_parser("skills", help="copy the agent skills into .claude/skills and .agents/skills")
    sk.add_argument("--update", action="store_true",
                    help="replace reqdeck's own copies with this version's; never a folder of yours")

    g = sub.add_parser("get", help="one requirement, with its chain up and down")
    g.add_argument("id")
    g.set_defaults(fn=cmd_get)

    s = sub.add_parser("search", help="regex over id, title, statement, rationale, detail")
    s.add_argument("query")
    s.add_argument("-l", "--long", action="store_true", help="include statements")
    s.set_defaults(fn=cmd_search)

    ls = sub.add_parser("list", help="all requirements, filterable")
    ls.add_argument("--kind", help="a level from .reqdeck.toml, e.g. TSR")
    ls.add_argument("--unit", help="file stem or prefix, e.g. firmware-node or TSSR_FWN")
    ls.add_argument("--topic", help="OPEN-QUESTIONS topic number, e.g. 06")
    ls.add_argument("--section", help="section key; includes its subsections")
    ls.add_argument("--verification")
    ls.add_argument("--status", choices=list(STATUS) + [k.lower() for k in STATUS],
                    help="review status; P/A/R shown in the third column")
    ls.add_argument("--security", action="store_true", help="only security-relevant requirements")
    ls.add_argument("-l", "--long", action="store_true", help="include statements")
    ls.set_defaults(fn=cmd_list)

    t = sub.add_parser("tree", help="trace chain in one or both directions")
    t.add_argument("id")
    t.add_argument("--up", action="store_true", help="only what it satisfies")
    t.add_argument("--down", action="store_true", help="only what satisfies it")
    t.set_defaults(fn=cmd_tree)

    sub.add_parser("coverage", help="where traceability is missing").set_defaults(fn=cmd_coverage)

    tr = sub.add_parser("trace", help="are these requirements referenced from source and test")
    tr.add_argument("ids", nargs="+", metavar="ID")
    tr.set_defaults(fn=cmd_trace)

    sub.add_parser("check", help="validate everything; exit 1 on any problem").set_defaults(fn=cmd_check)

    sub.add_parser("topics", help="topics with open and answered questions and requirement counts") \
        .set_defaults(fn=cmd_topics)

    q = sub.add_parser("questions", help="open questions, filterable")
    q.add_argument("--topic")
    q.add_argument("--open", action="store_true", help="only unanswered")
    q.add_argument("--answered", action="store_true", help="only answered")
    q.add_argument("-l", "--long", action="store_true", help="include the question text")
    q.set_defaults(fn=cmd_questions)

    sub.add_parser("verification", help="the verification methods").set_defaults(fn=cmd_verification)
    sub.add_parser("levels", help="levels and the units in each").set_defaults(fn=cmd_levels)

    d = sub.add_parser("doc", help="one unit as a document, with its sections")
    d.add_argument("unit", help="file stem or prefix")
    d.add_argument("--markdown", action="store_true", help="render as markdown")
    d.set_defaults(fn=cmd_doc)

    a = sub.add_parser("add", help="allocate the next ID and append a new requirement")
    a.add_argument("prefix", help="e.g. TSR, TSSR_HWB, ICD_BUS")
    a.add_argument("--title", default="")
    a.add_argument("--statement", required=True)
    a.add_argument("--source", default="", help="what decided it — an OQ, an ADR, a date")
    a.add_argument("--verification")
    a.add_argument("--satisfies", default="", help="IDs, comma or space separated")
    a.add_argument("--topic", default="", help="OPEN-QUESTIONS topic number")
    a.add_argument("--rationale", default="")
    a.add_argument("--section", default="", help="section key from the unit's .toml")
    a.add_argument("--security", action="store_true", help="carries a security property")
    a.add_argument("--field", nargs=2, action="append", metavar=("COLUMN", "VALUE"),
                   help="a column of this unit that reqdeck does not interpret")
    a.set_defaults(fn=cmd_add)

    e = sub.add_parser("edit", help="change fields of an existing requirement")
    e.add_argument("id")
    for f in EDITABLE:
        if f != "security":
            e.add_argument(f"--{f}")
    e.add_argument("--security", help="yes, or empty to clear")
    e.add_argument("--field", nargs=2, action="append", metavar=("COLUMN", "VALUE"))
    e.set_defaults(fn=cmd_edit)

    sub.add_parser("fmt", help="rewrite the CSV files in canonical form").set_defaults(fn=cmd_fmt)

    un = sub.add_parser("unit", help="create a new unit: a CSV and its .toml")
    un.add_argument("file", help="file stem, e.g. firmware-node")
    un.add_argument("--level", required=True)
    un.add_argument("--prefix", required=True,
                    help="e.g. TSSR_FWN; several, space-separated, for one file of stories")
    un.add_argument("--title", required=True)
    un.add_argument("--code", action="store_true", help="implemented in software, so code must reference it")
    un.add_argument("--columns", help="override the column list")
    un.set_defaults(fn=cmd_unit)

    u = sub.add_parser("url", help="link to where a requirement is written, for an issue")
    u.add_argument("ids", nargs="+", metavar="ID")
    u.add_argument("--ref", default="main", help="branch or tag to link at (default main)")
    u.add_argument("--markdown", action="store_true", help="as [ID](url)")
    u.set_defaults(fn=cmd_url)
    return p


def load_model(scan: bool = True) -> Model:
    root = config.find_root()
    if root is None:
        raise config.ConfigError(f"No {config.CONFIG_NAME} found here or above. "
                                 f"Run `reqdeck init` in the project root, or set REQDECK_ROOT.")
    return Model.load(config.load(root), scan=scan)


def cmd_skills(args) -> int:
    from .init import SKILL_DIRS, copy_skills
    root = config.find_root()
    if root is None:
        return _err(f"No {config.CONFIG_NAME} found here or above — run `reqdeck init` first.")
    written, kept = copy_skills(root, list(SKILL_DIRS), update=args.update)
    for w in written:
        print(f"wrote {w}")
    for k in kept:
        print(f"kept  {k}" + ("" if args.update else "  — --update replaces reqdeck's own copies"))
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "init":
        from .init import run
        return run(Path.cwd())
    if args.cmd == "skills":
        return cmd_skills(args)
    if args.cmd == "tui":
        try:
            from .viewer import main as tui
        except ModuleNotFoundError as e:
            if e.name in ("textual", "rich"):
                return _err("The TUI needs textual: pip install textual")
            raise
        try:
            return tui()
        except config.ConfigError as e:
            return _err(str(e))
    try:
        m = load_model(scan=args.cmd not in ("add", "edit", "fmt", "unit", "url", "levels",
                                                      "verification", "questions", "doc"))
    except config.ConfigError as e:
        print(e, file=sys.stderr)
        return 2
    try:
        return args.fn(m, args)
    except store.StoreError as e:
        return _err(str(e))
