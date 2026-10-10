"""Download Collin CAD residential appraisal and protest data from the Texas Open Data Portal (Socrata)."""
import csv, io, sys, time, urllib.parse, urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
BASE = "https://data.texas.gov/resource/{}.csv"
PAGE = 50000

DATASETS = {
    "homes_2026": ("5tkr-3759",
        "propid,geoid,nbhdcode,legalabssubname,situsbldgnum,situsstreetprefix,situsstreetname,"
        "situsstreetsuffix,situsunit,situscity,situszip,imprvyearbuilt,imprvclasscd,imprvmainarea,"
        "imprvpoolflag,landsizesqft,exempthmstdflag,noticevalland,noticevalimprv,noticevalmarket,"
        "noticevalassessed,currvalland,currvalimprv,currvalmarket,prevvalmarket",
        "propcategorycode='A' AND imprvmainarea > 0"),
    "protests": ("xmrt-bxjr",
        "year,propid,caseid,prottype,protbytype,protstatuscode,protstatusdescr,protreasoncodes,"
        "noticemarketval,finalmarketval,hearingnoshow,protwithdrawn,protsettled,arborder",
        "propcategorycode='A'"),
}

def fetch(name, ds, select, where):
    out = RAW / f"{name}.csv"
    rows, header, offset = [], None, 0
    while True:
        q = urllib.parse.urlencode({"$select": select, "$where": where, "$order": ":id",
                                    "$limit": PAGE, "$offset": offset})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(BASE.format(ds) + "?" + q, timeout=300) as r:
                    text = r.read().decode("utf-8")
                break
            except Exception as e:
                print("retry", e, file=sys.stderr); time.sleep(5)
        else:
            raise RuntimeError("failed")
        rd = list(csv.reader(io.StringIO(text)))
        header = header or rd[0]
        page = rd[1:]
        rows += page
        print(name, offset + len(page), file=sys.stderr)
        if len(page) < PAGE:
            break
        offset += PAGE
    with open(out, "w", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)
    print(f"{name}: {len(rows)} rows -> {out}")

if __name__ == "__main__":
    for name, (ds, sel, where) in DATASETS.items():
        fetch(name, ds, sel, where)
