"""Build data/seed.json: Aidan's five-star books, his verbatim Goodreads reviews,
and a real cover image per book.

Cover rule (Aidan, 2026-10-14): first edition, real photograph or scan only.
If no first-edition image is found, fall back to his imprint order
Vintage International > Picador > Penguin Classics, then to the earliest
edition with a cover, and log the fallback.

Sources, in order:
  1. ~/Desktop/hard-books-club/brand/covers/<slug>/ (hand-sourced, sources.csv)
  2. Open Library editions that carry a cover scan

Run: python3 scripts/build_seed.py   (network; caches under data/cache/)
"""
import csv, html, json, os, re, sys, time, urllib.parse, urllib.request, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.expanduser("~/Desktop/writing-topology/data/personal_corpus/goodreads_reads.json")
HBC = os.path.expanduser("~/Desktop/hard-books-club/brand/covers")
CACHE = os.path.join(ROOT, "data", "cache")
COVERS = os.path.join(ROOT, "public", "covers")
os.makedirs(CACHE, exist_ok=True)
os.makedirs(COVERS, exist_ok=True)

UA = {"User-Agent": "book-rooms/0.1 (aidanjude2016@gmail.com)"}
IMPRINTS = ["vintage international", "picador", "penguin classics"]
# Chapter counts, only where checked by hand. Everything else uses percent.
CHAPTERS = {"blood-meridian": 23}


def slugify(s):
    s = re.split(r"[:(]", s)[0]
    s = re.sub(r",\s*or,.*$", "", s)
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def get(url):
    key = os.path.join(CACHE, re.sub(r"[^A-Za-z0-9]+", "_", url)[-180:] + ".json")
    if os.path.exists(key):
        return json.load(open(key))
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                data = json.load(r)
            json.dump(data, open(key, "w"))
            time.sleep(0.4)
            return data
        except Exception as e:  # noqa
            print("  retry", url, e, file=sys.stderr)
            time.sleep(2 + attempt * 3)
    return None


def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 2000:
        return True
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            data = r.read()
        if len(data) < 2000:  # OL returns a 1x1 gif / tiny placeholder for missing covers
            return False
        open(dest, "wb").write(data)
        time.sleep(0.3)
        return True
    except Exception as e:  # noqa
        print("  download failed", url, e, file=sys.stderr)
        return False


def review_text(raw):
    t = re.sub(r"<br\s*/?>", "\n", raw or "")
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def year_of(s):
    m = re.search(r"(1[4-9]\d\d|20\d\d)", s or "")
    return int(m.group(1)) if m else None


def hbc_cover(slug):
    d = os.path.join(HBC, slug)
    src = os.path.join(d, "sources.csv")
    if not os.path.exists(src):
        return None
    rows = list(csv.DictReader(open(src)))
    for row in rows:
        f = os.path.join(d, row["option"] + ".jpg")
        if os.path.exists(f) and os.path.getsize(f) > 2000:
            first = row["option"].startswith("1-first")
            return {
                "file": f, "source_url": row["source_url"], "edition": row["edition"],
                "year": row["year"], "is_first_edition": first,
                "fallback_reason": None if first else "no first-edition image in hand-sourced set",
                "from_hbc": True,
            }
    return None


def ol_search(title, author):
    short = re.split(r"[:(]", title)[0]
    short = re.sub(r",?\s*or,?\s.*$", "", short, flags=re.I).strip()
    last = author.split()[-1]
    for params in ({"title": short, "author": last}, {"q": f"{short} {last}"}, {"q": short}):
        params.update({"fields": "key,title,first_publish_year,edition_count,author_name", "limit": 5})
        s = get("https://openlibrary.org/search.json?" + urllib.parse.urlencode(params))
        docs = [d for d in (s or {}).get("docs", []) if last.lower() in " ".join(d.get("author_name", [])).lower()]
        if docs:
            return max(docs[:3], key=lambda d: d.get("edition_count") or 0)
    return None


