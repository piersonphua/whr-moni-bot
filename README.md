# Telegram Expense Bot

Python Telegram bot that logs user expenses and returns simple spending summaries. The repo now supports:

- local long polling with SQLite
- Cloudflare Workers webhooks with D1

## MVP Features

- Log expenses with quick text input like `12.50 lunch`, `lunch 12.50`, or `12.50 lunch #food`
- Log expenses with `/add 12.50 lunch`
- View `/today`, `/week`, `/month`, `/recent`, and `/stats`
- Correct mistakes with `/undo`, `/delete <id>`, and `/edit <id> <amount> <description>`
- Infer basic categories and support tags
- Store data in SQLite locally or D1 on Cloudflare
- Run with long polling locally or Telegram webhooks on Cloudflare Workers

## Requirements

- Python 3.11+
- Telegram bot token from BotFather
- Local filesystem access for the SQLite database file if you use polling mode

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -e .[dev]
```

3. Copy `.env.example` to `.env` and fill in the required values.

## Run locally

```bash
python -m expense_bot.main
```

## Bot Commands

- `/start`
- `/help`
- `/add <amount> <description>`
- `/today`
- `/week`
- `/month`
- `/recent`
- `/stats`
- `/undo`
- `/delete <id>`
- `/edit <id> <amount> <description>`

## Deploy on Cloudflare Workers + D1

This repo includes a Cloudflare Worker entrypoint in [src/cloudflare_worker.py](/Users/piersonphua/Desktop/THE-CODEX/src/cloudflare_worker.py:1) and a starter Wrangler config in [wrangler.toml](/Users/piersonphua/Desktop/THE-CODEX/wrangler.toml:1).

### What changed for Cloudflare

- Command handling was moved into a reusable service layer so the same bot logic can run behind aiogram polling or a webhook worker.
- A D1-backed repository was added in [src/expense_bot/d1_repository.py](/Users/piersonphua/Desktop/THE-CODEX/src/expense_bot/d1_repository.py:1).
- The Cloudflare entrypoint accepts Telegram webhook requests and replies by calling Telegram's `sendMessage` API.

### Environment variables / secrets

Configure these in Cloudflare:

- `TELEGRAM_BOT_TOKEN`
- `DEFAULT_CURRENCY`
- `BOT_TIMEZONE`
- `WEBHOOK_SECRET`
- `WEBHOOK_PATH`
- `LOG_LEVEL`

`DATABASE_PATH`, `POLLING_TIMEOUT`, `RESTART_DELAY_SECONDS`, `MAX_RESTART_DELAY_SECONDS`, and `SQLITE_BUSY_TIMEOUT_MS` are only used by the local polling runtime.

For local `wrangler dev`, copy [.dev.vars.example](/Users/piersonphua/Desktop/THE-CODEX/.dev.vars.example:1) to `.dev.vars` and fill in the values there.

### D1 setup

1. Create a D1 database.
2. Replace `database_id` in `wrangler.toml`.
3. Apply the schema:

```bash
wrangler d1 execute traxpense --file=schema.sql
```

### Deploy

1. Install Wrangler and authenticate with Cloudflare.
2. Configure secrets:

```bash
wrangler secret put TELEGRAM_BOT_TOKEN
wrangler secret put WEBHOOK_SECRET
```

3. Deploy:

```bash
wrangler deploy
```

4. Set the Telegram webhook to your Worker URL plus `WEBHOOK_PATH`.

Example:

```bash
curl "https://api.telegram.org/bot<token>/setWebhook" \
  -d "url=https://<your-worker>.workers.dev/telegram/webhook" \
  -d "secret_token=<your-webhook-secret>"
```

### Local development

The local bot still runs with polling and SQLite:

```bash
python -m expense_bot.main
```

To test the Worker locally instead:

```bash
wrangler dev
```

## SQLite Schema

The bot creates two tables if they do not already exist:

- `expenses`
- `daily_summary`

### `expenses` columns

- `id`
- `telegram_user_id`
- `username`
- `display_name`
- `amount`
- `description`
- `currency`
- `category`
- `tags`
- `logged_at_utc`
- `logged_at_local`
- `source_message`
- `deleted_at_utc`

### `daily_summary` columns

- `telegram_user_id`
- `date`
- `currency`
- `total_amount`
- `updated_at_utc`

## Test

```bash
pytest
```
