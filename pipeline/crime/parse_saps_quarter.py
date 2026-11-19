"""Extract monthly station x category counts for the latest year from a SAPS
quarterly crime-stats workbook ('RAW Data' sheet). Writes a tidy CSV of all
stations (national) for that quarter: station, district, province, category,
month, count."""
import sys, datetime, openpyxl, pandas as pd
src, out = sys.argv[1], sys.argv[2]
ws = openpyxl.load_workbook(src, read_only=True, data_only=True)["RAW Data"]
rows = ws.iter_rows(values_only=True)
hdr = None
for r in rows:
    if r and r[4] == "Station":
        hdr = r; break
months = [(i, c) for i, c in enumerate(hdr) if isinstance(c, datetime.datetime)]
latest = max(c.year * 100 + c.month for _, c in months)
# take the latest three months (one quarter)
months = sorted(months, key=lambda t: t[1])[-3:]
print("months:", [c.strftime("%Y-%m") for _, c in months])
rec = []
for r in rows:
    if not r or r[2] != "Station" or r[4] is None:
        continue
    for i, c in months:
        rec.append((r[4].strip(), r[5], r[6], str(r[7]).strip(), r[8], c.strftime("%Y-%m"), r[i] or 0))
df = pd.DataFrame(rec, columns=["station", "district", "province", "category", "code", "month", "count"])
df.to_csv(out, index=False)
print(out, len(df), "rows;", df.station.nunique(), "stations;", df.category.nunique(), "categories")
