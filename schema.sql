CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    display_name TEXT NOT NULL,
    amount TEXT NOT NULL,
    description TEXT NOT NULL,
    currency TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'other',
    tags TEXT NOT NULL DEFAULT '',
    logged_at_utc TEXT NOT NULL,
    logged_at_local TEXT NOT NULL,
    source_message TEXT NOT NULL,
    deleted_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS daily_summary (
    telegram_user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    currency TEXT NOT NULL,
    total_amount TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY (telegram_user_id, date)
);
