"""Google News RSS: (a) per-place searches "<place>" "Cape Town", (b) weekly broad/topic/outlet searches.
Window enforced with after:/before:. Headline, link, date, outlet only."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
os.chdir(paths.lane_dir("news"))
import csv, time, requests, urllib.parse, datetime as dt, xml.etree.ElementTree as ET, email.utils, pandas as pd, sys
UA = paths.UA
AFTER, BEFORE = str(paths.NEWS_START), str(paths.NEWS_END + dt.timedelta(days=1))
def fetch(q, tag):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "en-ZA", "gl": "ZA", "ceid": "ZA:en"})
    for attempt in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200: break
        except Exception: pass
        time.sleep(20 * (attempt + 1))
    else:
        print("FAIL", q, flush=True); return []
    out = []
    for it in ET.fromstring(r.content).findall(".//item"):
        title = it.findtext("title") or ""; src = it.find("source")
        outlet = src.text if src is not None else ""; outlet_url = src.get("url") if src is not None else ""
        if outlet and title.endswith(" - " + outlet): title = title[: -len(outlet) - 3]
        try: d = email.utils.parsedate_to_datetime(it.findtext("pubDate")).strftime("%Y%m%d")
        except Exception: d = ""
        out.append(dict(source="gnews", query=tag, title=title.strip(), url=it.findtext("link") or "", date=d, outlet=outlet, outlet_url=outlet_url))
    return out
rows = []
gz = pd.read_csv("data/gazetteer.csv")
# (b) broad searches, weekly windows to get under the 100-item cap
broad = ['"Cape Town"', '"Cape Town" crime', '"Cape Town" police', '"Cape Town" shooting', '"Cape Town" taxi', '"Cape Town" MyCiTi OR Metrorail OR traffic',
         '"Cape Town" housing OR land OR informal settlement', '"Cape Town" tourism OR festival OR event', '"Cape Town" fire OR storm OR flood OR weather',
         '"Cape Town" council OR mayor OR ANC OR DA', '"Cape Town" business OR property OR investment', '"Cape Town" school OR hospital',
         '"Cape Town" site:news24.com', '"Cape Town" site:iol.co.za', '"Cape Town" site:groundup.org.za', '"Cape Town" site:dailymaverick.co.za',
         '"Cape Town" site:ewn.co.za', '"Cape Town" site:timeslive.co.za', 'site:capetownetc.com', '"Cape Town" site:capeargus.co.za OR site:capetimes.co.za']
d0 = paths.NEWS_START
n_weeks = -(-((paths.NEWS_END - paths.NEWS_START).days + 1) // 7)
for q in broad:
    for k in range(n_weeks):
        a = d0 + dt.timedelta(days=7 * k); b = min(a + dt.timedelta(days=7), paths.NEWS_END + dt.timedelta(days=1))
        res = fetch(f"{q} after:{a} before:{b}", "broad:" + q); rows += res
        print(q, a, len(res), flush=True); time.sleep(2)
# (a) per-place searches
for i, p in enumerate(gz["place"]):
    res = fetch(f'"{p}" "Cape Town" after:{AFTER} before:{BEFORE}', "place:" + p); rows += res
    if i % 25 == 0: print(i, p, len(res), len(rows), flush=True)
    time.sleep(1.5)
with open("tmp/raw/gnews.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print("total", len(rows))
