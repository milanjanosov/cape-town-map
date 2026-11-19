# Contributing

The short version is in README.md under "How to change the map". This file covers setup and how the pipeline is laid out.

## Setup

Python 3.11, 3.12 or 3.13 (the data was built on 3.12).

    python -m venv .venv
    source .venv/bin/activate          # Windows: .venv\Scripts\activate
    pip install -r requirements.txt

`rasterio`, `pyogrio` and `pyproj` ship wheels with GDAL and PROJ bundled, so pip needs no system GDAL. If pip starts compiling GDAL, there is no wheel for your Python version. Use 3.12, or conda:

    conda create -n capetown -c conda-forge python=3.12 geopandas rasterio contextily openpyxl requests poppler
    conda activate capetown

On a python.org install of Python on macOS, run its `Install Certificates.command` once, or HTTPS downloads fail with CERTIFICATE_VERIFY_FAILED.

Two lanes call `pdftotext`, which comes from poppler and is not a Python package: `brew install poppler` on macOS, `apt install poppler-utils` on Debian/Ubuntu.

## Pipeline layout

    pipeline/
      paths.py            every path and setting (env overrides: CTM_RAW, CTM_DATA, CTM_USER_AGENT,
                          CTM_NEWS_START, CTM_NEWS_END, CTM_TERRAIN_ZMAX)
      download.py         all downloads, per lane, cached in raw/<lane>/data/
      build.py            the run order per lane
      elevation/          build_web.py -> check_web.py (check image only)
      demography/         parse_ward_profiles_2011.py -> build.py -> maps.py -> export_web.py
      crime/              parse_saps_quarter.py (x4) -> precinct_population.py -> build_tables.py
                          -> make_maps.py (check images) -> export_web.py
      transit/            scrape_rail_times.py -> parse_myciti.py -> build_layers.py -> make_maps.py
                          -> write_sidecar.py
      news/               01 gazetteer -> 02 RSS/GDELT -> 03 gazetteer -> 04 Google News   (download)
                          03 -> 05_extract.py -> 06_plots_and_web.py                         (build)

Every script can also be run on its own, from any folder, for example `python pipeline/crime/build_tables.py`. Scripts read and write their lane's work folder `raw/<lane>/` (its `data/`, `out/` and `tmp/`) and write web layers to `data/`. The scripts print their checks as they go (sums against published totals, join counts). Read that output when something changes.

`raw/<lane>/out/` gets the stand-alone PNG maps that check the layers. Pass `--no-maps` to skip them. The transit and news maps fetch Esri basemap tiles, so they need a network connection.

## Hand-curated inputs (committed)

- `pipeline/elevation/inputs/labels_verified.csv`: label positions. Nominatim got two of them wrong (Bellville, Maclear's Beacon), and they were fixed by hand. `geocode.py` is the one-off lookup that produced `labels_nominatim.csv`.
- `pipeline/crime/inputs/neighbourhood_labels.json`: neighbourhood label points. Five were re-picked by hand to OSM place objects. `geocode_labels.py` made the first version.
- `pipeline/news/inputs/article_summaries.csv`: one hand-written summary per pinned article.

## Not included

- The transit lane's `gtfs_check.py` (it depends on a separate private project) and the elevation lane's `peaks_check.py` (it reads a reprojected DEM that was made by hand). Both are diagnostics only, and neither feeds the map.
- Raw data of any kind. See the licence notes in README.md, especially the GeoTerraImage population, which may be viewed but not redistributed.

## Before you push

- Run the lane you changed: `python build_all.py --lane <lane>`. Check the printed numbers, then look at the page locally.
- `git status`: nothing under `raw/` should show up (it is in `.gitignore`).
- Keep `data/` files small. The page downloads them all on load.
- Pushing to `main` deploys immediately.
