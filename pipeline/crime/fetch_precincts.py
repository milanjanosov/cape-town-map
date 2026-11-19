"""Download SAPS police precinct polygons (Western Cape) from the Western Cape
Government Spatial Data Warehouse ArcGIS server as GeoJSON."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
os.chdir(paths.lane_dir("crime"))
import json, urllib.request, urllib.parse
B = "https://gis.westerncape.gov.za/server2/rest/services/SpatialDataWarehouse/SAPS_PoliceStations/MapServer"
def q(layer, offset):
    p = dict(where="1=1", outFields="*", outSR="4326", f="geojson",
             resultOffset=offset, resultRecordCount=100)
    u = f"{B}/{layer}/query?" + urllib.parse.urlencode(p)
    return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=paths.UA), timeout=120))
for layer, name in [(3, "wc_saps_precincts"), (0, "wc_saps_stations")]:
    feats, off = [], 0
    while True:
        d = q(layer, off); fs = d.get("features", [])
        feats += fs; off += len(fs)
        if len(fs) < 100: break
    out = f"data/{name}.geojson"
    json.dump({"type": "FeatureCollection", "features": feats}, open(out, "w"))
    print(out, len(feats))
