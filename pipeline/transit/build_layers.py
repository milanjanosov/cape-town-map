"""Build the transit layers: routes and stops, all modes, with weekday departures.

Inputs (all in data/, fetched by fetch_sources.py, scrape_rail_times.py,
parse_myciti.py):
  cct_myciti_routes / cct_myciti_stops   City of Cape Town ODP, 2026-07
  cct_taxi_routes                        City of Cape Town ODP, 2026-07
  cct_rail_stations                      City of Cape Town ODP, 2026-07
  osm_train_routes.json                  OSM Metrorail route relations
  osm_places_stations.json               OSM station + place nodes
  myciti_stop_times.csv                  parsed MyCiTi PDF timetables (Oct 2026)
  rail_departures.csv                    PRASA timetable via kaapsetrains.co.za

Outputs:
  out/layers/routes.geojson, out/layers/stops.geojson   (full, for the PNGs)
  data/transit_routes.geojson, transit_stops.geojson (repo data/ folder)
  out/layers/match_report.txt                           (every join, counted)

Run: python pipeline/transit/build_layers.py
"""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import collections
import difflib
import json
import pathlib
import re

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import linemerge, unary_union

ROOT = paths.lane_dir("transit")
DATA = ROOT / "data"
OUT = ROOT / "out" / "layers"
OUT.mkdir(parents=True, exist_ok=True)
WEB = paths.DATA
UTM = 32734

MODE_COLOUR = {
    "rail": "#E4572E",          # Metrorail
    "brt": "#2E86DE",           # MyCiTi trunk (dedicated lanes)
    "bus": "#8FD3FE",           # MyCiTi feeder / direct
    "taxi": "#F6C945",          # minibus taxi
}
MODE_LABEL = {"rail": "Metrorail train", "brt": "MyCiTi BRT trunk",
              "bus": "MyCiTi bus (feeder / direct)", "taxi": "Minibus taxi route"}
RAIL_LINES = {  # OSM relation name prefix -> (line, line colour from OSM)
    "Southern Line": ("Southern Line", "#ed1c24"),
    "Northern Line": ("Northern Line", "#00a650"),
    "Central Line": ("Central Line", "#33bef3"),
    "Cape Flats Line": ("Cape Flats Line", "#8c493a"),
}
REPORT = []


