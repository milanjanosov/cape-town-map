"""Check-image choropleths and the ranked-table PNG."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
os.chdir(paths.lane_dir("crime"))
import json, numpy as np, pandas as pd, geopandas as gpd, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import matplotlib.patheffects as pe

P = gpd.read_file("data/coct_precinct_crime_2025_26.geojson").to_crs(32734)
metro = gpd.read_file("data/coct_metro_boundary.geojson").to_crs(32734)
L = pd.DataFrame(json.load(open(paths.inputs("crime") / "neighbourhood_labels.json")))
L = gpd.GeoDataFrame(L, geometry=gpd.points_from_xy(L.lon, L.lat), crs=4326).to_crs(32734)
LEFT = {"Sea Point", "Camps Bay", "Hout Bay", "Table View", "Constantia"}
P = P.copy(); P["geometry"] = P.geometry.intersection(metro.geometry.iloc[0])
SRC = ("Counts: SAPS quarterly crime statistics, Q1-Q4 2025/26 summed (Apr 2025 - Mar 2026). "
       "Population: GeoTerraImage 2024 estimate by SAPS precinct (Western Cape Government PDO).\n"
       "Precincts: Western Cape Government Spatial Data Warehouse (Makhaza rebuilt from PDO 2024 EA assignment). "
       "Hatched: rate unreliable (small or commuter population). Grey: no rate.")

def draw(col, breaks, colors, title, sub, legend_title, out):
    fig, ax = plt.subplots(figsize=(10, 12), dpi=150)
    fig.patch.set_facecolor("white")
    metro.plot(ax=ax, color="white", edgecolor="none")
    v = P[col]
    cls = np.digitize(v.fillna(-1), breaks[1:-1])
    for i, c in enumerate(colors):
        sel = (cls == i) & v.notna()
        P[sel].plot(ax=ax, color=c, edgecolor="white", linewidth=0.5)
    P[v.isna()].plot(ax=ax, color="#d9d9d9", edgecolor="white", linewidth=0.5)
    P[P.rate_flag.fillna("") != ""].plot(ax=ax, facecolor="none", edgecolor="#666666", hatch="///", linewidth=0.0)
    metro.boundary.plot(ax=ax, color="#555555", linewidth=0.8)
    for _, r in L.iterrows():
        ax.plot(r.geometry.x, r.geometry.y, "o", ms=3.5, color="black", mec="white", mew=0.8, zorder=5)
        left = r["name"] in LEFT
        ax.annotate(r["name"], (r.geometry.x, r.geometry.y), xytext=(-5 if left else 5, 3), textcoords="offset points", ha="right" if left else "left",
                    fontsize=9, zorder=6, path_effects=[pe.withStroke(linewidth=2.5, foreground="white")])
    hand = [Patch(facecolor=c, label=f"{breaks[i]:g} - {breaks[i+1]:g}" if i < len(colors) - 1 else f"{breaks[i]:g} or more")
            for i, c in enumerate(colors)]
    hand += [Patch(facecolor="white", edgecolor="#333333", hatch="///", label="unreliable rate"),
             Patch(facecolor="#d9d9d9", label="no rate"),
             Patch(facecolor="white", edgecolor="#555555", label="metro land in precincts mostly outside it")]
    ax.legend(handles=hand, title=legend_title, loc="upper right", frameon=True, fontsize=9, title_fontsize=9)
    ax.set_axis_off()
    x0, y0, x1, y1 = metro.total_bounds
    ax.set_xlim(x0 - 2000, x1 + 2000); ax.set_ylim(y0 - 2000, y1 + 2000)
    fig.text(0.05, 0.965, title, fontsize=17, weight="bold")
    fig.text(0.05, 0.945, sub, fontsize=11, color="#444444")
    fig.text(0.05, 0.02, SRC, fontsize=6.8, color="#555555")
    fig.savefig(out, bbox_inches="tight", facecolor="white"); plt.close(fig)
    print(out)

draw("murder_rate_100k", [0, 10, 25, 50, 100, 1e9],
     ["#fee5d9", "#fcae91", "#fb6a4a", "#de2d26", "#a50f15"],
     "Murders per 100,000 residents, by police precinct",
     "City of Cape Town, April 2025 - March 2026. Metro average: 73 per 100,000.",
     "Murders per 100,000", "out/capetown_murder_rate.png")
draw("res_burglary_rate_100k", [0, 150, 250, 350, 450, 1e9],
     ["#eff3ff", "#bdd7e7", "#6baed6", "#3182bd", "#08519c"],
     "Residential burglaries per 100,000 residents, by police precinct",
     "City of Cape Town, April 2025 - March 2026. Metro average: 205 per 100,000. Reported cases only.",
     "Burglaries per 100,000", "out/capetown_property_crime.png")

# ranked table PNG: top and bottom 10 by murder rate (precincts with a rate)
T = pd.read_csv("out/capetown_precinct_crime_ranked.csv")
T = T[T.murder_rate_100k.notna()]
top, bot = T.head(10), T.tail(10)
def rows(df):
    return [[int(r.murder_rank), r["name"] + (" *" if isinstance(r.rate_flag, str) and r.rate_flag else ""),
             f"{int(r.pop_gti_2024):,}", f"{int(r.murder):,}", f"{r.murder_rate_100k:.1f}",
             f"{int(r.res_burglary):,}", f"{r.res_burglary_rate_100k:.0f}"] for _, r in df.iterrows()]
hdr = ["Rank", "Precinct", "Population", "Murders", "per 100k", "Burglaries", "per 100k"]
fig, axes = plt.subplots(2, 1, figsize=(9, 8.2), dpi=150)
for ax, df, t in [(axes[0], top, "Highest murder rate (10 of 62 precincts)"), (axes[1], bot, "Lowest murder rate (10 of 62 precincts)")]:
    ax.set_axis_off(); ax.set_title(t, loc="left", fontsize=12, weight="bold")
    tb = ax.table(cellText=rows(df), colLabels=hdr, loc="upper center", cellLoc="right", colLoc="right",
                  colWidths=[0.07, 0.25, 0.14, 0.11, 0.11, 0.17, 0.11])
    tb.auto_set_font_size(False); tb.set_fontsize(9); tb.scale(1, 1.35)
    for (i, j), c in tb.get_celld().items():
        c.set_edgecolor("#dddddd")
        if i == 0: c.set_text_props(weight="bold"); c.set_facecolor("#f2f2f2")
        if j == 1: c._loc = "left"; c.set_text_props(ha="left")
fig.text(0.02, 0.01, "SAPS 2025/26 (Apr 2025 - Mar 2026), City of Cape Town precincts. Population: GeoTerraImage 2024 via WCG PDO.\n"
         "* small residential population, rate unstable. Table Bay Harbour excluded (about 1,000 residents). Full table: capetown_precinct_crime_ranked.csv",
         fontsize=7, color="#555555")
fig.savefig("out/capetown_precinct_ranking.png", bbox_inches="tight", facecolor="white")
print("out/capetown_precinct_ranking.png")
