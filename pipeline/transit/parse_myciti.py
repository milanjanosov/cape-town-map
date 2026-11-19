"""Parse MyCiTi PDF timetables (pdftotext -layout) into trips and stop times.

MyCiTi publishes no GTFS (google_transit.zip 404, /en/gtfs/ 404 on
2026-11-19); the 41 route PDFs on myciti.org.za/en/timetables/timetable-downloads
are the only machine-readable schedule. Each page is
    <ROUTE>: <name>
    MONDAYS TO FRIDAYS | SATURDAYS | SUNDAYS AND PUBLIC HOLIDAYS
    Direction: To ...
    <stop name>  [Dep|Arr]  hh:mm|-  hh:mm|- ...
Blocks of rows are separated by blank lines; within a block each column is one
trip and '-' keeps the column alignment, so token i of every row is trip i.

Writes data/myciti_stop_times.csv (route, day, direction, block, trip, seq,
stop_name, time, kind) and prints consistency checks: rows whose token count
differs from the block's mode are reported and dropped, never guessed.

Run: python pipeline/transit/parse_myciti.py   (needs pdftotext from poppler)
"""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import collections
import csv
import pathlib
import re
import subprocess

ROOT = paths.lane_dir("transit")
PDF = ROOT / "data" / "myciti_pdf"
TOK = re.compile(r"^([0-2]\d:[0-5]\d|-)$")
DAYS = {"MONDAYS TO FRIDAYS": "weekday", "SATURDAYS": "saturday",
        "SUNDAYS AND PUBLIC HOLIDAYS": "sunday"}


def parse_row(line):
    parts = re.split(r"\s{2,}", line.strip())
    toks = []
    while parts and all(TOK.match(p) for p in parts[-1].split()):
        toks = parts.pop().split() + toks
    if not parts or not toks:
        return None
    name = parts[0]
    kind = ""
    rest = parts[1:]
    if rest and rest[-1] in ("Dep", "Arr"):
        kind = rest[-1]
    elif name.endswith(" Dep") or name.endswith(" Arr"):
        name, kind = name[:-4].strip(), name[-3:]
    return name.strip(), kind, toks


def main():
    rows_out, bad, total = [], 0, 0
    trip_id = 0
    for pdf in sorted(PDF.glob("*.pdf")):
        txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True,
                             text=True).stdout
        for page in txt.split("\f"):
            lines = page.splitlines()
            route = day = direction = None
            for ln in lines[:6]:
                m = re.match(r"\s*([0-9A-Z]+[a-z]?):\s+(.+)", ln)
                if m and route is None:
                    route = m.group(1)
                for k, v in DAYS.items():
                    if ln.strip().startswith(k):
                        day = v
            block = []
            blocks = []
            for ln in lines:
                if ln.strip().startswith("Direction:"):
                    if block:
                        blocks.append((direction, block))
                        block = []
                    direction = ln.split(":", 1)[1].strip()
                    continue
                r = parse_row(ln) if ln.strip() else None
                if r:
                    block.append(r)
                elif block and not ln.strip():
                    blocks.append((direction, block))
                    block = []
            if block:
                blocks.append((direction, block))
            if not route or not day:
                continue
            for bi, (dirn, blk) in enumerate(blocks):
                mode = collections.Counter(len(t) for _, _, t in blk).most_common(1)[0][0]
                good = [r for r in blk if len(r[2]) == mode]
                total += len(blk)
                bad += len(blk) - len(good)
                ids = list(range(trip_id, trip_id + mode))
                trip_id += mode
                for seq, (name, kind, toks) in enumerate(good):
                    for j, tk in enumerate(toks):
                        if tk != "-":
                            rows_out.append(dict(route=route, day=day, direction=dirn, trip=ids[j],
                                                 seq=seq, stop_name=name, time=tk, kind=kind,
                                                 source=pdf.name))
    out = ROOT / "data" / "myciti_stop_times.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0]))
        w.writeheader()
        w.writerows(rows_out)
    print(f"rows parsed {total}, dropped for column mismatch {bad}; stop_times {len(rows_out)} -> {out.name}")


if __name__ == "__main__":
    main()
