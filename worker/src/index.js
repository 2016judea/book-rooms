// Group-chat API for book-rooms. Cloudflare Worker + D1 (free tier).
// Vercel rewrites /v1/* here, so the browser sees one origin.
import { tagSpoiler, buildDigest, aiOn } from "./ai.js";

const MAX_BODY = 2000;
const now = () => Date.now();
const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
const bad = (msg, status = 400) => json({ error: msg }, status);
const rid = (n = 10) => {
  const a = new Uint8Array(n);
  crypto.getRandomValues(a);
  return [...a].map((b) => "abcdefghijkmnpqrstuvwxyz23456789"[b % 32]).join("");
};

export function byline(u) {
  if (!u || !u.first_name) return null;
  const name = `${u.first_name} ${u.last_initial}.`;
  return u.city && u.state ? `${name} · ${u.city}, ${u.state}` : name;
}

async function me(env, req) {
  const token = req.headers.get("x-reader");
  if (!token || token.length < 20) return null;
  return env.DB.prepare("SELECT * FROM users WHERE token = ?").bind(token).first();
}

async function ensureMe(env, req) {
  const token = req.headers.get("x-reader");
  if (!token || token.length < 20 || token.length > 80) return null;
  let u = await me(env, req);
  if (!u) {
    const id = rid(8);
    await env.DB.prepare("INSERT INTO users (id, token, created_at) VALUES (?, ?, ?)").bind(id, token, now()).run();
    u = { id, token };
  }
  return u;
}

const publicUser = (u) =>
  u && { id: u.id, first_name: u.first_name, last_initial: u.last_initial, city: u.city, state: u.state, byline: byline(u) };

function bookOut(b) {
  return {
    id: b.id, title: b.title, author: b.author, first_published: b.first_published,
    unit: b.unit, unit_count: b.unit_count,
    cover: b.cover_image ? {
      image: b.cover_image, source_url: b.cover_source_url, edition: b.cover_edition,
      is_first_edition: !!b.cover_is_first, fallback_reason: b.cover_fallback_reason,
    } : null,
    preferred_editions: b.preferred_editions ? JSON.parse(b.preferred_editions) : [],
  };
}

// ---------- Open Library: search + create a group chat for a new book ----------
const IMPRINTS = ["vintage international", "picador", "penguin classics"];
const yearOf = (s) => { const m = /(1[4-9]\d\d|20\d\d)/.exec(s || ""); return m ? +m[1] : null; };
const slugify = (s) => s.toLowerCase().split(/[:(]/)[0].replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 80);

async function olJSON(url) {
  const r = await fetch(url, { headers: { "user-agent": "book-rooms/0.1 (aidanjude2016@gmail.com)" } });
  if (!r.ok) return null;
  return r.json();
}

async function pickCover(workKey, firstYear) {
  const eds = (await olJSON(`https://openlibrary.org${workKey}/editions.json?limit=300`)) || {};
  const entries = (eds.entries || []).filter((e) => e.covers && e.covers[0] > 0).map((e) => {
    const langs = (e.languages || []).map((l) => l.key);
    return { ...e, _y: yearOf(e.publish_date), _pub: (e.publishers || []).join(", "),
      _eng: !langs.length || langs.includes("/languages/eng") };
  });
  const dated = entries.filter((e) => e._y && e._eng).sort((a, b) => a._y - b._y);
  const pack = (e, first, reason) => ({
    image: `https://covers.openlibrary.org/b/id/${e.covers[0]}-L.jpg`,
    source_url: `https://openlibrary.org${e.key}`,
    edition: `${e._pub || "unknown publisher"}, ${e.publish_date || "?"}`,
    is_first: first ? 1 : 0, reason,
  });
  if (firstYear) {
    const f = dated.find((e) => e._y === firstYear);
    if (f) return pack(f, true, null);
  }
  for (const imp of IMPRINTS) {
    const f = dated.find((e) => e._pub.toLowerCase().includes(imp) || JSON.stringify(e.series || "").toLowerCase().includes(imp));
    if (f) return pack(f, false, `no first-edition image found; fell back to ${imp}`);
  }
  if (dated[0]) return pack(dated[0], false, "no first-edition or preferred-imprint image; earliest English edition with a cover");
  if (entries[0]) return pack(entries[0], false, "first edition with any cover");
  return null;
}

