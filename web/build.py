from pathlib import Path
d = Path(__file__).parent
(d / "index.html").write_text((d / "page.html").read_text().replace("/*__COMPS__*/", (d / "comps.js").read_text()))
