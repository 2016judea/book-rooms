"""Rank the western canon by relevance in modern culture -> the landing board.

Pool  : Harold Bloom, *The Western Canon* (1994), appendix (data/canon/bloom_appendix.json,
        parsed by parse_bloom.py), plus Aidan's five-star books by any of Bloom's 26
        central authors. Bloom's appendix lists Shakespeare only as "Plays"; that entry is
        expanded to the plays themselves. Other generic entries ("Poems", "Collected
        Stories", ...) have no single article and are logged as skipped.
Signal: English Wikipedia pageviews (user agents, all access) for the WORK's article over
        the last 12 complete months. Open Library already_read + want_to_read is kept as a
        secondary column for the top rows only.
Board : every canon work Aidan has read (his Goodreads read shelf, any rating; matched on
        the work, not the edition), plus the UNREAD_EXTRA most-viewed canon works he hasn't
        read, all ordered by pageviews (Aidan, 2026-10-15). Non-western works are excluded.

Writes data/canon/ranking.csv (every work, auditable), data/canon/board.json (the cut),
data/canon/skipped.tsv (generic or unresolved entries). Cached under data/cache/canon/.
Run: python3 scripts/build_canon.py
"""
import csv, datetime as dt, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache", "canon")
os.makedirs(CACHE, exist_ok=True)
UA = {"User-Agent": "book-rooms/0.1 (https://read-with-community.vercel.app; aidanjude2016@gmail.com)"}
UNREAD_EXTRA = 5
READS = os.path.expanduser("~/Desktop/writing-topology/data/personal_corpus/goodreads_reads.json")
# Bloom's appendix lists these "because of their influence on the Western canon" (p. 531);
# they are not western works, and the board is "western canon" (Aidan, 2026-10-14).
EXCLUDE = {
    "Ramayana": "Sanskrit epic (ancient India); listed by Bloom for its influence on the West, not a western work",
    "Bhagavad Gita": "Sanskrit scripture (ancient India); listed by Bloom for its influence on the West, not a western work",
    "Mahabharata": "Sanskrit epic (ancient India); listed by Bloom for its influence on the West, not a western work",
}
CENTRAL = ["Shakespeare", "Dante", "Chaucer", "Cervantes", "Montaigne", "Molière", "Milton", "Samuel Johnson",
           "Goethe", "Wordsworth", "Jane Austen", "Whitman", "Emily Dickinson", "Charles Dickens", "George Eliot",
           "Tolstoy", "Ibsen", "Freud", "Proust", "James Joyce", "Virginia Woolf", "Kafka", "Borges", "Neruda",
           "Pessoa", "Beckett"]  # Bloom p. 2, via Wikipedia "The Western Canon"
SHAKESPEARE_PLAYS = [
    "Hamlet", "Macbeth", "King Lear", "Othello", "Romeo and Juliet", "A Midsummer Night's Dream", "The Tempest",
    "Julius Caesar", "Twelfth Night", "Much Ado About Nothing", "The Merchant of Venice", "As You Like It",
    "Antony and Cleopatra", "The Taming of the Shrew", "Richard III", "Henry V", "Henry IV, Part 1",
    "Henry IV, Part 2", "Richard II", "Coriolanus", "Titus Andronicus", "Measure for Measure",
    "The Winter's Tale", "Cymbeline", "Pericles, Prince of Tyre", "Troilus and Cressida", "All's Well That Ends Well",
    "The Comedy of Errors", "The Two Gentlemen of Verona", "Love's Labour's Lost", "The Merry Wives of Windsor",
    "Timon of Athens", "King John", "Henry VI, Part 1", "Henry VI, Part 2", "Henry VI, Part 3", "Henry VIII",
    "The Two Noble Kinsmen"]
GENERIC = re.compile(r"^(the )?(complete |collected |selected |short |early |later |last |major )*"
                     r"(plays|poems|poetry|works|essays|stories|tales|letters|novels|prose|lyrics|fiction|"
                     r"dialogues|sonnets and poems|writings|notebooks|journals|diaries|criticism|fables|sermons|"
                     r"odes|elegies|hymns|songs|shorter poems|tragedies|comedies|histories)\b", re.I)


