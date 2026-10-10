# Writing requirements

## Levels

Requirements form a tree. Each level satisfies the one above it, and only that link is
ever written — the reverse is derived by the tool, so the two directions cannot disagree.

```
A-01, B-02              user stories          the root everything traces to
      ↑ satisfies
TSR_001                 system                what the product must do
      ↑ satisfies
ICD_BUS_001             interface             behaviour at a boundary between parts
TSSR_FWN_001            sub-system            what one part must do
      ↑ @REQ_REF
code and tests
```

The levels are configured in `.reqdeck.toml`; `reqdeck levels` shows them. The setup offers
three shapes:

| Shape | Levels | Fits |
|---|---|---|
| 1 | Story → System (`TSR`) → Sub-system (`TSSR_<unit>`) + Interface (`ICD_<if>`) | A product of several parts that talk to each other — firmware, hardware, an app |
| 2 | Story → System → Sub-system | Several parts, no boundary worth specifying on its own |
| 3 | Story → Requirement (`REQ`) | One app or one component |

**Which level a requirement belongs to:**

- **System** — what the product must do, independent of how it is built. A user could
  observe it. "The system shall support at least 50 independently controlled LEDs per
  model." No part named.
- **Interface** — behaviour at a boundary, which both sides must agree on: a protocol
  field, a command, an API endpoint, a connector pinout. Written once, satisfied by the
  sub-system requirements of both sides.
- **Sub-system** — what one part must do to meet the levels above. Names the part. "The
  Node shall drive each channel with 12-bit PWM at 1 kHz."

Each sub-system or interface prefix is one *unit*: one CSV, one `.toml`. A new unit is a
new part of the design — agree it with the user before `reqdeck unit`.

A level with `traced = false` (typically the system level) is never referenced from code.
It is traced through what satisfies it, and a test against a lower requirement verifies
everything above it.

## The fields

| Field | |
|---|---|
| `id` | Allocated by `reqdeck add`. Sequential per prefix, append-only, never reused |
| `title` | A few words |
| `statement` | One sentence with "shall". The obligation, nothing else |
| `rationale` | Optional, one line — only where the reason is not obvious |
| `satisfies` | IDs one level up. Empty is legitimate but rare, and then the rationale says why |
| `topic` | The OPEN-QUESTIONS topic that decided it, on levels that require one |
| `source` | What decided it: `OQ-0608.`, `ADR-0007.`, `Chosen 2026-07-26.` Always present |
| `verification` | How it will be shown to be met — one code, see below |
| `status` | `Proposed`, `Accepted` or `Reopened` |
| `security` | `Yes` where it carries a security property; empty otherwise |
| `section` | Where it is shown in its unit's document, a key from the `.toml` |

Multi-line detail — a byte layout, a state table — goes in `<unit>.details.md` under
`## <ID>`. It is part of the requirement and shown with it.

## The statement

- **One obligation.** Two "shall"s joined by "and" are usually two requirements. Split
  them unless they cannot be verified separately.
- **Verifiable.** Someone must be able to say pass or fail. "Fast", "robust" and
  "user-friendly" are not; a number, an observable behaviour or an inspectable property is.
- **Every number chosen by someone.** If the user did not choose it and no answered
  question fixes it, it is an open question.
- **What, not how**, at the system level. Sub-system requirements may name a mechanism
  when the mechanism *is* the decision.
- **No reasoning in the statement.** The why goes in `rationale`, or stays in the answered
  question that `source` points at.
- **Name the part.** "The Node shall", "The app shall", "The system shall".

## Linking

`satisfies` names what the requirement exists to fulfil, one level up — the link `check`
enforces against the levels in `.reqdeck.toml`. Look for the parent before leaving it
empty; an empty link must not mean the parent was never looked for. A requirement driven
by a constraint rather than a user need — a risk, a regulation — may genuinely have none,
and then its rationale says so.

## Verification methods

Configured per project (`reqdeck verification`). The common set:

| | | |
|---|---|---|
| **A** | Analysis | Calculation, modelling or simulation — a worst-case budget, a timing margin |
| **I** | Inspection | Examination of the design, drawings or source without operating it |
| **D** | Demonstration | A person operates the system and observes, with no instrument |
| **T** | Test | An automated test |

Embedded projects often split `T` into **U** unit test (host, hardware mocked), **S**
integration test (real silicon, driven by a rig) and **M** manual test (instruments, a
person). The split records *where* a requirement can be signed off, which is what says
when it can be.

A method marked `automated` makes the requirement untraced until a test names it.
Two distinctions decide most cases: **D against M** — the difference is an instrument;
**U against S** — logic is U, what a device actually does is S.

## Status

`Proposed` — written, not yet read by the user. `Accepted` — reviewed and agreed.
`Reopened` — was accepted, then changed, so it needs reading again. An agent writes
`Proposed` (the only thing `reqdeck add` can write); `reqdeck edit` on an accepted requirement
makes it `Reopened`, and the change and its reason go in `source`. Only the user accepts.

## Security relevance

`security = Yes` marks a requirement carrying a security property, so the set is
enumerable for a conformance argument (`reqdeck list --security`). Judge by whether an attacker
is in the story: a CRC against a marginal cable is not a security control, and marking it
would misdescribe it.

## Sections

Sections are presentation, not meaning. Group requirements by subject so a unit reads as
a document; the section key is stable and its number is derived, so restructuring a
document never touches a requirement's ID or row.
