"""Write compact per-city CSV shards + summary JSON for the website.

Each city shard holds every home in any neighborhood that has a home in that city, so a
home's comps are always in the same file. Comps are stored as row indexes within the shard.
"""
import json, re
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC, WEB = ROOT / "data" / "processed", ROOT / "web" / "data"
WEB.mkdir(parents=True, exist_ok=True)
MIN_HOMES = 900  # smaller towns are grouped into one "other" shard

def nice(c): return c.title().replace("Mckinney", "McKinney")

def slug(s): return re.sub(r"[^a-z]+", "-", s.lower()).strip("-")

def main():
    h = pd.read_pickle(PROC / "homes_scored.pkl")
    counts = h.situscity.value_counts()
    big = counts[counts >= MIN_HOMES].index.tolist()
    h["shard"] = np.where(h.situscity.isin(big), h.situscity.map(slug), "other-towns")
    nb_by_shard = h.groupby("shard").nbhdcode.unique()
    city_names = sorted(h.situscity.unique())
    city_idx = {c: i for i, c in enumerate(city_names)}
    cities = []
    for shard, nbs in nb_by_shard.items():
        g = h[h.nbhdcode.isin(nbs)].copy()
        g["home"] = (g.shard == shard).astype(int)  # 1 = searchable in this shard
        g = g.sort_values(["home", "situscity", "addr"], ascending=[False, True, True]).reset_index(drop=True)
        out = pd.DataFrame({
            "id": g.propid, "a": g.addr, "c": g.situscity.map(city_idx), "z": g.situszip.fillna(0).astype(int),
            "n": g.nbhdcode,
            "y": g.imprvyearbuilt.astype(int), "k": g.cls, "f": g.imprvmainarea.astype(int),
            "p": g.imprvpoolflag.fillna(False).astype(int), "h": g.exempthmstdflag.fillna(False).astype(int),
            "l": g.noticevalland.astype(int), "i": g.noticevalimprv.astype(int),
            "m": g.noticevalmarket.astype(int), "t": g.noticevalassessed.fillna(g.noticevalmarket).astype(int),
            "e": g.indicated.round(0).astype("Int64"), "o": g.home,
        })
        out.to_csv(WEB / f"{shard}.csv", index=False)
        label = "Other towns" if shard == "other-towns" else nice(g[g.home == 1].situscity.iloc[0])
        cities.append({"key": shard, "label": label, "homes": int(g.home.sum()),
                       "bytes": (WEB / f"{shard}.csv").stat().st_size})
    cities.sort(key=lambda c: -c["homes"])
    other = sorted(counts[counts < MIN_HOMES].index.str.title().tolist())

    nb = pd.read_csv(PROC / "nbhd_protests.csv")
    subs = h.groupby("nbhdcode").legalabssubname.agg(lambda s: s.mode().iat[0] if s.notna().any() else "")
    homes_n = h.groupby("nbhdcode").size()
    st = {r.nbhdcode: r for r in nb.itertuples()}
    nbmap = {}
    for code, name in subs.items():
        r = st.get(code)
        nbmap[code] = [str(name).title(), int(homes_n[code]),
                       int(r.protested) if r else 0, round(float(r.reduced), 3) if r else None,
                       None if (not r or pd.isna(r.cut)) else round(float(r.cut), 4)]
    # ---- Neighborhood explorer (neighborhoods with 40+ scored homes) ----
    s = h[h.indicated.notna()].copy()
    est = s.imprvyearbuilt <= 2024
    s["chg"] = np.where(est & (s.prevvalmarket > 0), s.noticevalmarket / s.prevvalmarket - 1, np.nan)
    nx = s.groupby("nbhdcode").agg(homes=("propid", "size"), val=("noticevalmarket", "median"),
                                   chg=("chg", "median"), over5=("gap_pct", lambda x: (x > 0.05).mean()),
                                   yb=("imprvyearbuilt", "median"),
                                   city=("situscity", lambda x: x.mode().iat[0])).reset_index()
    nx = nx[(nx.homes >= 40) & (nx.val >= 75000) & ~nx.nbhdcode.str.startswith("HOA")].merge(nb[["nbhdcode", "protested", "reduced", "cut"]], on="nbhdcode", how="left")
    nx["prate"] = nx.protested.fillna(0) / nx.homes
    q = pd.qcut(nx.over5, 4, labels=False)
    quart = (nx.groupby(q).agg(n=("homes", "size"), over5=("over5", "median"), prate=("prate", "median"),
                               reduced=("reduced", "median"), cut=("cut", "median")).round(4).to_dict("records"))
    r2 = lambda v, d: None if pd.isna(v) else round(float(v), d)
    nbx = [[r.nbhdcode, nice(r.city), subs.get(r.nbhdcode, "").title(), int(r.homes), int(round(r.val, -3)),
            r2(r.chg, 3), r2(r.over5, 3), r2(r.prate, 3), r2(r.reduced, 3), r2(r.cut, 4), int(r.yb)]
           for r in nx.itertuples()]
    summary = json.loads((PROC / "summary.json").read_text())
    summary["nbhd_quartiles"] = quart
    summary["nbhd_median_prate"] = round(float(nx.prate.median()), 4)
    (WEB / "meta.json").write_text(json.dumps({"cityNames": [nice(c) for c in city_names], "cities": cities, "otherTowns": other,
                                               "nbhd": nbmap, "nbx": nbx, "summary": summary}, separators=(",", ":")))
    print("explorer neighborhoods", len(nbx)); print(quart)
    for c in cities: print(c)
    print("total MB", round(sum(c["bytes"] for c in cities) / 1e6, 1))

if __name__ == "__main__":
    main()