def get(url, key, retries=6):
    path = os.path.join(CACHE, re.sub(r"[^A-Za-z0-9]+", "_", key)[-180:] + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                data = json.load(r)
            json.dump(data, open(path, "w"))
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                json.dump(None, open(path, "w"))
                return None
            time.sleep(2 + 4 * attempt)
        except Exception:
            time.sleep(2 + 4 * attempt)
    raise RuntimeError("fetch failed: " + url)  # never let a failed fetch read as zero views


WORKY = re.compile(r"novel|play|poem|poetry|epic|book|novella|story|stories|essay|treatise|scripture|text|tragedy|comedy|drama|saga|verse|work by|collection|memoir|autobiography|dialogue|romance|fable|satire|history by|chronicle|letters|sonnet", re.I)
BAD_DESC = re.compile(r"film|movie|television|tv series|miniseries|song|album|band|video game|character|city|capital|municipality|country|genre|king|ruler|deity|\bwar\b|battle|footballer|actor|actress|opera|ballet|musical", re.I)


PERSON = re.compile(r"\b(ruler|protagonist|hero|heroine|figure|deity|god|goddess|character|king|queen|emperor|poet|writer|philosopher)\b", re.I)


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\s*\(.*?\)\s*", " ", s)          # drop "(novel)", "(play)"
    s = re.sub(r"^(the|a|an|le|la|les|el|il|der|die|das)\s+", "", s.strip())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def resolve(work, author):
    """English Wikipedia article for the work (not the author). Search, then accept the
    first hit whose base title matches the work title; follow redirects; skip disambiguation."""
    q = f"{work} {author or ''}".strip()
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "generator": "search", "gsrsearch": q, "gsrlimit": 6,
        "prop": "pageprops|description", "redirects": 1})
    d = get(url, "s_" + q)
    pages = sorted(((d or {}).get("query") or {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    # search can miss the obvious page (Romeo and Juliet), so try the work's title directly too
    direct = "|".join([work, f"{work} (novel)", f"{work} (play)", f"{work} (poem)"])
    dd = get("https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "titles": direct, "prop": "pageprops|description", "redirects": 1}), "t_" + direct)
    pages = [p for p in ((dd or {}).get("query") or {}).get("pages", {}).values() if "missing" not in p and "invalid" not in p] + pages
    w = norm(work)
    a = norm(author or "")
    last = a.split()[-1] if a else ""
    found = []
    for p in pages:
        t = p["title"]
        desc = (p.get("description") or "").lower()
        if "disambiguation" in (p.get("pageprops") or {}):
            continue
        if a and norm(t) == a:
            continue  # the author's article, never the work's
        paren = re.search(r"\((.*?)\)", t)
        if paren and not WORKY.search(paren.group(1)):
            continue  # "(film)", "(character)", "(whale)"
        if BAD_DESC.search(desc) and not WORKY.search(desc):
            continue
        if not a and re.search(r"\bby\b|\b(19|20)\d\d\b", desc):
            continue  # an anonymous work's article is never "2001 novel by Joan London"
        if PERSON.search(desc):
            continue  # "Sumerian ruler and protagonist of the Epic of Gilgamesh" is the hero, not the work
        nt = norm(t)
        title_ok = nt == w or (min(len(nt), len(w)) > 5 and (nt in w or w in nt))
        if not title_ok:
            continue
        if nt != w and not (last and last in norm(desc)) and not (not a and WORKY.search(desc)):
            continue  # a partial title match must be confirmed by the author in the description
        if nt == w and last and desc and last not in norm(desc) and not WORKY.search(desc):
            continue
        found.append((nt != w, t, p.get("description", "")))  # exact title beats a partial one
    if found:
        found.sort(key=lambda f: f[0])
        return found[0][1], found[0][2]
    return None, None


def views(title, start, end):
    t = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
           f"{t}/monthly/{start}/{end}")
    d = get(url, f"pv_{start}_{end}_{title}")
    return sum(i["views"] for i in (d or {}).get("items", [])) if d else 0


def ol_counts(work, author):
    q = urllib.parse.urlencode({"title": work, **({"author": author.split()[-1]} if author else {}),
                                "fields": "key,already_read_count,want_to_read_count,ratings_count", "limit": 1})
    d = get("https://openlibrary.org/search.json?" + q, "ol_" + work + (author or ""))
    doc = ((d or {}).get("docs") or [{}])[0]
    return doc.get("already_read_count", 0) or 0, doc.get("want_to_read_count", 0) or 0, doc.get("ratings_count", 0) or 0


def gr_short(t):
    return re.sub(r"(,\s*or,?|\s+or,)\s.*$", "", re.split(r"[:(]", t)[0], flags=re.I).strip()


def match_read(o, reads):
    """Has Aidan read this work? Match his Goodreads read shelf on the WORK: same title
    (edition subtitles and series stripped) and the same author (surname, fuzzy for
    transliteration). Returns (read, how it matched, sure)."""
    from difflib import SequenceMatcher
    fold = lambda t: unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    titles = {norm(o["work"]), norm(re.sub(r"\s*\(.*?\)", "", o["article"] or ""))} - {""}
    last = fold((o["author"] or "").split()[-1]) if o["author"] else ""
    best = None
    for g in reads:
        gt = norm(gr_short(g["title"]))
        exact = gt in titles
        partial = not exact and any(len(t) > 5 and (t in gt or gt in t) for t in titles)
        if not (exact or partial):
            continue
        gl = [w for w in re.findall(r"[a-z]{3,}", fold(g["author"]))]
        author_ok = bool(last) and any(SequenceMatcher(None, last, w).ratio() >= 0.75 for w in gl)
        if last and not author_ok:
            continue
        sure = exact and (author_ok or not last) and bool(last)
        how = f'goodreads "{g["title"]}" by {g["author"]}, read {g.get("read_date") or g.get("read_year") or "undated"}'
        how += "" if sure else (" [title contains/contained]" if partial else " [anonymous work, title only]")
        if best is None or (sure and not best[2]):
            best = (True, how, sure)
    return best or (False, "", False)


def main():
    today = dt.date.today()
    end_month = today.replace(day=1) - dt.timedelta(days=1)                       # last complete month
    start_month = (end_month.replace(day=1) - dt.timedelta(days=330)).replace(day=1)  # 12 months back
    start, end = start_month.strftime("%Y%m01"), end_month.strftime("%Y%m%d")

    rows = json.load(open(os.path.join(ROOT, "data/canon/bloom_appendix.json")))
    pool, skipped = [], []
    for r in rows:
        if r["author"] == "William Shakespeare" and r["work"] == "Plays":
            pool += [{"work": p, "author": "William Shakespeare", "source": "Bloom appendix (Plays, expanded)"} for p in SHAKESPEARE_PLAYS]
        elif GENERIC.match(r["work"]):
            skipped.append((r["work"], r["author"] or "", "generic entry, no single article"))
        else:
            pool.append({"work": r["work"], "author": r["author"], "source": "Bloom appendix"})
    reads = json.load(open(READS))
    for g in reads:
        if any(c.lower() in g["author"].lower() for c in CENTRAL):
            pool.append({"work": gr_short(g["title"]), "author": g["author"], "source": "Aidan read, by a Bloom central author"})
    seen, uniq = set(), []
    for p in pool:
        k = (norm(p["work"]), norm(p["author"] or ""))
        if k not in seen:
            seen.add(k); uniq.append(p)
    print(len(uniq), "works in pool;", len(skipped), "generic entries skipped", file=sys.stderr)

    def work(p):
        title, desc = resolve(p["work"], p["author"])
        return {**p, "article": title, "description": desc, "views": views(title, start, end) if title else 0}
    with ThreadPoolExecutor(3) as ex:
        out = list(ex.map(work, uniq))
    for o in out:
        if not o["article"]:
            skipped.append((o["work"], o["author"] or "", "no matching English Wikipedia article"))
    # one row per article (two appendix entries can resolve to the same page)
    best = {}
    for o in out:
        if o["article"] and (o["article"] not in best or o["source"].startswith("Aidan")):
            best[o["article"]] = {**best.get(o["article"], {}), **o} if o["source"].startswith("Aidan") else o
    ranked = sorted(best.values(), key=lambda o: -o["views"])
    unread_n = 0
    for i, o in enumerate(ranked):
        o["rank"] = i + 1
        o["excluded"] = EXCLUDE.get(o["article"], "")
        o["read"], o["read_match"], o["read_sure"] = match_read(o, reads)
        on = False
        if not o["excluded"]:
            if o["read"]:
                on = True
            elif unread_n < UNREAD_EXTRA:
                on = True; unread_n += 1
        o["on_board"] = on
        o["ol_already_read"] = o["ol_want_to_read"] = o["ol_ratings"] = ""
        if i < 100:
            try:
                o["ol_already_read"], o["ol_want_to_read"], o["ol_ratings"] = ol_counts(o["work"], o["author"])
            except RuntimeError:
                pass  # secondary column only; blank when Open Library doesn't answer

    d = os.path.join(ROOT, "data", "canon")
    with open(os.path.join(d, "ranking.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "on_board", "read", "read_match", "read_match_sure", "excluded_reason", "work", "author", "wikipedia_article", "pageviews_12mo", "window_start",
                    "window_end", "ol_already_read", "ol_want_to_read", "ol_ratings", "source"])
        for o in ranked:
            w.writerow([o["rank"], int(o["on_board"]), int(o["read"]), o["read_match"], int(o["read_sure"]) if o["read"] else "", o["excluded"], o["work"], o["author"] or "", o["article"], o["views"], start, end,
                        o["ol_already_read"], o["ol_want_to_read"], o["ol_ratings"], o["source"]])
    with open(os.path.join(d, "skipped.tsv"), "w") as f:
        f.write("work\tauthor\treason\n" + "".join(f"{a}\t{b}\t{c}\n" for a, b, c in skipped))
    json.dump({"signal": "English Wikipedia pageviews, user agents, all access, monthly sum",
               "window": [start, end], "selection": f"every canon work Aidan has read + the {UNREAD_EXTRA} most-viewed unread", "unread_extra": UNREAD_EXTRA, "generated": today.isoformat(),
               "pool": "Bloom, The Western Canon (1994) appendix + Aidan's five-stars by Bloom's 26 central authors",
               "board": [{k: o[k] for k in ("rank", "work", "author", "article", "views", "source", "read", "read_match", "read_sure")} for o in ranked if o["on_board"]],
               "excluded": [{"rank": o["rank"], "article": o["article"], "views": o["views"], "reason": o["excluded"]} for o in ranked if o["excluded"]]},
              open(os.path.join(d, "board.json"), "w"), indent=1, ensure_ascii=False)
    with open(os.path.join(d, "excluded.tsv"), "w") as f:
        f.write("rank\twikipedia_article\tpageviews_12mo\treason\n" + "".join(f"{o['rank']}\t{o['article']}\t{o['views']}\t{o['excluded']}\n" for o in ranked if o["excluded"]))
    for o in [o for o in ranked if o["on_board"]]:
        print(o["rank"], o["views"], o["article"], "|", o["author"], "| READ" if o["read"] else "| unread", "" if (o["read_sure"] or not o["read"]) else "(unsure: " + o["read_match"] + ")", file=sys.stderr)
    for o in ranked:
        if "Blood Meridian" in o["work"]:
            print("Blood Meridian rank", o["rank"], o["views"], file=sys.stderr)


if __name__ == "__main__":
    main()