async function search(env, q) {
  q = (q || "").trim().slice(0, 100);
  if (q.length < 2) return { local: [], openlibrary: [] };
  const like = `%${q.replace(/[%_]/g, "")}%`;
  const local = await env.DB.prepare(
    "SELECT * FROM books WHERE title LIKE ?1 OR author LIKE ?1 ORDER BY shelf_rank IS NULL, shelf_rank LIMIT 8"
  ).bind(like).all();
  const have = new Set((local.results || []).map((b) => b.openlibrary_work));
  const ol = await olJSON(`https://openlibrary.org/search.json?${new URLSearchParams({
    q, fields: "key,title,author_name,first_publish_year,cover_i,edition_count", limit: "8" })}`);
  const openlibrary = ((ol && ol.docs) || [])
    .filter((d) => d.author_name && !have.has(d.key))
    .map((d) => ({ work: d.key, title: d.title, author: d.author_name[0], first_published: d.first_publish_year }));
  return { local: (local.results || []).map(bookOut), openlibrary };
}

async function createFromOL(env, workKey, user) {
  if (!/^\/works\/OL\d+W$/.test(workKey || "")) return bad("bad work");
  const existing = await env.DB.prepare("SELECT * FROM books WHERE openlibrary_work = ?").bind(workKey).first();
  if (existing) return json({ book: bookOut(existing) });
  const work = await olJSON(`https://openlibrary.org${workKey}.json`);
  if (!work) return bad("not found on Open Library", 404);
  const s = await olJSON(`https://openlibrary.org/search.json?${new URLSearchParams({ q: `key:${workKey}`, fields: "key,title,author_name,first_publish_year" })}`);
  const doc = (s && s.docs && s.docs[0]) || {};
  const title = work.title || doc.title;
  const author = (doc.author_name || ["Unknown"])[0];
  const fy = doc.first_publish_year || null;
  const cover = await pickCover(workKey, fy);
  let id = slugify(title);
  if (await env.DB.prepare("SELECT 1 FROM books WHERE id = ?").bind(id).first()) id = `${id}-${slugify(author).split("-").pop()}`;
  if (await env.DB.prepare("SELECT 1 FROM books WHERE id = ?").bind(id).first()) id = `${id}-${rid(4)}`;
  await env.DB.prepare(
    `INSERT INTO books (id,title,author,first_published,unit,unit_count,cover_image,cover_source_url,cover_edition,
      cover_is_first,cover_fallback_reason,openlibrary_work,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`
  ).bind(id, title, author, fy, "percent", 100, cover?.image ?? null, cover?.source_url ?? null, cover?.edition ?? null,
    cover?.is_first ?? null, cover?.reason ?? null, workKey, user?.id ?? null, now()).run();
  return json({ book: bookOut(await env.DB.prepare("SELECT * FROM books WHERE id = ?").bind(id).first()) });
}

// ---------- group chat ----------
async function chat(env, bookId, user) {
  const book = await env.DB.prepare("SELECT * FROM books WHERE id = ?").bind(bookId).first();
  if (!book) return bad("no such book", 404);
  const rows = await env.DB.prepare(
    `SELECT m.id, m.body, m.is_review, m.spoils_to, m.spoils_to_source, m.author_position, m.source, m.source_ref,
            m.created_at, u.id AS uid, u.first_name, u.last_initial, u.city, u.state
       FROM messages m JOIN users u ON u.id = m.user_id WHERE m.book_id = ? ORDER BY m.id LIMIT 1000`
  ).bind(bookId).all();
  let position = null;
  if (user) {
    const p = await env.DB.prepare("SELECT position FROM positions WHERE user_id = ? AND book_id = ?").bind(user.id, bookId).first();
    position = p ? p.position : null;
  }
  const readers = new Map();
  const messages = (rows.results || []).map((r) => {
    const u = { id: r.uid, first_name: r.first_name, last_initial: r.last_initial, city: r.city, state: r.state };
    readers.set(r.uid, publicUser(u));
    return {
      id: r.id, body: r.body, is_review: !!r.is_review, spoils_to: r.spoils_to, spoils_to_source: r.spoils_to_source,
      source: r.source, source_ref: r.source_ref, created_at: r.created_at, user: publicUser(u),
    };
  });
  return json({ book: bookOut(book), messages, readers: [...readers.values()], position, me: publicUser(user), ai: aiOn(env) });
}

