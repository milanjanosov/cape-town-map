"""Check image: the exported web layers drawn together in EPSG:3857.

hillshade PNG (placed at its sidecar bounds) + boundary + labels + 300 m contour decoded
from the z11 terrain-RGB tiles. If the contour hugs the shaded relief, tiles and image align.
Writes raw/elevation/out/capetown_hillshade_flat.png and raw/elevation/tmp/check_tiles.png.
"""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import json, math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from PIL import Image
import geopandas as gpd

LANE = paths.lane_dir("elevation")
WEB = paths.DATA
side = json.load(open(WEB / "elevation_layers.json"))
W, S, E, N = side["layers"][0]["bounds"]
R = 6378137.0


def merc(lon, lat):
    return R * np.radians(lon), R * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


img = np.array(Image.open(WEB / "elevation_hillshade.png"))
x0, y0 = merc(W, S); x1, y1 = merc(E, N)

# decode z11 terrain tiles into a mosaic
Z = 11
def t(lon, lat):
    n = 2 ** Z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
xa, ya = t(W, N); xb, yb = t(E, S)
mos = np.zeros(((yb - ya + 1) * 256, (xb - xa + 1) * 256))
for x in range(xa, xb + 1):
    for y in range(ya, yb + 1):
        a = np.array(Image.open(WEB / f"elevation_terrain/{Z}/{x}/{y}.png").convert("RGB")).astype(float)
        mos[(y - ya) * 256:(y - ya + 1) * 256, (x - xa) * 256:(x - xa + 1) * 256] = \
            -10000 + (a[..., 0] * 65536 + a[..., 1] * 256 + a[..., 2]) * 0.1
size = 2 * math.pi * R / 2 ** Z
tx0, ty1 = -math.pi * R + xa * size, math.pi * R - ya * size
txs = tx0 + (np.arange(mos.shape[1]) + .5) * size / 256
tys = ty1 - (np.arange(mos.shape[0]) + .5) * size / 256
print("terrain z11 mosaic max", mos.max())

bnd = gpd.read_file(WEB / "elevation_boundary.geojson").to_crs(3857)
lab = gpd.read_file(WEB / "elevation_labels.geojson").to_crs(3857)


def base(ax, contour=False):
    ax.set_facecolor("#a9c4d6")
    ax.imshow(img, extent=(x0, x1, y0, y1), interpolation="bilinear", zorder=1)
    if contour:
        ax.contour(txs, tys, mos, levels=[300], colors="red", linewidths=0.6, zorder=3)
    bnd.boundary.plot(ax=ax, color="#222", lw=1.1, ls="--", zorder=4)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_xticks([]); ax.set_yticks([])


OFFSET = {"Sea Point": (-6, 4, "right"), "Camps Bay": (-6, 0, "right"), "Signal Hill": (6, 6, "left"),
          "Lion's Head": (-6, -6, "right"), "City Bowl": (6, 0, "left"), "Woodstock": (6, 4, "left"),
          "Observatory": (6, -4, "left"), "Devil's Peak": (6, -2, "left"), "Table Mountain": (-6, -8, "right"),
          "Hout Bay": (-6, 0, "right"), "Constantiaberg": (-6, -6, "right"), "Constantia": (6, 0, "left"),
          "Cape Point": (6, 0, "left"), "Robben Island": (6, 0, "left"), "Simon's Town": (6, 0, "left")}

fig, ax = plt.subplots(figsize=(13, 17.5), dpi=150)
base(ax)
for _, r in lab.iterrows():
    dx, dy, ha = OFFSET.get(r["name"], (6, 0, "left"))
    peak = r["kind"] == "peak"
    ax.plot(r.geometry.x, r.geometry.y, "^" if peak else "o", ms=5 if peak else 3.5,
            color="#7a3b1d" if peak else "#111", mec="white", mew=0.7, zorder=6)
    ax.annotate(r["label"].replace(" International Airport", " Intl Airport"), (r.geometry.x, r.geometry.y),
                xytext=(dx, dy), textcoords="offset points", ha=ha, va="center",
                fontsize=8.5 if not peak else 8.5, fontweight="bold" if peak else "normal",
                color="#5a2a12" if peak else "#111", zorder=7,
                path_effects=[pe.withStroke(linewidth=2.6, foreground="white")])
ax.set_title("Cape Town: the mountain splits the city", fontsize=17, loc="left", pad=10)
ax.text(0.01, 0.005, "Relief: Copernicus DEM GLO-30 (ESA/EU, DLR, Airbus), multi-direction hillshade.  "
        "Labels and metro boundary: (c) OpenStreetMap contributors.  Peak heights: published values.",
        transform=ax.transAxes, fontsize=7.5, color="#333", va="bottom")
plt.tight_layout()
plt.savefig(LANE / "out" / "capetown_hillshade_flat.png", dpi=150)

fig, ax = plt.subplots(figsize=(10, 12), dpi=110)
base(ax, contour=True)
ax.set_xlim(*merc(18.33, -34.0)[0:1], merc(18.55, -34.0)[0])
ax.set_ylim(merc(18.4, -34.08)[1], merc(18.4, -33.88)[1])
ax.plot(lab.geometry.x, lab.geometry.y, "k^", ms=6)
ax.set_title("Alignment check: hillshade PNG + 300 m contour from z11 terrain-RGB tiles (red) + OSM peaks")
plt.savefig(LANE / "tmp" / "check_tiles.png")
