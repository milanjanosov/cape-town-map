"""Export crime layers for the MapLibre page (repo data/ folder, prefix crime_)."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
os.chdir(paths.lane_dir("crime"))
import json, os, pandas as pd, geopandas as gpd
from shapely import set_precision
W = str(paths.DATA)
P = gpd.read_file("data/coct_precinct_crime_2025_26.geojson").to_crs(32734)
metro = gpd.read_file("data/coct_metro_boundary.geojson").to_crs(32734).geometry.iloc[0]
P["geometry"] = P.geometry.intersection(metro).simplify(15, preserve_topology=True)
keep = ["name", "pop_gti_2024", "pop_ghsl_2025", "murder", "murder_rate_100k", "murder_rate_100k_ghsl",
        "res_burglary", "res_burglary_rate_100k", "res_burglary_rate_100k_ghsl",
        "vehicle_theft", "vehicle_theft_rate_100k", "theft_from_vehicle", "theft_from_vehicle_rate_100k",
        "vehicle_crime", "vehicle_crime_rate_100k", "res_robbery", "res_robbery_rate_100k",
        "carjacking", "carjacking_rate_100k", "aggr_robbery", "aggr_robbery_rate_100k", "rate_flag"]
G = P[keep + ["geometry"]].rename(columns={"pop_gti_2024": "population", "pop_ghsl_2025": "population_ghsl"}).to_crs(4326)
for c in G.columns:
    if c.endswith("_100k") or c.endswith("_ghsl"):
        G[c + "_label"] = G[c].map(lambda v: "no rate" if pd.isna(v) else f"{v:,.1f}") if c.endswith("_100k") else None
G = G[[c for c in G.columns if G[c].notna().any() or c == "rate_flag"]]
G["reliable"] = G.rate_flag.fillna("") == ""
G["geometry"] = set_precision(G.geometry.values, 1e-5)

def write(gdf, fn):
    path = os.path.join(W, fn)
    js = json.loads(gdf.to_json(na="null", drop_id=True))
    def rnd(o):
        if isinstance(o, float): return round(o, 5)
        if isinstance(o, list): return [rnd(x) for x in o]
        if isinstance(o, dict): return {k: rnd(v) for k, v in o.items()}
        return o
    for f in js["features"]: f["geometry"] = rnd(f["geometry"])
    json.dump(js, open(path, "w"), separators=(",", ":"))
    print(path, len(gdf), f"{os.path.getsize(path)/1e6:.2f} MB")
write(G, "crime_precincts.geojson")

S = gpd.read_file("data/wc_saps_stations.geojson")
S["precinct"] = S.COMPNT_NM.str.upper().str.strip()
S = S[S.precinct.isin(set(P.precinct))].copy()
S["name"] = S.PoliceStat.str.strip() + " police station"
S = S[["name", "geometry"]]
write(S, "crime_police_stations.geojson")

L = pd.DataFrame(json.load(open(paths.inputs("crime") / "neighbourhood_labels.json")))
L = gpd.GeoDataFrame(L[["name", "osm"]], geometry=gpd.points_from_xy(L.lon, L.lat), crs=4326)
write(L, "crime_neighbourhood_labels.geojson")

SRC = ("Counts: SAPS quarterly crime statistics 2025/26, four quarters summed (1 Apr 2025 - 31 Mar 2026), saps.gov.za. "
       "Population: GeoTerraImage 2024 EA estimates summed by precinct, published by Western Cape Government PDO (licence: view only, flagged). "
       "Open alternative: GHS-POP R2023A 2025, 100 m, JRC, CC BY 4.0 (fields *_ghsl). "
       "Precincts: Western Cape Government Spatial Data Warehouse (2020); Makhaza rebuilt from the PDO 2024 EA assignment.")
mr = ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"]
bl = ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"]
pu = ["#f2f0f7", "#cbc9e2", "#9e9ac8", "#756bb1", "#54278f"]
common_popup = {"name": "Precinct", "population": "Residents (2024 est.)"}
def layer(prop, count, title, ramp, breaks, legend, count_label):
    return {"file": "crime_precincts.geojson", "title": title, "geometry_type": "Polygon", "colour_by": prop,
            "colour_ramp": ramp, "class_breaks": breaks, "no_data_colour": "#d9d9d9",
            "units": "reported cases per 100,000 residents per year", "legend": legend,
            "hatch_where": {"reliable": False, "meaning": "rate unreliable: small or commuter population (see rate_flag)"},
            "popup_fields": {**common_popup, count: count_label, prop + "_label": "Per 100,000", "rate_flag": "Note"},
            "source": SRC}
side = {"lane": "crime", "period": "SAPS financial year 2025/26 (1 April 2025 - 31 March 2026)",
        "metro_totals": {"murders": int(P.murder.sum()), "population": int(P.pop_gti_2024.sum()),
                         "murder_rate_100k": round(P.murder.sum() / P.pop_gti_2024.sum() * 1e5, 1),
                         "res_burglary_rate_100k": round(P.res_burglary.sum() / P.pop_gti_2024.sum() * 1e5, 1),
                         "vehicle_crime_rate_100k": round(P.vehicle_crime.sum() / P.pop_gti_2024.sum() * 1e5, 1)},
        "layers": [
    layer("murder_rate_100k", "murder", "Murder rate by police precinct", mr, [0, 10, 25, 50, 100],
          "Murders per 100,000 residents, Apr 2025 - Mar 2026. Metro average 73.", "Murders (12 months)"),
    layer("res_burglary_rate_100k", "res_burglary", "Residential burglary rate by police precinct", bl, [0, 150, 250, 350, 450],
          "Reported residential burglaries per 100,000 residents, Apr 2025 - Mar 2026. Metro average 205. Higher reporting where insurance requires a case number.", "Residential burglaries (12 months)"),
    layer("vehicle_crime_rate_100k", "vehicle_crime", "Vehicle crime rate by police precinct", pu, [0, 150, 300, 600, 1200],
          "Theft of and from motor vehicles per 100,000 residents, Apr 2025 - Mar 2026. Metro average 348. Commuter, shopping and nightlife precincts score high because the cars are not residents'.", "Vehicle thefts + thefts from vehicles"),
    {"file": "crime_police_stations.geojson", "title": "SAPS police stations", "geometry_type": "Point",
     "colour_by": None, "colour_ramp": ["#1f2d3d"], "class_breaks": None, "units": None,
     "legend": "SAPS police station (Makhaza station point not in source layer)", "popup_fields": {"name": "Station"},
     "source": "Western Cape Government Spatial Data Warehouse, SAPS_PoliceStations layer 0."},
    {"file": "crime_neighbourhood_labels.geojson", "title": "Neighbourhood labels (crime lane)", "geometry_type": "Point",
     "colour_by": None, "colour_ramp": ["#000000"], "class_breaks": None, "units": None, "legend": "Reference places",
     "popup_fields": {"name": "Place"}, "source": "OpenStreetMap Nominatim place coordinates (ODbL); osm field gives the object."}]}
json.dump(side, open(os.path.join(W, "crime_layers.json"), "w"), indent=1)
print("crime_layers.json written")
