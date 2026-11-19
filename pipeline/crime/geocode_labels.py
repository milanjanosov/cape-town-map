"""Look up neighbourhood label coordinates from OpenStreetMap Nominatim
(one request per second) and save them with the OSM object they came from.

One-off helper, not part of the build: it writes raw/crime/data/neighbourhood_labels.json.
Five labels were then re-picked by hand; the build reads pipeline/crime/inputs/neighbourhood_labels.json."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
os.chdir(paths.lane_dir("crime"))
import json, time, urllib.request, urllib.parse
names = ["Sea Point", "Camps Bay", "Constantia", "Claremont", "Observatory",
         "Khayelitsha", "Mitchells Plain", "Durbanville", "Muizenberg",
         "Bellville", "Table View", "Gugulethu", "Hout Bay", "Cape Town city centre"]
out = []
for n in names:
    q = urllib.parse.urlencode({"q": f"{n}, Cape Town, South Africa", "format": "jsonv2", "limit": 1})
    req = urllib.request.Request("https://nominatim.openstreetmap.org/search?" + q,
                                 headers=paths.UA)
    r = json.load(urllib.request.urlopen(req, timeout=60))
    if r:
        x = r[0]; out.append(dict(name=n, lon=float(x["lon"]), lat=float(x["lat"]),
                                  osm=f'{x["osm_type"]}/{x["osm_id"]}', osm_class=f'{x["category"]}/{x["type"]}',
                                  display=x["display_name"]))
        print(n, x["lat"], x["lon"], x["category"], x["type"], "|", x["display_name"][:90])
    else:
        print(n, "NOT FOUND")
    time.sleep(1.2)
json.dump(out, open("data/neighbourhood_labels.json", "w"), indent=1)