def ol_cover(title, author, published):
    """published = original publication year from his Goodreads export (not OL's,
    which is often wrong). An edition counts as the first edition only if it is
    dated that year and is in English or carries no language (translations fall
    through to the imprint order)."""
    work = ol_search(title, author)
    if not work:
        return None, None
    eds = get(f"https://openlibrary.org{work['key']}/editions.json?limit=500") or {}
    entries = [e for e in eds.get("entries", []) if e.get("covers") and e["covers"][0] > 0]
    for e in entries:
        e["_year"] = year_of(e.get("publish_date"))
        e["_pub"] = ", ".join(e.get("publishers", []))
        langs = [l["key"] for l in e.get("languages", [])]
        e["_eng"] = (not langs) or "/languages/eng" in langs
    dated = sorted([e for e in entries if e["_year"] and e["_eng"]], key=lambda e: e["_year"])
    meta = {"openlibrary_work": work["key"], "first_published": published or work.get("first_publish_year")}

    def pack(e, first, reason, imprint=None):
        cid = e["covers"][0]
        return {
            "image_url": f"https://covers.openlibrary.org/b/id/{cid}-L.jpg",
            "source_url": f"https://openlibrary.org{e['key']}",
            "edition": f"{e['_pub'] or 'unknown publisher'}, {e.get('publish_date') or '?'}",
            "year": e["_year"], "is_first_edition": first, "fallback_reason": reason,
            "imprint": imprint,
        }

    if published:
        firsts = [e for e in dated if e["_year"] == published]
        if firsts:
            return pack(firsts[0], True, None), meta
    for imp in IMPRINTS:
        for e in dated:
            if imp in e["_pub"].lower() or imp in json.dumps(e.get("series", "")).lower():
                return pack(e, False, f"no first-edition image found; fell back to {imp.title()}", imp), meta
    if dated:
        return pack(dated[0], False, "no first-edition or preferred-imprint image; earliest English edition with a cover"), meta
    if entries:
        return pack(entries[0], False, "no dated English edition with a cover; first edition with any cover"), meta
    return None, meta


def buy_links():
    out = {}
    f = os.path.expanduser("~/Desktop/hard-books-club/archive/buy_links.csv")
    if os.path.exists(f):
        for row in csv.DictReader(open(f)):
            out.setdefault(row["slug"], []).append({"label": row["label"], "url": row["ebay_url"]})
    return out


def main():
    buys = buy_links()
    reads = json.load(open(CORPUS))
    five = [r for r in reads if r.get("rating") == 5]
    # Blood Meridian first, then most recently read
    five.sort(key=lambda r: (0 if "Blood Meridian" in r["title"] else 1, -(r.get("read_year") or 0), r["title"]))
    books, log = [], []
    for r in five:
        slug = slugify(r["title"])
        print(slug, file=sys.stderr)
        cover = hbc_cover(slug)
        meta = {}
        if cover:
            ext = ".jpg"
            dest = os.path.join(COVERS, slug + ext)
            shutil.copyfile(cover.pop("file"), dest)
            cover["image"] = f"/covers/{slug}{ext}"
            _, meta = ol_cover(r["title"], r["author"], r.get("published"))
        else:
            cover, meta = ol_cover(r["title"], r["author"], r.get("published"))
            if cover:
                dest = os.path.join(COVERS, slug + ".jpg")
                if download(cover["image_url"], dest):
                    cover["image"] = f"/covers/{slug}.jpg"
                else:
                    cover = None
        meta = meta or {}
        body = review_text(r.get("review"))
        books.append({
            "id": slug,
            "title": r["title"],
            "author": r["author"],
            "first_published": meta.get("first_published") or r.get("published"),
            "openlibrary_work": meta.get("openlibrary_work"),
            "unit": "chapter" if slug in CHAPTERS else "percent",
            "unit_count": CHAPTERS.get(slug, 100),
            "cover": cover,
            "preferred_editions": buys.get(slug, []),
            "review": {
                "rating": 5, "body": body, "author": "Aidan",
                "source": "goodreads",
                "source_ref": "Aidan's Goodreads review, read " + (r.get("read_date") or str(r.get("read_year"))),
            } if body else None,
        })
        if cover and cover.get("source_url") and not cover.get("from_hbc"):
            d = os.path.join(ROOT, "data", "covers", slug)
            os.makedirs(d, exist_ok=True)
            opt = "1-first-edition" if cover["is_first_edition"] else "1-" + re.sub(r"[^a-z0-9]+", "-", (cover.get("imprint") or "earliest-with-cover").lower())
            with open(os.path.join(d, "sources.csv"), "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["book", "option", "edition", "year", "source_url"])
                w.writerow([re.split(r"[:(]", r["title"])[0].strip(), opt, cover["edition"], cover["year"] or "", cover["source_url"]])
        log.append((slug, "none" if not cover else ("first" if cover["is_first_edition"] else "fallback"),
                    (cover or {}).get("fallback_reason") or "", (cover or {}).get("edition", "")))
    json.dump({"books": books}, open(os.path.join(ROOT, "data", "seed.json"), "w"), indent=1, ensure_ascii=False)
    with open(os.path.join(ROOT, "data", "cover_log.tsv"), "w") as f:
        f.write("book\tstatus\tfallback_reason\tedition\n")
        for row in log:
            f.write("\t".join(row) + "\n")
    from collections import Counter
    print(Counter(s for _, s, _, _ in log), "reviews:", sum(1 for b in books if b["review"]))


if __name__ == "__main__":
    main()
