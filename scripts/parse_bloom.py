"""Bloom, The Western Canon (1994), appendix -> data/canon/bloom_appendix.json.
Source: http://www.interleaves.org/~rteeter/grtbloom.html (linked from Wikipedia's
'The Western Canon' article). Each row: author (or None for anonymous works), work, age."""
import html, json, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = open(os.path.join(ROOT, "data/canon/bloom_appendix.html"), encoding="latin-1").read()
clean = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()
rows, author, age = [], None, None
for m in re.finditer(r"<h2[^>]*>(.*?)</h2>|<li[^>]*>(.*?)(?=<li|<dd|</ul|</ol|<h\d|$)|<dd[^>]*>(.*?)</dd>", src, re.S | re.I):
    h2, li, dd = m.groups()
    if h2:
        t = clean(h2)
        if "Age" in t: age = t
    elif li is not None:
        cites = re.findall(r"<cite>(.*?)</cite>", li, re.S | re.I)
        if cites and not clean(re.sub(r"<cite>.*?</cite>", "", li, flags=re.S | re.I)).strip(" ,:;()"):
            author = None
            rows += [{"author": None, "work": clean(c), "age": age} for c in cites]
        else:
            author = clean(li)
    elif dd is not None:
        for c in re.findall(r"<cite>(.*?)</cite>", dd, re.S | re.I) or [dd]:
            w = clean(c)
            if w: rows.append({"author": author, "work": w, "age": age})
json.dump(rows, open(os.path.join(ROOT, "data/canon/bloom_appendix.json"), "w"), indent=1, ensure_ascii=False)
print(len(rows), "works,", len({r["author"] for r in rows}), "authors")
for r in rows:
    if r["author"] and any(k in r["author"] for k in ("McCarthy", "Faulkner", "Homer", "Shakespeare", "Melville")): print(r)
