"""Parse the City of Cape Town 2011 Census ward profiles (111 PDFs) into one CSV.

Source PDFs: data/raw/ward_profiles_2011/2011_Census_CT_Ward_NNN_Profile.pdf
(City of Cape Town, Jan 2013, Census 2011 data supplied by Stats SA).
Only the "Total" column of each table is kept. Every section is checked:
the category counts must add up to the table's own Total row.
"""
import os, sys  # noqa: E401  (repo paths: see pipeline/paths.py)
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
import csv, re, subprocess, sys
from pathlib import Path

ROOT = paths.lane_dir("demography")
PDF_DIR = ROOT / "data" / "raw" / "ward_profiles_2011"
OUT = ROOT / "data" / "ward_census2011.csv"

NUM = r"\d{1,3}(?: \d{3})*"
ROW_END = re.compile(rf"({NUM})\s+(\d+\.\d+)%\s*$")

SECTIONS = {
    # key: (header regex, category names in table order, excluding Total)
    "popgroup": (r"^\s*Population\s+Num\s+%", ["black_african", "coloured", "asian", "white", "other"]),
    "income": (r"^\s*Income\s+Num", ["no_income", "r1_1600", "r1601_3200", "r3201_6400", "r6401_12800",
                                      "r12801_25600", "r25601_51200", "r51201_102400", "r102401_plus", "unspecified"]),
    "dwelling": (r"Type of Dwelling", ["formal", "informal_backyard", "informal_not_backyard", "other"]),
}


def num(s):
    return int(s.replace(" ", ""))


def section_totals(lines, header_re, n_cats):
    start = next(i for i, l in enumerate(lines) if re.search(header_re, l))
    vals = []
    for l in lines[start + 1:]:
        m = ROW_END.search(l)
        if not m:
            continue
        vals.append(num(m.group(1)))
        if l.strip().startswith("Total"):
            break
    if len(vals) != n_cats + 1:
        raise ValueError(f"expected {n_cats + 1} rows, got {len(vals)}: {vals}")
    return vals[:-1], vals[-1]


def labour(lines, label):
    for l in lines:
        if l.strip().startswith(label) and re.search(r"\d$", l.strip()):
            return num(re.split(r"\s{2,}", l.strip())[-1])
    raise ValueError(label)


def parse(pdf):
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    lines = txt.splitlines()
    ward = int(re.search(r"Ward_(\d{3})", pdf.name).group(1))
    flat = re.sub(r"\s+", " ", txt)
    row = {"ward": ward,
           "pop_official": num(re.search(r"population of Ward \d+ was (\d+(?: \d{3})*)", flat).group(1)),
           "hh_official": num(re.search(r"number of households was (\d+(?: \d{3})*)", flat).group(1))}
    desc = re.search(r"Ward \d{3} includes the areas? of (.*?)\s*1\s*Ward \d{3} Overview", flat)
    row["areas"] = desc.group(1).strip() if desc else ""
    problems = []
    for key, (hdr, cats) in SECTIONS.items():
        vals, total = section_totals(lines, hdr, len(cats))
        if sum(vals) != total:
            problems.append(f"{key}: sum {sum(vals)} != total {total}")
        for c, v in zip(cats, vals):
            row[f"{key}_{c}"] = v
        row[f"{key}_total"] = total
    for lab, col in [("Population aged 15 to 64 years", "pop_15_64"), ("Labour Force", "labour_force"),
                     ("Employed", "employed"), ("Unemployed", "unemployed")]:
        row[col] = labour(lines, lab)
    if row["employed"] + row["unemployed"] != row["labour_force"]:
        problems.append("labour force != employed + unemployed")
    return row, problems


if __name__ == "__main__":
    rows, bad = [], 0
    for pdf in sorted(PDF_DIR.glob("2011_Census_CT_Ward_*_Profile.pdf")):
        r, p = parse(pdf)
        if p:
            bad += 1
            print(pdf.name, p, file=sys.stderr)
        rows.append(r)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} wards parsed, {bad} with internal inconsistencies -> {OUT}")