async function postMessage(env, ctx, bookId, user, body) {
  const book = await env.DB.prepare("SELECT * FROM books WHERE id = ?").bind(bookId).first();
  if (!book) return bad("no such book", 404);
  if (!user.first_name) return bad("name needed", 409);
  const text = String(body.body || "").trim().slice(0, MAX_BODY);
  if (!text) return bad("empty");
  const recent = await env.DB.prepare("SELECT COUNT(*) AS n FROM messages WHERE user_id = ? AND created_at > ?").bind(user.id, now() - 60000).first();
  if (recent.n >= 12) return bad("slow down", 429);
  const p = await env.DB.prepare("SELECT position FROM positions WHERE user_id = ? AND book_id = ?").bind(user.id, bookId).first();
  const pos = p ? p.position : book.unit_count; // unknown position: gate as if finished, until the model tags it
  const res = await env.DB.prepare(
    "INSERT INTO messages (book_id,user_id,body,author_position,spoils_to,spoils_to_source,created_at) VALUES (?,?,?,?,?,?,?)"
  ).bind(bookId, user.id, text, p ? p.position : null, pos, "author_position", now()).run();
  const id = res.meta.last_row_id;
  if (aiOn(env)) {
    ctx.waitUntil((async () => {
      const t = await tagSpoiler(env, book, text);
      if (t != null) await env.DB.prepare("UPDATE messages SET spoils_to = ?, spoils_to_source = 'model' WHERE id = ?").bind(t, id).run();
    })().catch((e) => console.log("tag failed", e)));
  }
  return json({ id });
}

async function digest(env, ctx, bookId, pos) {
  if (!aiOn(env)) return json({ points: [], ai: false });
  const book = await env.DB.prepare("SELECT * FROM books WHERE id = ?").bind(bookId).first();
  if (!book) return bad("no such book", 404);
  pos = Math.max(0, Math.min(book.unit_count, pos | 0));
  const rows = await env.DB.prepare(
    `SELECT m.id, m.body, m.user_id, u.first_name, u.last_initial FROM messages m JOIN users u ON u.id = m.user_id
      WHERE m.book_id = ? AND m.spoils_to <= ? ORDER BY m.id DESC LIMIT 150`
  ).bind(bookId, pos).all();
  const msgs = (rows.results || []).reverse();
  const through = msgs.length ? msgs[msgs.length - 1].id : 0;
  const cached = await env.DB.prepare("SELECT * FROM digests WHERE book_id = ? AND visible_to_position = ?").bind(bookId, pos).first();
  const voices = new Set(msgs.map((m) => m.user_id)).size;
  if (voices < 2) return json({ points: [], voices, ai: true });
  const fresh = cached && cached.through_message_id === through;
  if (!fresh) {
    const job = (async () => {
      const points = await buildDigest(env, book, msgs);
      if (points) {
        await env.DB.prepare(
          "INSERT OR REPLACE INTO digests (book_id,visible_to_position,through_message_id,points,created_at) VALUES (?,?,?,?,?)"
        ).bind(bookId, pos, through, JSON.stringify(points), now()).run();
      }
      return points;
    })();
    if (!cached) {
      const points = await job.catch(() => null);
      return json({ points: points || [], voices, ai: true, stale: false });
    }
    ctx.waitUntil(job.catch((e) => console.log("digest failed", e)));
  }
  return json({ points: JSON.parse(cached.points), voices, ai: true, stale: !fresh });
}

// ---------- 1:1 chats ----------
async function openThread(env, user, otherId, bookId) {
  if (!user.first_name) return bad("name needed", 409);
  if (otherId === user.id) return bad("that's you");
  const other = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(otherId).first();
  const book = await env.DB.prepare("SELECT id FROM books WHERE id = ?").bind(bookId).first();
  if (!other || !book) return bad("not found", 404);
  const [a, b] = [user.id, otherId].sort();
  let t = await env.DB.prepare("SELECT * FROM direct_threads WHERE book_id = ? AND user_a = ? AND user_b = ?").bind(bookId, a, b).first();
  if (!t) {
    const id = rid(10);
    await env.DB.prepare("INSERT INTO direct_threads (id,book_id,user_a,user_b,created_at) VALUES (?,?,?,?,?)").bind(id, bookId, a, b, now()).run();
    t = { id };
  }
  return json({ thread_id: t.id });
}

async function threadFor(env, user, tid) {
  const t = await env.DB.prepare("SELECT * FROM direct_threads WHERE id = ?").bind(tid).first();
  if (!t || (t.user_a !== user.id && t.user_b !== user.id)) return null;
  return t;
}

