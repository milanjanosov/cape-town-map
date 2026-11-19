"""Clean OSM places into a matching gazetteer: one point per canonical name, aliases, ambiguity tier."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
os.chdir(paths.lane_dir("news"))
import json, pandas as pd, geopandas as gpd
els = json.load(open("data/osm_places_raw.json"))["elements"]
rows = []
for e in els:
    t = e.get("tags", {})
    lat = e.get("lat") or e.get("center", {}).get("lat"); lon = e.get("lon") or e.get("center", {}).get("lon")
    if t.get("name"): rows.append(dict(osm_id=f"{e['type']}/{e['id']}", name=t["name"], place=t.get("place"), lat=lat, lon=lon))
g = gpd.GeoDataFrame(pd.DataFrame(rows), geometry=gpd.points_from_xy([r["lon"] for r in rows], [r["lat"] for r in rows]), crs=4326)
metro = gpd.read_file(paths.osm_boundary()).geometry.iloc[0]
g = g[g.within(metro)].copy()

# variant spellings in OSM -> canonical
CANON = {"Parow-Oos": "Parow East", "Parowvallei": "Parow Valley", "Sybrandpark": "Sybrand Park", "Pelikan Park": "Pelican Park",
         "Dieprivier": "Diep River", "Fir Grove": "Firgrove", "Bo-Kaap (Schotschekloof)": "Bo-Kaap", "Waterfront": "V&A Waterfront",
         "Kalkbaai": "Kalk Bay", "Guguletu": "Gugulethu", "Elsiesriver": "Elsies River", "Eersterivier": "Eerste River",
         "Kuilsrivier": "Kuils River", "Du Noon": "Dunoon", "Mitchells Plain": "Mitchells Plain", "Bloubergstrand": "Blouberg",
         "Eersterivier Suid": "Eerste River South", "Sabata Dalindyebo Square (Green Point)": "Sabata Dalindyebo Square",
         "Mandela Park (Makaya)": "Mandela Park", "Victoria Mxenge (Site B)": "Victoria Mxenge", "Nonqubela (Site B)": "Nonqubela",
         "Mxolisi Phetani (Site C)": "Mxolisi Phetani", "Umrhabulo Triangle (Makhaza)": "Makhaza", "Silvertown - Khayelitsha": "Silvertown",
         "Broadlands Park (Tarentaalplaas)": "Broadlands Park", "Rome Estate (Kleinbos)": "Rome Estate", "Philippi - Farmland": "Philippi"}
g["canonical"] = g["name"].map(lambda n: CANON.get(n, n))
# extra aliases that appear in news but not as OSM names (regex alternatives, case-sensitive)
ALIASES = {"Kalk Bay": ["Kalk Bay", "Kalkbaai"], "Gugulethu": ["Gugulethu", "Guguletu"], "Elsies River": ["Elsies River", "Elsiesrivier", "Elsiesriver"],
           "Eerste River": ["Eerste River", "Eersterivier"], "Kuils River": ["Kuils River", "Kuilsrivier"], "Dunoon": ["Dunoon", "Du Noon"],
           "Mitchells Plain": ["Mitchells Plain", "Mitchell's Plain", "Mitchell’s Plain"], "Blouberg": ["Blouberg", "Bloubergstrand"],
           "City Centre": ["Cape Town CBD", "Cape Town city centre", "Cape Town City Centre", "CBD"], "V&A Waterfront": ["V&A Waterfront", "V&A", "Waterfront"],
           "Simon's Town": ["Simon's Town", "Simon’s Town", "Simonstown", "Simons Town"], "Gordon's Bay": ["Gordon's Bay", "Gordon’s Bay", "Gordons Bay"],
           "Sea Point": ["Sea Point", "Seapoint"], "Bo-Kaap": ["Bo-Kaap", "Bo Kaap"], "Imizamo Yethu": ["Imizamo Yethu"], "Khayelitsha": ["Khayelitsha", "Khayelitshas"],
           "St. James": ["St James", "St. James"], "Table View": ["Table View", "Tableview"], "Nyanga": ["Nyanga"], "Masiphumelele": ["Masiphumelele", "Masi"],
           "Makhaza": ["Makhaza"], "Hangberg": ["Hangberg"], "Philippi": ["Philippi"], "Fish Hoek": ["Fish Hoek", "Fishhoek"]}
# Tier B: real Cape Town suburbs whose names are also common words or places elsewhere.
# Counted only when the headline also carries a Cape Town cue (see 05_extract.py).
AMBIG = {"Observatory", "Woodstock", "Constantia", "Gardens", "Strand", "Harare", "Delft", "Atlantis", "Crossroads", "Langa", "Richmond",
         "Brooklyn", "Kensington", "Belgravia", "Rosebank", "Houghton", "Sunnyside", "Morningside", "Hillcrest", "Glenwood", "Bellair",
         "Woodlands", "Parkwood", "Montclair", "Portland", "Boston", "Philadelphia", "Eindhoven", "Casablanca", "Pella", "Eureka", "Khaya",
         "Sun City", "Riverside", "Mountain View", "Rocklands", "Retreat", "Newlands", "Rugby", "Surrey", "Vanguard", "Montague",
         "Highbury", "Windermere", "Thornton", "Sherwood", "Clifton", "Camelot", "Lakeside", "Penhill", "Phoenix", "Westlake",
         "Panorama", "Primrose Park", "Silversands", "Sunset Beach", "Ottery", "Hanover Park", "Steenberg", "Capri", "Plumstead",
         "Kenilworth", "Wynberg", "Claremont", "Rondebosch", "Salt River", "Maitland", "Green Point", "V&A Waterfront", "Nyanga",
         "Masiphumelele", "Philippi", "Tokai", "Sun Valley", "Eden Park", "Witsand", "Belmont Park", "Stellenberg", "Bridgetown", "Lansdowne", "Athlone", "Heathfield", "Southfield", "Crawford", "Goodwood",
         "Epping Forest", "Hout Bay", "Melkbosstrand", "Muizenberg", "Durbanville", "Parklands", "Milnerton", "City Centre"} \
        - {"Hout Bay", "Muizenberg", "Durbanville", "Melkbosstrand", "Parklands", "Milnerton"}  # these are unique enough in SA news
# Dobson = Stormers coach John Dobson; La Rochelle = French rugby club (both seen in the Nov 2026 run)
# Tier C: never counted (generic words, estates, or names that are almost always something else)
DROP = {"Metro", "Welcome", "The Glen", "The Links", "The Crest", "The Palms", "The Vines", "The Hague", "Good Hope", "Heritage Close",
        "Heritage Manor", "Heritage Mews", "Heritage Villas", "Tara", "Bene", "Aurora", "Alora", "Capricorn", "Arauna", "High Places",
        "Saint Tropez", "Square Hill", "Sweet Home", "Graceland", "Electric City", "Deep Freeze", "Smartie Town", "Labiance", "Goodrail",
        "Waters Edge Estate", "Twin Palms", "Seawinds", "Sea Breeze", "Summer Greens", "North Shore", "East Rock", "Golden Acre",
        "Cape Heritage", "Century Place", "Northgate", "Westgate", "Mandalay", "Malibu Village", "Morning Star", "Die Bos", "Die Rif",
        "Die Vlakte", "Die Wingerd", "De Tuin", "Pine Acres", "Park Estate", "Park Estates", "Hatton", "Wetton", "Gersham", "Victoria Park",
        "Mission Grounds", "Robben Island Village", "Klipfontein", "Bloemhof", "Richwood", "Sunridge", "Brooklyn", "Philadelphia",
        "Portland", "Boston", "Casablanca", "Eindhoven", "Dobson", "La Rochelle", "Phoenix", "Eureka", "Khaya", "Richmond", "Kensington", "Belgravia",
        "Rosebank", "Houghton", "Sunnyside", "Morningside", "Hillcrest", "Glenwood", "Bellair", "Woodlands", "Montclair", "Sun City",
        "Riverside", "Mountain View", "Rugby", "Surrey", "Vanguard", "Highbury", "Windermere", "Thornton", "Sherwood", "Camelot",
        "Pella", "Retreat", "Panorama", "Montague", "Westlake", "Lakeside", "Parkwood"}
RANK = {"town": 0, "suburb": 1, "quarter": 2, "village": 3, "neighbourhood": 4, "hamlet": 5}
g["rank"] = g["place"].map(RANK)
g = g[~g["canonical"].isin(DROP)]
g["is_node"] = g["osm_id"].str.startswith("node").map({True: 0, False: 1})  # OSM label node beats a way/relation bbox centre
g = g.sort_values(["canonical", "rank", "is_node"])
import numpy as np
spread = g.groupby("canonical").apply(lambda d: float(np.max(np.hypot((d.lat - d.lat.iloc[0]) * 111320, (d.lon - d.lon.iloc[0]) * 92300))), include_groups=False)
# manual picks where one name has two distant OSM places; chosen by what the headlines refer to
OVERRIDE = {"Westridge": "node/12188277791"}  # Mitchells Plain (Westridge Yankees, Athlone News), not Somerset West
for name, oid in OVERRIDE.items():
    g = g[(g.canonical != name) | (g.osm_id == oid)]
gz = g.groupby("canonical", as_index=False).first()
gz["spread_m"] = gz["canonical"].map(spread).round(0)
gz["n_osm_points"] = g.groupby("canonical").size().reindex(gz["canonical"]).values
gz["aliases"] = gz["canonical"].map(lambda c: "|".join(ALIASES.get(c, [c])))
gz["tier"] = gz["canonical"].map(lambda c: "B_needs_context" if c in AMBIG else "A")
gz = gz.rename(columns={"canonical": "place"})[["place", "aliases", "tier", "place", "osm_id", "lat", "lon", "n_osm_points", "spread_m"]]
gz = gz.loc[:, ~gz.columns.duplicated()]
gz["osm_place_type"] = g.groupby("canonical")["place"].first().reindex(gz["place"]).values
gz.to_csv("data/gazetteer.csv", index=False)
print(len(gz), gz.tier.value_counts().to_dict())
