"""Static check maps (4:5, dark) for the Cape Town demography lane."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import json
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap, LogNorm
from matplotlib.patches import Patch

ROOT = paths.lane_dir("demography")
PROC, OUT = ROOT / "data" / "processed", ROOT / "out"
OUT.mkdir(exist_ok=True)
UTM = 32734
BG, LAND, FG, MUTED = "#0b0f17", "#161c27", "#e8e6e1", "#8a909c"
plt.rcParams["font.family"] = "Helvetica Neue"

# Label anchors: representative points of City of Cape Town official planning suburb polygons
LABELS = {
    "CAPE TOWN CITY CENTRE": "City Centre", "SEA POINT": "Sea Point", "CAMPS BAY / BAKOVEN": "Camps Bay",
    "CONSTANTIA": "Constantia", "CLAREMONT": "Claremont", "MUIZENBERG": "Muizenberg",
    "KHAYELITSHA": "Khayelitsha", "MITCHELLS PLAIN CBD": "Mitchells Plain", "GUGULETU": "Gugulethu",
    "LANGA": "Langa", "BELLVILLE CBD": "Bellville", "DURBANVILLE": "Durbanville", "TABLE VIEW": "Table View",
    "SOMERSET WEST": "Somerset West", "HOUT BAY": "Hout Bay",
}


OFFSETS = {"Sea Point": (-4, 3, "right"), "City Centre": (4, 4, "left"), "Mitchells Plain": (-4, 3, "right"),
           "Khayelitsha": (4, -9, "left"), "Camps Bay": (-4, -3, "right"), "Hout Bay": (-4, 3, "right")}


def label_points():
    s = gpd.read_file(ROOT / "data" / "raw" / "suburbs_cct_odp.geojson")
    s = s[s.OFC_SBRB_NAME.isin(LABELS)].copy()
    assert len(s) == len(LABELS), set(LABELS) - set(s.OFC_SBRB_NAME)
    s = s.to_crs(UTM)
    s["geometry"] = s.representative_point()
    s["label"] = s.OFC_SBRB_NAME.map(LABELS)
    out = s.to_crs(4326)
    (ROOT / "data" / "label_points.geojson").write_text(out[["label", "OFC_SBRB_NAME", "geometry"]].to_json())
    return s


def frame(title, subtitle, source):
    fig = plt.figure(figsize=(8, 10), dpi=300, facecolor=BG)
    ax = fig.add_axes([0.02, 0.075, 0.96, 0.725])
    ax.set_facecolor(BG)
    ax.set_axis_off()
    fig.text(0.05, 0.955, title, color=FG, fontsize=21, fontweight="bold", va="top")
    fig.text(0.05, 0.912, subtitle, color=MUTED, fontsize=10.5, va="top", linespacing=1.4)
    fig.text(0.05, 0.03, source, color=MUTED, fontsize=6.6, va="bottom", linespacing=1.45)
    fig.text(0.95, 0.03, "New Science of Maps", color=MUTED, fontsize=7.5, ha="right", va="bottom", fontweight="bold")
    return fig, ax


def finish(ax, city, labels):
    city.boundary.plot(ax=ax, color="#5a6070", linewidth=0.5, zorder=4)
    for _, r in labels.iterrows():
        x, y = r.geometry.x, r.geometry.y
        ax.plot(x, y, "o", ms=2.6, color=FG, mec=BG, mew=0.6, zorder=6)
        dx, dy, ha = OFFSETS.get(r.label, (4, 3, "left"))
        ax.annotate(r.label, (x, y), xytext=(dx, dy), textcoords="offset points", color=FG, fontsize=7.6, ha=ha,
                    fontweight="bold", zorder=7,
                    path_effects=[pe.withStroke(linewidth=2.2, foreground=BG)])
    xmin, ymin, xmax, ymax = city.total_bounds
    padx = (xmax - xmin) * 0.03
    ax.set_xlim(xmin - padx, xmax + padx)
    ax.set_ylim(ymin - padx, ymax + padx)
    ax.set_aspect("equal")
    # 10 km scale bar
    x0, y0 = xmin + (xmax - xmin) * 0.02, ymin + (ymax - ymin) * 0.03
    ax.plot([x0, x0 + 10000], [y0, y0], color=FG, lw=1.4, zorder=8)
    ax.text(x0 + 5000, y0 + 900, "10 km", color=FG, fontsize=7, ha="center", zorder=8)


def class_legend(fig, colors, labels, title, x=0.05, y=0.835):
    fig.text(x, y, title, color=FG, fontsize=8.5, va="bottom", fontweight="bold")
    w = 0.9 / len(colors)
    for i, (c, l) in enumerate(zip(colors, labels)):
        fig.patches.append(plt.Rectangle((x + i * w, y - 0.016), w * 0.96, 0.011, color=c,
                                         transform=fig.transFigure, figure=fig))
        fig.text(x + i * w, y - 0.03, l, color=MUTED, fontsize=7.2, va="top")


def density_map(city, labels, checks):
    pop = np.load(PROC / "ghsl2020_utm34s_100m.npy") * checks["census2022_scale_factor_applied"]
    tr = json.loads((PROC / "ghsl2020_utm34s_100m.transform.json").read_text())
    dens = pop * 100.0  # people per km2 (100 m cell = 0.01 km2)
    h, w = dens.shape
    extent = [tr[2], tr[2] + w * tr[0], tr[5] + h * tr[4], tr[5]]
    fig, ax = frame(
        "Where Cape Town lives",
        "Residents per km² on a 100 m grid. GHSL 2020 population grid, rescaled so the city\n"
        "total matches the Census 2022 count of 4,772,846 (GHSL alone gives 4.71 million, -1.3%).",
        "Data: European Commission JRC, GHS-POP R2023A epoch 2020, 100 m (CC BY 4.0); Stats SA Census 2022 city total;\n"
        "City of Cape Town Open Data Portal ward and suburb boundaries. Cells outside the 2026 ward boundary are hidden.")
    city.plot(ax=ax, color=LAND, zorder=1)
    # mask outside city
    from rasterio.features import geometry_mask
    from rasterio.transform import Affine
    m = geometry_mask(city.geometry, out_shape=dens.shape, transform=Affine(*tr), invert=True)
    d = np.where(m & (dens >= 100), dens, np.nan)
    cmap = matplotlib.colormaps["magma"]
    norm = LogNorm(vmin=100, vmax=40000)
    ax.imshow(d, extent=extent, cmap=cmap, norm=norm, interpolation="nearest", zorder=2)
    finish(ax, city, labels)
    # continuous legend
    cax = fig.add_axes([0.05, 0.818, 0.5, 0.011])
    cb = fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=cmap), cax=cax, orientation="horizontal")
    cb.set_ticks([100, 1000, 5000, 10000, 40000], labels=["100", "1,000", "5,000", "10,000", "40,000+"])
    cb.ax.tick_params(colors=MUTED, labelsize=7.2, length=0)
    cb.outline.set_visible(False)
    fig.text(0.05, 0.835, "Residents per km² (log scale; under 100 not drawn)", color=FG, fontsize=8.5,
             fontweight="bold")
    fig.savefig(OUT / "capetown_population_density.png", facecolor=BG)
    plt.close(fig)


def choropleth(gdf, col, bins, colors, labels_txt, legend_title, title, subtitle, source, fname, city, labels):
    fig, ax = frame(title, subtitle, source)
    city.plot(ax=ax, color=LAND, zorder=1)
    cmap = ListedColormap(colors)
    norm = BoundaryNorm(bins, len(colors))
    gdf.plot(ax=ax, column=col, cmap=cmap, norm=norm, edgecolor=BG, linewidth=0.35, zorder=2)
    finish(ax, city, labels)
    class_legend(fig, colors, labels_txt, legend_title)
    fig.savefig(OUT / fname, facecolor=BG)
    plt.close(fig)


def main():
    checks = json.loads((ROOT / "data" / "checks.json").read_text())
    labels = label_points()
    w26 = gpd.read_file(PROC / "wards2026_ghsl.gpkg").to_crs(UTM)
    city = gpd.GeoDataFrame(geometry=[w26.union_all()], crs=UTM)
    w11 = gpd.read_file(PROC / "wards2011_census.gpkg").to_crs(UTM)

    density_map(city, labels, checks)

    choropleth(
        w11, "median_hh_income_month_2011",
        [0, 3200, 6400, 12800, 25600, 1e9],
        ["#2b1b3d", "#5b2a6e", "#a2416f", "#e07a5f", "#f6c87a"],
        ["under R3,200", "R3,200-6,400", "R6,400-12,800", "R12,800-25,600", "over R25,600"],
        "Median monthly household income, Census 2011 (2011 rand)",
        "Where the money is",
        "Median monthly household income per ward, Census 2011, the latest small-area income\n"
        "Stats SA has published. Census 2022 income has not been released. Rand amounts are\n"
        "2011 prices and well below today's; read the pattern, not the amounts.",
        "Data: Stats SA Census 2011 via City of Cape Town 2011 ward profiles (111 wards, 2011 boundaries). Median interpolated\n"
        "within the census income bands; denominator = households with a stated income (unspecified excluded).\n"
        "Ward boundaries: Stats SA 2011 wards, published by UCT Libraries.",
        "capetown_income.png", city, labels)

    choropleth(
        w11, "pct_informal",
        [0, 2, 10, 25, 50, 101],
        ["#1f2a36", "#3d4f5f", "#c58b4c", "#e0662f", "#ff3d2e"],
        ["under 2%", "2-10%", "10-25%", "25-50%", "over 50%"],
        "Households living in an informal dwelling (shack), Census 2011",
        "Formal and informal Cape Town",
        "Share of households in an informal dwelling, in a backyard or in an informal settlement,\n"
        "per ward. Census 2011; Census 2022 puts the city-wide formal share at 87.5%, but has\n"
        "not published it by ward.",
        "Data: Stats SA Census 2011 via City of Cape Town 2011 ward profiles (111 wards). Denominator = all households in the\n"
        "ward's dwelling table. Informal = 'informal dwelling / shack in backyard' + 'not in backyard'. Ward boundaries: Stats SA 2011.",
        "capetown_informal_dwellings.png", city, labels)

    # check image: GV2025 median freehold residential valuation by suburb
    sub = gpd.read_file(PROC / "suburbs_valuation.gpkg").to_crs(UTM)
    sub = sub[sub.GV2025_VAL.notna() & (sub.NUM_RES_PROP >= 20) & (sub.NUM_RES_PROP / (sub.area / 1e6) >= 20)]
    choropleth(
        sub, "GV2025_VAL",
        [0, 500_000, 1_000_000, 2_000_000, 4_000_000, 1e12],
        ["#2b1b3d", "#5b2a6e", "#a2416f", "#e07a5f", "#f6c87a"],
        ["under R0.5m", "R0.5-1m", "R1-2m", "R2-4m", "over R4m"],
        "Median municipal valuation of a freehold house, GV2025",
        "What a house is worth",
        "Median municipal valuation (General Valuation 2025) of freehold residential properties per\n"
        "suburb. Blank: suburbs with fewer than 20 such properties or fewer than 20 per km\u00b2\n"
        "(farms, nature reserves), and informal areas, which have no freehold valuation.",
        "Data: City of Cape Town Open Data Portal, 'Valuations Suburbs for 2022 and 2025' (freehold residential only; sectional-title\n"
        "flats excluded) joined to the City's official planning suburbs.",
        "check_capetown_valuation_gv2025.png", city, labels)
    print("maps written")


if __name__ == "__main__":
    main()
