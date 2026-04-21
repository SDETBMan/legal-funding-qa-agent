"""Repo-root CLI shim so ``python main.py`` forwards to :mod:`agent.main`."""

from __future__ import annotations

import sys

from agent.main import main

if __name__ == "__main__":
    main(sys.argv[1:])
