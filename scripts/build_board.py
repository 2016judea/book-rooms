"""data/canon/board.json -> the landing board.

For each work on the board: reuse the existing group chat when it is one of Aidan's
five-stars (same book id, his review stays), otherwise create an empty group chat with a
cover chosen by the house rule (first edition > Vintage International > Picador >
Penguin Classics; real images only, via build_seed.ol_cover). Every cover choice for a
new book is appended to data/cover_log.tsv and data/covers/<slug>/sources.csv.

Writes worker/board.sql: clears shelf_rank on every book, upserts new books, then sets
shelf_rank = pageview rank for the board. Nothing is deleted.
Run: python3 scripts/build_board.py && (cd worker && wrangler d1 execute book-rooms --remote --file=board.sql)
"""
import csv, importlib.util, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("seed", os.path.join(ROOT, "scripts", "build_seed.py"))
seed_mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(seed_mod)
from build_canon import norm  # noqa: E402  (same folder)

q = lambda v: "NULL" if v is None else (str(int(v)) if isinstance(v, (bool, int)) else "'" + str(v).replace("'", "''") + "'")


def dims(path):
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", path], capture_output=True, text=True).stdout
    w = re.search(r"pixelWidth: (\d+)", out); h = re.search(r"pixelHeight: (\d+)", out)
    return (int(w.group(1)), int(h.group(1))) if w and h else (None, None)


def hashed(img):
    import hashlib
    if not img or not img.startswith("/covers/"):
        return img
    f = os.path.join(ROOT, "public", img.lstrip("/").split("?")[0])
    return img.split("?")[0] + "?v=" + hashlib.sha1(open(f, "rb").read()).hexdigest()[:8] if os.path.exists(f) else img


