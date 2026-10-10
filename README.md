# reqkit

Requirements, open questions and traceability, kept in a git repository and worked on
together by a person and an AI agent.

The method: write a product brief, split the design into topics, find each topic's open
questions with the user, answer them one at a time, and only then derive requirements
from the answers. Each requirement traces up to a user story and down to the code and
tests that implement it. The agent drafts and recommends, the user decides, and the files
record which requirements a person has actually reviewed.

reqkit is the tool and the agent skills for that method. It works the same for an
embedded product of several boards and firmwares as for a single iOS app.

| | |
|---|---|
| `req.py` | The CLI — query, add, edit, trace, validate. Standard library only |
| `tui.py` | Browse requirements as documents, with their sections, and accept them |
| `init.sh` | Set a project up, asking as it goes |
| `skills/req-cli/` | Skill: using the CLI |
| `skills/req-method/` | Skill: the method — phases, levels, writing requirements, `@REQ_REF` |
| `tool/` | Everything the CLI and the TUI share |

## Using it in a project

```bash
git submodule add https://github.com/danielriege/reqkit .reqkit
.reqkit/init.sh
```

`init.sh` asks for the shape of the requirement tree and the parts of the product, then
writes `.reqkit.toml`, one requirement file per part, an `OPEN-QUESTIONS.md`, and links
both skills into `.claude/skills/` and `.agents/skills/` so Claude Code and Codex find
them.

Python 3.11 or newer. The CLI needs nothing else; the TUI needs
[Textual](https://textual.textualize.io/):

```bash
python3 .reqkit/req.py check
pip install textual && .reqkit/tui.py
```

Or install both into the project's venv, which puts `req` and `req-tui` on the path:

```bash
pip install -e ".reqkit[tui]"
```

## The files in a project

```
.reqkit.toml                    levels, verification methods, marker rules
docs/OPEN-QUESTIONS.md          topics and questions — markdown, edited by hand
docs/requirements/
  stories.csv   stories.toml    user stories, one section per persona
  system.csv    system.toml     one unit per prefix
  icd-bus.csv   icd-bus.toml
  icd-bus.details.md            multi-line detail, one `## <ID>` per requirement
```

A unit's **CSV** holds one requirement per row, ordered by ID and only ever appended to,
so a row's line is as permanent as its ID and the diff of a change is the rows it touched.
It is written by `req add` and `req edit`, never by hand, and `check` rejects a file that
is not in the exact form the tool writes.

Its **`.toml`** holds what describes the unit: level, prefix, title, description, whether
it is implemented in code, and its sections:

```toml
level = "TSSR"
prefix = "TSSR_FWN"
title = "Node firmware"
code = true

[[sections]]
key = "render"
title = "Rendering"

[[sections]]
key = "render.pwm"
title = "PWM output"
```

A requirement names its section by key. Numbers — `2.1` above — come from declaration
order when the document is rendered, so inserting or moving a section never touches a
requirement.

## `.reqkit.toml`

```toml
requirements = "docs/requirements"
questions = "docs/OPEN-QUESTIONS.md"

[[levels]]                    # most abstract first
kind = "STORY"
reviewed = false              # no source, verification or status
traced = false                # never referenced from code
separator = "-"
digits = 2                    # A-01

[[levels]]
kind = "TSR"
satisfies = ["STORY"]         # what it may link to; check enforces it
topic = true                  # names the OPEN-QUESTIONS topic behind it
traced = false

[[levels]]
kind = "TSSR"
satisfies = ["TSR"]
topic = true

[verification.T]
name = "Test"
definition = "An automated test shows the requirement is met."
automated = true              # untraced until a test names it

[markers]
extensions = [".c", ".h", ".swift"]       # files scanned for @REQ_REF
skip = ["docs", "build"]                  # directory names not scanned
test_paths = ["test", "spec"]             # a path containing one is a test
declaration_extensions = [".h", ".swift"] # outside tests, markers only here
interface_suffixes = ["_interface"]       # never marked
[editor]                      # where the TUI opens a code or test reference
command = "nvim +{line} {file}"           # or "code --goto {file}:{line}"
# suspend = true                          # hand the terminal over until it exits
```

Without `[verification]` the methods are A, I, D and T. Without `[markers]` every common
source extension is scanned and markers may sit anywhere.

## The TUI

`tui.py` shows each unit as a document — sections numbered, every requirement a card with
its status, statement, detail tables and fields — beside the open questions by topic. It
works entirely from the keyboard, with vim keys, and with the mouse.

| | |
|---|---|
| `j` `k` `h` `l`, `gg` `G`, `ctrl+d` `ctrl+u` | Move, as in vim |
| `enter` | In the tree: into the reading pane |
| `tab` `shift+tab` | In the reading pane: the next, previous link, highlighted and previewed |
| `enter` `gd` | Follow the link; the tree moves there too. A code or test reference opens in the editor |
| `ctrl+o` `[` · `]` | Back, forward through the jumps |
| `/` · `n` `N` | Search · next, previous result |
| `a` | Accept the highlighted requirement |
| `t` | Theme |
| `<` `>` | Sidebar width — or drag the divider |
| `?` | All keys |

Every requirement and question ID in the reading pane is a link, and so is every code and
test reference, shown with what it is attached to — the test function, the type. Hovering
one shows the same preview as `tab`: the requirement, or the source around the marker. A
reference opens in `[editor]`'s command, or `$VISUAL` / `$EDITOR` through a preset for
nvim, vim, helix, VS Code, Cursor, Zed and others; a terminal editor gets the terminal
until it exits, as in lazygit.

It draws like lazygit: rounded panel borders that change colour on focus, a selected line,
one hint line, and no background anywhere — the terminal's own shows through. The themes
are Textual's own — Dracula, Nord, Gruvbox, Tokyo Night, Catppuccin, Solarized, Monokai,
One Dark, Rosé Pine, Flexoki — each given reqkit's full colour suite by a file in
[tool/themes/](tool/themes/README.md), which also says how to add your own. A light theme
belongs on a light terminal. The theme and the sidebar width are remembered per user in
`~/.config/reqkit/tui.json`.

## Status

Every reviewed requirement is `Proposed`, `Accepted` or `Reopened`. `req add` can only
write `Proposed`; `req edit` turns an `Accepted` requirement `Reopened`. Nothing in the CLI
writes `Accepted` — a person does, in the TUI, after reading the requirement. An agent
that could accept its own work would erase the only record of what a human has reviewed.

## Developing reqkit

```bash
python3 -m unittest discover tests     # the TUI tests skip without textual
```
