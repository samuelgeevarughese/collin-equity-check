// Equity comps engine. Mirrors pipeline/model.py exactly (validated in tests/parity.mjs).
(function (root) {
  function findComps(rows, subject) {
    // rows: all homes in the shard (objects with id,n,k,f,y,p,l,i). subject: one of them.
    const pool = rows.filter(r => r.n === subject.n && r.k === subject.k && r.id !== subject.id)
      .sort((a, b) => a.id - b.id);
    let cand = [], tolUsed = null;
    for (const [sqTol, ybTol] of [[0.15, 8], [0.25, 15]]) {
      cand = pool.filter(r => Math.abs(r.f - subject.f) <= sqTol * subject.f && Math.abs(r.y - subject.y) <= ybTol);
      tolUsed = { sqTol, ybTol };
      if (cand.length >= 5) break;
    }
    if (cand.length < 3) return { comps: [], indicated: null, tolUsed };
    const scored = cand.map((r, idx) => ({ r, idx,
      score: Math.abs(r.f - subject.f) / subject.f + Math.abs(r.y - subject.y) / 20 + (r.p !== subject.p ? 0.1 : 0) }));
    scored.sort((a, b) => a.score - b.score || a.idx - b.idx);
    const comps = scored.slice(0, 10).map(({ r, score }) => {
      const psf = r.i / r.f;
      return { ...r, psf, score, adjusted: subject.l + psf * subject.f };
    });
    const adj = comps.map(c => c.adjusted).sort((a, b) => a - b);
    const mid = adj.length >> 1;
    const indicated = adj.length % 2 ? adj[mid] : (adj[mid - 1] + adj[mid]) / 2;
    return { comps, indicated, tolUsed };
  }
  root.Comps = { findComps };
  if (typeof module !== "undefined") module.exports = { findComps };
})(typeof window !== "undefined" ? window : globalThis);
