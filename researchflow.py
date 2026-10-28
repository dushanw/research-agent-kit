#!/usr/bin/env python3
"""Entry point; also usable without installation."""
import sys
if sys.version_info < (3, 10):
    raise SystemExit("ResearchFlow needs Python 3.10 or newer. Your projects can use a different Python.")
from rf.cli import main
if __name__ == "__main__":
    raise SystemExit(main())
