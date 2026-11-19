"""Draw out/capetown_transit_network.png and out/capetown_service_frequency.png.

Reads out/layers/routes.geojson + stops.geojson (build_layers.py) and the OSM
place nodes for the neighbourhood labels. Esri Dark Gray basemap (free, no key;
CARTO needs a key now - see TransitPulse README).

Run: python pipeline/transit/make_maps.py
"""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import json
import pathlib

import contextily as ctx
import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from pyproj import Transformer

ROOT = paths.lane_dir("transit")
OUT = ROOT / "out"
ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_{layer}/MapServer/tile/{{z}}/{{y}}/{{x}}"
BG = "#0b0d10"
COL = {"rail": "#E4572E", "brt": "#2E86DE", "bus": "#8FD3FE", "taxi": "#F6C945"}
T = Transformer.from_crs(4326, 3857, always_xy=True)

# frame: Atlantis in the north to Simon's Town in the south, Sea Point to Somerset West
W, S, E, N = 18.30, -34.23, 18.92, -33.54
X0, Y0 = T.transform(W, S)
X1, Y1 = T.transform(E, N)
AX = [0.0, 0.05, 1.0, 0.85]          # map axes in figure fractions
FIG = (12, 13.5)
_aspect = (AX[2] * FIG[0]) / (AX[3] * FIG[1])
if (X1 - X0) / (Y1 - Y0) < _aspect:   # grow, never crop (TransitPulse fit_aspect)
    _pad = (_aspect * (Y1 - Y0) - (X1 - X0)) / 2
    X0, X1 = X0 - _pad, X1 + _pad
else:
    _pad = ((X1 - X0) / _aspect - (Y1 - Y0)) / 2
    Y0, Y1 = Y0 - _pad, Y1 + _pad

# label name -> where its coordinate comes from (verified 2026-11-19)
PLACE_LABELS = ["Sea Point", "Woodstock", "Claremont", "Wynberg", "Muizenberg", "Khayelitsha",
                "Mitchells Plain", "Table View", "Langa", "Hout Bay", "Atlantis", "Durbanville",
                "Fish Hoek", "Somerset West"]
STATION_LABELS = {"City Centre": "Cape Town", "Bellville": "Bellville"}


def labels(stops):
    osm = json.load(open(ROOT / "data" / "osm_places_stations.json"))["elements"]
    out = {}
    for e in osm:
        n = e["tags"].get("name")
        if n in PLACE_LABELS and "place" in e["tags"] and n not in out:
            out[n] = (e["lon"], e["lat"])
    rail = stops[stops["mode"] == "rail"].to_crs(4326)
    for lab, st in STATION_LABELS.items():
        g = rail[rail.name == st].geometry.iloc[0]
        out[lab] = (g.x, g.y)
    missing = set(PLACE_LABELS) - set(out)
    assert not missing, missing
    return out


def base_ax(title, subtitle):
    fig = plt.figure(figsize=FIG, dpi=200, facecolor=BG)
    ax = fig.add_axes(AX)
    ax.set_xlim(X0, X1)
    ax.set_ylim(Y0, Y1)
    ax.set_aspect("equal")
    ax.axis("off")
    ctx.add_basemap(ax, source=ESRI.format(layer="Base"), crs="EPSG:3857", zoom=11,
                    attribution=False, zorder=0)
    ax.add_patch(plt.Rectangle((X0, Y0), X1 - X0, Y1 - Y0, color="black", alpha=0.35, lw=0, zorder=0.5))
    fig.text(0.03, 0.965, title, color="white", fontsize=22, weight="bold", va="top")
    fig.text(0.03, 0.928, subtitle, color="#b8c0cc", fontsize=11.5, va="top")
    return fig, ax


OFFSET = {"City Centre": (1500, 900, "left"), "Woodstock": (-300, -2000, "right"), "Langa": (900, 300, "left"),
          "Sea Point": (-600, 300, "right")}


