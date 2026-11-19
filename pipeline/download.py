"""Fetch every raw source the five lanes need into raw/<lane>/data/.

    python download_data.py                    # everything (long: news alone is ~30 min)
    python download_data.py --lane crime       # one lane (repeatable: --lane crime --lane demography)
    python download_data.py --list             # show what would be fetched, and what is already here
    python download_data.py --lane crime --force   # re-fetch even if present

Files already on disk are skipped. Requests are spaced out (1 s per host, Nominatim 1.1 s,
GDELT 20-45 s). Every step reports OK / SKIP / FAIL, and the run ends with a summary plus the
steps that need a human.
"""
import argparse
import json
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import paths  # noqa: E402

PY = sys.executable
_last_hit = {}


def polite(url, gap=1.0):
    host = urllib.parse.urlparse(url).netloc
    wait = gap - (time.time() - _last_hit.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()


# Some servers send their TLS certificate without the intermediate CA. Browsers (and curl on macOS)
# fetch it themselves; Python does not. For those hosts the missing intermediate is downloaded from
# the issuer's published URL (the leaf certificate's "CA Issuers" field) and added to the trust
# store. The chain is still verified up to a root CA, so certificate checking stays on.
MISSING_INTERMEDIATE = {
    "www.saps.gov.za": "http://crt.sectigo.com/SectigoPublicServerAuthenticationCAOVR36.crt",
}
_ctx = {}


def ssl_context(host):
    if host not in _ctx:
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            ctx = ssl.create_default_context()
        if host in MISSING_INTERMEDIATE:
            der = urllib.request.urlopen(MISSING_INTERMEDIATE[host], timeout=60).read()
            ctx.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(der))
        _ctx[host] = ctx
    return _ctx[host]


def http_get(url, timeout=300, gap=1.0, data=None):
    polite(url, gap)
    req = urllib.request.Request(url, data=data, headers=paths.UA)
    host = urllib.parse.urlparse(url).netloc
    ctx = ssl_context(host) if url.startswith("https") else None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return r.read()


def fetch_file(url, out, check_zip=False, tries=4, gap=1.0):
    """Download url to out (via a .part file), retrying; validate zip containers if asked."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.name + ".part")
    last = None
    for attempt in range(tries):
        try:
            part.write_bytes(http_get(url, gap=gap))
            if check_zip:
                zipfile.ZipFile(part).testzip()
            part.replace(out)
            return out
        except Exception as e:  # noqa: BLE001 - report and retry
            last = e
            time.sleep(5 * (attempt + 1))
    part.unlink(missing_ok=True)
    raise RuntimeError(f"{url}: {last}")


def have(*files):
    return all(Path(f).exists() and Path(f).stat().st_size > 0 for f in files)


def run_script(lane, script, *args):
    """Run one of the lane's own fetch scripts (they know their sources)."""
    cmd = [PY, str(paths.PIPELINE / lane / script), *args]
    r = subprocess.run(cmd)
    if r.returncode:
        raise RuntimeError(f"{script} exited with {r.returncode}")


def arcgis_geojson(url, out, where="1=1", fields="*", page=1000):
    feats, off = [], 0
    while True:
        q = urllib.parse.urlencode(dict(where=where, outFields=fields, outSR=4326, f="geojson",
                                        resultOffset=off, resultRecordCount=page))
        d = json.loads(http_get(f"{url}/query?{q}"))
        got = d.get("features", [])
        feats += got
        off += len(got)
        if len(got) < page or not d.get("exceededTransferLimit", len(got) == page):
            break
    Path(out).write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    return len(feats)


def ghsl_tile(epoch, dest_dir):
    """JRC GHS-POP R2023A, 100 m Mollweide tile R14_C20 (covers Cape Town), unzipped."""
    name = f"GHS_POP_E{epoch}_GLOBE_R2023A_54009_100_V1_0_R14_C20"
    tif = Path(dest_dir) / f"{name}.tif"
    if have(tif):
        return "present"
    url = (f"https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/"
           f"GHS_POP_E{epoch}_GLOBE_R2023A_54009_100/V1-0/tiles/{name}.zip")
    z = fetch_file(url, Path(dest_dir) / f"{name}.zip", check_zip=True)
    with zipfile.ZipFile(z) as zf:
        zf.extract(f"{name}.tif", dest_dir)
    return "downloaded"