def review_text(raw):
    import html as h
    t = re.sub(r"<br\s*/?>", "\n", raw or ""); t = re.sub(r"<[^>]+>", "", t); t = h.unescape(t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def main():
    board = json.load(open(os.path.join(ROOT, "data/canon/board.json")))["board"]
    seed = json.load(open(os.path.join(ROOT, "data/seed.json")))["books"]
    def last(a): return norm(a or "").split()[-1] if a else ""
    existing = {(norm(re.sub(r"(,\s*or,?|\s+or,)\s.*$", "", re.split(r"[:(]", b["title"])[0], flags=re.I)), last(b["author"])): b for b in seed}
    now = int(time.time() * 1000)
    sql = ["UPDATE books SET shelf_rank = NULL;"]
    log_rows, out = [], []
    for e in board:
        key = (norm(e["work"]), last(e["author"]))
        b = existing.get(key)
        if b:
            out.append({"id": b["id"], "rank": e["rank"], "title": b["title"], "new": False})
            sql.append(f"UPDATE books SET shelf_rank = {e['rank']} WHERE id = {q(b['id'])};")
            if b.get("cover"):
                continue
            # one of his five-stars with no cover yet: source one now, same rule as new chats
            slug, title, author = b["id"], e["work"], e["author"] or ""
            cover, _ = seed_mod.ol_cover(title, author, -1)
            if cover and seed_mod.download(cover["image_url"], os.path.join(ROOT, "public", "covers", slug + ".jpg")):
                w, h = dims(os.path.join(ROOT, "public", "covers", slug + ".jpg"))
                sql.append(f"UPDATE books SET cover_image = {q(hashed('/covers/' + slug + '.jpg'))}, cover_source_url = {q(cover['source_url'])},"
                           f" cover_edition = {q(cover['edition'])}, cover_is_first = 0, cover_fallback_reason = {q(cover['fallback_reason'])},"
                           f" cover_w = {q(w)}, cover_h = {q(h)} WHERE id = {q(slug)};")
                log_rows.append((slug, "fallback", cover["fallback_reason"] or "", cover["edition"], "canon board"))
                print(e["rank"], slug, "fallback (was none)", cover["edition"], file=sys.stderr)
            continue
        title = re.sub(r"\s*\((novel|play|poem|book|epic|novella|short story|essay)\)$", "", e["article"]) or e["work"]
        author = e["author"] or "Anonymous"
        slug = seed_mod.slugify(title)
        # Open Library edition dates are not reliable enough to call anything a first edition
        # (a 2010 Penguin carried "first" on year alone), so canon covers go straight to the
        # imprint order: Vintage International > Picador > Penguin Classics > earliest English.
        cover, meta = seed_mod.ol_cover(title, author if e["author"] else "", -1)
        if meta: meta["first_published"] = None
        img = w = h = None
        if cover:
            dest = os.path.join(ROOT, "public", "covers", slug + ".jpg")
            if seed_mod.download(cover["image_url"], dest):
                img = hashed(f"/covers/{slug}.jpg"); w, h = dims(dest)
                d = os.path.join(ROOT, "data", "covers", slug); os.makedirs(d, exist_ok=True)
                opt = "1-first-edition" if cover["is_first_edition"] else "1-" + re.sub(r"[^a-z0-9]+", "-", (cover.get("imprint") or "earliest-with-cover"))
                with open(os.path.join(d, "sources.csv"), "w", newline="") as f:
                    cw = csv.writer(f); cw.writerow(["book", "option", "edition", "year", "source_url"])
                    cw.writerow([title, opt, cover["edition"], cover["year"] or "", cover["source_url"]])
            else:
                cover = None
        status = "none" if not cover else ("first" if cover["is_first_edition"] else "fallback")
        log_rows.append((slug, status, (cover or {}).get("fallback_reason") or "", (cover or {}).get("edition", ""), "canon board"))
        fy = (meta or {}).get("first_published")
        sql.append(
            "INSERT INTO books (id,title,author,first_published,unit,unit_count,cover_image,cover_source_url,cover_edition,"
            "cover_is_first,cover_fallback_reason,cover_year,cover_w,cover_h,openlibrary_work,preferred_editions,shelf_rank,created_by,created_at) VALUES ("
            + ",".join(q(v) for v in [slug, title, author, fy, "percent", 100, img, (cover or {}).get("source_url"),
                                       (cover or {}).get("edition"), (cover or {}).get("is_first_edition"),
                                       (cover or {}).get("fallback_reason"),
                                       (cover or {}).get("year") if (cover or {}).get("is_first_edition") else None,
                                       w, h, (meta or {}).get("openlibrary_work"), "[]", e["rank"], "canon", now])
            + f") ON CONFLICT(id) DO UPDATE SET shelf_rank = {e['rank']}, cover_image = excluded.cover_image, cover_source_url = excluded.cover_source_url,"
              " cover_edition = excluded.cover_edition, cover_is_first = excluded.cover_is_first, cover_fallback_reason = excluded.cover_fallback_reason,"
              " cover_year = excluded.cover_year, cover_w = excluded.cover_w, cover_h = excluded.cover_h;")
        out.append({"id": slug, "rank": e["rank"], "title": title, "new": True, "cover": status})
        print(e["rank"], slug, status, (cover or {}).get("edition", ""), file=sys.stderr)
    # Aidan's own Goodreads review, verbatim, in every board chat for a book he has read
    # (any rating). Five-stars were seeded by seed_sql.py and are left alone. No review, no message.
    from email.utils import parsedate_to_datetime
    reads = json.load(open(os.path.expanduser("~/Desktop/workspace/writing-topology/data/personal_corpus/goodreads_reads.json")))
    five = {b["id"] for b in seed}
    seeded = empty = 0
    for e, o in zip(board, out):
        if not e.get("read"):
            continue
        m = re.match(r'goodreads "(.*?)" by (.*?), read (.*?)(?: \[|$)', e["read_match"])
        g = next((r for r in reads if m and r["title"] == m.group(1) and r["author"] == m.group(2)), None)
        body = review_text((g or {}).get("review"))
        if o["id"] in five:
            seeded += bool(next((b for b in seed if b["id"] == o["id"] and b.get("review")), None)); empty += not next((b for b in seed if b["id"] == o["id"] and b.get("review")), None)
            continue
        sql.append(f"DELETE FROM messages WHERE user_id = 'aidanj' AND source = 'goodreads' AND book_id = {q(o['id'])};")
        if not body:
            empty += 1
            continue
        try:
            when = int(parsedate_to_datetime(g["read_date"]).timestamp() * 1000)
        except Exception:
            when = int(time.time() * 1000) - 86400000 * 365 * 2  # undated read: older than any live chat
        ref = "Aidan's Goodreads review, read " + (g.get("read_date") or str(g.get("read_year") or "undated"))
        sql.append("INSERT INTO messages (book_id,user_id,body,is_review,author_position,spoils_to,spoils_to_source,source,source_ref,created_at) VALUES ("
                   + ",".join(q(v) for v in [o["id"], "aidanj", body, 1, 100, 100, "author_position", "goodreads", ref, when]) + ");")
        seeded += 1
    print(f"board chats seeded with his review: {seeded}; empty: {empty + sum(1 for e in board if not e.get('read'))}", file=sys.stderr)
    open(os.path.join(ROOT, "worker", "board.sql"), "w").write("\n".join(sql) + "\n")
    # cover log: keep the five-star rows, replace the canon rows
    logp = os.path.join(ROOT, "data", "cover_log.tsv")
    keep = [l for l in open(logp).read().splitlines() if l and not l.endswith("\tcanon board")]
    if keep and not keep[0].endswith("\tsource"):
        keep[0] += "\tsource"
        keep = [keep[0]] + [l + "\taidan five-star" for l in keep[1:]]
    open(logp, "w").write("\n".join(keep + ["\t".join(r) for r in log_rows]) + "\n")
    json.dump(out, open(os.path.join(ROOT, "data/canon/board_books.json"), "w"), indent=1, ensure_ascii=False)
    print(sum(1 for o in out if o["new"]), "new group chats;", sum(1 for o in out if not o["new"]), "of his five-stars on the board", file=sys.stderr)


if __name__ == "__main__":
    main()