def put_labels(ax, lab):
    for name, (lon, lat) in lab.items():
        x, y = T.transform(lon, lat)
        dx, dy, ha = OFFSET.get(name, (0, 0, "center"))
        ax.text(x + dx, y + dy, name, color="white", fontsize=10.5, weight="bold", ha=ha, va="bottom",
                zorder=20, path_effects=[pe.withStroke(linewidth=3, foreground="black")])


def footer(fig, text):
    fig.text(0.03, 0.012, text, color="#8a93a0", fontsize=7.5, va="bottom")


def network(routes, stops, lab):
    fig, ax = base_ax("Cape Town public transport",
                      "Every mode with open route data, by mode. Minibus taxis carry the most "
                      "commuters but run without a timetable.\nGolden Arrow buses (the largest formal "
                      "bus operator) publish no route data at all and are missing.")
    r = routes.to_crs(3857)
    r[r["mode"] == "taxi"].plot(ax=ax, color=COL["taxi"], lw=0.45, alpha=0.30, zorder=2)
    r[r["mode"] == "bus"].plot(ax=ax, color=COL["bus"], lw=1.0, alpha=0.85, zorder=3)
    r[r["mode"] == "brt"].plot(ax=ax, color=COL["brt"], lw=2.6, alpha=1, zorder=4)
    rail = r[r["mode"] == "rail"]
    rail.plot(ax=ax, color="white", lw=4.2, zorder=5)
    rail.plot(ax=ax, color=COL["rail"], lw=2.6, zorder=6)
    s = stops.to_crs(3857)
    rs = s[(s["mode"] == "rail") & (s.weekday_departures > 0)]
    ax.scatter(rs.geometry.x, rs.geometry.y, s=16, c="white", edgecolors=COL["rail"], linewidths=1.2, zorder=8)
    closed = s[(s["mode"] == "rail") & (s.weekday_departures == 0)]
    ax.scatter(closed.geometry.x, closed.geometry.y, s=12, c="none", edgecolors="#9aa3ad",
               linewidths=0.9, zorder=8)
    bs = s[s["mode"] == "brt"]
    ax.scatter(bs.geometry.x, bs.geometry.y, s=11, c="white", edgecolors=COL["brt"], linewidths=1.0, zorder=7)
    put_labels(ax, lab)
    n = r["mode"].value_counts()
    h = [Line2D([], [], color=COL["rail"], lw=3, label=f"Metrorail train ({n['rail']} lines)"),
         Line2D([], [], color=COL["brt"], lw=3, label=f"MyCiTi BRT trunk ({n['brt']} routes)"),
         Line2D([], [], color=COL["bus"], lw=1.5, label=f"MyCiTi feeder / direct bus ({n['bus']} routes)"),
         Line2D([], [], color=COL["taxi"], lw=1.5, alpha=0.7, label=f"Minibus taxi route ({n['taxi']:,} surveyed)"),
         Line2D([], [], marker="o", ls="", mfc="white", mec=COL["rail"], label="Train station (2026 timetable)"),
         Line2D([], [], marker="o", ls="", mfc="none", mec="#9aa3ad", label="Station with no trains in 2026"),
         Line2D([], [], marker="o", ls="", mfc="white", mec=COL["brt"], ms=5, label="MyCiTi station")]
    leg = ax.legend(handles=h, loc="lower right", frameon=True, fontsize=9.5, facecolor="#111418",
                    edgecolor="#333", labelcolor="white", borderpad=0.9)
    leg.set_zorder(30)
    footer(fig, "Data: City of Cape Town Open Data Portal (MyCiTi routes and stops, taxi routes, rail "
                "stations, 2026-07); OpenStreetMap contributors (Metrorail lines, place names); PRASA "
                "timetable via kaapsetrains.co.za.\nBasemap: Esri, HERE, Garmin, OpenStreetMap "
                "contributors. Map: The New Science of Maps, 2026-11.")
    p = OUT / "capetown_transit_network.png"
    fig.savefig(p, facecolor=BG)
    plt.close(fig)
    print("wrote", p)


