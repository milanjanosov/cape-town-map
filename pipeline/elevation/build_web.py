"""Cape Town elevation lane: web exports + check image.

Writes into the repo's data/ folder (paths.DATA):
  elevation_hillshade.png         coloured relief, sea transparent, EPSG:3857 grid
  elevation_terrain/{z}/{x}/{y}.png  Mapbox terrain-RGB, z8-12 (paths.TERRAIN_ZMAX), 256 px
  elevation_labels.geojson        landmarks/peaks with heights
  elevation_boundary.geojson      City of Cape Town mainland boundary (OSM)
  elevation_layers.json           sidecar
Inputs: raw/elevation/data/ (python download_data.py --lane elevation) and
pipeline/elevation/inputs/labels_verified.csv. Run from anywhere.
"""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import csv, json, math, os
from pathlib import Path
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling, transform_bounds
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT
from PIL import Image
import geopandas as gpd

LANE = paths.lane_dir("elevation")
WEB = paths.DATA
DATA = LANE / "data"
TILES = [DATA / f"Copernicus_DSM_COG_10_{t}_00_DEM.tif" for t in
         ("S34_00_E018", "S35_00_E018", "S34_00_E019", "S35_00_E019")]
W, S, E, N = 18.28, -34.38, 19.06, -33.44          # lon/lat window
ZMIN, ZMAX = 8, paths.TERRAIN_ZMAX

# ---------- merged source (EPSG:4326, native 1 arcsec) ----------
from rasterio.merge import merge
srcs = [rasterio.open(t) for t in TILES]
mos, mtr = merge(srcs)  # full 2x2 degree block, so low-zoom tiles have no cliff at the window edge
mos = mos[0].astype("float32")
MCRS = srcs[0].crs


def warp_to(dst_tr, shape, crs="EPSG:3857", rs=Resampling.bilinear):
    out = np.zeros(shape, "float32")
    reproject(mos, out, src_transform=mtr, src_crs=MCRS, dst_transform=dst_tr,
              dst_crs=crs, resampling=rs)
    return out


# ---------- hillshade + hypsometric relief ----------
def hillshade(z, res, az=315, alt=45, zf=1.0):
    gy, gx = np.gradient(z * zf, res)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    a, al = np.radians(360 - az + 90), np.radians(alt)
    return np.clip(np.sin(al) * np.cos(slope) + np.cos(al) * np.sin(slope) * np.cos(a - aspect), 0, 1)


def multi_hs(z, res):
    hs = sum(w * hillshade(z, res, az) for az, w in ((315, .5), (270, .2), (0, .15), (225, .15)))
    return hs


RAMP = [(0, (0.80, 0.86, 0.72)), (40, (0.74, 0.82, 0.64)), (150, (0.86, 0.84, 0.66)),
        (400, (0.80, 0.70, 0.55)), (800, (0.70, 0.62, 0.55)), (1100, (0.85, 0.83, 0.82)),
        (1600, (0.97, 0.97, 0.97))]


def tint(z):
    zs = np.array([r[0] for r in RAMP], float)
    cols = np.array([r[1] for r in RAMP])
    return np.stack([np.interp(z, zs, cols[:, i]) for i in range(3)], -1)


def relief_rgba(z, res, sea_rgb=None):
    hs = multi_hs(z, res)
    rgb = tint(z) * (0.35 + 0.75 * hs[..., None])
    rgb = np.clip(rgb, 0, 1)
    sea = z <= 0.5
    a = np.where(sea, 0, 1.0)
    if sea_rgb is not None:
        rgb[sea] = sea_rgb
        a[:] = 1
    return np.dstack([rgb, a]), sea


def merc_bounds():
    return transform_bounds("EPSG:4326", "EPSG:3857", W, S, E, N)


def export_hillshade():
    x0, y0, x1, y1 = merc_bounds()
    res = 36.0  # metres in mercator (~30 m ground at 34 S)
    w, h = int((x1 - x0) / res), int((y1 - y0) / res)
    tr = from_bounds(x0, y0, x1, y1, w, h)
    z = warp_to(tr, (h, w))
    ground_res = res * math.cos(math.radians(33.9))
    rgba, _ = relief_rgba(z, ground_res)
    Image.fromarray((rgba * 255).astype("uint8"), "RGBA").save(WEB / "elevation_hillshade.png", optimize=True)
    print("hillshade", w, h, os.path.getsize(WEB / "elevation_hillshade.png") / 1e6, "MB")
    return z, tr


# ---------- terrain-RGB tiles ----------
def tile_bounds(x, y, z):
    n = 2 ** z
    R = 6378137 * math.pi
    size = 2 * R / n
    return (-R + x * size, R - (y + 1) * size, -R + (x + 1) * size, R - y * size)


def lonlat_to_tile(lon, lat, z):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def encode_rgb(h):
    v = np.round((np.clip(h, -10000, None) + 10000) * 10).astype("int64")
    return np.dstack([(v >> 16) & 255, (v >> 8) & 255, v & 255]).astype("uint8")


def export_terrain():
    root = WEB / "elevation_terrain"
    n = 0
    for z in range(ZMIN, ZMAX + 1):
        xa, ya = lonlat_to_tile(W, N, z)
        xb, yb = lonlat_to_tile(E, S, z)
        for x in range(xa, xb + 1):
            for y in range(ya, yb + 1):
                b = tile_bounds(x, y, z)
                h = warp_to(from_bounds(*b, 256, 256), (256, 256))
                h[h < 0] = 0  # sea and the few negative void-fill pixels
                d = root / str(z) / str(x)
                d.mkdir(parents=True, exist_ok=True)
                Image.fromarray(encode_rgb(h), "RGB").save(d / f"{y}.png", optimize=True)
                n += 1
    print("terrain tiles", n)