async function getThread(env, user, tid) {
  const t = await threadFor(env, user, tid);
  if (!t) return bad("not found", 404);
  const otherId = t.user_a === user.id ? t.user_b : t.user_a;
  const other = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(otherId).first();
  const book = await env.DB.prepare("SELECT * FROM books WHERE id = ?").bind(t.book_id).first();
  const rows = await env.DB.prepare("SELECT id, user_id, body, created_at FROM direct_messages WHERE thread_id = ? ORDER BY id LIMIT 1000").bind(tid).all();
  const msgs = rows.results || [];
  const last = msgs.length ? msgs[msgs.length - 1].id : 0;
  await env.DB.prepare("INSERT OR REPLACE INTO direct_reads (thread_id,user_id,last_read_id) VALUES (?,?,?)").bind(tid, user.id, last).run();
  return json({
    id: t.id, book: bookOut(book), other: publicUser(other), me: publicUser(user),
    blocked: !!t.blocked_by, blocked_by_me: t.blocked_by === user.id,
    messages: msgs.map((m) => ({ id: m.id, mine: m.user_id === user.id, body: m.body, created_at: m.created_at })),
  });
}

async function postThread(env, user, tid, body) {
  if (!user.first_name) return bad("name needed", 409);
  const t = await threadFor(env, user, tid);
  if (!t) return bad("not found", 404);
  if (t.blocked_by) return bad("blocked", 403);
  const text = String(body.body || "").trim().slice(0, MAX_BODY);
  if (!text) return bad("empty");
  const res = await env.DB.prepare("INSERT INTO direct_messages (thread_id,user_id,body,created_at) VALUES (?,?,?,?)").bind(tid, user.id, text, now()).run();
  await env.DB.prepare("INSERT OR REPLACE INTO direct_reads (thread_id,user_id,last_read_id) VALUES (?,?,?)").bind(tid, user.id, res.meta.last_row_id).run();
  return json({ id: res.meta.last_row_id });
}

async function inbox(env, user) {
  const rows = await env.DB.prepare(
    `SELECT t.id, t.book_id, t.blocked_by, CASE WHEN t.user_a = ?1 THEN t.user_b ELSE t.user_a END AS other_id,
            (SELECT MAX(id) FROM direct_messages d WHERE d.thread_id = t.id) AS last_id,
            (SELECT body FROM direct_messages d WHERE d.thread_id = t.id ORDER BY id DESC LIMIT 1) AS last_body,
            (SELECT created_at FROM direct_messages d WHERE d.thread_id = t.id ORDER BY id DESC LIMIT 1) AS last_at,
            (SELECT COUNT(*) FROM direct_messages d WHERE d.thread_id = t.id AND d.user_id != ?1
               AND d.id > COALESCE((SELECT last_read_id FROM direct_reads r WHERE r.thread_id = t.id AND r.user_id = ?1), 0)) AS unread
       FROM direct_threads t WHERE (t.user_a = ?1 OR t.user_b = ?1) ORDER BY last_at DESC`
  ).bind(user.id).all();
  const out = [];
  for (const r of rows.results || []) {
    if (!r.last_id) continue; // an opened-but-empty thread is not a conversation yet
    const other = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(r.other_id).first();
    const book = await env.DB.prepare("SELECT id,title,author FROM books WHERE id = ?").bind(r.book_id).first();
    out.push({ id: r.id, other: publicUser(other), book, last_body: r.last_body, last_at: r.last_at, unread: r.blocked_by ? 0 : r.unread });
  }
  return json({ threads: out, unread: out.reduce((n, t) => n + t.unread, 0) });
}

