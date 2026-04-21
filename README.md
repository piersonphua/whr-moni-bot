# Telegram Expense Bot

Python Telegram bot that logs user expenses to a local SQLite database and returns simple spending summaries.

## MVP Features

- Log expenses with quick text input like `12.50 lunch`, `lunch 12.50`, or `12.50 lunch #food`
- Log expenses with `/add 12.50 lunch`
- View `/today`, `/week`, `/month`, `/recent`, and `/stats`
- Correct mistakes with `/undo`, `/delete <id>`, and `/edit <id> <amount> <description>`
- Infer basic categories and support tags
- Store data locally in SQLite
- Run with long polling in local or hosted environments such as Replit

## Requirements

- Python 3.11+
- Telegram bot token from BotFather
- Local filesystem access for the SQLite database file

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

## Deploy on Replit

The bot is designed to run with long polling. This keeps deployment simple on low-traffic hosts and avoids webhook setup.

Important:

- Replit free tier workspace runs are not truly always-on
- If the workspace sleeps, the bot stops until the repl wakes again
- For a personal low-traffic bot, this may still be acceptable
- If you need 24/7 uptime, you need a paid Replit Publishing option such as a Reserved VM background worker

Set the following environment variables in Replit:

- `TELEGRAM_BOT_TOKEN`
- `DATABASE_PATH`
- `DEFAULT_CURRENCY`
- `BOT_TIMEZONE`
- `POLLING_TIMEOUT`
- `RESTART_DELAY_SECONDS`
- `MAX_RESTART_DELAY_SECONDS`
- `SQLITE_BUSY_TIMEOUT_MS`
- `LOG_LEVEL`

Recommended Replit command:

```bash
python -m expense_bot.main
```

Notes:

- Keep `DATABASE_PATH` on Replit's persistent filesystem, for example `data/expenses.db`
- The process automatically retries after transient crashes or network failures
- SQLite is configured for lightweight low-concurrency usage

### Step-by-step

1. Create a new Replit App.
2. Choose Python as the language or import this repository from GitHub.
3. Open the `Shell` tab and install dependencies:

```bash
pip install -e .
```

4. Open the `Secrets` tool in Replit.
5. Add these secrets:
   - `TELEGRAM_BOT_TOKEN`
   - `DATABASE_PATH` with value `data/expenses.db`
   - `DEFAULT_CURRENCY` with value `SGD`
   - `BOT_TIMEZONE` with value `Asia/Singapore`
   - `POLLING_TIMEOUT` with value `30`
   - `RESTART_DELAY_SECONDS` with value `5`
   - `MAX_RESTART_DELAY_SECONDS` with value `60`
   - `SQLITE_BUSY_TIMEOUT_MS` with value `5000`
   - `LOG_LEVEL` with value `INFO`
6. Make sure the project contains the `.replit` file with:

```ini
run = "python -m expense_bot.main"
```

7. Click `Run`.
8. Wait for logs showing that polling has started and the bot connected successfully.
9. Send `/start` to your bot in Telegram.
10. Test one expense like `12.50 lunch`.

### Updating the bot later

1. Push code changes to the Replit App or GitHub-connected repo.
2. Open the Shell and run:

```bash
pip install -e .
```

3. Click `Run` again.

### If it stops working

- Check whether the workspace went to sleep
- Open Replit and click `Run` again
- Review logs for Telegram auth errors or SQLite file path errors
- Confirm `TELEGRAM_BOT_TOKEN` is still valid

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