# =============================================================== elevation
def elevation_steps():
    d = paths.lane_dir("elevation") / "data"
    steps = []
    for t in ("S34_00_E018", "S35_00_E018", "S34_00_E019", "S35_00_E019"):
        n = f"Copernicus_DSM_COG_10_{t}_00_DEM"
        steps.append((f"Copernicus DEM GLO-30 tile {t}", [d / f"{n}.tif"],
                      lambda n=n: fetch_file(f"https://copernicus-dem-30m.s3.amazonaws.com/{n}/{n}.tif", d / f"{n}.tif")))
    steps.append(("City of Cape Town boundary (OSM relation 79604 via Nominatim)", [paths.osm_boundary()], osm_boundary))
    return steps


def osm_boundary():
    import geopandas as gpd
    raw = paths.lane_dir("elevation") / "tmp" / "cct_raw.geojson"
    raw.write_bytes(http_get("https://nominatim.openstreetmap.org/lookup?osm_ids=R79604&format=geojson&polygon_geojson=1",
                             gap=1.1))
    g = gpd.read_file(raw).explode(index_parts=False)
    g = g[g.geometry.centroid.x < 20]  # drop the sub-Antarctic Prince Edward Islands (same relation)
    g[["geometry"]].dissolve().to_file(paths.osm_boundary(), driver="GeoJSON")


# =============================================================== demography
# www.capetown.gov.za redirects these to /media/<id>/...; the older resource.capetown.gov.za host times out.
WARD_PDF = ("https://www.capetown.gov.za/_documents/resource.capetown.gov.za/documentcentre/Documents/"
            "Maps%20and%20statistics/2011_Census_CT_Ward_{:03d}_Profile.pdf")


def demography_steps():
    raw = paths.lane_dir("demography") / "data" / "raw"
    wp = raw / "ward_profiles_2011"
    layers = [raw / n for n in ("wards2011_statssa_uct.geojson", "wards_cct_odp.geojson", "suburbs_cct_odp.geojson",
                                "valuations_suburbs_gv2022_gv2025.json")]

    def ward_pdfs():
        wp.mkdir(parents=True, exist_ok=True)
        for i in range(1, 112):
            f = wp / f"2011_Census_CT_Ward_{i:03d}_Profile.pdf"
            if not have(f):
                fetch_file(WARD_PDF.format(i), f)
    return [
        ("City of Cape Town ODP + Stats SA 2011 ward layers (fetch_layers.py)", layers,
         lambda: run_script("demography", "fetch_layers.py")),
        ("Census 2011 ward profiles, 111 PDFs (capetown.gov.za)",
         [wp / f"2011_Census_CT_Ward_{i:03d}_Profile.pdf" for i in range(1, 112)], ward_pdfs),
        ("GHS-POP R2023A epoch 2020 tile R14_C20 (JRC)",
         [raw / "ghsl" / "GHS_POP_E2020_GLOBE_R2023A_54009_100_V1_0_R14_C20.tif"], lambda: ghsl_tile(2020, raw / "ghsl")),
    ]


# =============================================================== crime
WCG = "https://gis.westerncape.gov.za/server2/rest/services"
QUARTERS = ("1st", "2nd", "3rd", "4th")


