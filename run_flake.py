"""Запуск Flake без установки: python run_flake.py"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        from flakewin.selftest import run_selftest
        index = sys.argv.index("--selftest")
        out = sys.argv[index + 1] if len(sys.argv) > index + 1 else "selftest.png"
        sys.exit(run_selftest(out))

    from flakewin.app import main
    sys.exit(main())
