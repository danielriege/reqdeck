![reqdeck's TUI: a requirement with a preview of the code that implements it](https://raw.githubusercontent.com/danielriege/reqdeck/main/docs/demo.gif)

<div align="center">
<h1>reqdeck</h1>
Think of <a href="https://www.ibm.com/products/requirements-management">IBM DOORS</a>, but it lives in your git repo, fits in your terminal, and your AI agent can read it.
<br><br>

<a href="https://github.com/danielriege/reqdeck/actions/workflows/release.yml"><img src="https://github.com/danielriege/reqdeck/actions/workflows/release.yml/badge.svg" alt="Release"></a>
<img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+">
<a href="https://pypi.org/project/reqdeck/"><img src="https://img.shields.io/pypi/v/reqdeck" alt="PyPI"></a>
<a href="https://github.com/danielriege/reqdeck/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license"></a>

</div>

## The problem

AI agents write code faster than anyone can review it. Describe roughly what you want and
you get something that runs. That is vibe coding, and for a weekend project it is great.

For anything bigger it breaks in a predictable way. The agent builds what it *guesses* you
meant. Every gap in the description gets filled with a plausible default — a timeout, a
limit, a retry policy, a field nobody asked for — and none of them were decided by anyone.
It works in the demo. Three months later nobody can say what the system is *supposed* to do,
so nobody can say whether it does it, and every change is a coin flip.

Old-school engineering has had an answer to this for decades: the
[V-model](https://en.wikipedia.org/wiki/V-model). Down the left side, you write down what to
build, at increasing levels of detail — user needs, system requirements, the requirements on
each part. Up the right side, you prove each of those levels with a test. Every requirement
has a reason above it and a test beside it.

Agents made the bottom of the V nearly free. Code is cheap now. **The left side** — deciding
what to build — **and the right side** — proving it was built — are what is left, and they
matter more than they ever did. They are also exactly the parts an agent cannot do alone:
the decisions have to come from a person, and the proof has to be checkable by one.

## What reqdeck does

reqdeck keeps both sides of the V in your repo, next to the code, linked together, in files
an agent reads as easily as you do.

- **Open questions first.** Before anything is a requirement it is a question in
  `OPEN-QUESTIONS.md`. The agent researches it, lays out options, recommends one. **You
  decide.** The answer is written down where the question was.
- **Requirements from answers.** Each requirement names the decision it came from. No
  source, no requirement — an agent cannot slip in a number nobody chose.
- **Traced, both ways.** Each requirement names what it satisfies one level up. Code and tests
  name what they implement with a `@REQ_REF` marker. `reqdeck coverage` tells you what is
  untested, unimplemented or unjustified, and `reqdeck trace` exits non-zero for a requirement
  that is not implemented and tested — put it in CI.
- **Reviewed by a human.** Every requirement is `Proposed` until *you* accept it, in the TUI.
  The CLI has no way to write `Accepted`, so an agent cannot mark its own homework.
- **Skills for your agent.** Two skills for Claude Code and Codex: one for the CLI, one for
  the method.

It works the same for an embedded product of three boards and two firmwares as for a single
iOS app.

## Try it

The repo has an example project — Tick, a made-up iOS to-do app with its brief, its open
questions, 23 requirements on three levels below its user stories, and a few Swift files
that point at them.

```bash
pip install reqdeck
git clone https://github.com/danielriege/reqdeck
cd reqdeck/examples/tick
reqdeck tui
```

Move with `j` `k`, `tab` through the links of a requirement, `enter` to follow one. Then:

```bash
reqdeck coverage          # what is untested, uncoded, unreviewed
reqdeck get SW_APP_006    # one requirement: its chain up and down, its code and tests
reqdeck questions --open  # what is still undecided
```

## Use it in your project

```bash
pip install reqdeck
cd your-project
reqdeck init
```

`reqdeck init` asks for the shape of your requirement tree and the parts of your product,
then writes `.reqdeck.toml`, one requirement file per part, an `OPEN-QUESTIONS.md`, and copies
both skills into `.claude/skills/` and `.agents/skills/` — commit them, and every agent working
on the project has them. It asks everything first, refuses to overwrite anything, and leaves
the project untouched if it fails halfway. After upgrading reqdeck, `reqdeck skills --update`
refreshes the copies.

Python 3.11 or newer, macOS or Linux. Pin it in your project's dependencies, so CI checks with
the version you work with.

Then tell your agent to load the `reqdeck-method` skill and start with a product brief.

### As a Claude Code plugin

Rather have the skills everywhere than committed to each project? Install them as a plugin:

```
/plugin install reqdeck --marketplace danielriege/reqdeck
```

The plugin is only the skills — the agent still runs the `reqdeck` command, so `pip install
reqdeck` either way.

## The method

1. **Brief.** One page: what it is, for whom, what it deliberately is not.
2. **Stories.** Personas and user stories — the root everything traces to.
3. **Topics.** Cut the design into areas: scope, each interface, each part, power, security…
4. **Questions.** For each topic, find what is undecided — with your agent, not by it.
5. **Answers.** One question per session. The agent researches and recommends, you decide,
   the answer is written in place with the date and the reasoning.
6. **Requirements.** When a topic is answered, its requirements get written. Writing them
   finds gaps; each gap becomes a new question, not an invented value.
7. **Build.** Code and tests carry `@REQ_REF` markers. `reqdeck coverage` is the progress bar.

The `reqdeck-method` skill holds the details: the levels, how a requirement is worded, which
verification method fits, where a marker goes.

## The TUI

![A unit shown as a document, with numbered sections and a detail table](https://raw.githubusercontent.com/danielriege/reqdeck/main/docs/document.png)

`reqdeck tui` shows every unit as a document — sections numbered, each requirement a card with its
status, statement, detail tables and fields — beside the open questions by topic. The tree
always has the cursor; the right pane shows what it highlights.

Beside each requirement in the tree are two marks. The letter is its review status: `A`ccepted,
`P`roposed, `R`eopened. The symbol is how far it is built, judged over it and everything that
satisfies it: `✓` done, `◑` untested, `◔` partial, `○` not implemented, `✗` unsatisfied. The
card says which requirements beneath it keep it from done, and `reqdeck get` prints the same.

| | |
|---|---|
| `j` `k` `h` `l` · `gg` `G` | Move through the tree, as in vim |
| `tab` `shift+tab` | The next, previous link in the right pane, previewed beside it |
| `enter` | Follow the link. A code or test reference opens in your editor |
| `ctrl+o` · `]` | Back, forward through the jumps |
| `/` · `n` `N` | Search · next, previous result |
| `ctrl+d` `ctrl+u` | Scroll the right pane |
| `a` | Accept the highlighted requirement |
| `t` | Theme |
| `?` | All keys |

Every requirement and question ID in the right pane is a link, and so is every code and test
reference, shown with what it is attached to — the test function, the type. Hovering one, or
`tab`-ing to it, previews it: the requirement, or the source around the marker. `enter` on a
reference opens it in `[editor]`, or `$VISUAL`/`$EDITOR`; a terminal editor like nvim gets
the terminal until you quit it, as in lazygit.

It draws like lazygit: rounded borders, one hint line that only lists what applies right
now, and no background — your terminal's shows through. The themes are Textual's own
(Dracula, Nord, Gruvbox, Tokyo Night, Catppuccin, Solarized, Monokai, One Dark, Rosé Pine,
Flexoki), each given a full colour suite by a file in [reqdeck/themes/](https://github.com/danielriege/reqdeck/blob/main/reqdeck/themes/README.md),
where you can add your own. Your theme and sidebar width are remembered in
`~/.config/reqdeck/tui.json`.

It reloads from disk every 30 seconds, so what an agent or your editor writes shows up on its
own — `Reloading` spins at the left of the hint line while it does, and only a change redraws
anything. `r` reloads at once. Set `"reload"` in `tui.json` to the seconds between reloads, or
`0` to turn it off.

## The CLI

```bash
reqdeck get TSR_009                    # one requirement, its chain, its code and tests
reqdeck search 'beacon|sync'           # regex over id, title, statement, detail
reqdeck list --topic 06 --status proposed
reqdeck coverage                       # where traceability is missing
reqdeck trace TSSR_FWN_004             # implemented and tested? exit 1 if not
reqdeck check                          # validate everything, exit 1 on any problem
reqdeck questions --open --topic 04
reqdeck add TSSR_FWN --title "Channel PWM" --statement "The Node shall …" \
    --satisfies TSR_025 --topic 06 --source "OQ-0608." --verification T
reqdeck edit TSR_009 --statement "…" --source "…"
```

Every command takes `--json`. `add` allocates the next ID and can only write `Proposed`;
`edit` turns an `Accepted` requirement `Reopened`, so a changed requirement goes back to you.
`reqdeck check` exits 1 on any problem — run it in CI next to your tests.

## The files

```
.reqdeck.toml                    levels, verification methods, marker rules, editor
docs/OPEN-QUESTIONS.md          topics and questions — markdown, edited by hand
docs/requirements/
  stories.csv   stories.toml    user stories, one section per persona
  system.csv    system.toml     one unit per prefix
  icd-bus.csv   icd-bus.toml
  icd-bus.details.md            byte layouts, state tables — one `## <ID>` each
```

A unit's **CSV** holds one requirement per row, ordered by ID and only ever appended to. A
row's line is as permanent as its ID, and the diff of a change is exactly the rows it
touched. It is written by `reqdeck add` and `reqdeck edit`, never by hand; `check` rejects a file
that is not in the exact form the tool writes.

Its **`.toml`** describes the unit — level, prefix, title, whether code implements it — and
its sections:

```toml
level = "SW"
prefix = "SW_APP"
title = "App"
code = true

[[sections]]
key = "reminders"
title = "Reminders"

[[sections]]
key = "reminders.snooze"     # nests under reminders: shown as 1.1
title = "Snooze"
```

A requirement names its section by key. Numbers come from declaration order when the
document is drawn, so inserting a section renumbers the document without touching a single
requirement — the way DOORS does it.

## `.reqdeck.toml`

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
kind = "SYS"
satisfies = ["STORY"]         # what it may link to — check enforces it
topic = true                  # names the OPEN-QUESTIONS topic behind it
traced = false

[[levels]]
kind = "SW"
satisfies = ["SYS"]
topic = true
code = true                   # what it needs before it is done — see below

[verification.T]
name = "Test"
definition = "An automated test shows the requirement is met."
automated = true              # untraced until a test names it

[markers]
test_paths = ["Tests"]                    # a path containing one is a test
declaration_extensions = [".h", ".swift"] # outside tests, markers only here
interface_suffixes = ["_interface"]       # never marked

[editor]
command = "nvim +{line} {file}"           # or "code --goto {file}:{line}"
```

Without `[verification]` the methods are A, I, D and T. Without `[markers]` every common
source file is scanned and a marker may sit anywhere.

### What a level needs

Three keys on a `[[levels]]` entry say what each of its requirements needs before it is done.
Each is `true` or `false`; left out, it takes the default in the last column, which is how
reqdeck behaved before the keys existed.

| Key | Met when | Left out |
|---|---|---|
| `satisfied` | a requirement of a lower level names it in `satisfies` — **or**, where the level also has `code = true`, a code marker names it itself | `true` if another level lists this one in its `satisfies` |
| `code` | a code `@REQ_REF` names it — **or**, where the level also has `satisfied = true`, **every** requirement beneath it is named by code, or is satisfied by requirements that all are | the unit's `code = true` |
| `test` | a test `@REQ_REF` names it — **or**, where the level also has `satisfied = true`, **every** requirement beneath it is named by a test, or is satisfied by requirements that all are | the verification method's `automated = true` |

`code` and `test` follow one rule: **a marker on the requirement itself, or a marker on every
branch beneath it.** "Beneath" is everything that satisfies it, all the way down, and *every
branch* means each requirement satisfying it is named by a marker, or is in turn satisfied by
requirements that all are. One branch without is enough to leave it short. With three
software requirements satisfying a system requirement and code on two, the system
requirement is not coded and shows as partial; code on the third makes it coded. Tests are
counted the same way, separately: code on all three and a test on two leaves it untested.

So a level with `satisfied = true` and `code = true` is done in either of two ways:

- **Broken down.** Lower requirements satisfy it, and code names every one of them (or every
  one of theirs, where they are broken down further).
- **Implemented as it stands.** Code names it directly, and nothing needs to satisfy it.

`test = true` adds the same again for tests, on top of either way.

With `satisfied = false`, only a marker on the requirement itself counts, for `code` and for
`test`. A level with `traced = false` may never be named by a marker directly, so `code = true`
or `test = true` there needs `satisfied = true` — the markers can only be beneath it — and
`check` refuses the config otherwise.

`coverage`, `trace`, `get` and the progress marks in the TUI all judge by these same rules.

```toml
[[levels]]
kind = "TSR"                  # a technical system requirement
satisfies = ["STORY"]
traced = false                # never named by code itself...
satisfied = true              # ...so a TSSR or an ICD must satisfy it,
code = true                   # and code must name every one of those,
test = true                   # and a test must name every one of those too
```

## Limitations

- **Small teams.** It is built for one person and their agents, or a handful of people. Two
  branches that both add a requirement to the same unit conflict on the last line of its
  CSV — trivially resolved, but resolved by hand.
- **Markers are text.** `@REQ_REF` is found by a regex, not by parsing your language. Whether
  the *right* code carries the marker is a judgement the tool cannot make for you.
- **No web view.** The TUI is the viewer. `reqdeck doc <unit> --markdown` renders a unit as
  markdown when you need to hand it to someone without a terminal.
- **macOS and Linux.** Windows is untested, and handing the terminal to an editor certainly
  is.

## Development

```bash
python3 -m unittest discover tests     # the TUI tests skip without textual
```

The demo GIF and the screenshot above are recorded, not drawn: `scripts/record-demo.sh`
installs this checkout into a throwaway virtualenv and plays `docs/demo.tape` and
`docs/document.tape` through [vhs](https://github.com/charmbracelet/vhs). It needs vhs and nvim.

Every change a user would notice gets a line under `Unreleased` in
[CHANGELOG.md](https://github.com/danielriege/reqdeck/blob/main/CHANGELOG.md), in the same
commit. A release renames that section to its version; publishing refuses a version the
changelog does not name.

## License

MIT. See [LICENSE](https://github.com/danielriege/reqdeck/blob/main/LICENSE).
