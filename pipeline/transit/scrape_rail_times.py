"""Metrorail Western Cape departures per station, from kaapsetrains.co.za.

PRASA publishes no GTFS and metrorail.co.za / prasa.com did not resolve on
2026-11-19. Kaapse Train Times (a third-party timetable app) prerenders one
page per (line, station) holding the printed PRASA timetable as plain text:
"Monday to Friday train times from X / Trains to Y hh:mm . hh:mm ...".

This walks every line index page, fetches each station page once, and writes
data/rail_departures.csv: line, station_slug, station_name, day, towards,
departures, first, last. Departures are counted per line page, so a station
on two lines (Bellville: Northern + Central) is summed later.

Run: python pipeline/transit/scrape_rail_times.py  (pages are cached in raw/transit/data/kaapsetrains/pages,
so a second run is offline)
"""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import csv
import html
import pathlib
import re
import time
import urllib.request

ROOT = paths.lane_dir("transit")
RAW = ROOT / "data" / "kaapsetrains" / "pages"
RAW.mkdir(parents=True, exist_ok=True)
BASE = "https://kaapsetrains.co.za"
LINES = ["southern", "northern", "central", "cape-flats"]
TIME = re.compile(r"\b([0-2]\d:[0-5]\d)\b")


def get(path):
    f = RAW / (path.strip("/").replace("/", "__") + ".html")
    if f.exists():
        return f.read_text()
    req = urllib.request.Request(BASE + path, headers=paths.UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        s = r.read().decode("utf-8", "replace")
    f.write_text(s)
    time.sleep(1.0)
    return s


def text_of(s):
    i = s.find('id="root"')
    t = re.sub(r"<[^>]+>", " ", s[i:])
    return html.unescape(re.sub(r"\s+", " ", t))


def main():
    rows = []
    for line in LINES:
        idx = get(f"/{line}/")
        slugs = sorted(set(re.findall(r'href="/(?:southern|northern|central|cape-flats)/([a-z0-9-]+)/"', idx)))
        print(line, len(slugs), "stations")
        for slug in slugs:
            try:
                t = text_of(get(f"/{line}/{slug}/"))
            except Exception as e:
                print("  skip", line, slug, e)
                continue
            m = re.search(r"Kaapse Train Times › [^›]+? Line (.+?) station train timetable", t)
            name = m.group(1).strip() if m else slug
            # split into day blocks
            blocks = re.split(r"(Monday to Friday|Saturday|Sunday) train times from ", t)
            for k in range(1, len(blocks) - 1, 2):
                day = {"Monday to Friday": "weekday"}.get(blocks[k], blocks[k].lower())
                body = blocks[k + 1].split(" About ")[0]
                for dest, times in re.findall(r"Trains to (.+?) ((?:[0-2]\d:[0-5]\d(?: · )?)+)", body):
                    ts = TIME.findall(times)
                    rows.append(dict(line=line, station_slug=slug, station_name=name, day=day,
                                     towards=dest.strip(), departures=len(ts),
                                     first=min(ts), last=max(ts), times=" ".join(ts)))
    out = ROOT / "data" / "rail_departures.csv"
    with out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "rows ->", out)


if __name__ == "__main__":
    main()