def frequency(routes, stops, lab):
    fig, ax = base_ax("Where the timetabled service is",
                      "Departures per stop on a normal weekday (Mon-Fri), MyCiTi buses and Metrorail "
                      "trains. Faint yellow: minibus-taxi routes,\nwhich have no timetable - in most of the "
                      "Cape Flats they ARE the service. One train carries roughly ten busloads.")
    r = routes.to_crs(3857)
    r[r["mode"] == "taxi"].plot(ax=ax, color=COL["taxi"], lw=0.45, alpha=0.22, zorder=2)
    r[r["mode"] != "taxi"].plot(ax=ax, color="#59616b", lw=0.8, alpha=0.9, zorder=3)
    s = stops.to_crs(3857).sort_values("weekday_departures")
    bounds = [1, 25, 75, 150, 300, 600, 1500]
    cmap = ListedColormap(["#3b1f5c", "#6a2c8a", "#b03b85", "#e65c5c", "#f99a3e", "#fde68a"])
    norm = BoundaryNorm(bounds, cmap.N)
    zero = s[s.weekday_departures == 0]
    ax.scatter(zero.geometry.x, zero.geometry.y, s=8, c="none", edgecolors="#7a828c", lw=0.7, zorder=5)
    for mode, mk in (("bus", "o"), ("brt", "o"), ("rail", "D")):
        x = s[(s["mode"] == mode) & (s.weekday_departures > 0)]
        size = 6 + 60 * np.sqrt(x.weekday_departures / 1500)
        if mode == "rail":
            size = size * 1.6
        ax.scatter(x.geometry.x, x.geometry.y, s=size, c=x.weekday_departures, cmap=cmap, norm=norm,
                   marker=mk, edgecolors="black" if mode != "rail" else "white",
                   linewidths=0.3 if mode != "rail" else 0.7, zorder=6 if mode != "rail" else 7)
    put_labels(ax, lab)
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    cax = fig.add_axes([0.62, 0.085, 0.33, 0.012])
    cb = fig.colorbar(sm, cax=cax, orientation="horizontal", ticks=bounds)
    cb.ax.tick_params(colors="white", labelsize=8.5)
    cb.outline.set_edgecolor("#555")
    cb.set_label("weekday departures per stop", color="white", fontsize=9)
    h = [Line2D([], [], marker="o", ls="", mfc="#e65c5c", mec="black", label="MyCiTi stop / station"),
         Line2D([], [], marker="D", ls="", mfc="#e65c5c", mec="white", label="Metrorail station"),
         Line2D([], [], marker="o", ls="", mfc="none", mec="#7a828c", label="no timetabled service found"),
         Line2D([], [], color=COL["taxi"], lw=1.5, alpha=0.6, label="minibus-taxi route (no timetable)")]
    leg = ax.legend(handles=h, loc="lower right", bbox_to_anchor=(0.985, 0.10), fontsize=9,
                    facecolor="#111418", edgecolor="#333", labelcolor="white")
    leg.set_zorder(30)
    footer(fig, "Departures counted from MyCiTi PDF timetables (Oct 2026, 41 routes) and the PRASA "
                "Metrorail timetable (in force from 8 Jun 2026) via kaapsetrains.co.za. Stops and stations: "
                "City of Cape Town ODP.\nTermini count departures only. Golden Arrow buses publish no data "
                "and are not shown. Basemap: Esri, HERE, Garmin, OSM. Map: The New Science of Maps, 2026-11.")
    p = OUT / "capetown_service_frequency.png"
    fig.savefig(p, facecolor=BG)
    plt.close(fig)
    print("wrote", p)


if __name__ == "__main__":
    routes = gpd.read_file(OUT / "layers" / "routes.geojson")
    stops = gpd.read_file(OUT / "layers" / "stops.geojson")
    lab = labels(stops)
    network(routes, stops, lab)
    frequency(routes, stops, lab)
