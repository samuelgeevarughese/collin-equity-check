"""Unequal-appraisal (equity) comps model + protest outcome analysis for Collin County homes.

Method (Texas Tax Code 41.43(b)(3) style equity argument):
  For a subject home, comparable homes are drawn from the same appraisal neighborhood,
  same construction class family, living area within +/-15% and year built within +/-8 years
  (widened to +/-25% / +/-15 years if fewer than 5 comps). Up to 10 closest comps are kept.
  Each comp is adjusted to the subject by applying the comp's improvement value per sq ft
  to the subject's living area and using the subject's own land value:
      adjusted_comp = subject_land + comp_imprv_value / comp_sqft * subject_sqft
  The indicated equity value is the median adjusted comp. All values are 2026 notice
  (pre-protest) market values, so the model never sees protest outcomes.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW, OUT = ROOT / "data" / "raw", ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)

def load_homes():
    h = pd.read_csv(RAW / "homes_2026.csv", low_memory=False)
    h = h.dropna(subset=["noticevalmarket", "noticevalimprv", "noticevalland", "imprvyearbuilt", "situscity"])
    h = h[(h.noticevalimprv > 0) & (h.imprvmainarea >= 500) & (h.imprvmainarea <= 15000)]
    h = h[h.imprvyearbuilt <= 2025]  # skip homes still under construction
    h["cls"] = h.imprvclasscd.fillna("").str.extract(r"^(R\d\d)", expand=False)
    h = h[h.cls.notna()].copy()
    h["ipsf"] = h.noticevalimprv / h.imprvmainarea
    parts = [h.situsbldgnum.fillna("").astype(str).str.replace(r"\.0$", "", regex=True),
             h.situsstreetprefix.fillna(""), h.situsstreetname.fillna(""), h.situsstreetsuffix.fillna("")]
    h["addr"] = (parts[0] + " " + parts[1] + " " + parts[2] + " " + parts[3]).str.split().str.join(" ")
    unit = h.situsunit.fillna("").astype(str)
    h.loc[unit != "", "addr"] = h.addr + " #" + unit
    return h.reset_index(drop=True)

def comps_for_all(h):
    """Vectorised-ish per-neighborhood comp search. Returns per-home indicated value + comp ids."""
    ind = np.full(len(h), np.nan); ncomp = np.zeros(len(h), int); comp_ids = [None] * len(h)
    for (_, _), g in h.groupby(["nbhdcode", "cls"]):
        g = g.sort_values("propid")
        idx = g.index.values
        sq = g.imprvmainarea.values; yb = g.imprvyearbuilt.values; ipsf = g.ipsf.values
        pool = g.imprvpoolflag.fillna(False).values.astype(bool); land = g.noticevalland.values
        pid = g.propid.values
        for k, i in enumerate(idx):
            for sq_tol, yb_tol in ((0.15, 8), (0.25, 15)):
                m = (np.abs(sq - sq[k]) <= sq_tol * sq[k]) & (np.abs(yb - yb[k]) <= yb_tol)
                m[k] = False
                if m.sum() >= 5:
                    break
            c = np.where(m)[0]
            if len(c) < 3:
                continue
            score = np.abs(sq[c] - sq[k]) / sq[k] + np.abs(yb[c] - yb[k]) / 20 + (pool[c] != pool[k]) * 0.1
            c = c[np.argsort(score, kind="stable")[:10]]  # ties -> lower propid (matches web app)
            adj = land[k] + ipsf[c] * sq[k]
            ind[i] = np.median(adj); ncomp[i] = len(c); comp_ids[i] = pid[c].tolist()
    h["indicated"] = ind; h["ncomp"] = ncomp; h["comps"] = comp_ids
    h["gap_pct"] = (h.noticevalmarket - h.indicated) / h.indicated
    return h

def protest_outcomes():
    p = pd.read_csv(RAW / "protests.csv", low_memory=False)
    p = p.dropna(subset=["noticemarketval", "finalmarketval"])
    p = p[p.noticemarketval > 0]
    p["reduced"] = p.finalmarketval < p.noticemarketval
    p["cut_pct"] = (p.noticemarketval - p.finalmarketval) / p.noticemarketval
    p["filer"] = np.where(p.protbytype == "OW", "Owner", np.where(p.protbytype == "AG", "Agent", "Other"))
    return p

def main():
    h = comps_for_all(load_homes())
    p = protest_outcomes()
    print("homes:", len(h), "with comps:", h.indicated.notna().mean().round(3))

    # ---- Validation: does the model's gap predict 2026 ARB reductions? ----
    p26 = p[p.year == 2026].drop_duplicates("propid", keep="last")
    v = h.merge(p26[["propid", "reduced", "cut_pct", "filer"]], on="propid", how="inner").dropna(subset=["gap_pct"])
    v["band"] = pd.cut(v.gap_pct, [-1, -0.05, 0, 0.05, 0.10, 10],
                       labels=["Under by 5%+", "Under 0-5%", "Over 0-5%", "Over 5-10%", "Over 10%+"])
    val = (v.groupby("band", observed=True)
             .agg(n=("propid", "size"), reduced=("reduced", "mean"), median_cut=("cut_pct", "median"))
             .reset_index())
    print(val.to_string())
    corr = v[["gap_pct", "cut_pct"]].corr(method="spearman").iloc[0, 1]

    # ---- County protest stats ----
    by_year = (p.groupby("year").agg(protests=("propid", "size"), reduced=("reduced", "mean"),
               median_cut_if_reduced=("cut_pct", lambda s: s[s > 0].median())).reset_index())
    by_filer = (p[(p.year == 2026) & p.filer.isin(["Owner", "Agent"])].groupby("filer")
                .agg(protests=("propid", "size"), reduced=("reduced", "mean"),
                     median_cut_if_reduced=("cut_pct", lambda s: s[s > 0].median())).reset_index())
    # outcome path for owner filers 2026
    own26 = p[(p.year == 2026) & (p.filer == "Owner")]
    path = (own26.groupby("protstatusdescr").agg(n=("propid", "size"), reduced=("reduced", "mean"))
            .sort_values("n", ascending=False).head(6).reset_index())
    print(by_year.to_string()); print(by_filer.to_string()); print(path.to_string())

    # ---- Neighborhood protest stats (2026) ----
    p26n = p26.merge(h[["propid", "nbhdcode"]], on="propid")
    homes_n = h.groupby("nbhdcode").size()
    nb = (p26n.groupby("nbhdcode").agg(protested=("propid", "size"), reduced=("reduced", "mean"),
          cut=("cut_pct", lambda s: s[s > 0].median())).reset_index())
    nb["homes"] = nb.nbhdcode.map(homes_n)

    summary = {
        "homes": int(len(h)), "homes_with_comps": int(h.indicated.notna().sum()),
        "over5": float((h.gap_pct > 0.05).mean()),
        "validation": {"rows": int(len(v)), "spearman": float(corr),
                       "bands": val.assign(reduced=val.reduced.round(4), median_cut=val.median_cut.round(4)).to_dict("records")},
        "by_year": by_year.round(4).to_dict("records"),
        "by_filer": by_filer.round(4).to_dict("records"),
        "owner_paths": path.round(4).to_dict("records"),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    h.to_pickle(OUT / "homes_scored.pkl"); nb.to_csv(OUT / "nbhd_protests.csv", index=False)
    print(json.dumps({k: summary[k] for k in ("homes", "homes_with_comps", "over5")}), "spearman", round(corr, 3))

if __name__ == "__main__":
    main()