def crime_steps():
    d = paths.lane_dir("crime") / "data"
    steps = []
    for q in QUARTERS:
        out = d / "raw_saps" / f"2025-2026_{q}_Quarter.xlsx"
        url = f"https://www.saps.gov.za/services/downloads/2025/2025-2026_-_{q}_Quarter_WEB.xlsx"
        steps.append((f"SAPS crime statistics 2025/26 {q} quarter workbook", [out],
                      lambda url=url, out=out: fetch_file(url, out, check_zip=True, tries=6)))
    steps += [
        ("WCG SAPS precinct polygons + station points (fetch_precincts.py)",
         [d / "wc_saps_precincts.geojson", d / "wc_saps_stations.geojson"], lambda: run_script("crime", "fetch_precincts.py")),
        ("GeoTerraImage 2024 population summed by precinct x municipality (WCG PDO, VIEW-ONLY licence)",
         [d / "gti_pop_by_precinct_mun.json"], gti_population),
        ("GeoTerraImage 2024 enumeration areas assigned to Makhaza (WCG PDO, VIEW-ONLY licence)",
         [d / "gti_makhaza_eas.geojson"],
         lambda: arcgis_geojson(f"{WCG}/PDO/Population_Dashboards_2024/MapServer/5", d / "gti_makhaza_eas.geojson",
                                where="Precinct='MAKHAZA'", fields="Precinct,EA_CODE11,TOTAL_PP24")),
        ("Stats SA 2011 City of Cape Town municipal boundary (WCG)", [d / "coct_metro_boundary.geojson"],
         lambda: arcgis_geojson(f"{WCG}/SpatialDataWarehouse/StatsSA_CensusBoundaries/MapServer/4",
                                d / "coct_metro_boundary.geojson", where="MN_MDB_C='CPT'", fields="MN_NAME,MN_MDB_C")),
        ("GHS-POP R2023A epoch 2025 tile R14_C20 (JRC)",
         [d / "raw_ghsl" / "GHS_POP_E2025_GLOBE_R2023A_54009_100_V1_0_R14_C20.tif"],
         lambda: ghsl_tile(2025, d / "raw_ghsl")),
    ]
    return steps


def gti_population():
    print("  NOTE: the WCG item says 'Data can be viewed but not downloaded'. This fetches per-precinct totals\n"
          "  at run time for your own build; do not commit or redistribute the file (raw/ is git-ignored).")
    stats = json.dumps([{"statisticType": "sum", "onStatisticField": "TOTAL_PP24", "outStatisticFieldName": "pop"}])
    q = urllib.parse.urlencode(dict(where="1=1", groupByFieldsForStatistics="Precinct,MN_NAME_18",
                                    outStatistics=stats, f="json"))
    raw = http_get(f"{WCG}/PDO/Population_Dashboards_2024/MapServer/5/query?{q}")
    if "features" not in json.loads(raw):
        raise RuntimeError(f"unexpected answer: {raw[:300]!r}")
    (paths.lane_dir("crime") / "data" / "gti_pop_by_precinct_mun.json").write_bytes(raw)


# =============================================================== transit
MYCITI_ROUTES = ["101", "102", "103", "104", "105", "106", "107", "108", "109", "111", "113", "213", "214a", "214b",
                 "214c", "215", "216", "223", "231", "233", "234", "235", "236", "237", "244", "245", "246", "260",
                 "261", "262", "D01", "D02", "D03", "D04", "D05", "D08", "T01", "T01X", "T02", "T03", "T04"]
OSM_STATIONS_Q = ('[out:json][timeout:200];(node["railway"~"station|halt"](-34.30,18.30,-33.40,19.10);'
                  'node["place"~"suburb|town|neighbourhood|quarter"](-34.30,18.30,-33.45,19.00););out body;')


def transit_steps():
    d = paths.lane_dir("transit") / "data"
    pdf = d / "myciti_pdf"

    def myciti():
        for r in MYCITI_ROUTES:
            f = pdf / f"{r}.pdf"
            if not have(f):
                fetch_file(f"https://www.myciti.org.za/docs/route-timetables/{r}-timetable.pdf", f)

    def osm_places():
        raw = http_get("https://overpass-api.de/api/interpreter", timeout=400, gap=5,
                       data=urllib.parse.urlencode({"data": OSM_STATIONS_Q}).encode())
        json.loads(raw)
        (d / "osm_places_stations.json").write_bytes(raw)

    return [
        ("City of Cape Town ODP transit layers + OSM route relations (fetch_sources.py)",
         [d / f"{n}.geojson" for n in ("cct_myciti_routes", "cct_myciti_stops", "cct_taxi_routes", "cct_rail_stations")]
         + [d / "osm_train_routes.json"], lambda: run_script("transit", "fetch_sources.py")),
        ("OSM railway stations and place nodes (Overpass)", [d / "osm_places_stations.json"], osm_places),
        ("MyCiTi timetable PDFs (41 routes, myciti.org.za)", [pdf / f"{r}.pdf" for r in MYCITI_ROUTES], myciti),
        ("Metrorail timetable pages from kaapsetrains.co.za (scrape_rail_times.py, cached per page)",
         [d / "rail_departures.csv"], lambda: run_script("transit", "scrape_rail_times.py")),
    ]


