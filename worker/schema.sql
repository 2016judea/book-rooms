-- See DATA_MODEL.md. A review is a message with is_review = 1.
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,            -- public id, shown in links and bylines
  token TEXT UNIQUE NOT NULL,     -- per-browser secret, never shown
  first_name TEXT,
  last_initial TEXT,
  city TEXT,                      -- nullable; powers "near you" and meetups
  state TEXT,                     -- nullable; two-letter USPS code
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS books (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  author TEXT NOT NULL,
  first_published INTEGER,
  unit TEXT NOT NULL DEFAULT 'percent',
  unit_count INTEGER NOT NULL DEFAULT 100,
  cover_image TEXT,
  cover_source_url TEXT,
  cover_edition TEXT,
  cover_is_first INTEGER,
  cover_fallback_reason TEXT,
  openlibrary_work TEXT,
  preferred_editions TEXT,        -- JSON [{label,url}]
  shelf_rank INTEGER,             -- order on the covers row; null = not on the row
  created_by TEXT,
  created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  body TEXT NOT NULL,
  is_review INTEGER NOT NULL DEFAULT 0,
  author_position INTEGER,
  spoils_to INTEGER NOT NULL DEFAULT 0,
  spoils_to_source TEXT NOT NULL DEFAULT 'author_position',
  source TEXT NOT NULL DEFAULT 'group_chat',
  source_ref TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_book ON messages(book_id, id);
CREATE TABLE IF NOT EXISTS positions (
  user_id TEXT NOT NULL,
  book_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (user_id, book_id)
);
CREATE TABLE IF NOT EXISTS digests (
  book_id TEXT NOT NULL,
  visible_to_position INTEGER NOT NULL,
  through_message_id INTEGER NOT NULL,
  points TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (book_id, visible_to_position)
);
CREATE TABLE IF NOT EXISTS direct_threads (
  id TEXT PRIMARY KEY,
  book_id TEXT NOT NULL,
  user_a TEXT NOT NULL,           -- lower id of the pair
  user_b TEXT NOT NULL,
  blocked_by TEXT,
  created_at INTEGER NOT NULL,
  UNIQUE (book_id, user_a, user_b)
);
CREATE TABLE IF NOT EXISTS direct_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS dm_thread ON direct_messages(thread_id, id);
CREATE TABLE IF NOT EXISTS direct_reads (
  thread_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  last_read_id INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (thread_id, user_id)
);
