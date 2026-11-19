"""Assemble the deployed index.html (repo root) from src/template.html with the MapLibre CSS inlined.

Edit src/template.html, never index.html directly: index.html is overwritten by this script.
Run: python src/build.py   (or python build_all.py --page-only)
"""
from pathlib import Path

H = Path(__file__).resolve().parent
css = (H / "maplibre-gl.css").read_text()
out = H.parent / "index.html"
out.write_text((H / "template.html").read_text().replace("/*MLCSS*/", css))
print("index.html", out.stat().st_size)
