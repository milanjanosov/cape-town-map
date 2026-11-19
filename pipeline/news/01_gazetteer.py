"""Fetch OSM place nodes/ways in the Cape Town metro bbox via Overpass (clip to metro boundary later)."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
os.chdir(paths.lane_dir("news"))
import json, time, requests
UA = paths.UA
Q = """
[out:json][timeout:120][bbox:-34.37,18.30,-33.46,19.02];
nwr["place"~"^(suburb|neighbourhood|quarter|town|village|hamlet)$"];
out center tags;
"""
for url in ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]:
    try:
        r = requests.post(url, data={"data": Q}, headers=UA, timeout=200)
        r.raise_for_status(); break
    except Exception as e:
        print(url, e); time.sleep(10)
json.dump(r.json(), open("data/osm_places_raw.json", "w"))
print(len(r.json()["elements"]))
