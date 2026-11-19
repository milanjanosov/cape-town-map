"""Fetch every Cape Town transit source this lane uses into data/.

- City of Cape Town Open Data Portal (ArcGIS FeatureServer): MyCiTi routes and
  stops, minibus-taxi routes, railway lines and stations. Paged queries, WGS84.
- OpenStreetMap via Overpass: bus route relations (Golden Arrow et al.) and
  train route relations, as the only open source for Golden Arrow geometry.
- Stellenbosch GTFS (DT4A, Mobility Database mdb-1965): the only South African
  Western Cape GTFS in the catalogue; checked, but it is outside the metro.

Run: python pipeline/transit/fetch_sources.py   (or: python download_data.py --lane transit)
"""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import json
import pathlib
import time
import urllib.parse
import urllib.request

ROOT = paths.lane_dir("transit")
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

B = "https://esapqa.capetown.gov.za/agsext/rest/services/Theme_Based"
LAYERS = {
    "cct_myciti_routes": f"{B}/ODP_SPLIT_6/FeatureServer/9",
    "cct_myciti_stops": f"{B}/ODP_SPLIT_6/FeatureServer/10",
    "cct_taxi_routes": f"{B}/ODP_SPLIT_6/FeatureServer/11",
    "cct_rail_lines": f"{B}/ODP_SPLIT_12/FeatureServer/5",
    "cct_rail_stations": f"{B}/ODP_SPLIT_12/FeatureServer/6",
}


def get(url, data=None, timeout=180):
    req = urllib.request.Request(url, data=data, headers=paths.UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_layer(name, url):
    feats, offset = [], 0
    while True:
        q = urllib.parse.urlencode({
            "where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson",
            "resultOffset": offset, "resultRecordCount": 1000,
        })
        d = json.loads(get(f"{url}/query?{q}"))
        got = d.get("features", [])
        feats += got
        if len(got) < 1000:
            break
        offset += len(got)
    out = DATA / f"{name}.geojson"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print(f"{name}: {len(feats)} features -> {out.name}")


OVERPASS = "https://overpass-api.de/api/interpreter"
# City of Cape Town metro bbox (S, W, N, E)
BBOX = "-34.36,18.30,-33.47,19.00"


def fetch_osm(name, route_filter):
    q = f"""[out:json][timeout:300];
relation{route_filter}({BBOX});
out body;
>;
out skel qt;"""
    raw = get(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(), timeout=400)
    (DATA / f"{name}.json").write_bytes(raw)
    d = json.loads(raw)
    n = sum(1 for e in d["elements"] if e["type"] == "relation")
    print(f"{name}: {n} relations")


if __name__ == "__main__":
    for k, v in LAYERS.items():
        fetch_layer(k, v)
    fetch_osm("osm_bus_routes", '["type"="route"]["route"="bus"]')
    time.sleep(5)
    fetch_osm("osm_train_routes", '["type"="route"]["route"="train"]')
    gz = DATA / "stellenbosch_gtfs.zip"
    if not gz.exists():
        gz.write_bytes(get("https://files.mobilitydatabase.org/mdb-1965/latest.zip"))
    print("stellenbosch_gtfs.zip", gz.stat().st_size)
