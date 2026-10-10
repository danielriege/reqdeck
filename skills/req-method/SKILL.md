---
name: req-method
description: The reqkit way of designing a product with its user — product brief, topics, open questions answered one at a time, then requirements derived from the answers, traced to code and tests with @REQ_REF. Use when setting up a new project for requirements, starting or continuing design work, discussing or answering an open question, writing or reviewing requirements, deciding a requirement's level, or adding @REQ_REF markers to code and tests.
---

# The reqkit method

A design is built *with* the user, not for them. The agent researches, drafts, lays out
options and recommends; **the user decides**. Every requirement traces to a decision the
user actually made, and the files record which requirements the user has actually read.

The tool is the **req-cli** skill. Two references go with this file — read them when the
work reaches them:

- [references/writing-requirements.md](references/writing-requirements.md) — levels,
  fields, how a statement is written, verification methods, status.
- [references/markers.md](references/markers.md) — `@REQ_REF` in code and tests.

## The rules that matter most

**Do not invent requirements.** A requirement carries a `source` naming what decided it —
an answered question, an ADR, a dated choice by the user. If you cannot write that source,
it is not a requirement: it is a question, and it goes in OPEN-QUESTIONS. **A number
nobody chose is not a requirement either.** "At least 50 channels" is a requirement only
if the user chose 50.

**OPEN-QUESTIONS is the source of truth.** Requirements are derived from answered
questions; architecture notes, ADRs, READMEs and agent instructions restate them and go
stale. When a document disagrees with an answered question, the question is right and the
document is wrong — fix the document. Check a requirement against the question that
produced it rather than assuming it kept up.

**Never set a requirement to `Accepted`.** One you write is `Proposed`; one you change
that was `Accepted` becomes `Reopened`. Only the user accepts, after reading. An agent that
accepts its own work destroys the one signal recording what a human has reviewed. The CLI
cannot write `Accepted`; do not get around it.

**Work topic by topic.** Requirements for a topic are written after the topic is
discussed, not before.

**Ask rather than assume** when a decision would materially change the design. Give a
recommendation; let the user decide.

**A risk is not an open question.** A question is undecided and gets decided. A risk may
happen whatever is decided, and gets watched — in a risk register, not as a question.

## Phase 0 — Setting up

1. Add reqkit as a submodule: `git submodule add https://github.com/danielriege/reqkit .reqkit`.
2. Before running the setup, agree with the user what the parts of the product are. The
   setup asks for the *shape* of the requirement tree — see
   [writing-requirements.md](references/writing-requirements.md#levels) — and for one unit
   per part (firmware, hardware, app, an interface between two of them). It is fine to
   start with fewer units; `req unit` adds one later.
3. Run `.reqkit/init.sh` from the project root. It is interactive: relay each question to
   the user rather than answering it yourself, or have the user run it. It writes
   `.reqkit.toml`, creates the units and OPEN-QUESTIONS, and links both skills for Claude
   Code and Codex.
4. Record in the project's agent instructions (`AGENTS.md` / `CLAUDE.md`) that the project
   uses reqkit and this method, and which topics are complete as that changes.

## Phase 1 — Product brief

A short document: what the product is, for whom, the problem it solves, what it
deliberately is not, and what would make it a success. Draft it from conversation, then
let the user correct it. Keep it short — a page, not a spec. Everything later is checked
against it.

## Phase 2 — Personas and user stories

Personas are short prose in a product document: who they are, what they are comfortable
with, what they buy, what to avoid. User stories are the root of the requirement tree and
live in the stories unit, one row each:

```bash
python3 .reqkit/req.py add A --statement "As a collector, I want to turn the display on from my phone, so that I don't have to reach behind the shelf."
```

One story prefix per persona (`A-01`, `B-01`). Story IDs are permanent. If you drafted the
stories, say so, and make "are these stories real?" the first open question.

## Phase 3 — Topics

Agree with the user the list of areas where design decisions are needed, and write each as
a topic in OPEN-QUESTIONS:

```markdown
## Topic 04 — Bus physical layer
```

Topics are numbered `01`–`99` and never renumbered. Typical topics: scope and market,
scale, each interface, each part's hardware and software, power, mechanical, verification,
compliance, security. Topics are a way to cut the work into sessions, so a topic should be
discussable in a few sittings.

## Phase 4 — Finding the open questions

For each topic, find the questions *with* the user. A question is something undecided
whose answer changes the design. While collecting, do not answer:

```markdown
### OQ-0403 — Connector
**Question:** Which connector joins a Node to the bus, given the 2 mm pitch of the bricks?
**Answer:**
**Blocks:** Rev A layout, TSSR_HWB
```

IDs are `OQ-TTNN`: topic, then the next free number within it. **Questions never move**,
and are never deleted — an answered one stays where it is. `Blocks` says what waits on it,
so the order to answer them in is visible.

```bash
python3 .reqkit/req.py topics              # open and answered per topic
python3 .reqkit/req.py questions --open --topic 04 -l
```

## Phase 5 — Answering, one question at a time

One question, or a few tightly related ones, per session. For each:

1. **Read what is already decided.** Answered questions in this and neighbouring topics,
   and requirements already derived from them.
2. **Research.** Datasheets, prior art, the market, standards, the existing code. Check
   facts rather than recalling them; stock, prices and versions change.
3. **Lay out the options** with their trade-offs, and **recommend one**. Say what would
   change your recommendation.
4. **The user decides.** Do not write an answer the user has not given.
5. **Write the answer in place**, with the date and the reasoning a later reader needs:
   `**Chosen 2026-08-16.** JST SH, because …`. Expensive decisions get an ADR as well.
6. **New questions** surfaced while answering are added to their topic, not answered in
   passing. A consequence that may hit whatever is decided is a risk.
7. **Fix downstream documents** that the answer contradicts.

## Phase 6 — Requirements from a finished topic

When a topic's questions are answered, derive its requirements — see
[writing-requirements.md](references/writing-requirements.md). Each takes its `source`
from the answers and its `topic` from the topic, and is written with `req add`.

Writing requirements finds gaps: a number nobody chose, a behaviour no answer covers, a
parent that does not exist yet. **Each gap becomes a new open question**, not a
requirement with an invented value. Tell the user what you found.

Then the user reviews. They read the `Proposed` requirements and accept them in the TUI:

```bash
python3 .reqkit/req.py list --status proposed --topic 06
.reqkit/tui.py
```

## Phase 7 — Building it

Work is tracked as tasks that name the requirements they implement — at the level that
reaches code, never a level marked `traced = false`. Code and tests carry `@REQ_REF`
markers ([markers.md](references/markers.md)); `req trace` decides whether a change left
what it claims traced, and `req coverage` is the measure of progress, not task counts.

A change in behaviour that no requirement covers is a finding. Raise it as a question
rather than shipping unspecified behaviour.

## Documents in general

Minimum needed to understand the content. No status badges, progress tracking or
"to be written" placeholders. Describe only the current state — never what moved or what
used to be there; git holds the history.
