"""The one place that says where files live. Every pipeline script imports from here.

Layout (all relative to the repo root unless an environment variable overrides it):

    raw/<lane>/data/   downloads and intermediate tables for one lane   (CTM_RAW, git-ignored)
    raw/<lane>/out/    check images and stand-alone PNG maps
    raw/<lane>/tmp/    scratch files
    data/              what index.html loads; the pipeline writes the web layers here (CTM_DATA)
    pipeline/<lane>/inputs/   small hand-curated inputs that ARE committed (label fixes, summaries)

Other settings:
    CTM_USER_AGENT     HTTP User-Agent for every request (default below, no contact details)
    CTM_NEWS_START     first day of the news window, YYYY-MM-DD (default: the published snapshot)
    CTM_NEWS_END       last day of the news window, inclusive
"""
import datetime as _dt
import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RAW = Path(os.environ.get("CTM_RAW", REPO / "raw")).resolve()
DATA = Path(os.environ.get("CTM_DATA", REPO / "data")).resolve()
PIPELINE = REPO / "pipeline"

USER_AGENT = os.environ.get("CTM_USER_AGENT", "cape-town-map/1.0 (+https://github.com/milanjanosov/cape-town-map)")
UA = {"User-Agent": USER_AGENT}

LANES = ["elevation", "demography", "crime", "transit", "news"]

# Highest terrain-tile zoom written. index.html asks for maxzoom 12 (z13 tiles were never deployed).
TERRAIN_ZMAX = int(os.environ.get("CTM_TERRAIN_ZMAX", 12))

# News window (publication dates, inclusive). Default = the snapshot that is live on the site.
NEWS_START = _dt.date.fromisoformat(os.environ.get("CTM_NEWS_START", "2026-10-19"))
NEWS_END = _dt.date.fromisoformat(os.environ.get("CTM_NEWS_END", "2026-11-19"))


def news_window_label():
    """'19 Oct - 19 Nov 2026' style label for map titles and legends."""
    a, b = NEWS_START, NEWS_END
    left = f"{a.day} {a:%b}" + ("" if a.year == b.year else f" {a.year}")
    return f"{left} - {b.day} {b:%b} {b.year}"


def lane_dir(lane):
    """Work folder for one lane, with data/, out/ and tmp/ created."""
    p = RAW / lane
    for sub in ("data", "out", "tmp"):
        (p / sub).mkdir(parents=True, exist_ok=True)
    return p


def inputs(lane):
    """Committed hand-curated inputs for one lane."""
    return PIPELINE / lane / "inputs"


# Shared file: the OSM metro boundary is downloaded by the elevation lane and reused by news.
def osm_boundary():
    return lane_dir("elevation") / "data" / "cct_boundary_osm.geojson"


DATA.mkdir(parents=True, exist_ok=True)
