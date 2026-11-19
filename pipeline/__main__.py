"""python -m pipeline download [...]  |  python -m pipeline build [...]"""
import sys

from pipeline import build, download

USAGE = "usage: python -m pipeline {download|build} [options]   (--help after the command for options)"

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("download", "build"):
        print(USAGE)
        sys.exit(2)
    mod = download if sys.argv[1] == "download" else build
    sys.exit(mod.main(sys.argv[2:]))
