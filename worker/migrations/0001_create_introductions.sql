CREATE TABLE IF NOT EXISTS introductions (
  username TEXT PRIMARY KEY,
  json_url TEXT NOT NULL,
  base_site_url TEXT NOT NULL,
  introduction_data TEXT NOT NULL CHECK (json_valid(introduction_data)),
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS introductions_updated_at_idx
  ON introductions (updated_at);
