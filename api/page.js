// /b/<id> — the SPA, with link-preview tags for that book's group chat so a link
// texted to a friend unfurls as the first-edition cover.
import { readFileSync } from "node:fs";

const API = "https://book-rooms-api.small-business-intelligence-mcp.workers.dev";
let shell = null;
function loadShell() {
  if (shell) return shell;
  for (const p of [new URL("../public/index.html", import.meta.url), `${process.cwd()}/public/index.html`]) {
    try { return (shell = readFileSync(p, "utf8")); } catch (_) {}
  }
  throw new Error("index.html not found");
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export default async function handler(req, res) {
  const id = String(req.query.id || "").replace(/[^a-z0-9-]/g, "");
  const host = req.headers["x-forwarded-host"] || req.headers.host;
  const origin = `https://${host}`;
  let book = null;
  try {
    const r = await fetch(`${API}/v1/books/${id}`);
    if (r.ok) book = (await r.json()).book;
  } catch (_) {}
  let html = loadShell();
  if (book) {
    const title = `${book.title} — ${book.author}`;
    const img = book.cover && book.cover.image ? (book.cover.image.startsWith("http") ? book.cover.image : origin + book.cover.image) : null;
    const tags = [
      `<meta property="og:title" content="${esc(title)}">`,
      `<meta property="og:description" content="Read with community.">`,
      `<meta name="description" content="Read with community.">`,
      `<meta property="og:type" content="website">`,
      `<meta property="og:url" content="${esc(origin + "/b/" + book.id)}">`,
      img ? `<meta property="og:image" content="${esc(img)}">` : "",
      `<meta name="twitter:card" content="${img ? "summary_large_image" : "summary"}">`,
    ].filter(Boolean).join("\n");
    html = html.replace(/<!--OG-->[\s\S]*?<!--\/OG-->/, `<!--OG-->\n${tags}\n<!--/OG-->`)
               .replace(/<title>[^<]*<\/title>/, `<title>${esc(title)}</title>`);
  }
  res.setHeader("content-type", "text/html; charset=utf-8");
  res.setHeader("cache-control", "public, max-age=0, s-maxage=300, stale-while-revalidate=86400");
  res.status(book ? 200 : 404).send(html);
}