// ---------- router ----------
export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const path = url.pathname.replace(/\/+$/, "");
    const m = (re) => re.exec(path);
    const body = req.method === "POST" || req.method === "PUT" ? await req.json().catch(() => ({})) : {};
    try {
      if (path === "/v1/health") return json({ ok: true, ai: aiOn(env) });
      if (path === "/v1/books" && req.method === "GET") {
        const r = await env.DB.prepare("SELECT * FROM books WHERE shelf_rank IS NOT NULL ORDER BY shelf_rank").all();
        return json({ books: (r.results || []).map(bookOut) });
      }
      if (path === "/v1/search") return json(await search(env, url.searchParams.get("q")));
      let g;
      if ((g = m(/^\/v1\/books\/([a-z0-9-]+)$/)) && req.method === "GET") {
        const b = await env.DB.prepare("SELECT * FROM books WHERE id = ?").bind(g[1]).first();
        return b ? json({ book: bookOut(b) }) : bad("no such book", 404);
      }
      if ((g = m(/^\/v1\/users\/([a-z0-9]+)$/))) {
        const u = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(g[1]).first();
        return u && u.first_name ? json({ user: publicUser(u) }) : bad("not found", 404);
      }
      if ((g = m(/^\/v1\/users\/([a-z0-9]+)$/))) {
        const u = await env.DB.prepare("SELECT * FROM users WHERE id = ?").bind(g[1]).first();
        return u && u.first_name ? json({ user: publicUser(u) }) : bad("not found", 404);
      }
      if ((g = m(/^\/v1\/books\/([a-z0-9-]+)\/chat$/))) return chat(env, g[1], await me(env, req));
      if ((g = m(/^\/v1\/books\/([a-z0-9-]+)\/digest$/))) return digest(env, ctx, g[1], +url.searchParams.get("pos") || 0);

      if (path === "/v1/admin/retag" && req.method === "POST") {
        if (!env.ADMIN_TOKEN || req.headers.get("x-admin") !== env.ADMIN_TOKEN) return bad("no", 403);
        if (!aiOn(env)) return bad("ai off", 409);
        const rows = await env.DB.prepare(
          "SELECT m.id, m.body, m.book_id FROM messages m WHERE m.spoils_to_source != 'model' ORDER BY m.id LIMIT ?"
        ).bind(Math.min(20, body.limit || 8)).all();
        const done = [];
        await Promise.all((rows.results || []).map(async (r) => {
          const book = await env.DB.prepare("SELECT * FROM books WHERE id = ?").bind(r.book_id).first();
          const t = await tagSpoiler(env, book, r.body);
          if (t != null) {
            await env.DB.prepare("UPDATE messages SET spoils_to = ?, spoils_to_source = 'model' WHERE id = ?").bind(t, r.id).run();
            done.push({ id: r.id, book: r.book_id, spoils_to: t, of: book.unit_count });
          }
        }));
        return json({ done, remaining: (rows.results || []).length - done.length });
      }

      const user = await ensureMe(env, req);
      if (!user) return bad("no reader token", 401);
      if (path === "/v1/books" && req.method === "POST") return createFromOL(env, body.work, user);
      if (path === "/v1/me" && req.method === "GET") return json({ me: publicUser(user) });
      if (path === "/v1/me" && req.method === "PUT") {
        const first = String(body.first_name || "").trim().slice(0, 40);
        const last = String(body.last_name || "").trim();
        if (!first || !last) return bad("first name and last name are required");
        const initial = last[0].toUpperCase();
        let city = String(body.city || "").trim().slice(0, 60) || null;
        let state = String(body.state || "").trim().toUpperCase() || null;
        if (!city || !/^[A-Z]{2}$/.test(state || "")) { city = null; state = null; }
        await env.DB.prepare("UPDATE users SET first_name = ?, last_initial = ?, city = ?, state = ? WHERE id = ?")
          .bind(first, initial, city, state, user.id).run();
        return json({ me: publicUser({ ...user, first_name: first, last_initial: initial, city, state }) });
      }
      if ((g = m(/^\/v1\/books\/([a-z0-9-]+)\/position$/)) && req.method === "PUT") {
        const pos = Math.max(0, Math.min(1000, body.position | 0));
        await env.DB.prepare("INSERT OR REPLACE INTO positions (user_id,book_id,position,updated_at) VALUES (?,?,?,?)").bind(user.id, g[1], pos, now()).run();
        return json({ position: pos });
      }
      if ((g = m(/^\/v1\/books\/([a-z0-9-]+)\/messages$/)) && req.method === "POST") return postMessage(env, ctx, g[1], user, body);
      if (path === "/v1/dm" && req.method === "POST") return openThread(env, user, body.user_id, body.book_id);
      if (path === "/v1/dm" && req.method === "GET") return inbox(env, user);
      if ((g = m(/^\/v1\/dm\/([a-z0-9]+)$/)) && req.method === "GET") return getThread(env, user, g[1]);
      if ((g = m(/^\/v1\/dm\/([a-z0-9]+)$/)) && req.method === "POST") return postThread(env, user, g[1], body);
      if ((g = m(/^\/v1\/dm\/([a-z0-9]+)\/block$/)) && req.method === "POST") {
        const t = await threadFor(env, user, g[1]);
        if (!t) return bad("not found", 404);
        if (body.unblock && t.blocked_by !== user.id) return bad("only the person who blocked can unblock", 403);
        if (!body.unblock && t.blocked_by) return json({ ok: true });
        await env.DB.prepare("UPDATE direct_threads SET blocked_by = ? WHERE id = ?").bind(body.unblock ? null : user.id, t.id).run();
        return json({ ok: true });
      }
      return bad("not found", 404);
    } catch (e) {
      console.log("error", e && e.stack);
      return bad("server error", 500);
    }
  },
};
