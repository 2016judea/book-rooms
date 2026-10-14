"""data/seed.json -> worker/seed.sql (books + Aidan's verbatim Goodreads reviews as messages).
Idempotent: books upsert; Aidan's imported reviews are replaced."""
import json, os, secrets, time
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
       "DELETE FROM messages WHERE user_id='aidanj' AND source='goodreads';"]
for i, b in enumerate(seed["books"]):
    c = b.get("cover") or {}
    out.append(
        "INSERT INTO books (id,title,author,first_published,unit,unit_count,cover_image,cover_source_url,cover_edition,"
        "cover_is_first,cover_fallback_reason,openlibrary_work,preferred_editions,shelf_rank,created_by,created_at) VALUES ("
        + ",".join(q(v) for v in [b["id"], b["title"], b["author"], b.get("first_published"), b["unit"], b["unit_count"],
                                   c.get("image"), c.get("source_url"), c.get("edition"), c.get("is_first_edition"),
                                   c.get("fallback_reason"), b.get("openlibrary_work"), json.dumps(b.get("preferred_editions") or []),
                                   i, "aidanj", now])
        + ") ON CONFLICT(id) DO UPDATE SET title=excluded.title, author=excluded.author, cover_image=excluded.cover_image,"
          " cover_source_url=excluded.cover_source_url, cover_edition=excluded.cover_edition, cover_is_first=excluded.cover_is_first,"
          " cover_fallback_reason=excluded.cover_fallback_reason, preferred_editions=excluded.preferred_editions, shelf_rank=excluded.shelf_rank,"
          " unit=excluded.unit, unit_count=excluded.unit_count, first_published=excluded.first_published, openlibrary_work=excluded.openlibrary_work;")
    r = b.get("review")
    if r:
        out.append("INSERT INTO messages (book_id,user_id,body,is_review,author_position,spoils_to,spoils_to_source,source,source_ref,created_at) VALUES ("
                   + ",".join(q(v) for v in [b["id"], "aidanj", r["body"], 1, b["unit_count"], b["unit_count"], "author_position",
                                              "goodreads", r["source_ref"], now - (len(seed["books"]) - i)]) + ");")
open(os.path.join(ROOT, "worker", "seed.sql"), "w").write("\n".join(out) + "\n")
print(len(out), "statements")
