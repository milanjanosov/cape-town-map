"""Merge sources -> data/articles.csv; headline place matching -> data/place_mentions.csv; topic rule; per-place summary."""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
os.chdir(paths.lane_dir("news"))
import re, pandas as pd, numpy as np, glob, os
raw = []
for f in ["tmp/raw/rss.csv", "tmp/raw/gdelt.csv", "tmp/raw/gnews.csv"]:
    if os.path.exists(f): raw.append(pd.read_csv(f, dtype=str).fillna(""))
df = pd.concat(raw, ignore_index=True)
n_raw = len(df)
df["date"] = df["date"].str[:8]
df = df[(df["date"] >= paths.NEWS_START.strftime("%Y%m%d")) & (df["date"] <= paths.NEWS_END.strftime("%Y%m%d"))]
n_window = len(df)
df["title"] = df["title"].str.replace(r"\s+", " ", regex=True).str.strip()
# strip trailing outlet tags such as " | DistrictMail & Helderberg Gazette" or " - LNN - Network News"
SUFFIX = r"(\s+[|\-–]\s+[^|]{0,60}(Gazette|News|Mail|Times|Argus|Herald|Tatler|Bulletin|Vision|Weekly|Express|Echo|Voice|IOL|News24|LNN|Daily Maverick|GroundUp|SABC|EWN|TimesLIVE|CapeTownETC|Sowetan|Citizen|Post|Atlantic Sun|Plainsman|Sentinel|Chronicle)[^|]{0,30})+$"
SUFFIX2 = r"\s+\|\s+(?:\S+\s?){1,4}$"  # any short trailing ' | Tag' (outlet or section names, e.g. TygerBurger)
for _ in range(2): df["title"] = df["title"].str.replace(SUFFIX2, "", regex=True).str.strip()
for _ in range(2): df["title"] = df["title"].str.replace(SUFFIX, "", regex=True).str.strip()
df = df[df["title"].str.len() > 15]
# outlet normalisation
def norm_outlet(o0):
    o = o0.lower()
    for k, v in [("news24", "News24"), ("iol", "IOL"), ("groundup", "GroundUp"), ("dailymaverick", "Daily Maverick"), ("daily maverick", "Daily Maverick"),
                 ("ewn", "EWN"), ("eyewitness", "EWN"), ("timeslive", "TimesLIVE"), ("capetownetc", "CapeTownETC"), ("cape town etc", "CapeTownETC"),
                 ("cape argus", "Cape Argus"), ("capeargus", "Cape Argus"), ("cape times", "Cape Times"), ("capetimes", "Cape Times"), ("sabc", "SABC News")]:
        if k in o: return v
    return re.sub(r"^https?://|/$", "", o0.strip()).replace("www.", "")
