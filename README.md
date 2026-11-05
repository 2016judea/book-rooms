# Read with community.

**Live:** https://read-with-community.vercel.app

## Vision

Aidan, verbatim:

> honestly the true idea is that this is a place where I can chat with my friends about books, anyone can and it will start by being my friends and family — but I'd be amazing if the platform grew and real people started having book discussions in person again

## Brand principle

Aidan, verbatim:

> their is such a craving for human connection, I don't wanna shy away from this on the website design and branding and marketing — we have an humanly obligation here

People are the design. Real first names and real cities are prominent. Nothing reads like a forum, a feed or an anonymous comment section. No invented counts, avatars or "X readers online"; the only numbers shown come from the database.

## Why it exists

People start a chat with another reader, someone in the same city or state, to meet in person and talk about the book, or to set up a local book club. Everything below serves that.

## Spec (pinned)

Each line is something Aidan asked for on 2026-10-14. Don't drift from them.

1. **The 40/60 first screen.** The top 40% of the first screen, at 390×664 and at 1440×900, is the words **"Read with community."** set large enough that the type fills it. Nothing else is up there. The board of covers starts directly below and fills the other 60%.
2. **Black and white is the UX.** Pure black and pure white. No accent colour, no decorative greys, no coloured links. Hierarchy comes from size, weight and inversion. Spoiler and digest states are black and white too. **The covers are the only colour** and stay as printed.
3. **The board.** A wall you scroll down through, not a carousel. **It shows the western canon, ranked by relevance in modern culture** (Aidan, 2026-10-14):
   - *Pool:* the works in Harold Bloom's *The Western Canon* (1994) appendix, plus his five-stars by Bloom's 26 central authors. Bloom lists Shakespeare only as "Plays", so that entry is expanded to the plays. The source copy is `data/canon/bloom_appendix.html`, from the list Wikipedia links.
   - *Signal:* English Wikipedia pageviews over the last 12 complete months, counted on the work's own article (Hamlet, not Shakespeare), with the matched article logged per work. Open Library read counts are kept as a secondary column only.
   - *Selection* (Aidan, 2026-10-15: "only ones ive read. Plus the next top 5"): every canon work on his Goodreads read shelf, at any rating and matched on the work rather than the edition, plus the 5 most-viewed canon works he hasn't read. The whole board is ordered by pageviews, has no cap and no pins, and the unread five carry no marker. Non-western works are excluded, with reasons in `data/canon/excluded.tsv`. `ranking.csv` has a read column and the Goodreads entry behind each match. Refresh with `scripts/build_canon.py` then `scripts/build_board.py`.
   - *Seeded with his words:* every board chat for a book he has read opens with his Goodreads review, verbatim, at any rating, signed `Aidan J. · Minneapolis, MN`, dated with his read date and spoiler-tagged. No review means an empty chat; nothing is written for him.
   - His five-stars that miss the cut, and every other book, keep their group chats and reviews, reachable through search and `/b/<id>`. Nothing is deleted.
   Every cover gets equal dignity: the same column width at its true aspect ratio, so heights vary and widths never do. Quiet, even gutters, with 3 columns at 390 and 7 at 1440.
   Design principle, Aidan verbatim: *"these the humankinds most profound ideas."* (This is direction for the board, not copy for the page.)
   Under each cover sits a museum label in EB Garamond: title, author and first-edition year (only when the pictured cover is a verified first edition). Below it is the people line from the database ("Aidan J., Sarah K. +3", plus "2 near you" when the viewer gave a location and it's true). A chat with a message in the last 24 hours gets one small black dot. Labels are 14px or larger, black on white.
   His 86 five-star books were seeded from his Goodreads export (`goodreads_reads.json`, rating = 5). New canon chats start empty, and their covers skip straight to the imprint order, because Open Library dates are too unreliable to call anything a first edition. Images are real photographs or scans, never generated. Source order: first edition, then Vintage International, then Picador, then Penguin Classics (vintage printings). Each image's source is in `data/covers/<slug>/sources.csv`, in the same columns as Intellectual Reads (`book, option, edition, year, source_url`). The 11 books hand-sourced in `~/Desktop/workspace/hard-books-club/brand/covers/` are reused as they are. `data/cover_log.tsv` lists every fallback.
4. **Search goes sticky after a short scroll.** Once the headline scrolls away, a search bar (17px, so iOS doesn't zoom) and the Inbox link pin to the top of the board. Search by title or author. A book that has a group chat opens it. A book without one gets one, with Open Library metadata and a cover chosen by the same rule.
5. **One tap from a cover into the group chat.** No details page, no sign-up wall, no name prompt to read. The back gesture returns to the covers.
6. **Each book is a group chat**, laid out like an iPhone Messages group thread. The header shows the title and author, with back on the left. Your messages are black bubbles on the right. Everyone else's are white bubbles with a black hairline on the left. A review is a message.
7. **His reviews are messages in the thread**, verbatim, by `Aidan J. · Minneapolis, MN`. 34 of the 86 books have one. A book without a review opens empty, and nothing is invented.
8. **Bylines** read `First L. · City, ST`. City and state are optional, and without them the byline is `First L.`. Only the last initial is stored.
9. **One composer at the bottom.** A single line that grows as you type. On the first send the message is held, and a sheet asks for first name, last name and an optional city (a Census list of US places, so the state is always a valid code). On confirm, the held message posts. If the sheet is dismissed, the draft stays.
10. **Spoiler gating by place in the book.** Each reader sets where they are, by chapter where the count is known (Blood Meridian: 23) and by percent otherwise. Claude tags each message with the furthest point it reveals. Messages from further ahead stay blurred until the reader catches up or taps to read.
11. **"What's being argued."** A pinned card at the top of the thread names up to three live disagreements, each side attributed to the reader who said it. Tapping one highlights the messages behind it and puts you in the composer. It only summarises messages the reader is allowed to see.
12. **Tap a byline to open a 1:1 chat** with that person, titled with their byline and the book. The composer opens with his line, verbatim: `yo you wanna meetup and talk about the book in person?` They can send it as is or edit it. The same name intercept applies.
13. **Near you.** Readers in your city, then your state, show at the top of a group chat with a "near you" marker. If you gave no location this is skipped, and nobody is asked for a location just to browse.
14. **Inbox.** One link in the sticky search bar shows an unread count. No email or phone number is ever shown or exchanged. Each 1:1 chat has a Block button.
15. **Shareable links.** Every group chat has its own URL (`/b/blood-meridian`) and a Share button that opens the iOS share sheet. Pasted into iMessage, the link unfurls with the first-edition cover, `<Book> — <Author>` and "Read with community." A friend who opens it lands in the chat, scrolled to the newest message.
16. **Copy.** Any copy beyond his verbatim lines is a placeholder for him to replace: the sheet and button labels, "What's being argued", "Near you", the empty states, and the 1:1 privacy line.

## How it works

- `public/index.html` is the whole app (vanilla JS, no build). Vercel serves it.
- `api/page.js` serves `/b/<id>` with that book's link-preview tags.
- `worker/` is a Cloudflare Worker with a D1 database (free tier) holding books, readers, messages, positions, digests and 1:1 chats. Vercel rewrites `/v1/*` to it, so the browser sees one origin. Schema in `worker/schema.sql`, model in `DATA_MODEL.md`.
- `worker/src/ai.js` has the two Claude calls (`claude-opus-5-5`, structured JSON output, server-side refusal fallback). The model tags spoilers and summarises what readers said. It is never the source of a fact about the book shown as true. Turn both off with `AI_ENABLED = "0"` in `worker/wrangler.toml`. With AI off, a message is gated at its author's position.
- Identity is a per-browser token in localStorage, with no accounts. A reply reaches someone only when they come back in the same browser.
- Analytics: Vercel Web Analytics plus the shared PostHog block (per-browser IDs).
- Cover URLs carry `?v=<sha1 of the file>`, generated by the data build. `/covers/*` is cached for 1 hour, because Vercel applied the old year-long `immutable` header to 404s as well.

## Rebuild

```sh
python3 scripts/build_seed.py      # covers + reviews -> data/seed.json (network, cached)
python3 scripts/seed_sql.py        # -> worker/seed.sql
cd worker && wrangler d1 execute book-rooms --remote --file=seed.sql && wrangler deploy
npx vercel deploy --prod           # from the repo root
```

Credentials come from `~/Desktop/workspace/bricks/.env`. The Worker holds the `ANTHROPIC_API_KEY` and `ADMIN_TOKEN` secrets. `POST /v1/admin/retag` (header `x-admin`) re-tags messages that were never tagged by the model.

MIT licence. Book metadata from Open Library. Cover images belong to their publishers and photographers, and each one's source is recorded.
