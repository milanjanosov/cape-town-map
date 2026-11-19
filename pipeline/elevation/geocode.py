"""Geocode labels with Nominatim (1 req/s, generic UA).

One-off helper, not part of the build. Usage: python pipeline/elevation/geocode.py out.csv
The build reads the hand-checked pipeline/elevation/inputs/labels_verified.csv instead
(two Nominatim misses were corrected by hand, see README).
"""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import json, time, urllib.parse, urllib.request, csv, sys
Q = [("City Bowl","Gardens, Cape Town"),("Sea Point","Sea Point, Cape Town"),("Camps Bay","Camps Bay, Cape Town"),
 ("Woodstock","Woodstock, Cape Town"),("Observatory","Observatory, Cape Town"),("Claremont","Claremont, Cape Town"),
 ("Constantia","Constantia, Cape Town"),("Muizenberg","Muizenberg"),("Bellville","Bellville, Cape Town"),
 ("Khayelitsha","Khayelitsha"),("Mitchells Plain","Mitchells Plain"),("Durbanville","Durbanville"),
 ("Hout Bay","Hout Bay"),("Simon's Town","Simon's Town"),("Table View","Table View, Cape Town"),("Somerset West","Somerset West"),
 ("Table Mountain (Maclear's Beacon)","Maclear's Beacon"),("Lion's Head","Lion's Head, Cape Town"),("Signal Hill","Signal Hill, Cape Town"),
 ("Devil's Peak","Devil's Peak, Cape Town"),("Constantiaberg","Constantiaberg"),("Cape Point","Cape Point"),("Robben Island","Robben Island"),
 ("Cape Town International Airport","Cape Town International Airport")]
out = []
for lab, q in Q:
    u = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 3, "countrycodes": "za"})
    r = json.load(urllib.request.urlopen(urllib.request.Request(u, headers=paths.UA)))
    if r:
        x = r[0]; out.append([lab, q, x["lat"], x["lon"], x["osm_type"], x["osm_id"], x.get("class"), x.get("type"), x["display_name"][:70]])
        print(out[-1])
    else:
        print("MISS", lab)
    time.sleep(1.1)
with open(sys.argv[1], "w", newline="") as f:
    w = csv.writer(f); w.writerow(["label","query","lat","lon","osm_type","osm_id","class","type","display"]); w.writerows(out)