df["outlet"] = df["outlet"].map(norm_outlet)
df["title_key"] = df["title"].str.lower().str.replace(r"[^a-z0-9 ]", "", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
# keep the queries that found each story (needed for the ambiguity rule), then dedupe by headline
qs = df.groupby("title_key")["query"].apply(lambda s: "|".join(sorted(set(x for x in s if x))))
srcs = df.groupby("title_key")["source"].apply(lambda s: "|".join(sorted(set(s))))
nout = df.groupby("title_key")["outlet"].nunique()
if "snippet" not in df: df["snippet"] = ""
df["snippet"] = df["snippet"].fillna("")
snip = df.groupby("title_key")["snippet"].agg(lambda s: max(s, key=len))
# prefer an original publisher URL (RSS/GDELT) over a Google News redirect when the same headline came from both
orig = df[~df["url"].str.contains("news.google.com", na=False)].groupby("title_key")["url"].first()
df = df.sort_values(["title_key", "source"]).drop_duplicates("title_key").copy()
df["queries"] = df["title_key"].map(qs); df["sources"] = df["title_key"].map(srcs); df["n_outlets_same_headline"] = df["title_key"].map(nout)
df["snippet"] = df["title_key"].map(snip)
df["url"] = df["title_key"].map(orig).fillna(df["url"])
df["url_is_google_redirect"] = df["url"].str.contains("news.google.com", na=False)
df = df.sort_values("date", ascending=False).reset_index(drop=True)
import hashlib
df["article_id"] = ["a" + hashlib.md5(k.encode()).hexdigest()[:10] for k in df["title_key"]]  # stable across reruns

# ---- topic rule: keyword hits in the headline; most hits wins; tie -> earlier in this list; zero hits -> other
TOPICS = {
 "crime": r"\b(murder|murders|murdered|killed|killing|killings|shooting|shootings|shot dead|gunman|gunmen|gunfire|guns?|firearms?|gangs?|gang-related|stabbed|stabbing|robbery|robberies|robbed|hijack\w*|arrested|arrests?|police|saps|crime|crimes|criminal|suspects?|accused|sentenced|rape|raped|assault\w*|drugs?|extortion|bodies|body found|theft|stolen|burglar\w*|kidnap\w*|abduct\w*|mandrax|anti-gang|vigilante\w*|violence|violent|dna|inquest|murder accused)\b",
 "transport": r"\b(taxis?|taxi rank|myciti|bus|buses|metrorail|trains?|rail|railway|prasa|traffic|roads?|roadworks|n1|n2|m3|m5|highway|expressway|intersection|airport|flights?|airlines?|transnet|cyclists?|commuters?|crash|crashes|collision|golden arrow|e-hailing|uber)\b",
 "housing": r"\b(housing|houses|homes|homeowners?|evict\w*|evictions?|informal settlements?|shacks?|rent|rental|rentals|tenants?|land invasion|occupation|occupiers|backyarders?|social housing|densification|gentrification|homeless\w*|affordable|apartments?|retirement village|demolition\w*|demolish\w*|resettled)\b",
 "tourism/events": r"\b(tourism|tourists?|festivals?|concerts?|events?|marathon|beach|beaches|beachfront|restaurants?|wine|hotels?|visitors?|cruise|music|exhibition|theatre|comedy|jazz|stadium|test match|test cricket|proteas|springboks?|stormers|blitzboks?|sevens|rugby|cricket|league|holiday\w*|travel|whales?|penguins?|sharks?|hikers?|hiking|table mountain|christmas market\w*|market day|racing|racecourse|showcase|lights|football|soccer|netball|athletics|fun run|fundraising run|sport|sports)\b",
 "weather/fire": r"\b(fire|fires|blaze|wildfires?|veld fire|firefighters?|floods?|flooding|storms?|rain|rainfall|wind|winds|windy|weather|heatwave|heat|drought|dams?|snow|cold front|swells?|water restrictions?|water|day zero|load.?shedding|outages?|power cuts?|electricity|interruptions?)\b",
 "politics": r"\b(mayor|council|councillors?|minister|ministers|government|parliament|elections?|by-elections?|vote|votes|voting|voters?|ballots?|wards?|party|parties|premier|municipal|municipality|city of cape town|budget|protests?|marches|march|policy|province|provincial|independence|referendum|coalition|hill-lewis|winde|ramaphosa|lge)\b",
 "business": r"\b(business|businesses|company|companies|invest\w*|economy|economic|jobs?|job seekers|startups?|property|properties|prices?|retail|retailers?|mall|shops?|shopping|banks?|rand|sales?|billion|r\d+(\.\d+)?bn|tech|offices?|employment|unemployment|industry|industrial|trade|exports?|growth|construction|acquisition|developer|development|trading|traders|informal trad\w*)\b",
}
ACRONYM_POLITICS = re.compile(r"\b(ANC|DA|EFF|GNU|PA|GOOD|IFP|FF\+|ActionSA)\b")  # case-sensitive so 'Da Gama' etc. do not count
TOPIC_ORDER = list(TOPICS)
TRE = {k: re.compile(v, re.I) for k, v in TOPICS.items()}
def topic(t):
    t = re.sub(r"\b(comes?|came|coming) under fire\b|\bopen(ed|s)? fire\b", " shooting ", t, flags=re.I)  # gunfire, not fire
    hits = {k: len(r.findall(t)) for k, r in TRE.items()}
    hits["politics"] += len(ACRONYM_POLITICS.findall(t))
    best = max(hits.values())
    if best == 0: return "other"
    return next(k for k in TOPIC_ORDER if hits[k] == best)
_gz = pd.read_csv("data/gazetteer.csv")
_al = sorted({a for s in _gz["aliases"] for a in s.split("|")}, key=len, reverse=True)
ALIAS_RE = re.compile(r"(?<![A-Za-z])(" + "|".join(re.escape(a) for a in _al) + r")(?![A-Za-z])")
df["topic"] = df["title"].map(lambda t: topic(ALIAS_RE.sub(" ", t)))  # place names removed first, so 'N1 City' is not transport

# ---- place matching
gz = pd.read_csv("data/gazetteer.csv")
CUE = re.compile(r"Cape Town|Kaapstad|Western Cape|\bWC\b|Capetonian|Cape Flats|Cape Peninsula|Atlantic Seaboard|Southern Suburbs|Northern Suburbs|West Coast", re.I)
FOREIGN = {"Harare", "Delft", "Atlantis", "Constantia", "Nyanga", "Strand", "Gardens", "City Centre", "V&A Waterfront", "Observatory", "Woodstock", "Langa", "Crossroads", "Capri", "Sun Valley", "Eden Park", "Witsand", "Belmont Park", "Stellenberg"}
pats = []
for _, r in gz.iterrows():
    for a in r["aliases"].split("|"):
        pats.append((a, r["place"], r["tier"]))
pats.sort(key=lambda x: -len(x[0]))  # longest first, so "Bellville South" beats "Bellville"
def match(title, queries):
    taken = np.zeros(len(title) + 1, bool); found = []
    for alias, place, tier in pats:
        for m in re.finditer(r"(?<![A-Za-z])" + re.escape(alias) + r"(?![A-Za-z])", title):
            if taken[m.start():m.end()].any(): continue
            # all-caps headline words and lowercase are not matched (case-sensitive); also skip "Constantia Kloof" (Johannesburg)
            if alias == "Constantia" and title[m.end():m.end() + 6] == " Kloof": continue
            if alias == "Woodstock" and re.search(r"festival|1969|New York|Vermont", title, re.I): continue
            taken[m.start():m.end()] = True; found.append((place, tier, alias))
    out = []
    a_places = [p for p, t, _ in found if t == "A"]
    cue = bool(CUE.search(title)) or len(a_places) > 0
    for place, tier, alias in found:
        if tier == "A": rule = "unambiguous"
        elif cue and (len(a_places) > 0 or CUE.search(title)): rule = "ambiguous+headline_cue"
        elif place not in FOREIGN and ("place:" + place) in queries: rule = "ambiguous+place_query"
        else: continue
        out.append(dict(place=place, alias_matched=alias, tier=tier, rule=rule))
    return out
pm = []
for _, r in df.iterrows():
    for m in match(r["title"], r["queries"]):
        pm.append(dict(article_id=r["article_id"], **m, date=r["date"], topic=r["topic"], outlet=r["outlet"], title=r["title"]))
pm = pd.DataFrame(pm).drop_duplicates(["article_id", "place"])
pm.to_csv("data/place_mentions.csv", index=False)
df["n_places_in_headline"] = df["article_id"].map(pm.groupby("article_id").size()).fillna(0).astype(int)
df["mentions_cape_town"] = df["title"].str.contains("Cape Town", case=False)
df[["article_id", "date", "outlet", "title", "url", "topic", "n_places_in_headline", "mentions_cape_town", "sources", "queries", "n_outlets_same_headline", "url_is_google_redirect"]].to_csv("data/articles.csv", index=False)
df[["article_id", "title_key", "title", "outlet", "snippet"]].to_csv("tmp/article_snippets.csv", index=False)  # descriptions kept local only, for writing summaries

# ---- per-place summary
summ = []
for p, g in pm.groupby("place"):
    tc = g["topic"].value_counts()
    tc_nonother = tc.drop("other", errors="ignore")
    dom = tc_nonother.index[0] if len(tc_nonother) else "other"
    if len(tc_nonother) > 1 and tc_nonother.iloc[0] == tc_nonother.iloc[1]:
        dom = next(t for t in TOPIC_ORDER if t in tc_nonother.index and tc_nonother[t] == tc_nonother.iloc[0])
    row = dict(place=p, mentions=len(g), dominant_topic=dom, dominant_share=round(tc.get(dom, 0) / len(g), 2))
    for t in TOPIC_ORDER + ["other"]: row["topic_" + re.sub(r"\W", "_", t)] = int(tc.get(t, 0))
    summ.append(row)
summ = pd.DataFrame(summ).merge(gz[["place", "lat", "lon", "osm_id", "osm_place_type", "tier"]], on="place").sort_values("mentions", ascending=False)
summ.to_csv("data/place_summary.csv", index=False)
print(f"raw rows {n_raw}, in window {n_window}, unique headlines {len(df)}")
print("articles with >=1 place:", (df.n_places_in_headline > 0).sum(), " places hit:", len(summ))
print(df.groupby("sources").size().sort_values().tail(8))
print(df.topic.value_counts())
print(summ.head(25)[["place", "mentions", "dominant_topic", "dominant_share"]].to_string())
print(pm.rule.value_counts())