# ---------- labels ----------
OFFICIAL = {  # widely published summit heights, metres
    "Table Mountain (Maclear's Beacon)": 1086, "Devil's Peak": 1000, "Lion's Head": 669,
    "Signal Hill": 350, "Constantiaberg": 928}
KIND = {"Table Mountain (Maclear's Beacon)": "peak", "Devil's Peak": "peak", "Lion's Head": "peak",
        "Signal Hill": "peak", "Constantiaberg": "peak", "Cape Point": "landmark",
        "Robben Island": "landmark", "Cape Town International Airport": "landmark"}


def dem_at(lon, lat, radius_px=8):
    r, c = rasterio.transform.rowcol(mtr, lon, lat)
    return float(mos[r, c]), float(mos[r - radius_px:r + radius_px + 1, c - radius_px:c + radius_px + 1].max())


def export_labels():
    feats = []
    for r in csv.DictReader(open(paths.inputs("elevation") / "labels_verified.csv")):
        lon, lat = float(r["lon"]), float(r["lat"])
        pt, mx = dem_at(lon, lat)
        kind = KIND.get(r["label"], "place")
        off = OFFICIAL.get(r["label"])
        name = r["label"].replace(" (Maclear's Beacon)", "")
        disp = f"{name} {off:,} m" if off else name
        feats.append({"type": "Feature",
                      "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                      "properties": {"name": name, "label": disp, "kind": kind,
                                     "height_m": off, "height_m_dem": round(mx if kind == "peak" else pt),
                                     "osm_ref": f"{r['osm_type']}/{r['osm_id']}"}})
    json.dump({"type": "FeatureCollection", "features": feats},
              open(WEB / "elevation_labels.geojson", "w"), ensure_ascii=False)
    print("labels", len(feats))
    return feats


def export_boundary():
    g = gpd.read_file(DATA / "cct_boundary_osm.geojson").to_crs(32734)
    g["geometry"] = g.simplify(15)
    g = g.to_crs(4326)
    g["name"] = "City of Cape Town"
    g["area_km2"] = round(float(gpd.read_file(DATA / "cct_boundary_osm.geojson").to_crs(32734).area.sum() / 1e6), 1)
    g[["name", "area_km2", "geometry"]].to_file(WEB / "elevation_boundary.geojson", driver="GeoJSON",
                                                COORDINATE_PRECISION=5)
    return g


def export_sidecar():
    side = {
        "lane": "elevation",
        "source": "Copernicus DEM GLO-30 (2021 release, DSM, 1 arcsec) via AWS Open Data s3://copernicus-dem-30m; "
                  "(c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS "
                  "by the European Union and ESA; free licence with attribution. Labels and boundary (c) OpenStreetMap "
                  "contributors, ODbL.",
        "layers": [
            {"file": "elevation_hillshade.png", "title": "Terrain relief", "geometry_type": "raster image",
             "bounds": [W, S, E, N], "image_crs": "EPSG:3857 grid (use as MapLibre image source with these corners)",
             "maplibre_coordinates": [[W, N], [E, N], [E, S], [W, S]],
             "suggested_opacity": 0.85, "units": "m", "sea": "transparent (DEM = 0)",
             "colour_ramp": {str(k): "#%02x%02x%02x" % tuple(int(c * 255) for c in v) for k, v in RAMP},
             "legend_text": "Height above sea level, shaded from the north-west. Green = Cape Flats lowland, "
                            "brown/grey = mountain."},
            {"file": "elevation_terrain/{z}/{x}/{y}.png", "title": "3D terrain", "geometry_type": "raster-dem tiles",
             "encoding": "mapbox", "tileSize": 256, "minzoom": ZMIN, "maxzoom": ZMAX, "bounds": [W, S, E, N],
             "suggested_exaggeration": 1.5, "units": "m",
             "note": "height = -10000 + (R*65536 + G*256 + B) * 0.1; sea set to 0 m. Outside bounds: no tiles."},
            {"file": "elevation_labels.geojson", "title": "Peaks and neighbourhoods", "geometry_type": "Point",
             "colour_by": "kind", "categories": {"peak": "#7a3b1d", "place": "#222222", "landmark": "#1f5f8b"},
             "label_field": "label",
             "popup_fields": {"name": "Name", "kind": "Type", "height_m": "Published height (m)",
                              "height_m_dem": "Height in the 30 m DEM (m)", "osm_ref": "OSM object"},
             "legend_text": "Peak labels carry published summit heights; the 30 m DEM reads sharp summits low "
                            "(Lion's Head 600 m vs 669 m published)."},
            {"file": "elevation_boundary.geojson", "title": "City of Cape Town metro boundary",
             "geometry_type": "MultiPolygon", "colour_by": None, "style": {"line": "#333333", "width": 1.5,
                                                                          "dash": [3, 2], "fill": "none"},
             "popup_fields": {"name": "Name", "area_km2": "Area (km2, mainland + Robben Island)"},
             "note": "OSM relation 79604; the Prince Edward Islands (sub-Antarctic, also in the relation) removed."},
        ],
    }
    json.dump(side, open(WEB / "elevation_layers.json", "w"), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    WEB.mkdir(parents=True, exist_ok=True)
    export_boundary()
    export_labels()
    export_sidecar()
    export_hillshade()
    export_terrain()
