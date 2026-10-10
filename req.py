#!/usr/bin/env python3
"""reqkit's command line. The logic lives in tool/; this only starts it.

    ./req.py get TSR_009
    ./req.py check

Run from anywhere inside a project holding `.reqkit.toml`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tool.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(script=Path(__file__)))
