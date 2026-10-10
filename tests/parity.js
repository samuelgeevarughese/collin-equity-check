// Checks that the browser comps engine reproduces the Python model's indicated value for every home in a shard.
const fs = require("fs");
const { findComps } = require("../web/comps.js");
const file = process.argv[2];
const [head, ...lines] = fs.readFileSync(file, "utf8").trim().split("\n");
const cols = head.split(",");
const num = new Set(["id", "c", "z", "y", "f", "p", "h", "l", "i", "m", "t", "o"]);
const rows = lines.map(l => { const v = l.split(","); const o = {};
  cols.forEach((c, j) => o[c] = num.has(c) ? +v[j] : c === "e" ? (v[j] === "" ? null : +v[j]) : v[j]); return o; });
let n = 0, bad = 0;
for (const r of rows) {
  if (!r.o) continue;
  const { indicated } = findComps(rows, r);
  const js = indicated == null ? null : Math.round(indicated);
  n++;
  if ((js == null) !== (r.e == null) || (js != null && Math.abs(js - r.e) > 1)) { if (bad < 5) console.log("mismatch", r.id, js, r.e); bad++; }
}
console.log(`${file}: ${n} homes checked, ${bad} mismatches`);
