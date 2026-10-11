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

### Changed

- `r` reloads in the background with the same spinner, instead of freezing the TUI while it
  reads. A file that fails to load is reported once, not on every reload.

## [0.1.0] - 2026-10-10

First release: CSV requirements and open questions in your repository, `@REQ_REF` markers
in code and tests, the `reqdeck` CLI and TUI, and the skills for Claude Code.

[Unreleased]: https://github.com/danielriege/reqdeck/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/danielriege/reqdeck/releases/tag/v0.1.0
