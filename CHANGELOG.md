# Changelog

What changed in each release of reqdeck. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

Every change a user would notice gets a line under **Unreleased**, in the commit that makes
it. To release: rename **Unreleased** to the version and date, open a new empty
**Unreleased** above it, bump `reqdeck/__init__.py`, tag `vX.Y.Z` — and paste the section
into the GitHub release.

## [Unreleased]

### Added

- The TUI reloads from disk every 30 seconds, so what an agent or an editor writes shows up
  on its own. `Reloading` spins at the left of the hint line while it runs; a reload that
  finds nothing changed redraws nothing, and one that does keeps the reading pane where it
  was scrolled. `"reload"` in `~/.config/reqdeck/tui.json` sets the seconds, `0` turns it off.

- Every requirement shows how far it is built, beside its review status: Done, Untested,
  Partial, Not implemented or Unsatisfied, judged over it and everything that satisfies it, so
  a user story is Done only once its whole chain is. The tree marks it `✓` `◑` `◔` `○` `✗`, the
  card's title carries it, the level view counts the Done per unit, and `reqdeck get` prints
  it with what keeps it from Done — `progress` in `--json`.
- `satisfied`, `code` and `test` on a `[[levels]]` entry set what that level needs before it is
  done. Unset, they follow from `satisfies`, the unit's `code` and the verification method, as
  before. `code = true` or `test = true` on a `traced = false` level is now allowed, met by
  markers on every requirement beneath it.

### Changed

- A requirement that must both be satisfied from below and named by code is done either way:
  broken down, with code naming every requirement beneath it, or implemented as it stands,
  with code naming it. Before, it needed its own code marker and something satisfying it — an interface
  requirement with code but nothing satisfying it was a gap, and so was one whose code sat on
  the software requirements beneath it.
- A test beneath a requirement counts for it only where its level must be satisfied, and then
  every requirement beneath it needs one — as for code. Before, one test anywhere beneath was
  enough, so a system requirement with one tested and one untested software requirement
  beneath it counted as tested.
- `r` reloads in the background with the same spinner, instead of freezing the TUI while it
  reads. A file that fails to load is reported once, not on every reload.

## [0.1.0] - 2026-10-10

First release: CSV requirements and open questions in your repository, `@REQ_REF` markers
in code and tests, the `reqdeck` CLI and TUI, and the skills for Claude Code.

[Unreleased]: https://github.com/danielriege/reqdeck/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/danielriege/reqdeck/releases/tag/v0.1.0