# =============================================================== news
def news_steps():
    w = paths.lane_dir("news")
    return [
        ("City of Cape Town boundary (shared with elevation)", [paths.osm_boundary()], osm_boundary),
        ("OSM place names in the metro (Overpass, 01_gazetteer.py)", [w / "data" / "osm_places_raw.json"],
         lambda: run_script("news", "01_gazetteer.py")),
        ("Matching gazetteer (local, 03_build_gazetteer.py)", [w / "data" / "gazetteer.csv"],
         lambda: run_script("news", "03_build_gazetteer.py")),
        ("Outlet RSS feeds (02_collect_gdelt_rss.py rss)", [w / "tmp" / "raw" / "rss.csv"],
         lambda: run_script("news", "02_collect_gdelt_rss.py", "rss")),
        ("GDELT DOC 2.0 headlines (02_collect_gdelt_rss.py gdelt; slow, often HTTP 429)", [w / "tmp" / "raw" / "gdelt.csv"],
         lambda: run_script("news", "02_collect_gdelt_rss.py", "gdelt")),
        ("Google News RSS searches, broad + one per suburb (04_collect_google_news.py, ~20 min)",
         [w / "tmp" / "raw" / "gnews.csv"], lambda: run_script("news", "04_collect_google_news.py")),
    ]


STEPS = {"elevation": elevation_steps, "demography": demography_steps, "crime": crime_steps,
         "transit": transit_steps, "news": news_steps}

MANUAL = {
    "crime": "GeoTerraImage precinct population is fetched at run time from a 'view only' WCG service; never commit it.",
    "news": f"News window is {paths.NEWS_START} .. {paths.NEWS_END} (set CTM_NEWS_START / CTM_NEWS_END to refresh). "
            "Google News only returns recent items, so an old window cannot be re-collected exactly. New articles "
            "need a 1-2 sentence summary added by hand to pipeline/news/inputs/article_summaries.csv "
            "(otherwise their pins show the headline only).",
    "elevation": "Label positions are hand-checked in pipeline/elevation/inputs/labels_verified.csv (not re-geocoded).",
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lane", action="append", choices=paths.LANES, help="only this lane (repeatable)")
    ap.add_argument("--force", action="store_true", help="re-download even if the files are present")
    ap.add_argument("--list", action="store_true", help="list the steps and whether their files exist; fetch nothing")
    a = ap.parse_args(argv)
    lanes = a.lane or paths.LANES
    results = []
    for lane in lanes:
        print(f"\n=== {lane}")
        for title, outs, action in STEPS[lane]():
            present = have(*outs)
            if a.list:
                print(f"  [{'present' if present else 'missing'}] {title}")
                continue
            if present and not a.force:
                print(f"  SKIP (present)  {title}")
                results.append((lane, "SKIP", title, ""))
                continue
            print(f"  ...             {title}", flush=True)
            try:
                if a.force:
                    for f in outs:
                        Path(f).unlink(missing_ok=True)
                action()
                missing = [str(Path(f).relative_to(paths.REPO)) if paths.REPO in Path(f).parents else str(f)
                           for f in outs if not have(f)]
                if missing:
                    raise RuntimeError(f"finished but files are missing: {missing[:3]}")
                print(f"  OK              {title}")
                results.append((lane, "OK", title, ""))
            except Exception as e:  # noqa: BLE001 - keep going, report at the end
                print(f"  FAIL            {title}\n                  {e}")
                results.append((lane, "FAIL", title, str(e)))
    if a.list:
        return 0
    print("\n=== summary")
    for lane, st, title, err in results:
        print(f"  {st:5s} {lane:10s} {title}" + (f"\n        -> {err[:300]}" if err else ""))
    notes = [f"  {lane}: {MANUAL[lane]}" for lane in lanes if lane in MANUAL]
    if notes:
        print("\n=== needs a human\n" + "\n".join(notes))
    fails = [r for r in results if r[1] == "FAIL"]
    if fails:
        print(f"\n{len(fails)} step(s) failed. Re-run the same command to retry only what is missing; "
              "if a source keeps failing, its URL is in pipeline/download.py or the lane's fetch script.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
