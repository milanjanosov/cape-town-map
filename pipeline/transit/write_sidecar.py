"""Write data/transit_layers.json (layer description sidecar)."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import json
import pathlib

ROOT = paths.lane_dir("transit")
WEB = paths.DATA

side = {
    "lane": "transit",
    "generated": "2026-11-19",
    "notes": [
        "No GTFS exists for Cape Town proper (checked Mobility Database by bbox, Transitland Atlas, "
        "City of Cape Town portal, MyCiTi site, DT4A GitLab, GitHub). Departures are counted from "
        "published timetables instead: MyCiTi PDFs (Oct 2026) and the PRASA Metrorail timetable "
        "(in force 8 Jun 2026) as republished by kaapsetrains.co.za.",
        "Golden Arrow Bus Services (the largest formal bus operator) publishes no routes, stops or "
        "timetables: it is absent from every layer.",
        "Minibus taxis carry the largest share of public-transport commuters but have no timetable; "
        "their routes are drawn, with no frequency.",
        "A train departure carries roughly ten times a bus departure; do not read rail and bus "
        "counts as equal service.",
    ],
    "layers": [
        {
            "file": "transit_routes.geojson",
            "title": "Public transport routes",
            "geometry_type": "LineString / MultiLineString",
            "colour_by": "mode",
            "colour_property": "colour",
            "categories": {
                "rail": {"colour": "#E4572E", "label": "Metrorail train", "line_width": 3.5,
                         "draw_order": 4},
                "brt": {"colour": "#2E86DE", "label": "MyCiTi BRT trunk", "line_width": 3,
                        "draw_order": 3},
                "bus": {"colour": "#8FD3FE", "label": "MyCiTi feeder / direct bus", "line_width": 1.5,
                        "draw_order": 2},
                "taxi": {"colour": "#F6C945", "label": "Minibus-taxi route (no timetable)",
                         "line_width": 0.8, "opacity": 0.35, "draw_order": 1},
            },
            "suggested_toggles": ["rail", "brt", "bus", "taxi"],
            "units": None,
            "legend": "Public transport routes by mode. Taxi routes are surveyed origin-destination "
                      "paths, many overlap.",
            "popup_fields": {
                "route_name": "Route",
                "route_ref": "Number",
                "operator": "Operator",
                "route_type": "Type",
                "weekday_trips": "Trips per weekday (MyCiTi only; -1 = not available)",
                "weekday_station_departures": "Station departures per weekday (rail line total)",
            },
            "extra_properties": {"line_colour": "official-style Metrorail line colour (rail only)"},
            "source": "City of Cape Town Open Data Portal (MyCiTi routes, Taxi Routes; 2026-07); "
                      "OpenStreetMap contributors (Metrorail route relations, 2026-11-19); MyCiTi "
                      "timetables Oct 2026.",
            "licence": "City of Cape Town open-data terms of use "
                       "(https://www.capetown.gov.za/General/Terms-of-use-open-data); OSM data ODbL.",
            "vintage": "geometry 2026-07 (CCT) / 2026-11 (OSM); timetables Oct 2026 (MyCiTi), Jun 2026 (rail)",
        },
        {
            "file": "transit_stops.geojson",
            "title": "Stops and stations - weekday departures",
            "geometry_type": "Point",
            "colour_by": "weekday_departures",
            "colour_ramp": ["#7a828c", "#3b1f5c", "#6a2c8a", "#b03b85", "#e65c5c", "#f99a3e", "#fde68a"],
            "class_breaks": [0, 1, 25, 75, 150, 300, 600, 1500],
            "class_note": "0 = no timetabled service found (grey, hollow); then 1-24, 25-74, 75-149, "
                          "150-299, 300-599, 600+",
            "size_by": "weekday_departures (sqrt scale)",
            "symbol_by_mode": {"rail": "diamond / larger, white outline", "brt": "circle", "bus": "circle"},
            "units": "departures per weekday (Mon-Fri)",
            "legend": "Weekday departures per stop. MyCiTi stops are grouped by name (both platforms of "
                      "one stop = one point). Rail termini count departures only.",
            "popup_fields": {
                "name": "Stop",
                "mode": "Mode",
                "operator": "Operator",
                "weekday_departures_display": "Weekday service",
                "weekday_departures": "Departures per weekday",
                "saturday_departures": "Departures on Saturday (rail)",
                "peak_hour_departures": "Departures 07:00-07:59 (rail)",
                "first_train": "First train",
                "last_train": "Last train",
                "routes": "Routes / lines",
            },
            "source": "Stops: City of Cape Town Open Data Portal (MyCiTi Bus Stops, Railway Stations; "
                      "2026-07). Departures: MyCiTi PDF timetables (myciti.org.za, created 2026-10-14); "
                      "PRASA Metrorail timetable via kaapsetrains.co.za (scraped 2026-11-19).",
            "licence": "CCT open-data terms; MyCiTi timetables are public documents (no licence stated); "
                       "kaapsetrains.co.za is a third-party app with no stated licence - attribute it.",
            "vintage": "MyCiTi Oct 2026; Metrorail timetable in force from 8 Jun 2026",
        },
    ],
}
(WEB / "transit_layers.json").write_text(json.dumps(side, indent=2))
print("wrote", WEB / "transit_layers.json")
