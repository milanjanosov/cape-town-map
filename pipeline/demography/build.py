"""Build the Cape Town demography layers: tables, web GeoJSON, check numbers.

Inputs (data/raw/, see fetch_layers.py and parse_ward_profiles_2011.py):
  wards2011_statssa_uct.geojson     Stats SA 2011 wards (111 in CPT)
  wards_cct_odp.geojson             City of Cape Town wards, 2026 delimitation (118)
  suburbs_cct_odp.geojson           City official planning suburbs (778)
  valuations_suburbs_gv2022_gv2025.json  median freehold residential valuation by suburb
  ghsl/GHS_POP_E2020_..._R14_C20.tif     GHSL population grid, 100 m, epoch 2020
  data/ward_census2011.csv          parsed City 2011 ward profiles (Census 2011)
Outputs:
  data/processed/*.gpkg (under raw/demography/); web GeoJSON is written by export_web.py
"""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask
from rasterio.warp import Resampling, calculate_default_transform, reproject
from rasterio.features import rasterize
from shapely.geometry import box, mapping

ROOT = paths.lane_dir("demography")
RAW, PROC = ROOT / "data" / "raw", ROOT / "data" / "processed"
WEB = paths.DATA
PROC.mkdir(exist_ok=True, parents=True)
WEB.mkdir(exist_ok=True, parents=True)
UTM = 32734  # WGS 84 / UTM 34S, metres
GHSL = RAW / "ghsl" / "GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R14_C20.tif"

CENSUS2022_CPT_POP = 4_772_846   # Stats SA Census 2022, City of Cape Town (census.statssa.gov.za)
CENSUS2022_CPT_HH = 1_452_845
CENSUS2011_CPT_POP = 3_740_026   # Stats SA Census 2011, City of Cape Town (City 2011 profile)
CENSUS2011_CPT_HH = 1_068_573

# monthly household income bands, Census 2011 (Rand, nominal 2011)
BANDS = [("no_income", 0, 0), ("r1_1600", 1, 1600), ("r1601_3200", 1601, 3200), ("r3201_6400", 3201, 6400),
         ("r6401_12800", 6401, 12800), ("r12801_25600", 12801, 25600), ("r25601_51200", 25601, 51200),
         ("r51201_102400", 51201, 102400), ("r102401_plus", 102401, None)]


def median_income(row):
    """Grouped median of monthly household income (linear within band), unspecified excluded."""
    counts = [row[f"income_{b}"] for b, _, _ in BANDS]
    n = sum(counts)
    half, cum = n / 2, 0
    for (b, lo, hi), c in zip(BANDS, counts):
        if cum + c >= half:
            if b == "no_income":
                return 0.0
            if hi is None:
                return float(lo)  # open top band: report its floor
            return lo + (half - cum) / c * (hi - lo)
        cum += c
    return np.nan


def wards2011():
    g = gpd.read_file(RAW / "wards2011_statssa_uct.geojson")[["WARDNO", "WARD_ID", "geometry"]]
    g = g.rename(columns={"WARDNO": "ward", "WARD_ID": "ward_id_statssa"})
    d = pd.read_csv(ROOT / "data" / "ward_census2011.csv")
    g = g.merge(d, on="ward", how="inner", validate="1:1")
    assert len(g) == 111, len(g)
    g["area_km2"] = g.to_crs(UTM).area / 1e6
    g["population"] = g.pop_official
    g["households"] = g.hh_official
    g["density_per_km2"] = g.population / g.area_km2
    inc_n = g.income_total - g.income_unspecified
    g["income_households"] = inc_n
    g["hh_low_income"] = g.income_no_income + g.income_r1_1600 + g.income_r1601_3200
    g["hh_high_income"] = g.income_r25601_51200 + g.income_r51201_102400 + g.income_r102401_plus
    g["pct_low_income"] = 100 * g.hh_low_income / inc_n
    g["pct_high_income"] = 100 * g.hh_high_income / inc_n
    g["median_hh_income_month_2011"] = g.apply(median_income, axis=1)
    g["hh_informal"] = g.dwelling_informal_backyard + g.dwelling_informal_not_backyard
    g["pct_informal"] = 100 * g.hh_informal / g.dwelling_total
    g["pct_informal_backyard"] = 100 * g.dwelling_informal_backyard / g.dwelling_total
    g["pct_informal_not_backyard"] = 100 * g.dwelling_informal_not_backyard / g.dwelling_total
    g["unemployment_rate"] = 100 * g.unemployed / g.labour_force
    for c in ["black_african", "coloured", "asian", "white", "other"]:
        g[f"pct_{c}"] = 100 * g[f"popgroup_{c}"] / g.popgroup_total
    return g


def city_boundary():
    w = gpd.read_file(RAW / "wards_cct_odp.geojson")
    w["ward"] = w.WARD_NAME.astype(int)
    return w


