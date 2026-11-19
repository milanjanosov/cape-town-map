"""Export the demography layers to the repo data/ folder (paths.DATA)."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import json
from pathlib import Path

import geopandas as gpd
import numpy as np

ROOT = paths.lane_dir("demography")
PROC = ROOT / "data" / "processed"
WEB = paths.DATA
WEB.mkdir(parents=True, exist_ok=True)
UTM = 32734
TOL = 15  # metres


def write(gdf, name, cols, decimals=1):
    g = gdf.to_crs(UTM).copy()
    g["geometry"] = g.geometry.simplify(TOL, preserve_topology=True).make_valid()
    g = g[~g.geometry.is_empty].to_crs(4326)
    g = g[cols + ["geometry"]].copy()
    for c in cols:
        if g[c].dtype.kind == "f":
            g[c] = g[c].round(decimals)
    path = WEB / name
    path.write_text(g.to_json(drop_id=True, na="null"))
    # round coordinates to 5 decimals
    d = json.loads(path.read_text())

    def rnd(x):
        return [rnd(v) for v in x] if isinstance(x[0], list) else [round(x[0], 5), round(x[1], 5)]
    for f in d["features"]:
        f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
    path.write_text(json.dumps(d, separators=(",", ":")))
    mb = path.stat().st_size / 1e6
    print(f"{name}: {len(g)} features, {mb:.2f} MB")
    assert mb < 5, name
    return len(g)


def main():
    checks = json.loads((ROOT / "data" / "checks.json").read_text())

    # 1. 500 m density grid
    grid = gpd.read_file(PROC / "grid500_ghsl.gpkg")
    grid["pop_2022_est"] = grid.pop_2022_est.round(0)
    grid["ghsl_pop_2020"] = grid.ghsl_pop_2020.round(0)
    grid["density_per_km2"] = grid.density_per_km2.round(0)
    grid["area_km2"] = grid.area_km2.round(3)
    write(grid, "demography_density_grid500.geojson", ["density_per_km2", "pop_2022_est", "ghsl_pop_2020", "area_km2"])

    # 2. Census 2011 wards
    w = gpd.read_file(PROC / "wards2011_census.gpkg")
    w["ward_label"] = "Ward " + w.ward.astype(str)
    w["median_hh_income_month_2011"] = w.median_hh_income_month_2011.round(-1)
    w["median_income_open_top"] = w.median_hh_income_month_2011 >= 102401
    cols = ["ward", "ward_label", "areas", "population", "households", "area_km2", "density_per_km2",
            "median_hh_income_month_2011", "income_households", "hh_low_income", "pct_low_income",
            "hh_high_income", "pct_high_income",
            "dwelling_total", "hh_informal", "pct_informal", "dwelling_informal_backyard", "pct_informal_backyard",
            "dwelling_informal_not_backyard", "pct_informal_not_backyard",
            "labour_force", "employed", "unemployed", "unemployment_rate",
            "popgroup_total", "popgroup_black_african", "pct_black_african", "popgroup_coloured", "pct_coloured",
            "popgroup_asian", "pct_asian", "popgroup_white", "pct_white", "popgroup_other", "pct_other"]
    write(w, "demography_wards2011_census.geojson", cols)

    # 3. 2026 wards with GHSL-based density
    w26 = gpd.read_file(PROC / "wards2026_ghsl.gpkg")
    w26["ward_label"] = "Ward " + w26.ward.astype(str)
    w26["pop_2022_est"] = w26.pop_2022_est.round(0)
    w26["ghsl_pop_2020"] = w26.ghsl_pop_2020.round(0)
    w26["density_2022_est_per_km2"] = w26.density_2022_est_per_km2.round(0)
    write(w26, "demography_wards2026_density.geojson",
          ["ward", "ward_label", "area_km2", "pop_2022_est", "ghsl_pop_2020", "density_2022_est_per_km2"])

    # 4. suburb valuations
    s = gpd.read_file(PROC / "suburbs_valuation.gpkg")
    s["area_km2"] = s.to_crs(UTM).area / 1e6
    s["props_per_km2"] = s.NUM_RES_PROP / s.area_km2
    s = s[s.GV2025_VAL.notna() & (s.NUM_RES_PROP >= 20) & (s.props_per_km2 >= 20)].copy()
    s = s.rename(columns={"OFC_SBRB_NAME": "suburb", "NUM_RES_PROP": "freehold_res_properties",
                          "MED_LAND_EXTENT_m2": "median_erf_m2", "MED_TOT_BLD_AREA_m2": "median_building_m2",
                          "GV2022_VAL": "median_value_gv2022", "GV2025_VAL": "median_value_gv2025"})
    s["suburb"] = s.suburb.str.title()
    s["change_2022_2025_pct"] = 100 * (s.median_value_gv2025 / s.median_value_gv2022 - 1)
    write(s, "demography_suburb_valuation_gv2025.geojson",
          ["suburb", "freehold_res_properties", "median_value_gv2025", "median_value_gv2022", "change_2022_2025_pct",
           "median_erf_m2", "median_building_m2"])

    # 5. label points
    lp = gpd.read_file(ROOT / "data" / "label_points.geojson")
    d = json.loads(lp[["label", "geometry"]].to_json(drop_id=True))
    for f in d["features"]:
        f["geometry"]["coordinates"] = [round(c, 5) for c in f["geometry"]["coordinates"]]
    (WEB / "demography_labels.geojson").write_text(json.dumps(d, separators=(",", ":")))

    seq = ["#2b1b3d", "#5b2a6e", "#a2416f", "#e07a5f", "#f6c87a"]
    dens_ramp = ["#1c1030", "#4a1c6b", "#8c2981", "#d3436e", "#fb8761", "#fcfdbf"]
    src_census11 = ("Stats SA Census 2011, via City of Cape Town 2011 ward profiles (Jan 2013); ward boundaries Stats SA 2011 "
                    "(published by UCT Libraries). Stats SA copyright: free use with attribution.")
    layers = {
        "lane": "demography",
        "updated": "2026-11-19",
        "layers": [
            {
                "file": "demography_density_grid500.geojson",
                "title": "Population density (500 m grid)",
                "geometry": "Polygon",
                "color_by": "density_per_km2",
                "ramp": dens_ramp,
                "breaks": [500, 2000, 5000, 10000, 20000],
                "units": "residents per km²",
                "legend": "Residents per km², GHSL 2020 grid rescaled to the Census 2022 city total (4,772,846)",
                "popup": {"density_per_km2": "Residents per km²", "pop_2022_est": "Residents in cell (2022 est.)",
                          "area_km2": "Land area in city (km²)"},
                "source": f"European Commission JRC GHS-POP R2023A, epoch 2020, 100 m (CC BY 4.0), aggregated to 500 m and "
                          f"scaled x{checks['census2022_scale_factor_applied']} to the Stats SA Census 2022 City of Cape Town total. "
                          "Modelled grid, not a census count.",
            },
            {
                "file": "demography_wards2011_census.geojson",
                "title": "Household income by ward (Census 2011)",
                "geometry": "Polygon",
                "color_by": "median_hh_income_month_2011",
                "ramp": seq,
                "breaks": [3200, 6400, 12800, 25600],
                "units": "rand per month (2011 prices)",
                "legend": "Median monthly household income, Census 2011, 2011 rand. Latest small-area income available; "
                          "Census 2022 income not released.",
                "popup": {"ward_label": "Ward (2011)", "areas": "Areas", "households": "Households",
                          "median_hh_income_month_2011": "Median household income / month (R, 2011)",
                          "pct_low_income": "% households R3,200/month or less (incl. no income)",
                          "pct_high_income": "% households above R25,600/month",
                          "unemployment_rate": "Unemployment rate % (15-64, official definition)"},
                "denominators": {"pct_low_income": "income_households (households with stated income)",
                                 "pct_high_income": "income_households",
                                 "unemployment_rate": "labour_force"},
                "source": src_census11,
            },
            {
                "file": "demography_wards2011_census.geojson",
                "title": "Informal dwellings by ward (Census 2011)",
                "geometry": "Polygon",
                "color_by": "pct_informal",
                "ramp": ["#1f2a36", "#3d4f5f", "#c58b4c", "#e0662f", "#ff3d2e"],
                "breaks": [2, 10, 25, 50],
                "units": "% of households",
                "legend": "Households in an informal dwelling (backyard shack or informal settlement), Census 2011",
                "popup": {"ward_label": "Ward (2011)", "areas": "Areas", "dwelling_total": "Households",
                          "pct_informal": "% informal dwelling", "pct_informal_backyard": "% backyard shack",
                          "pct_informal_not_backyard": "% shack not in backyard (informal settlement)"},
                "denominators": {"pct_informal": "dwelling_total (all households in the dwelling table)"},
                "source": src_census11,
            },
            {
                "file": "demography_wards2011_census.geojson",
                "title": "Population density by ward (Census 2011)",
                "geometry": "Polygon",
                "color_by": "density_per_km2",
                "ramp": dens_ramp[:5],
                "breaks": [1000, 3000, 6000, 12000],
                "units": "residents per km²",
                "legend": "Residents per km² of ward area, Census 2011 (ward area includes parks, industry, farmland)",
                "popup": {"ward_label": "Ward (2011)", "population": "Population (2011)", "area_km2": "Area km²",
                          "density_per_km2": "Residents per km²"},
                "source": src_census11,
            },
            {
                "file": "demography_wards2011_census.geojson",
                "title": "Population group by ward (Census 2011, optional)",
                "geometry": "Polygon",
                "color_by": None,
                "note": "Not a colour layer. Fields pct_black_african, pct_coloured, pct_asian, pct_white, pct_other "
                        "(Stats SA self-identified population-group categories, denominator popgroup_total) are included "
                        "for popups only, to explain the spatial legacy of apartheid-era Group Areas. Label factually.",
                "popup": {"pct_black_african": "% Black African", "pct_coloured": "% Coloured", "pct_asian": "% Indian/Asian",
                          "pct_white": "% White", "pct_other": "% Other"},
                "source": src_census11,
            },
            {
                "file": "demography_suburb_valuation_gv2025.geojson",
                "title": "Median house valuation by suburb (GV2025)",
                "geometry": "Polygon",
                "color_by": "median_value_gv2025",
                "ramp": seq,
                "breaks": [500000, 1000000, 2000000, 4000000],
                "units": "rand",
                "legend": "Median municipal valuation of freehold residential property, General Valuation 2025",
                "popup": {"suburb": "Suburb", "median_value_gv2025": "Median value GV2025 (R)",
                          "median_value_gv2022": "Median value GV2022 (R)", "change_2022_2025_pct": "Change 2022-2025 %",
                          "freehold_res_properties": "Freehold residential properties", "median_erf_m2": "Median plot m²"},
                "source": "City of Cape Town Open Data Portal, 'Valuations Suburbs for 2022 and 2025' (freehold residential "
                          "only) joined to 'Official Planning Suburbs'; City of Cape Town open data terms of use. Suburbs with "
                          "<20 freehold properties or <20 per km² (farms, reserves) omitted; informal areas have no value.",
            },
            {
                "file": "demography_wards2026_density.geojson",
                "title": "Wards 2026 with estimated population",
                "geometry": "Polygon",
                "color_by": "density_2022_est_per_km2",
                "ramp": dens_ramp[:5],
                "breaks": [1000, 3000, 6000, 12000],
                "units": "residents per km²",
                "legend": "Estimated residents per km² on the 2026 ward boundaries (GHSL 2020 scaled to Census 2022)",
                "popup": {"ward_label": "Ward (2026)", "pop_2022_est": "Estimated residents", "area_km2": "Area km²",
                          "density_2022_est_per_km2": "Residents per km²"},
                "source": "City of Cape Town ODP 'Wards' (2026 delimitation); population from GHS-POP 2020 scaled to Census 2022.",
            },
            {
                "file": "demography_labels.geojson",
                "title": "Neighbourhood labels",
                "geometry": "Point",
                "color_by": None,
                "popup": {"label": "Neighbourhood"},
                "source": "Representative points of City of Cape Town official planning suburb polygons.",
            },
        ],
        "checks": checks,
    }
    (WEB / "demography_layers.json").write_text(json.dumps(layers, indent=2))
    print("sidecar written")


if __name__ == "__main__":
    main()
