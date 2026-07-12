CREATE TABLE IF NOT EXISTS sender_accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  local_account_id INTEGER NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_sender_assignments (
  user_id INTEGER PRIMARY KEY,
  sender_account_id INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (sender_account_id) REFERENCES sender_accounts(id)
);

CREATE INDEX IF NOT EXISTS idx_sender_assignment_sender
ON user_sender_assignments(sender_account_id);
