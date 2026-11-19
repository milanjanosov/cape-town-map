"""Map PNG, topics PNG, and web layer export (GeoJSON + news_layers.json) into the repo data/ folder.

Pin summaries come from pipeline/news/inputs/article_summaries.csv (hand-written, 1-2 sentences
paraphrasing the headline). Articles without a summary get an empty one and a warning."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
os.chdir(paths.lane_dir("news"))
import json, re, pandas as pd, numpy as np, geopandas as gpd, matplotlib, matplotlib.pyplot as plt, contextily as cx
from matplotlib.colors import BoundaryNorm, ListedColormap
matplotlib.rcParams["font.family"] = "DejaVu Sans"
summ = pd.read_csv("data/place_summary.csv"); arts = pd.read_csv("data/articles.csv", dtype={"date": str}); pm = pd.read_csv("data/place_mentions.csv", dtype={"date": str})
metro = gpd.read_file(paths.osm_boundary()).to_crs(3857)
pts = gpd.GeoDataFrame(summ, geometry=gpd.points_from_xy(summ.lon, summ.lat), crs=4326).to_crs(3857)
BREAKS = [1, 2, 4, 8, 16, 32, 10000]
RAMP = ["#fde0c5", "#facba6", "#f59e72", "#eb7f5a", "#d14d4d", "#8e1f3d"]
cmap = ListedColormap(RAMP); norm = BoundaryNorm(BREAKS, cmap.N)
fig, ax = plt.subplots(figsize=(10, 12.5), dpi=150)
metro.boundary.plot(ax=ax, color="#555", lw=0.8, zorder=2)
p = pts.sort_values("mentions")
ax.scatter(p.geometry.x, p.geometry.y, s=12 + 22 * np.sqrt(p.mentions) ** 1.6, c=p.mentions, cmap=cmap, norm=norm, edgecolor="#333", lw=0.4, alpha=0.9, zorder=3)
xmin, ymin, xmax, ymax = metro.total_bounds; pad = 3000
ax.set_xlim(xmin - pad, xmax + pad); ax.set_ylim(ymin - pad, ymax + pad)
cx.add_basemap(ax, source=cx.providers.Esri.WorldGrayCanvas, zoom=11, attribution=False)
top = pts.head(15)
placed = []
for _, r in top.iterrows():
    x, y = r.geometry.x, r.geometry.y
    for dx, dy in [(1, 1), (1, -1), (-1, 1), (-1, -1), (1.6, 0), (-1.6, 0), (0, 1.8), (0, -1.8), (2.2, 2), (-2.2, -2)]:
        lx, ly = x + dx * 2200, y + dy * 1500
        if all(abs(lx - a) > 6000 or abs(ly - b) > 1500 for a, b in placed): break
    placed.append((lx, ly))
    ax.annotate(f"{r.place} ({r.mentions})", (x, y), (lx, ly), fontsize=8.5, ha="left" if dx >= 0 else "right", va="center", zorder=5,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85), arrowprops=dict(arrowstyle="-", color="#444", lw=0.5))
ax.set_axis_off()
n_art = len(arts); n_pl = (arts.n_places_in_headline > 0).sum()
ax.set_title(f"Which Cape Town places made the headlines\n{paths.news_window_label()}", fontsize=15, loc="left", fontweight="bold")
for v in [1, 4, 16, 32]:
    ax.scatter([], [], s=12 + 22 * np.sqrt(v) ** 1.6, color=cmap(norm(v)), edgecolor="#333", lw=0.4, label=f"{v}")
ax.legend(title="Headlines naming the place", loc="lower right", frameon=True, labelspacing=1.4, borderpad=1, fontsize=8, title_fontsize=8.5)
fig.text(0.02, 0.015, f"{n_art:,} unique headlines (GDELT, Google News RSS, outlet RSS); {n_pl:,} name at least one suburb. Places matched in headlines against OSM suburbs within the\nCity of Cape Town; bare 'Cape Town' mentions not counted. Top 15 labelled. Basemap: Esri World Gray Canvas. Places: OpenStreetMap contributors. Map: New Science of Maps.", fontsize=7, color="#444")
plt.savefig("out/capetown_news_mentions_map.png", bbox_inches="tight"); plt.close()

# ---- topics figure: stacked horizontal bars for top 15
TOP = ["crime", "transport", "housing", "tourism/events", "weather/fire", "politics", "business", "other"]
TCOL = ["#c0392b", "#2e86c1", "#8e6c3a", "#27ae60", "#e67e22", "#7d3c98", "#566573", "#d5d8dc"]
t15 = summ.head(15).iloc[::-1]
fig, ax = plt.subplots(figsize=(10, 7), dpi=150)
left = np.zeros(len(t15))
for t, c in zip(TOP, TCOL):
    v = t15["topic_" + re.sub(r"\W", "_", t)].values
    ax.barh(t15.place, v, left=left, color=c, label=t, edgecolor="white", lw=0.5); left += v
for i, (_, r) in enumerate(t15.iterrows()):
    ax.text(r.mentions + 0.3, i, f"{r.mentions}   top topic: {r.dominant_topic} ({r['topic_' + re.sub(chr(92) + 'W', '_', r.dominant_topic)]})", va="center", fontsize=8.5)
ax.set_xlim(0, t15.mentions.max() * 1.45)
ax.spines[["top", "right"]].set_visible(False); ax.set_xlabel("Headlines naming the place")
ax.legend(ncol=8, loc="upper left", bbox_to_anchor=(0, -0.08), fontsize=8, frameon=False, handlelength=1)
ax.set_title("What the headlines said about the 15 most-named places", loc="left", fontsize=13, fontweight="bold")
fig.text(0.01, -0.06, f"Topic = keyword rule on the headline (most keyword hits wins; ties go to the earlier topic in the legend order; no hit = other).\nDominant topic ignores 'other'. {paths.news_window_label()}.", fontsize=7, color="#444")
plt.savefig("out/capetown_news_topics.png", bbox_inches="tight"); plt.close()
t15.iloc[::-1][["place", "mentions", "dominant_topic", "dominant_share"] + ["topic_" + re.sub(r"\W", "_", t) for t in TOP]].to_csv("out/capetown_news_top15_topics.csv", index=False)

# ---- web export
import os
WEBD = str(paths.DATA)
pm = pm.merge(arts[["article_id", "url"]], on="article_id", how="left")
feats = []
for _, r in summ.iterrows():
    g = pm[pm.place == r.place].sort_values("date", ascending=False).head(5)
    heads = [dict(title=h.title, outlet=h.outlet, date=f"{h.date[:4]}-{h.date[4:6]}-{h.date[6:]}", url=h.url) for h in g.itertuples()]
    props = dict(place=r.place, mentions=int(r.mentions), dominant_topic=r.dominant_topic, dominant_share=float(r.dominant_share),
                 dominant_topic_label=f"{r.dominant_topic} ({int(round(r.dominant_share*100))}% of headlines)",
                 **{k: int(r[k]) for k in summ.columns if k.startswith("topic_")},
                 headlines=heads,
                 osm_id=r.osm_id, osm_place_type=r.osm_place_type, match_tier=r.tier)
    feats.append(dict(type="Feature", geometry=dict(type="Point", coordinates=[round(r.lon, 5), round(r.lat, 5)]), properties=props))
json.dump(dict(type="FeatureCollection", features=feats), open(f"{WEBD}/news_mentions.geojson", "w"), ensure_ascii=False)
side = {"lane": "news", "files": [{
  "file": "news_mentions.geojson", "title": "In the news: places named in headlines", "geometry_type": "Point",
  "color_by": "mentions", "size_by": "mentions", "color_ramp": RAMP, "class_breaks": BREAKS[:-1], "units": "headlines",
  "legend_text": f"Number of unique news headlines ({paths.news_window_label()}) that name the suburb. Generic 'Cape Town' mentions are not counted.",
  "alt_color_by": {"property": "dominant_topic", "categories": dict(zip(TOP, TCOL))},
  "popup_fields": {"place": "Place", "mentions": "Headlines naming it", "dominant_topic_label": "Most common topic",
                   "topic_crime": "Crime", "topic_transport": "Transport", "topic_housing": "Housing", "topic_tourism_events": "Tourism / events",
                   "topic_weather_fire": "Weather / fire", "topic_politics": "Politics", "topic_business": "Business", "topic_other": "Other",
                   "headlines": "Recent headlines (array of {title, outlet, date, url})"},
  "headlines_property_note": "headlines is an array of up to 5 most recent {title, outlet, date, url}; titles only, no article text.",
  "source": "GDELT DOC 2.0 API, Google News RSS search, outlet RSS feeds; places from OpenStreetMap place=suburb/neighbourhood/etc. within the City of Cape Town (ODbL).",
  "licence": "Headlines are quoted as titles with links only; place points (c) OpenStreetMap contributors, ODbL.",
  "vintage": f"News {paths.news_window_label()}, collected {paths.NEWS_END.day} {paths.NEWS_END:%b %Y}; OSM extract at collection time.",
  "caveats": "Headline-only matching; news over-represents crime, the CBD and the Atlantic seaboard; Google News search coverage thins for older dates."}]}
json.dump(side, open(f"{WEBD}/news_layers.json", "w"), indent=1, ensure_ascii=False)

# ---- per-article pins: one Point per article-place pair, jittered 80-150 m around the suburb point
import hashlib, math, html
summ_txt = pd.read_csv(paths.inputs("news") / "article_summaries.csv")
gz = pd.read_csv("data/gazetteer.csv").set_index("place")
A = arts.set_index("article_id")
TC = dict(zip(TOP, TCOL))
pins = []
for r in pm.itertuples():
    a = A.loc[r.article_id]; srow = summ_txt[summ_txt.article_id == r.article_id]
    if srow.empty:  # new article (news refreshed): no hand-written summary yet
        print(f"WARNING no summary for {r.article_id}: {a.title[:70]}")
        srow = pd.DataFrame([dict(summary="", basis="none")])
    h = int(hashlib.md5(f"{r.article_id}{r.place}".encode()).hexdigest(), 16)
    ang = (h % 3600) / 3600 * 2 * math.pi; rad = 80 + (h // 3600) % 71  # metres, 80-150
    lat0, lon0 = gz.loc[r.place, "lat"], gz.loc[r.place, "lon"]
    lat = lat0 + rad * math.sin(ang) / 111320; lon = lon0 + rad * math.cos(ang) / (111320 * math.cos(math.radians(lat0)))
    d = f"{r.date[:4]}-{r.date[4:6]}-{r.date[6:]}"
    pins.append(dict(type="Feature", geometry=dict(type="Point", coordinates=[round(lon, 5), round(lat, 5)]), properties=dict(
        article_id=r.article_id, title=a.title, url=a.url, outlet=a.outlet, date=d, outlet_date=f"{a.outlet}, {d}",
        summary=srow.summary.iloc[0], summary_basis=srow.basis.iloc[0], topic=a.topic, topic_color=TC[a.topic], place=r.place,
        url_is_google_redirect=bool(a.url_is_google_redirect), jitter_m=int(rad))))
json.dump(dict(type="FeatureCollection", features=pins), open(f"{WEBD}/news_articles.geojson", "w"), ensure_ascii=False)
side["files"].insert(0, {
  "file": "news_articles.geojson", "title": "In the news: one pin per article", "geometry_type": "Point",
  "color_by": "topic", "categories": TC, "units": "article",
  "legend_text": f"Each pin is one news article ({paths.news_window_label()}) whose headline names a Cape Town suburb, placed at that suburb's OSM point and spread 80-150 m so pins do not stack. Colour = topic from a headline keyword rule.",
  "popup_fields": {"title": "Headline (link it to url)", "outlet_date": "Outlet, date", "summary": "Summary", "topic": "Topic"},
  "link_field": "url",
  "notes": "summary is 1-2 sentences written from the headline only (summary_basis='headline') or headline plus the outlet's RSS description ('headline+snippet'); it adds nothing beyond those. url is the publisher URL where we had one (outlet RSS or GDELT); url_is_google_redirect=true marks Google News links, which open the article in a browser via Google's redirect. An article naming two suburbs has two pins.",
  "source": side["files"][0]["source"], "licence": side["files"][0]["licence"], "vintage": side["files"][0]["vintage"], "caveats": side["files"][0]["caveats"]})
json.dump(side, open(f"{WEBD}/news_layers.json", "w"), indent=1, ensure_ascii=False)
for f in ["news_mentions.geojson", "news_articles.geojson"]: print(f, round(os.path.getsize(f"{WEBD}/" + f) / 1e6, 2), "MB")
print("pins", len(pins), "places", len(feats))
