"""Select City of Cape Town precincts and attach population denominators.

Primary denominator: GHS-POP R2023A, epoch 2025, 100 m (JRC, CC BY 4.0), summed
into each precinct polygon (cells assigned by centre point, Mollweide grid).
Cross-check: GeoTerraImage 2024 EA-level estimate (TOTAL_PP24) published by the
Western Cape Government PDO dashboard, summed by precinct (view-only licence:
used only as an aggregated check, not redistributed).
Metro membership: a precinct is in the metro if >50% of its GTI population lies
in EAs of the City of Cape Town municipality.
"""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
os.chdir(paths.lane_dir("crime"))
import json
import numpy as np, pandas as pd, geopandas as gpd, rasterio
from rasterio.features import rasterize

P = gpd.read_file("data/wc_saps_precincts.geojson")
P["precinct"] = P["COMPNT_NM"].str.strip().str.upper()

gti = pd.DataFrame([f["attributes"] for f in json.load(open("data/gti_pop_by_precinct_mun.json"))["features"]])
gti["precinct"] = gti["Precinct"].str.strip().str.upper()
tot = gti.groupby("precinct")["pop"].sum()
ct = gti[gti["MN_NAME_18"] == "City of Cape Town"].groupby("precinct")["pop"].sum()
share = (ct / tot).fillna(0)
print("GTI precinct names not in polygons:", sorted(set(tot.index) - set(P.precinct)))
print("Polygons not in GTI:", sorted(set(P.precinct) - set(tot.index)))
print("Straddling precincts (0<share<1):")
print(share[(share > 0) & (share < 0.999)].round(3).sort_values())

P["gti_pop_2024"] = P.precinct.map(tot)
P["coct_share"] = P.precinct.map(share).fillna(0)
M = P[P.coct_share > 0.5].copy()

# Makhaza (Khayelitsha) reports crime separately but is missing from the 2020
# WCG precinct layer, where its area is still part of Harare. Rebuild it by
# dissolving the EAs that the WCG PDO 2024 dataset assigns to MAKHAZA
# (data/gti_makhaza_eas.geojson), cut it out of Harare, and add it as a polygon.
mk = gpd.read_file("data/gti_makhaza_eas.geojson").to_crs(32734)
mk_geom = mk.dissolve().buffer(2).buffer(-2).iloc[0]
M = M.to_crs(32734)
inside = M.intersection(mk_geom).area / 1e6
print("Makhaza overlap km2 by precinct:", inside[inside > 0.01].round(2).to_dict(), dict(zip(M.precinct[inside > 0.01], [1]*9)))
mk_geom = mk_geom.intersection(M.loc[M.precinct == "HARARE"].geometry.iloc[0].buffer(50))
M.loc[M.precinct == "HARARE", "geometry"] = M.loc[M.precinct == "HARARE"].geometry.difference(mk_geom)
row = dict(precinct="MAKHAZA", PolicePrec="Makhaza", gti_pop_2024=tot["MAKHAZA"], coct_share=1.0, geometry=mk_geom)
M = gpd.GeoDataFrame(pd.concat([M, gpd.GeoDataFrame([row], crs=32734)], ignore_index=True), crs=32734).to_crs(4326)

with rasterio.open("data/raw_ghsl/GHS_POP_E2025_GLOBE_R2023A_54009_100_V1_0_R14_C20.tif") as r:
    Mm = M.to_crs(r.crs)
    w = rasterio.windows.from_bounds(*Mm.total_bounds, transform=r.transform).round_offsets().round_lengths()
    a = r.read(1, window=w).astype("float64"); a[a < 0] = 0
    tr = r.window_transform(w)
lab = rasterize([(g, i + 1) for i, g in enumerate(Mm.geometry)], out_shape=a.shape, transform=tr, fill=0, dtype="int32")
sums = np.bincount(lab.ravel(), weights=a.ravel(), minlength=len(Mm) + 1)
M["ghsl_pop_2025"] = sums[1:].round().astype(int)
M = M[["precinct", "PolicePrec", "gti_pop_2024", "ghsl_pop_2025", "coct_share", "geometry"]]
M.to_file("data/coct_precincts_pop.geojson", driver="GeoJSON")
print(len(M), "metro precincts; GHSL sum", M.ghsl_pop_2025.sum(), "GTI sum", round(M.gti_pop_2024.sum()))
print("ratio GHSL/GTI per precinct:", (M.ghsl_pop_2025 / M.gti_pop_2024).describe().round(2).to_dict())
