# Data model — group chats about books

Written from the need alone, before looking at any data (BUSINESS.md rule 5).

The need, in Aidan's words: *"Group chats about books. Leave reviews. Discuss ideas
with your peers."* A reader opens a book, says what they thought, and talks with
other people reading the same book — without having the ending spoiled, and without
having to scroll back through a day of chat to find out what the argument is.

## Entities and joins

```
user 1─* reading_position *─1 book 1─1 group_chat
user 1─* message *─1 group_chat          (a review is a message, is_review = 1)
group_chat 1─* digest ─* message          (each point cites the messages behind it)
book 1─* cover                            (one per edition; one is chosen)
user 2─* direct_thread *─1 book           (1:1 chat, the book is the context)
direct_thread 1─* direct_message
```

### user
| field | question it answers for the reader |
|---|---|
| user_id | which browser is me, across visits (per-browser token, no password) |
| first_name | who said this (required to post) |
| last_initial | which Aidan (required; the full last name is never stored) |
| city (nullable) | where they read — **this is what powers "near you" and in-person meetups** |
| state (nullable, 2-letter USPS) | same; chosen from a Census place list so it is always valid |
| created_at | how long has this person been around |

### book
| field | question it answers |
|---|---|
| book_id (slug) | which book, joined everywhere |
| title, author | what is it |
| first_published (year) | when was it written |
| unit (`chapter` or `percent`) | how do I say where I am — chapters where the count is known, else % through |
| unit_count | how many chapters, so "ch. 9 of 23" means something |
| openlibrary_work | where the metadata came from, so it can be checked |

### cover
| field | question it answers |
|---|---|
| book_id | which book |
| image_url | what does it look like (a real photograph or scan, never generated) |
| source_url | where the image came from, so it can be checked |
| edition (publisher, year) | which edition is pictured |
| is_first_edition | is this the first edition, or a fallback |
| fallback_reason | if not, why not (no first-edition image found) |

### group_chat
| field | question it answers |
|---|---|
| group_chat_id = book_id | one group chat per book |
| created_by, created_at | who opened it, when |
| member_count (derived) | how many readers are here |
| last_activity (derived) | is anyone talking now |

### reading_position
| field | question it answers |
|---|---|
| user_id, book_id | whose place, in which book |
| position | how far am I (chapter number, or percent) — sets what I may see |
| updated_at | when did I last move |

### message
| field | question it answers |
|---|---|
| message_id, group_chat_id, user_id | who said what, where |
| body | what they said |
| is_review | is this their review of the book (imported reviews are) |
| source (`group_chat`, `goodreads`), source_ref | written here, or imported verbatim and from where |
| author_position | where the author was when they said it |
| spoils_to | the furthest point in the book it refers to — **model-tagged**; I see it unblurred only once my position reaches it |
| spoils_to_source (`model`, `author_position`) | was the gate set by the model, or by the author's place (fallback when AI is off) |
| reply_to | which message this answers |
| created_at | when |

### digest ("what's being argued")
| field | question it answers |
|---|---|
| group_chat_id | which group chat |
| visible_to_position | the reader position it was computed for — a digest never summarises messages that reader can't see yet |
| points[] | the 2–3 live disagreements |
| points[].question | what is the disagreement, in a line |
| points[].sides[] | each side, as the readers put it |
| points[].message_ids[] | the messages behind it, so a late arrival can jump in with one tap |
| through_message_id | how current is it — recomputed when new messages arrive |
| created_at | when |

### direct_thread
| field | question it answers |
|---|---|
| thread_id | which 1:1 chat |
| user_a, user_b | the two readers |
| book_id | which book brought them together |
| blocked_by (nullable) | has one of them closed it |

### direct_message
| field | question it answers |
|---|---|
| message_id, thread_id, user_id | who said what, in which 1:1 chat |
| body | what they said (opens pre-filled with Aidan's meetup line) |
| created_at | when |
| last_read (per reader) | how many are unread — the inbox count |

## Rules the model obeys

- The model **tags** (`spoils_to`) and **summarises what readers said** (digest).
  It is never the source of a fact about the book shown as true. The digest
  attributes every claim to readers and cites message ids; ids that don't exist are
  dropped server-side.
- Imported reviews are verbatim and attributed. No review or message is invented.

## Reality check (filled after the model was written)

| field | source | fillable? |
|---|---|---|
| book title/author/year | Goodreads export (his shelves), Open Library | yes |
| unit_count (chapters) | known per book only where checked; else `percent` | partial — `percent` is the honest fallback, not a reshaped model |
| cover image + source + edition | hard-books-club/brand/covers (hand-sourced), Open Library editions with covers | yes; first-edition flag is checked per book, fallbacks logged |
| review messages (seed) | his Goodreads reviews, verbatim | yes, 34 of his 86 five-star books |
| message, position, digest | readers, live | yes, created in use |
| spoils_to | Claude, per message | yes when `ANTHROPIC_API_KEY` is set; falls back to author_position |

*Revised 2026-10-14, same day: "room" became "group chat", the review entity folded
into message (`is_review`), bylines and the 1:1 meetup chat were added (Aidan).*
