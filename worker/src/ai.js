// The two AI steps. Both do a step of the reader's work; neither is ever the
// source of a fact about the book that gets shown as true.
//   tagSpoiler  — how far into the book does this message reach? (a gate, not a claim)
//   buildDigest — what are readers arguing about? (attributed to readers, cites message ids)
import Anthropic from "@anthropic-ai/sdk";

const MODEL = "claude-opus-5-5";

export const aiOn = (env) => env.AI_ENABLED === "1" && !!env.ANTHROPIC_API_KEY;

async function structured(env, system, user, schema, effort = "low") {
  const client = new Anthropic({ apiKey: env.ANTHROPIC_API_KEY, timeout: 60_000, maxRetries: 1 });
  const res = await client.beta.messages.create({
    model: MODEL,
    max_tokens: 4000,
    betas: ["server-side-fallback-2026-07-01"],
    fallbacks: "default",
    output_config: { effort, format: { type: "json_schema", schema } },
    system,
    messages: [{ role: "user", content: user }],
  });
  if (res.stop_reason === "refusal" || res.stop_reason === "max_tokens") return null;
  const text = res.content.filter((b) => b.type === "text").map((b) => b.text).join("");
  try { return JSON.parse(text); } catch { return null; }
}

function unitWords(book) {
  return book.unit === "chapter"
    ? `The book has ${book.unit_count} chapters. Answer with a chapter number from 0 to ${book.unit_count}.`
    : `Answer with a percentage of the way through the book, from 0 to 100.`;
}

export async function tagSpoiler(env, book, text) {
  const system =
    "You gate spoilers in a book group chat. Readers set how far they are in the book; a message stays " +
    "blurred for anyone who has not reached the furthest point it reveals. Your answer is only used as " +
    "that gate. It is never shown to anyone as a statement about the book.\n\n" +
    "Return the furthest point in the book whose events, deaths, twists, reveals or ending this message " +
    "names, describes or clearly implies. Opinions about the prose, the author, themes in general, or " +
    "the opening premise reach 0. A message about the ending reaches the end. When unsure between two " +
    "points, pick the later one: a reader who sees a spoiler early is harmed, one who waits is not.";
  const user = `Book: ${book.title} by ${book.author}.\n${unitWords(book)}\n\nMessage:\n"""${text}"""`;
  const out = await structured(env, system, user, {
    type: "object",
    properties: { spoils_to: { type: "integer" } },
    required: ["spoils_to"],
    additionalProperties: false,
  });
  if (!out || typeof out.spoils_to !== "number") return null;
  return Math.max(0, Math.min(book.unit_count, Math.round(out.spoils_to)));
}

export async function buildDigest(env, book, msgs) {
  const system =
    "You read a book group chat and name the live disagreements, so someone arriving late can join in. " +
    "Rules: only report what readers in the chat said, attributed to them by first name. Never state a " +
    "fact about the book yourself, never add your own opinion, never summarise the plot. A disagreement " +
    "needs at least two readers taking different positions; if there are none, return an empty list. " +
    "Return at most 3, the liveliest first. Each question is one short line a reader would say. Each " +
    "side is one short line, starting with the reader's first name. Cite the ids of the messages behind it.";
  const lines = msgs.map((m) => `[${m.id}] ${m.first_name} ${m.last_initial}.: ${m.body.slice(0, 1200)}`).join("\n");
  const user = `Book: ${book.title} by ${book.author}.\n\nChat:\n${lines}`;
  const out = await structured(env, system, user, {
    type: "object",
    properties: {
      points: {
        type: "array",
        items: {
          type: "object",
          properties: {
            question: { type: "string" },
            sides: { type: "array", items: { type: "string" } },
            message_ids: { type: "array", items: { type: "integer" } },
          },
          required: ["question", "sides", "message_ids"],
          additionalProperties: false,
        },
      },
    },
    required: ["points"],
    additionalProperties: false,
  }, "medium");
  if (!out || !Array.isArray(out.points)) return null;
  const known = new Set(msgs.map((m) => m.id));
  return out.points
    .map((p) => ({ question: p.question, sides: p.sides.slice(0, 3), message_ids: p.message_ids.filter((id) => known.has(id)) }))
    .filter((p) => p.message_ids.length >= 2)
    .slice(0, 3);
}
