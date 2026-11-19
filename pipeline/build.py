"""Rebuild the web layers in data/ from raw/ (run download_data.py first), then index.html.

    python build_all.py                   # all lanes, then index.html
    python build_all.py --lane crime      # one lane (repeatable)
    python build_all.py --no-maps         # skip the stand-alone check PNGs (some need basemap tiles)
    python build_all.py --page-only       # only re-assemble index.html from src/

Each lane runs its own scripts in the order its README gave. Check images land in raw/<lane>/out/.
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import paths  # noqa: E402

PY = sys.executable


def crime_parse():
    d = paths.lane_dir("crime") / "data"
    return [("parse_saps_quarter.py", str(d / "raw_saps" / f"2025-2026_{q}_Quarter.xlsx"),
             str(d / f"saps_2025_26_Q{i}.csv")) for i, q in enumerate(("1st", "2nd", "3rd", "4th"), 1)]


# (script, *args); entries marked MAP are check images only and are skipped by --no-maps
MAP = "map"
ORDER = {
    "elevation": [("build_web.py",), (MAP, "check_web.py")],
    "demography": [("parse_ward_profiles_2011.py",), ("build.py",),
                   ("maps.py",),  # also writes data/label_points.geojson, which export_web.py needs
                   ("export_web.py",)],
    "crime": lambda: crime_parse() + [("precinct_population.py",), ("build_tables.py",), (MAP, "make_maps.py"),
                                      ("export_web.py",)],
    "transit": [("scrape_rail_times.py",),  # offline when the downloader has cached the pages
                ("parse_myciti.py",), ("build_layers.py",), (MAP, "make_maps.py"), ("write_sidecar.py",)],
    "news": [("03_build_gazetteer.py",), ("05_extract.py",), ("06_plots_and_web.py",)],
}


def steps(lane, maps=True):
    seq = ORDER[lane]() if callable(ORDER[lane]) else ORDER[lane]
    out = []
    for s in seq:
        if s[0] == MAP:
            if maps:
                out.append(s[1:])
        else:
            out.append(s)
    return out


def build_page():
    r = subprocess.run([PY, str(paths.REPO / "src" / "build.py")])
    return r.returncode == 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lane", action="append", choices=paths.LANES)
    ap.add_argument("--no-maps", action="store_true", help="skip check-image scripts")
    ap.add_argument("--page-only", action="store_true", help="only rebuild index.html from src/")
    a = ap.parse_args(argv)
    if a.page_only:
        return 0 if build_page() else 1
    failed = []
    for lane in a.lane or paths.LANES:
        print(f"\n=== {lane}", flush=True)
        for script, *args in steps(lane, maps=not a.no_maps):
            t = time.time()
            print(f"--- {lane}/{script} {' '.join(Path(x).name for x in args)}", flush=True)
            r = subprocess.run([PY, str(paths.PIPELINE / lane / script), *args])
            if r.returncode:
                print(f"FAIL {lane}/{script} (exit {r.returncode}); later steps of this lane skipped")
                failed.append(f"{lane}/{script}")
                break
            print(f"    done in {time.time() - t:.0f} s", flush=True)
    print("\n=== index.html")
    if not build_page():
        failed.append("src/build.py")
    if failed:
        print("\nFailed:", ", ".join(failed), "\nMissing inputs? Run: python download_data.py --list")
        return 1
    print(f"\nAll done. Web layers are in {paths.DATA}. Preview: python -m http.server 8000, then open "
          "http://localhost:8000/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
