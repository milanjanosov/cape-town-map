"""Fetch the vector layers for the Cape Town demography lane.

Writes raw GeoJSON / JSON into raw/demography/data/raw/. Re-runnable; overwrites.
"""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import json, urllib.parse, urllib.request
from pathlib import Path

RAW = paths.lane_dir("demography") / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
UA = paths.UA


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def query_all(layer_url, where="1=1", geometry=True, page=1000):
    feats, offset = [], 0
    while True:
        q = {"where": where, "outFields": "*", "f": "geojson" if geometry else "json",
             "returnGeometry": str(geometry).lower(), "outSR": 4326,
             "resultOffset": offset, "resultRecordCount": page}
        d = get(layer_url + "/query?" + urllib.parse.urlencode(q))
        got = d.get("features", [])
        feats += got
        if len(got) < page:
            break
        offset += page
    return feats


LAYERS = {
    # Stats SA 2011 census wards, republished by UCT Libraries (EPSG:4326)
    "wards2011_statssa_uct.geojson": ("https://services3.arcgis.com/GMycIhSIBQnnjV35/arcgis/rest/services/"
                                       "Census_2011_Wards_of_South_Africa/FeatureServer/2", "CAT_B='CPT'", True),
    # City of Cape Town ODP: current wards (service only serves WARD_YEAR 2026 now)
    "wards_cct_odp.geojson": ("https://esapqa.capetown.gov.za/agsext/rest/services/Theme_Based/ODP_SPLIT_5/FeatureServer/6",
                              "1=1", True),
    # City of Cape Town ODP: official planning suburbs
    "suburbs_cct_odp.geojson": ("https://esapqa.capetown.gov.za/agsext/rest/services/Theme_Based/ODP_SPLIT_5/FeatureServer/3",
                                "1=1", True),
    # City of Cape Town ODP: freehold residential valuations by suburb, GV2022 and GV2025 (table)
    "valuations_suburbs_gv2022_gv2025.json": ("https://services6.arcgis.com/nyYfO9SxHU2ChQd9/arcgis/rest/services/"
                                              "Valuations_Suburbs_for_2022_and_2025/FeatureServer/0", "1=1", False),
    # City of Cape Town ODP: 2025 population estimates by suburb (table, modelled from Census 2022)
    "popest2025_suburbs.json": ("https://services6.arcgis.com/nyYfO9SxHU2ChQd9/arcgis/rest/services/"
                                "Population_Estimates_2026_(Suburb_Level)/FeatureServer/0", "1=1", False),
}

if __name__ == "__main__":
    for name, (url, where, geom) in LAYERS.items():
        feats = query_all(url, where, geom)
        out = {"type": "FeatureCollection", "features": feats} if geom else [f["attributes"] for f in feats]
        (RAW / name).write_text(json.dumps(out))
        print(f"{name}: {len(feats)} rows")
