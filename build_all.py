"""Rebuild data/ from raw/ and re-assemble index.html. Same as: python -m pipeline build

    python build_all.py --lane crime
    python build_all.py --page-only
"""
import sys

from pipeline.build import main

if __name__ == "__main__":
    sys.exit(main())
