"""data/seed.json -> worker/seed.sql (books + Aidan's verbatim Goodreads reviews as messages).
Idempotent: books upsert; Aidan's imported reviews are replaced."""
import json, os, re, secrets, subprocess, time
from email.utils import parsedate_to_datetime
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
seed = json.load(open(os.path.join(ROOT, "data", "seed.json")))
tokf = os.path.join(ROOT, "data", "aidan_token.txt")  # gitignored: lets Aidan post as himself
if not os.path.exists(tokf):
    open(tokf, "w").write("aidan-" + secrets.token_urlsafe(24))
token = open(tokf).read().strip()
q = lambda v: "NULL" if v is None else (str(int(v)) if isinstance(v, (bool, int)) else "'" + str(v).replace("'", "''") + "'")
now = int(time.time() * 1000)
out = [f"INSERT INTO users (id,token,first_name,last_initial,city,state,created_at) VALUES ('aidanj',{q(token)},'Aidan','J','Minneapolis','MN',{now}) "
       "ON CONFLICT(id) DO UPDATE SET first_name='Aidan', last_initial='J', city='Minneapolis', state='MN';",
       "DELETE FROM messages WHERE user_id='aidanj' AND source='goodreads' AND book_id IN ("
       + ",".join(q(b["id"]) for b in seed["books"]) + ");"]
def dims(img):
    if not img or not img.startswith("/covers/"):
        return None, None
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", os.path.join(ROOT, "public", img.lstrip("/"))],
                         capture_output=True, text=True).stdout
    w = re.search(r"pixelWidth: (\d+)", out); h = re.search(r"pixelHeight: (\d+)", out)
    return (int(w.group(1)), int(h.group(1))) if w and h else (None, None)


def hashed(img):
    """/covers/x.jpg -> /covers/x.jpg?v=<sha1[:8] of the file>, so a browser that cached a
    404 or an older image during a deploy gap can never be stuck with it."""
    import hashlib
    if not img or not img.startswith("/covers/"):
        return img
    f = os.path.join(ROOT, "public", img.lstrip("/").split("?")[0])
    return img.split("?")[0] + "?v=" + hashlib.sha1(open(f, "rb").read()).hexdigest()[:8] if os.path.exists(f) else img


def year(v):
    m = re.search(r"(1[4-9]\d\d|20\d\d)", str(v or ""))
    return int(m.group(1)) if m else None


def read_ms(ref):
    try:
        return int(parsedate_to_datetime(ref.split("read ", 1)[1]).timestamp() * 1000)
    except Exception:
        return None


for i, b in enumerate(seed["books"]):
    c = b.get("cover") or {}
    w, h = dims(c.get("image"))
    cy = year(c.get("year")) if c.get("is_first_edition") else None
    out.append(
        "INSERT INTO books (id,title,author,first_published,unit,unit_count,cover_image,cover_source_url,cover_edition,"
        "cover_is_first,cover_fallback_reason,cover_year,cover_w,cover_h,openlibrary_work,preferred_editions,shelf_rank,created_by,created_at) VALUES ("
        + ",".join(q(v) for v in [b["id"], b["title"], b["author"], b.get("first_published"), b["unit"], b["unit_count"],
                                   hashed(c.get("image")), c.get("source_url"), c.get("edition"), c.get("is_first_edition"),
                                   c.get("fallback_reason"), cy, w, h, b.get("openlibrary_work"), json.dumps(b.get("preferred_editions") or []),
                                   i, "aidanj", now])
        + ") ON CONFLICT(id) DO UPDATE SET title=excluded.title, author=excluded.author, cover_image=excluded.cover_image,"
          " cover_source_url=excluded.cover_source_url, cover_edition=excluded.cover_edition, cover_is_first=excluded.cover_is_first,"
          " cover_fallback_reason=excluded.cover_fallback_reason, cover_year=excluded.cover_year, cover_w=excluded.cover_w, cover_h=excluded.cover_h, preferred_editions=excluded.preferred_editions, shelf_rank=excluded.shelf_rank,"
          " unit=excluded.unit, unit_count=excluded.unit_count, first_published=excluded.first_published, openlibrary_work=excluded.openlibrary_work;")
    r = b.get("review")
    if r:
        out.append("INSERT INTO messages (book_id,user_id,body,is_review,author_position,spoils_to,spoils_to_source,source,source_ref,created_at) VALUES ("
                   + ",".join(q(v) for v in [b["id"], "aidanj", r["body"], 1, b["unit_count"], b["unit_count"], "author_position",
                                              "goodreads", r["source_ref"], read_ms(r["source_ref"]) or now - 86400000 * 365]) + ");")
open(os.path.join(ROOT, "worker", "seed.sql"), "w").write("\n".join(out) + "\n")
print(len(out), "statements")