def log(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    REPORT.append(s)


def norm(s):
    s = str(s).lower().replace("&", "and")
    s = re.sub(r"\bst\.?\s", "saint ", s)
    return re.sub(r"[^a-z0-9]", "", s)


SUFFIX = re.compile(r"\s+(\d+[a-z]?|north|south|east|west|nb|sb|eb|wb|a|b|c|d|station|rail)$", re.I)


def base(s):
    s = str(s).strip()
    for _ in range(3):
        s = SUFFIX.sub("", s)
    return norm(s)


def simplify(gdf, tol=12):
    g = gdf.to_crs(UTM)
    g["geometry"] = g.geometry.simplify(tol, preserve_topology=False)
    g = g[~g.geometry.is_empty & g.geometry.notna()]
    return g.to_crs(4326)


# ---------------------------------------------------------------- MyCiTi
def myciti():
    st = pd.read_csv(DATA / "myciti_stop_times.csv")
    wk = st[st.day == "weekday"].copy()
    wk["route_key"] = wk.route.str.upper()
    trips_per_route = wk.groupby("route_key").trip.nunique()

    r = gpd.read_file(DATA / "cct_myciti_routes.geojson")
    log(f"MyCiTi routes: {len(r)} CCT features, status {r.RT_STS.value_counts().to_dict()}")
    r = r[r.RT_STS == "Active"].copy()
    r["route_key"] = r.RT_NMBR.str.upper().str.strip()
    r = r.dissolve(by="route_key", aggfunc="first").reset_index()
    r["mode"] = np.where(r.RT_TYPE.str.startswith("Trunk"), "brt", "bus")
    r["weekday_trips"] = r.route_key.map(trips_per_route).fillna(0).astype(int)
    miss = sorted(set(trips_per_route.index) - set(r.route_key))
    log(f"  active routes {len(r)}; timetabled routes without CCT geometry: {miss}")
    log(f"  CCT active routes without a timetable PDF: "
        f"{sorted(r.loc[r.weekday_trips == 0, 'route_key'])}")
    routes = gpd.GeoDataFrame(dict(
        mode=r["mode"], route_ref=r.route_key, route_name=r.RT_NAME,
        operator="MyCiTi (City of Cape Town)", route_type=r.RT_TYPE,
        weekday_trips=r.weekday_trips, colour=r["mode"].map(MODE_COLOUR),
        source="City of Cape Town ODP (geometry); MyCiTi PDF timetables Oct 2026 (trips)"),
        geometry=r.geometry, crs=4326)
    route_geom_utm = dict(zip(r.route_key, r.to_crs(UTM).geometry))

    # ---- stops: cluster CCT stop points by base name, then attach departures
    s = gpd.read_file(DATA / "cct_myciti_stops.geojson")
    s = s[s.STOP_STS == "Active"].to_crs(UTM).copy()
    s["key"] = s.STOP_NAME.map(base)
    groups = []
    for key, grp in s.groupby("key"):
        pts = np.c_[grp.geometry.x, grp.geometry.y]
        lab = -np.ones(len(pts), int)
        c = 0
        for i in range(len(pts)):  # single-linkage clusters at 400 m
            if lab[i] >= 0:
                continue
            stack, lab[i] = [i], c
            while stack:
                j = stack.pop()
                near = np.where((np.hypot(*(pts - pts[j]).T) < 400) & (lab < 0))[0]
                lab[near] = c
                stack += list(near)
            c += 1
        for k in range(c):
            sub = grp[lab == k]
            groups.append(dict(key=key, name=sorted(sub.STOP_NAME, key=len)[0],
                               n_points=len(sub), is_station=(sub.STOP_TYPE == "IRT Station").any(),
                               geometry=Point(sub.geometry.x.mean(), sub.geometry.y.mean())))
    G = gpd.GeoDataFrame(groups, crs=UTM)
    G["name"] = G.name.str.replace(SUFFIX, "", regex=True).str.strip()
    keys = sorted(set(G.key))

    dep = (wk[wk.kind != "Arr"].groupby(["route_key", "stop_name"]).size()
           .rename("dep").reset_index())
    G["weekday_departures"] = 0
    G["routes"] = [[] for _ in range(len(G))]
    unmatched = collections.Counter()
    fuzzy = {}
    for row in dep.itertuples():
        k = base(row.stop_name)
        if k not in set(G.key):
            m = difflib.get_close_matches(k, keys, n=1, cutoff=0.82)
            if not m:
                unmatched[row.stop_name] += row.dep
                continue
            fuzzy[row.stop_name] = m[0]
            k = m[0]
        cand = G.index[G.key == k]
        rg = route_geom_utm.get(row.route_key)
        if rg is not None:
            d = G.loc[cand].geometry.distance(rg)
            if d.min() > 600:
                unmatched[row.stop_name] += row.dep
                continue
            gi = d.idxmin()
        elif len(cand) == 1:
            gi = cand[0]
        else:
            unmatched[row.stop_name] += row.dep
            continue
        G.at[gi, "weekday_departures"] += row.dep
        G.at[gi, "routes"] = sorted(set(G.at[gi, "routes"]) | {row.route_key})
    tot = dep.dep.sum()
    um = sum(unmatched.values())
    log(f"MyCiTi stops: {len(s)} active CCT points -> {len(G)} stop groups")
    log(f"  weekday departures {tot:,}; placed {tot - um:,} ({1 - um / tot:.1%}); "
        f"unplaced {um:,} across {len(unmatched)} names: {unmatched.most_common(15)}")
    log(f"  fuzzy name matches used: {fuzzy}")
    G = G.to_crs(4326)
    stops = gpd.GeoDataFrame(dict(
        mode=np.where(G.is_station, "brt", "bus"), name=G.name,
        operator="MyCiTi (City of Cape Town)",
        weekday_departures=G.weekday_departures.astype(int),
        routes=G.routes.map(lambda x: ", ".join(x)),
        has_timetable=G.weekday_departures > 0,
        source="City of Cape Town ODP (location); MyCiTi PDF timetables Oct 2026"),
        geometry=G.geometry, crs=4326)
    return routes, stops


# ---------------------------------------------------------------- rail
def osm_rail_lines():
    d = json.load(open(DATA / "osm_train_routes.json"))["elements"]
    nodes = {e["id"]: (e["lon"], e["lat"]) for e in d if e["type"] == "node"}
    ways = {e["id"]: e["nodes"] for e in d if e["type"] == "way"}
    per_line = collections.defaultdict(set)
    for e in d:
        if e["type"] != "relation":
            continue
        name = e["tags"].get("name", "")
        if "Business Express" in name:
            continue
        for pre, (line, col) in RAIL_LINES.items():
            if name.startswith(pre):
                for m in e["members"]:
                    if m["type"] == "way" and m["role"] in ("", "route", "forward", "backward"):
                        per_line[line].add(m["ref"])
    feats = []
    for line, wids in per_line.items():
        segs = [LineString([nodes[n] for n in ways[w] if n in nodes])
                for w in wids if w in ways and len(ways[w]) > 1]
        geom = linemerge(unary_union(segs))
        feats.append(dict(line=line, colour=dict(RAIL_LINES.values())[line], geometry=geom))
        log(f"  OSM {line}: {len(wids)} ways")
    return gpd.GeoDataFrame(feats, crs=4326)


def rail():
    rd = pd.read_csv(DATA / "rail_departures.csv")
    wk = rd[rd.day == "weekday"].copy()
    wk["key"] = wk.station_name.map(norm)
    # departures between 07:00 and 07:59 (the morning-peak hour)
    wk["peak"] = wk.times.fillna("").map(lambda t: sum(x.startswith("07:") for x in t.split()))
    agg = wk.groupby("key").agg(name=("station_name", "first"), weekday_departures=("departures", "sum"),
                                peak_hour=("peak", "sum"), first=("first", "min"), last=("last", "max"),
                                lines=("line", lambda x: ", ".join(sorted(set(x)))))
    sat = rd[rd.day == "saturday"].assign(key=lambda x: x.station_name.map(norm)).groupby("key").departures.sum()
    agg["saturday_departures"] = sat.reindex(agg.index).fillna(0).astype(int)

    cct = gpd.read_file(DATA / "cct_rail_stations.geojson")
    cct = cct[cct.NAME.str.strip() != ""].copy()
    # CCT spellings: "Cape Town (Junction)", "Mutual (Juntion)", "Koeberg Weg"...
    cct["NAME"] = cct.NAME.str.replace(r"\s*\((Junction|Juntion)\)", "", regex=True).str.strip()
    cct = cct.drop_duplicates("NAME")
    cct["key"] = cct.NAME.map(norm)
    osm = json.load(open(DATA / "osm_places_stations.json"))["elements"]
    osm = pd.DataFrame([dict(key=norm(e["tags"]["name"]), lon=e["lon"], lat=e["lat"])
                        for e in osm if e["tags"].get("railway") in ("station", "halt")
                        and e["tags"].get("name")]).drop_duplicates("key")
    alias = {"koebergweg": "koebergroad", "acaciapark": "akasiapark", "hugenot": "huguenot",
             "vlottenberg": "vlottenburg"}
    cct["key"] = cct.key.map(lambda k: alias.get(k, k))

    rows = []
    for k, a in agg.iterrows():
        hit = cct[cct.key == k]
        src = "CCT"
        if hit.empty:
            m = difflib.get_close_matches(k, list(cct.key), n=1, cutoff=0.85)
            hit = cct[cct.key == m[0]] if m else hit
        if not hit.empty:
            geom = hit.geometry.iloc[0]
        else:
            o = osm[osm.key == k]
            if o.empty:
                m = difflib.get_close_matches(k, list(osm.key), n=1, cutoff=0.85)
                o = osm[osm.key == m[0]] if m else o
            if o.empty:
                log(f"  rail station without coordinates: {a['name']}")
                continue
            geom, src = Point(o.lon.iloc[0], o.lat.iloc[0]), "OSM"
        rows.append(dict(mode="rail", name=a["name"], operator="Metrorail (PRASA)",
                         weekday_departures=int(a.weekday_departures),
                         saturday_departures=int(a.saturday_departures),
                         peak_hour_departures=int(a.peak_hour), first_train=a["first"],
                         last_train=a["last"], routes=a.lines.replace("-", " ").title().replace(",", " Line,") + " Line",
                         has_timetable=True, location_source=src, geometry=geom))
    used = {norm(r["name"]) for r in rows}
    closed = cct[~cct.key.isin(set(agg.index)) & ~cct.key.isin(used)]
    for _, c in closed.iterrows():
        rows.append(dict(mode="rail", name=c.NAME, operator="Metrorail (PRASA)", weekday_departures=0,
                         saturday_departures=0, peak_hour_departures=0, first_train="", last_train="",
                         routes="", has_timetable=False, location_source="CCT", geometry=c.geometry))
    log(f"Rail: {len(agg)} timetabled stations ({(pd.DataFrame(rows).location_source == 'OSM').sum()} "
        f"located from OSM, outside the CCT layer); CCT stations with no 2026 trains: "
        f"{sorted(closed.NAME)}")
    stops = gpd.GeoDataFrame(rows, crs=4326)
    stops["source"] = "PRASA timetable (Jun 2026) via kaapsetrains.co.za; location CCT ODP / OSM"

    lines = osm_rail_lines()
    trips = wk.groupby("line").departures.sum()
    key = {"Southern Line": "southern", "Northern Line": "northern", "Central Line": "central",
           "Cape Flats Line": "cape-flats"}
    routes = gpd.GeoDataFrame(dict(
        mode="rail", route_ref=lines.line, route_name=lines.line, operator="Metrorail (PRASA)",
        route_type="Commuter rail", weekday_trips=-1,
        weekday_station_departures=lines.line.map(lambda l: int(trips.get(key[l], 0))),
        colour=MODE_COLOUR["rail"], line_colour=lines.colour,
        source="OpenStreetMap Metrorail route relations (geometry); PRASA timetable via kaapsetrains.co.za"),
        geometry=lines.geometry, crs=4326)
    return routes, stops


# ---------------------------------------------------------------- taxi
def taxi():
    t = gpd.read_file(DATA / "cct_taxi_routes.geojson")
    t["o"] = t.ORGN.str.title().str.strip()
    t["d"] = t.DSTN.str.title().str.strip()
    log(f"Taxi: {len(t)} CCT route lines, {t.o.nunique()} origins, {t.d.nunique()} destinations, "
        f"{t.to_crs(UTM).length.sum() / 1000:,.0f} km of line (overlapping)")
    return gpd.GeoDataFrame(dict(
        mode="taxi", route_ref="", route_name=t.o + " - " + t.d,
        operator="Minibus-taxi associations (various)", route_type="Minibus taxi (informal, no timetable)",
        weekday_trips=-1, colour=MODE_COLOUR["taxi"],
        source="City of Cape Town ODP, Taxi Routes (2026-07)"), geometry=t.geometry, crs=4326)


def to_web(gdf, path, tol):
    g = simplify(gdf, tol) if tol else gdf.copy()
    g = g.drop(columns=[c for c in ("source",) if c in g.columns])
    js = json.loads(g.to_json(drop_id=True))

    def rnd(c):
        return [rnd(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 5), round(c[1], 5)]
    for f in js["features"]:
        f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
        f["properties"] = {k: (int(v) if isinstance(v, float) and v.is_integer() else v)
                           for k, v in f["properties"].items() if v is not None}
    path.write_text(json.dumps(js, separators=(",", ":")))
    log(f"  wrote {path.name}: {len(js['features'])} features, {path.stat().st_size / 1e6:.2f} MB")


def main():
    mr, ms = myciti()
    rr, rs = rail()
    tr = taxi()
    for c in ("weekday_station_departures", "line_colour"):
        for g in (mr, tr):
            g[c] = None
    routes = pd.concat([tr, mr, rr], ignore_index=True)
    stops = pd.concat([ms, rs], ignore_index=True)
    stops["weekday_departures_display"] = stops.weekday_departures.map(
        lambda v: f"{v:,} departures per weekday" if v else "no timetabled service")
    routes = gpd.GeoDataFrame(routes, crs=4326)
    stops = gpd.GeoDataFrame(stops, crs=4326)
    routes.to_file(OUT / "routes.geojson", driver="GeoJSON")
    stops.to_file(OUT / "stops.geojson", driver="GeoJSON")
    log("Routes by mode:", routes["mode"].value_counts().to_dict())
    log("Stops by mode:", stops["mode"].value_counts().to_dict())
    log("Weekday departures by mode:", stops.groupby("mode").weekday_departures.sum().to_dict())
    WEB.mkdir(parents=True, exist_ok=True)
    to_web(routes, WEB / "transit_routes.geojson", 15)
    to_web(stops, WEB / "transit_stops.geojson", 0)
    (OUT / "match_report.txt").write_text("\n".join(REPORT) + "\n")


if __name__ == "__main__":
    main()
