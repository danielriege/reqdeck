---
name: req-cli
description: Query, add, edit and validate requirements and open questions with reqkit's req.py CLI. Use when looking up which requirement covers a behaviour, before implementing or changing a feature, when writing or reviewing a test, adding @REQ_REF markers, writing new requirements, checking traceability, listing open questions, or before claiming work is complete. Applies in any repository with a .reqkit.toml.
---

# req — the reqkit CLI

A project using reqkit has `.reqkit.toml` in its root and reqkit itself as a submodule,
usually at `.reqkit/`. Run the CLI from anywhere inside the project:

```bash
python3 .reqkit/req.py --json get TSR_009
```

If the project's venv has reqkit installed, the same commands are `req <cmd>`. Prefer the
explicit path, which works either way. Every command takes `--json`; prefer it, since it is
stable and carries the transitive chain the human-readable form draws as a tree.

The method behind the files — levels, how a requirement is written, the open-question
workflow, `@REQ_REF` rules — is the **req-method** skill. This one is the tool.

## The files

Requirements live in the folder `.reqkit.toml` names, one *unit* per prefix:

| File | Holds | Edit with |
|---|---|---|
| `<unit>.csv` | One requirement per row, ordered by ID, append-only | `req add`, `req edit` — never by hand |
| `<unit>.toml` | Level, prefix, title, description, `code`, sections | By hand |
| `<unit>.details.md` | Multi-line detail — tables, layouts — one `## <ID>` each | By hand |

**Never edit a CSV by hand.** Quoting is easy to break, a hand edit can set a status the
tool would refuse, and `check` rejects any file not in the exact form the tool writes. If a
CSV has been edited outside the tool, `req fmt` rewrites it canonically.

Open questions live in markdown (`questions =` in `.reqkit.toml`) and are edited by hand.

## Commands

| | |
|---|---|
| `get <ID>` | One requirement with its chain up and down, detail, code and test refs |
| `search <regex>` | Over id, title, statement, rationale and detail |
| `list [--kind --unit --topic --section --verification --status --security] [-l]` | Filtered inventory |
| `tree <ID> [--up\|--down]` | Just the chain |
| `doc <unit> [--markdown]` | A unit as a document, sections numbered |
| `levels` | Levels, and the units in each |
| `topics` | Every topic: open and answered questions, requirement count |
| `questions [--topic NN] [--open\|--answered] [-l]` | The open questions |
| `coverage` | Where traceability is missing |
| `trace <ID>...` | Are these referenced from code and tests? Exit 1 if not |
| `check` | Validate everything. **Exit 1 on any problem** |
| `verification` | The verification methods this project uses |
| `add <PREFIX> ...` | Allocate the next ID and append a requirement |
| `edit <ID> --<field> ...` | Change fields of an existing requirement |
| `unit <file> --level --prefix --title [--code]` | Create a new unit |
| `fmt` | Rewrite the CSVs in canonical form |
| `url <ID>...` | Link to the requirement's row on GitHub, for an issue |

## Before implementing anything

Find what governs it, and read the statement before writing code:

```bash
python3 .reqkit/req.py --json search 'keyframe|interpolat'
python3 .reqkit/req.py --json get TSSR_FWN_012
```

If nothing matches, that is a finding — say so rather than inventing behaviour.

## Adding a requirement

**A new ID comes from `add`, never from typing one.** It allocates the next number, finds
the unit holding the prefix, validates every link, and writes `Proposed` — it has no way
to write anything else.

```bash
python3 .reqkit/req.py add TSSR_FWN --title "Channel PWM" \
    --statement "The Node shall drive each channel with 12-bit PWM at 1 kHz." \
    --satisfies TSR_025,TSR_026 --topic 06 --source "OQ-0608." --verification S \
    [--rationale "..."] [--section render.pwm] [--security]
```

- `--topic` is required on levels that set `topic = true`; it must be a topic in
  OPEN-QUESTIONS.
- `--satisfies` must name existing requirements of a level this one may satisfy.
- `--section` must be a key declared in the unit's `.toml`. Add the section there first.
- A column the unit has beyond the standard ones: `--field <column> <value>`.
- Stories: `add A --statement "As a …"` — no source, verification or status.

It refuses a prefix no unit holds. A new prefix is a new unit of the design — create it
deliberately with `req unit`, and only when the user has agreed the unit exists.

Multi-line detail does not go in the CSV. Append a block to `<unit>.details.md`:

```markdown
## ICD_BUS_014

| Off | Len | Field | Notes |
|---|---|---|---|
| 0 | 1 | Form and count | ... |
```

## Changing a requirement

```bash
python3 .reqkit/req.py edit TSR_009 --statement "..." --source "OQ-0507. Reopened 2026-10-10 by OQ-0512: ..."
```

`edit` changes any field but `id` and `status`. **Changing an Accepted requirement turns
it Reopened automatically** — say what changed and why in `source`. Nothing in the CLI
sets `Accepted`: only the user does, in the TUI (`.reqkit/tui.py`, key `a`) or by hand.
Never work around that.

IDs are permanent. Never renumber, never reuse a retired ID, never delete a row that code,
tests or issues may point at.

## Sections

A requirement's `section` is a stable key; numbers are derived from declaration order in
the unit's `.toml`, so inserting a section never touches a row:

```toml
[[sections]]
key = "power"
title = "Power"

[[sections]]
key = "power.bus"            # nests under power: shown as 1.1
title = "Bus supply"
description = "What the cable carries."
```

Reorder or insert by editing the `.toml`. Move a requirement with `edit --section`.

## Interpreting `check` and `coverage`

`check` fails on anything structurally wrong: a dangling link, a link to the wrong level, a
duplicate ID, a malformed ID, a missing required field, an undeclared section or topic, a
non-canonical CSV, a detail block for a requirement that is not in that unit, and every
`@REQ_REF` rule. It prints the status tally and never fails on it.

`coverage` reports work not yet done:

| | |
|---|---|
| `dangling` | Satisfies something that does not exist — always a bug |
| `orphans` | No satisfies link. Legitimate only with the reason in the rationale |
| `unsatisfied` | A story, or a parent level, nothing satisfies yet |
| `untested` | Verification is automated, but no test names it or anything beneath it |
| `uncoded` | Unit has `code = true`, but no code names it |
| `not_accepted` | Awaiting the user's review — not a gap to close by editing |

Gaps are normal while topics are still being discussed. **Do not close them by inventing
links or markers.** Report them.

## Before claiming work is complete

```bash
python3 .reqkit/req.py trace TSSR_FWN_012 ICD_BUS_014   # what the change claims to implement
python3 .reqkit/req.py check
```

`trace` refuses a level marked `traced = false` (typically the system level) and names
what satisfies it instead: a task names the level that reaches code.