def ghsl_utm():
    """Reproject the GHSL tile (Mollweide) to UTM 34S at 100 m, cropped to the city, sum-preserving."""
    wards = city_boundary().to_crs(UTM)
    xmin, ymin, xmax, ymax = wards.total_bounds
    pad = 3000
    with rasterio.open(GHSL) as src:
        bb = gpd.GeoSeries([box(xmin - pad, ymin - pad, xmax + pad, ymax + pad)], crs=UTM).to_crs(src.crs)
        arr, tr = mask(src, [mapping(bb.iloc[0])], crop=True, nodata=0)
        arr = np.where(arr[0] < 0, 0, arr[0]).astype("float64")
        src_crs = src.crs
    w = int((xmax - xmin + 2 * pad) // 100)
    h = int((ymax - ymin + 2 * pad) // 100)
    dst_tr = rasterio.transform.from_origin(xmin - pad, ymax + pad, 100, 100)
    dst = np.zeros((h, w), "float64")
    # 100 m -> 100 m with near-identical cell area; use 'sum' to preserve counts
    reproject(arr, dst, src_transform=tr, src_crs=src_crs, dst_transform=dst_tr, dst_crs=f"EPSG:{UTM}",
              resampling=Resampling.sum)
    return dst, dst_tr, arr.sum()


def main():
    checks = {}
    w11 = wards2011()
    checks["wards_2011_count"] = int(len(w11))
    checks["wards_2011_population_sum"] = int(w11.population.sum())
    checks["wards_2011_households_sum"] = int(w11.households.sum())
    checks["census2011_cpt_population_published"] = CENSUS2011_CPT_POP
    checks["census2011_cpt_households_published"] = CENSUS2011_CPT_HH
    checks["wards_2011_area_km2"] = round(float(w11.area_km2.sum()), 1)

    w26 = city_boundary()
    checks["wards_2026_count"] = int(len(w26))
    w26u = w26.to_crs(UTM)
    w26["area_km2"] = w26u.area / 1e6
    checks["city_area_km2_from_2026_wards"] = round(float(w26.area_km2.sum()), 1)

    pop, tr, raw_sum = ghsl_utm()
    ids = rasterize([(g, i + 1) for i, g in enumerate(w26u.geometry)], out_shape=pop.shape, transform=tr,
                    fill=0, dtype="int32")  # cell-centre assignment
    sums = np.bincount(ids.ravel(), weights=pop.ravel(), minlength=len(w26u) + 1)
    w26["ghsl_pop_2020"] = sums[1:]
    checks["ghsl_2020_sum_in_bbox"] = round(float(pop.sum()))
    city_ghsl = float(w26.ghsl_pop_2020.sum())
    checks["ghsl_2020_sum_in_city"] = round(city_ghsl)
    checks["census2022_cpt_population_published"] = CENSUS2022_CPT_POP
    checks["ghsl_2020_vs_census2022_ratio"] = round(city_ghsl / CENSUS2022_CPT_POP, 3)
    w26["ghsl_density_per_km2"] = w26.ghsl_pop_2020 / w26.area_km2
    # Census-2022-scaled estimate: GHSL spatial pattern, rescaled so the city total equals Census 2022
    scale = CENSUS2022_CPT_POP / city_ghsl
    w26["pop_2022_est"] = w26.ghsl_pop_2020 * scale
    w26["density_2022_est_per_km2"] = w26.pop_2022_est / w26.area_km2
    checks["census2022_scale_factor_applied"] = round(scale, 4)

    # 500 m grid for the web density layer (GHSL 2020, rescaled to Census 2022 total)
    k = 5
    h, wd = (pop.shape[0] // k) * k, (pop.shape[1] // k) * k
    agg = pop[:h, :wd].reshape(h // k, k, wd // k, k).sum(axis=(1, 3))
    x0, y0 = tr.c, tr.f
    rows, cols = np.nonzero(agg >= 5)
    cells = gpd.GeoDataFrame(
        {"ghsl_pop_2020": agg[rows, cols]},
        geometry=[box(x0 + c * 500, y0 - (r + 1) * 500, x0 + (c + 1) * 500, y0 - r * 500) for r, c in zip(rows, cols)],
        crs=UTM)
    city = w26u.union_all()
    cells = cells[cells.intersects(city)].copy()
    cells["geometry"] = cells.intersection(city)
    cells = cells[~cells.is_empty]
    cells["area_km2"] = cells.area / 1e6
    cells = cells[cells.area_km2 > 0.01]
    cells["pop_2022_est"] = cells.ghsl_pop_2020 * scale
    # clipped coastal/edge cells: divide by the land part, but never by less than 0.05 km2
    cells["density_per_km2"] = cells.pop_2022_est / cells.area_km2.clip(lower=0.05)
    checks["grid_500m_cells"] = int(len(cells))
    checks["grid_500m_pop_2022_est_sum"] = round(float(cells.pop_2022_est.sum()))

    # suburbs + valuations
    sub = gpd.read_file(RAW / "suburbs_cct_odp.geojson")[["OFC_SBRB_NAME", "geometry"]]
    val = pd.read_json(RAW / "valuations_suburbs_gv2022_gv2025.json").drop(columns=["FID"])
    sub = sub.merge(val, left_on="OFC_SBRB_NAME", right_on="OFFICIAL_SUBURB", how="left")
    checks["suburbs_total"] = int(len(sub))
    checks["suburbs_with_valuation"] = int(sub.GV2025_VAL.notna().sum())
    checks["valuation_rows_unmatched"] = int((~val.OFFICIAL_SUBURB.isin(sub.OFC_SBRB_NAME)).sum())

    # save processed
    w11.to_file(PROC / "wards2011_census.gpkg", driver="GPKG")
    w26.to_file(PROC / "wards2026_ghsl.gpkg", driver="GPKG")
    cells.to_file(PROC / "grid500_ghsl.gpkg", driver="GPKG")
    sub.to_file(PROC / "suburbs_valuation.gpkg", driver="GPKG")
    np.save(PROC / "ghsl2020_utm34s_100m.npy", pop)
    (PROC / "ghsl2020_utm34s_100m.transform.json").write_text(json.dumps(list(tr)[:6]))
    (ROOT / "data" / "checks.json").write_text(json.dumps(checks, indent=2))
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
