# Cape Town, before you move

Interactive map: terrain in 3D, population, income, house prices, informal housing, crime by police precinct, public transport, and last month's local news pinned to suburbs. Open https://milanjanosov.github.io/cape-town-map/

Data and credits:
- Terrain: Copernicus DEM GLO-30 (ESA/EU, DLR e.V., Airbus Defence and Space), free licence with attribution
- Places, boundary, rail geometry: (c) OpenStreetMap contributors, ODbL
- Crime: SAPS quarterly crime statistics 2025/26 (Apr 2025 - Mar 2026); precinct population: GeoTerraImage 2024 estimates published by the Western Cape Government; precincts: Western Cape Government Spatial Data Warehouse
- Demography: Stats SA Census 2011 (ward profiles, City of Cape Town) and Census 2022 city total; JRC GHS-POP R2023A (CC BY 4.0)
- House prices: City of Cape Town General Valuation 2025 (open data portal)
- Transport: City of Cape Town open data (MyCiTi routes and stops, minibus-taxi routes, rail stations), MyCiTi timetables (Oct 2026), Metrorail timetable via kaapsetrains.co.za
- News: headlines and links via public RSS feeds and GDELT; summaries are paraphrased from headlines and feed descriptions

Every coloured area is a district average, not a street-level verdict. Made by The New Science of Maps.

## How to change the map

### What is in this repo

| Path | What it is |
|---|---|
| `index.html` | The deployed page. **Built output**, generated from `src/` by `python src/build.py`. Do not edit it by hand. |
| `src/template.html` | The page source: layout, CSS and the whole map script. Edit this. |
| `src/maplibre-gl.css` | MapLibre GL 4.7.1 stylesheet, inlined into `index.html` at build time. |
| `src/build.py` | Inlines the CSS into the template and writes `index.html`. |
| `data/` | Everything the page loads: GeoJSON layers, the hillshade PNG, terrain-RGB tiles (`elevation_terrain/{z}/{x}/{y}.png`, z8-12) and one `<lane>_layers.json` sidecar per lane that documents fields, colour ramps and sources. |
| `pipeline/<lane>/` | The scripts that make `data/`, one folder per lane: `elevation`, `demography`, `crime`, `transit`, `news`. `inputs/` holds the few hand-curated files (checked label positions, news summaries). |
| `pipeline/paths.py` | The one path config. Downloads go to `raw/<lane>/` (git-ignored), web layers to `data/`. |
| `download_data.py` | Fetches every raw source (same as `python -m pipeline download`). |
| `build_all.py` | Rebuilds `data/` and `index.html` from `raw/` (same as `python -m pipeline build`). |

### Run the page locally

You don't need a build step to look at the page:

    python -m http.server 8000
    # open http://localhost:8000/

Opening `index.html` directly as a file does not work, because the browser blocks loading `data/` from `file://`.

### Edit the page

All page logic is in the inline `<script>` of `src/template.html`:

- `THEMES`: the choropleth layers, of which you pick one (density, income, house prices, informal housing, murder, burglary, car crime). Each entry names its GeoJSON (`src`), the property to colour by (`field`), the class `breaks`, the colour `ramp` (one more colour than breaks), legend text, credit and popup rows.
- `MODES`: the four transit modes, filtered from `data/transit_routes.geojson` by its `mode` property.
- `OVERLAYS`: the checkboxes (news pins, most-mentioned suburbs, transit modes, stops, police stations, labels). `on:true` marks the ones shown at start.
- The `map.on('load', ...)` block adds the sources and MapLibre layers. The popup code below it formats what a click shows.

After editing, run `python src/build.py` (or `python build_all.py --page-only`), reload the browser, and commit both `src/template.html` and `index.html`.

### Add a layer

1. Put the file in `data/` as GeoJSON in EPSG:4326, with coordinates rounded to 5 decimals, ideally under 5 MB. If a script makes it, put the script under `pipeline/<lane>/`, take its paths from `pipeline.paths`, and add it to `ORDER` in `pipeline/build.py`.
2. For a choropleth, add an entry to `THEMES` (copy an existing one). For points or lines, add a source and a layer in the `map.on('load')` block, plus an entry in `OVERLAYS` with the same `id` as the layer so that its checkbox toggles it.
3. Add the credit to the attribution line in the template and to the list above.

### Rebuild the data

You need Python 3.11+ and `pdftotext` (from poppler). [CONTRIBUTING.md](CONTRIBUTING.md) covers setup.

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python download_data.py --list              # what each lane needs, and what is already on disk
    python download_data.py --lane crime        # fetch one lane (leave out --lane for all)
    python build_all.py --lane crime            # rebuild that lane's files in data/, then index.html

Downloads are cached in `raw/`, so a re-run only fetches what is missing (`--force` re-fetches). Rough sizes and times:

- elevation: 4 DEM tiles, about 110 MB
- demography: 111 ward PDFs and one GHSL tile
- crime: 4 SAPS workbooks (about 45 MB) and one GHSL tile
- transit: 41 PDFs and 123 rail pages, fetched at 1 request/s
- news: about 30 minutes, mostly spent waiting on Google News and GDELT rate limits

Some sources cannot be reproduced byte for byte. The City of Cape Town and OpenStreetMap layers are live and change over time, and Google News search only returns recent items. A rebuild therefore matches the committed files in structure and very closely in values, but not always exactly.

### Refresh the news

The news layer is a snapshot of one month of headlines (19 Oct - 19 Nov 2026). To make a new one:

    export CTM_NEWS_START=2027-01-01 CTM_NEWS_END=2027-01-31
    python download_data.py --lane news --force
    python build_all.py --lane news

Each pin shows a one- or two-sentence summary from `pipeline/news/inputs/article_summaries.csv`. The summaries are written by hand from the headline and keyed by `article_id`. New articles have no summary yet, so their pins show only the headline and the build prints a warning for each one. Add rows to the CSV and rebuild. Also update the window in the page text (`src/template.html`, search for "last month") and in this README.

### Deploy

GitHub Pages serves `main` from the repo root. Push to `main` and the live site updates within a minute or two:

    git add -A && git commit -m "Describe the change" && git push origin main

### Licences and what is not in the repo

- `raw/` is never committed, because some sources allow use but not redistribution.
- The denominator for the crime rates is the **GeoTerraImage 2024 precinct population**. The Western Cape Government publishes it with the note "Data can be viewed but not downloaded". The downloader fetches the per-precinct totals from the WCG server at run time, for your own build only; do not commit or share that file. The published layer carries only the derived totals and rates, plus an open alternative denominator from GHSL (the `*_ghsl` fields).
- City of Cape Town data falls under the City of Cape Town open-data terms of use. Stats SA allows free use with attribution. GHSL is CC BY 4.0 and OSM is ODbL. kaapsetrains.co.za and the MyCiTi timetables state no licence; both are attributed.
