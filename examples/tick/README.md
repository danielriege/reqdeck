# Tick

A made-up iOS to-do app, specified the reqkit way. No app here — just its brief, its open
questions, its requirements on four levels, and three Swift files that carry `@REQ_REF`
markers. Enough to poke at.

```bash
cd examples/tick
../../tui.py                   # browse it — needs: pip install textual
../../req.py check             # valid?
../../req.py coverage          # what is untested, uncoded, unreviewed
../../req.py get SW_APP_006    # one requirement, its chain and its code
../../req.py questions --open  # what is still undecided
```

| | |
|---|---|
| [docs/product-brief.md](docs/product-brief.md) | What Tick is, and what it is not |
| [docs/OPEN-QUESTIONS.md](docs/OPEN-QUESTIONS.md) | Six topics, answered and open |
| [docs/requirements/](docs/requirements/) | Stories → `SYS` → `IF_SYNC` / `SW_APP` / `SW_WID` |
| [Sources/](Sources/) · [Tests/](Tests/) | The code and tests the markers point from |

The gaps are on purpose. `SYS_006` has nothing beneath it, `SW_APP_003` has no code, ten
requirements still wait for a human to review them, and an open question blocks two stories
nobody has written requirements for yet. That is what a project looks like halfway, and what
`req coverage` is for.

The code does not build — it is there to be pointed at.
