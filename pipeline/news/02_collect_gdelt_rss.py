"""Collect GDELT DOC 2.0 artlist (4-day windows) + local outlet RSS. Headlines/URLs/dates/outlets only.

Usage: 02_collect_gdelt_rss.py rss   -> tmp/raw/rss.csv
       02_collect_gdelt_rss.py gdelt -> tmp/raw/gdelt.csv   (slow: GDELT rate-limits hard)
Window: paths.NEWS_START .. paths.NEWS_END (env CTM_NEWS_START / CTM_NEWS_END)."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
os.chdir(paths.lane_dir("news"))
import re, sys, json, time, pandas as pd, requests, datetime as dt, xml.etree.ElementTree as ET, csv, os
UA = paths.UA
os.makedirs("tmp/raw", exist_ok=True)
rows = []
start = dt.datetime.combine(paths.NEWS_START, dt.time()); end = dt.datetime.combine(paths.NEWS_END + dt.timedelta(days=1), dt.time())
QUERIES = ['"Cape Town" sourcecountry:SF sourcelang:english']  # a second, worldwide query was dropped: GDELT rate-limited this IP (HTTP 429) for most of the run
MODE = sys.argv[1] if len(sys.argv) > 1 else 'all'
for q in (QUERIES if MODE in ('all', 'gdelt') else []):
    t = start
    while t < end:
        t2 = min(t + dt.timedelta(days=4), end)
        params = dict(query=q, mode="artlist", maxrecords=250, format="json", sort="datedesc",
                      startdatetime=t.strftime("%Y%m%d%H%M%S"), enddatetime=t2.strftime("%Y%m%d%H%M%S"))
        js = None
        for attempt in range(8):
            time.sleep(20 if attempt == 0 else 45)
            try:
                r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, headers=UA, timeout=60)
                js = r.json() if r.text.strip().startswith("{") else None
            except Exception as e:
                js = None
            if js is not None: break
        arts = (js or {}).get("articles", [])
        print(q[:30], t.date(), len(arts), flush=True)
        for a in arts:
            rows.append(dict(source="gdelt", query=q, title=a.get("title",""), url=a.get("url",""),
                             date=a.get("seendate","")[:8], outlet=a.get("domain",""), country=a.get("sourcecountry",""), snippet=""))
        t = t2
        if rows: pd.DataFrame(rows).to_csv('tmp/raw/gdelt.csv', index=False)  # incremental save
FEEDS = {
 "news24": "https://feeds.news24.com/articles/news24/SouthAfrica/rss",
 "news24_topstories": "https://feeds.news24.com/articles/news24/TopStories/rss",
 "iol": "https://iol.co.za/rss/iol/news",
 "iol_capeargus": "https://iol.co.za/rss/iol/capeargus",
 "groundup": "https://groundup.org.za/sitenews/rss/",
 "dailymaverick": "https://www.dailymaverick.co.za/dmrss/",
 "ewn": "https://ewn.co.za/RSS%20Feeds/Latest%20News",
 "timeslive": "https://www.timeslive.co.za/rss/",
 "capetownetc": "https://www.capetownetc.com/feed/",
 "sabcnews": "https://www.sabcnews.com/sabcnews/feed/",
}
status = {}
for name, url in (FEEDS.items() if MODE in ('all', 'rss') else []):
    time.sleep(2)
    try:
        r = requests.get(url, headers=UA, timeout=30)
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        n = 0
        for it in items:
            g = lambda tag: (it.findtext(tag) or "").strip()
            pd = g("pubDate")
            try:
                d = dt.datetime.strptime(pd[5:16], "%d %b %Y").strftime("%Y%m%d")
            except Exception:
                d = pd
            rows.append(dict(source="rss:"+name, query="", title=g("title"), url=g("link"), date=d, outlet=name.split("_")[0], country="SF", snippet=re.sub(r"<[^>]+>", " ", g("description"))[:400]))
            n += 1
        status[name] = f"ok {n} items"
    except Exception as e:
        status[name] = f"fail {type(e).__name__} http={getattr(locals().get('r'),'status_code',None)}"
    print(name, status[name], flush=True)
if status: json.dump(status, open("tmp/rss_status.json", "w"), indent=1)
with open(f"tmp/raw/{MODE}.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("total rows", len(rows))
