#!/usr/bin/env python3
"""reqkit's TUI. The logic lives in tool/; this only starts it.

Needs textual: pip install textual — or install reqkit with the `tui` extra.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from tool.viewer import main  # noqa: E402
except ModuleNotFoundError as e:
    if e.name not in ("textual", "rich"):
        raise
    sys.exit("The TUI needs textual: pip install textual")

if __name__ == "__main__":
    sys.exit(main(script=Path(__file__)))
