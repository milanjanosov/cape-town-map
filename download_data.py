"""Fetch every raw source into raw/ (git-ignored). Same as: python -m pipeline download

    python download_data.py --list
    python download_data.py --lane crime
"""
import sys

from pipeline.download import main

if __name__ == "__main__":
    sys.exit(main())
