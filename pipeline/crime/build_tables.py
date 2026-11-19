"""Sum the four 2025/26 SAPS quarterly releases into financial-year station
counts for the City of Cape Town precincts and compute rates per 100,000.

Denominators: pop_gti_2024 (primary: GeoTerraImage 2024 EA estimate via WCG PDO,
summed by precinct) and pop_ghsl_2025 (open-licence sensitivity check)."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
os.chdir(paths.lane_dir("crime"))
import pandas as pd, geopandas as gpd, numpy as np

CATS = {
    "murder": ["Murder"],
    "res_burglary": ["Burglary at residential premises"],
    "vehicle_theft": ["Theft of motor vehicle and motorcycle"],
    "theft_from_vehicle": ["Theft out of or from motor vehicle"],
    "vehicle_crime": ["Theft of motor vehicle and motorcycle", "Theft out of or from motor vehicle"],
    "res_robbery": ["Robbery at residential premises"],
    "carjacking": ["Carjacking"],
    "aggr_robbery": ["Robbery with aggravating circumstances"],
}
MIN_POP = 5000      # below this no rate is shown
UNSTABLE_POP = 15000

d = pd.concat([pd.read_csv(f"data/saps_2025_26_Q{q}.csv") for q in range(1, 5)])
assert sorted(d.month.unique()) == [f"2025-{m:02d}" for m in range(4, 13)] + ["2026-01", "2026-02", "2026-03"]
d["precinct"] = d.station.str.upper().str.strip()
P = gpd.read_file("data/coct_precincts_pop.geojson")
P = P.rename(columns={"gti_pop_2024": "pop_gti_2024", "ghsl_pop_2025": "pop_ghsl_2025"})
P["pop_gti_2024"] = P.pop_gti_2024.round().astype(int)
P["name"] = P.precinct.str.title().str.replace("'S", "'s").str.replace("-West", "-West")

for k, cats in CATS.items():
    s = d[d.category.isin(cats)].groupby("precinct")["count"].sum()
    P[k] = P.precinct.map(s).fillna(0).astype(int)
    for pc, popcol in [("", "pop_gti_2024"), ("_ghsl", "pop_ghsl_2025")]:
        r = P[k] / P[popcol] * 1e5
        P[f"{k}_rate_100k{pc}"] = r.where(P[popcol] >= MIN_POP).round(1)

P["rate_flag"] = np.select([P.pop_gti_2024 < MIN_POP, P.pop_gti_2024 < UNSTABLE_POP],
                           ["no rate: residential population under 5,000", "unstable: population under 15,000"], "")
P.loc[P.precinct == "CAPE TOWN CENTRAL", "rate_flag"] = "commuter/visitor area: daytime population far above residents"
P.to_file("data/coct_precinct_crime_2025_26.geojson", driver="GeoJSON")

cols = ["name", "pop_gti_2024", "pop_ghsl_2025", "murder", "murder_rate_100k", "murder_rate_100k_ghsl",
        "res_burglary", "res_burglary_rate_100k", "vehicle_crime", "vehicle_crime_rate_100k",
        "res_robbery", "res_robbery_rate_100k", "carjacking", "carjacking_rate_100k", "rate_flag"]
T = P[cols].sort_values("murder_rate_100k", ascending=False, na_position="last")
T.insert(0, "murder_rank", range(1, len(T) + 1))
T.loc[T.murder_rate_100k.isna(), "murder_rank"] = np.nan
T.to_csv("out/capetown_precinct_crime_ranked.csv", index=False)

# --- checks -------------------------------------------------------------
wc = d[(d.province == "Western Cape") & (d.category == "Murder")]
print("WC murders FY", wc["count"].sum(), "| WC murders Jan-Mar 2026", wc[wc.month >= "2026-01"]["count"].sum())
print("National murders FY", d[d.category == "Murder"]["count"].sum())
dist = d[d.district == "City of Cape Town District"]
for k, cats in CATS.items():
    print(f"{k:20s} district total {dist[dist.category.isin(cats)]['count'].sum():7d}  mapped precincts {P[k].sum():7d}")
print("stations in district not mapped:", sorted(set(dist.precinct) - set(P.precinct)))
print("metro pop GTI", P.pop_gti_2024.sum(), "GHSL", P.pop_ghsl_2025.sum())
print("metro murder rate (GTI)", round(P.murder.sum() / P.pop_gti_2024.sum() * 1e5, 1))
ok = P.murder_rate_100k.notna()
print("Spearman murder rate GTI vs GHSL:", round(P.loc[ok, "murder_rate_100k"].corr(P.loc[ok, "murder_rate_100k_ghsl"], method="spearman"), 3))
print("Spearman burglary rate GTI vs GHSL:", round(P.loc[ok, "res_burglary_rate_100k"].corr(P.loc[ok, "res_burglary_rate_100k_ghsl"], method="spearman"), 3))
pd.set_option("display.width", 250)
print(T.drop(columns=["rate_flag"]).to_string(index=False))
print(P[P.rate_flag != ""][["name", "pop_gti_2024", "rate_flag"]])
