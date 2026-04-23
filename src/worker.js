const CATEGORY_KEYWORDS = {
  food: new Set(["lunch", "dinner", "breakfast", "coffee", "tea", "snack", "meal", "restaurant", "food"]),
  transport: new Set(["taxi", "grab", "uber", "bus", "train", "mrt", "transport", "fuel", "petrol"]),
  shopping: new Set(["shop", "shopping", "clothes", "shirt", "shoes", "mall", "purchase"]),
  groceries: new Set(["grocery", "groceries", "supermarket", "market"]),
  entertainment: new Set(["movie", "cinema", "game", "concert", "netflix", "spotify"]),
  utilities: new Set(["electric", "water", "internet", "phone", "utility", "utilities"]),
  health: new Set(["doctor", "clinic", "medicine", "pharmacy", "hospital"]),
};

const HELP_TEXT = (currency) =>
  [
    "Log expenses by sending a message like `12.50 lunch`, `lunch 12.50`, or `12.50 lunch #food`.",
    "",
    "Commands:",
    "/add <amount> <description>",
    "/today",
    "/week",
    "/month",
    "/recent",
    "/stats",
    "/undo",
    "/delete <id>",
    "/edit <id> <amount> <description>",
    "/help",
    "",
    `Default currency: ${currency}`,
  ].join("\n");

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const webhookPath = env.WEBHOOK_PATH || "/telegram/webhook";

    if (request.method === "GET" && url.pathname === "/healthz") {
      return json({ ok: true });
    }

    if (request.method !== "POST" || url.pathname !== webhookPath) {
      return new Response("Not Found", { status: 404 });
    }

    if (env.WEBHOOK_SECRET) {
      const provided = request.headers.get("x-telegram-bot-api-secret-token");
      if (provided !== env.WEBHOOK_SECRET) {
        return new Response("Unauthorized", { status: 401 });
      }
    }

    const update = await request.json();
    const message = update.message || update.edited_message;
    if (!message || typeof message.text !== "string") {
      return json({ ok: true });
    }

    const user = message.from || {};
    const chat = message.chat || {};
    const context = {
      telegramUserId: Number(user.id || 0),
      username: user.username || "",
      displayName: user.first_name || chat.title || "Telegram User",
    };

    await ensureSchema(env.DB);
    const reply = await processMessage(env, context, message.text.trim());
    if (reply) {
      await sendTelegramMessage(env.TELEGRAM_BOT_TOKEN, chat.id, reply.text, reply.parseMode);
    }
    return json({ ok: true });
  },
};

async function processMessage(env, user, text) {
  if (!text) return null;
  if (text.startsWith("/")) {
    return processCommand(env, user, text);
  }
  return handleExpenseEntry(env, user, text, text);
}

async function processCommand(env, user, text) {
  const [commandPart, ...rest] = text.split(" ");
  const args = rest.join(" ").trim();
  const command = commandPart.slice(1).split("@", 1)[0].toLowerCase();
  const currency = env.DEFAULT_CURRENCY || "SGD";
  const timezone = env.BOT_TIMEZONE || "Asia/Singapore";

  if (command === "start" || command === "help") {
    return { text: HELP_TEXT(currency), parseMode: "Markdown" };
  }
  if (command === "add") {
    if (!args) return { text: "Usage: /add 12.50 lunch" };
    return handleExpenseEntry(env, user, args, text);
  }
  if (command === "today") {
    const { start, end } = getDateRange("day", timezone);
    const total = await sumExpenses(env.DB, user.telegramUserId, start, end);
    return { text: `Today: ${formatAmount(total)} ${currency}` };
  }
  if (command === "week") {
    const { start, end } = getDateRange("week", timezone);
    const total = await sumExpenses(env.DB, user.telegramUserId, start, end);
    return { text: `This week: ${formatAmount(total)} ${currency}` };
  }
  if (command === "month") {
    const { start, end } = getDateRange("month", timezone);
    const total = await sumExpenses(env.DB, user.telegramUserId, start, end);
    return { text: `This month: ${formatAmount(total)} ${currency}` };
  }
  if (command === "recent") {
    return recentExpenses(env, user.telegramUserId);
  }
  if (command === "undo") {
    return undoExpense(env, user.telegramUserId);
  }
  if (command === "delete") {
    return deleteExpense(env, user.telegramUserId, args);
  }
  if (command === "edit") {
    return editExpense(env, user.telegramUserId, args);
  }
  if (command === "stats") {
    return stats(env, user.telegramUserId, currency, timezone);
  }
  return null;
}

async function handleExpenseEntry(env, user, rawText, sourceMessage) {
  const parsed = parseExpenseText(rawText);
  if (parsed.error) return { text: parsed.error };

  const currency = env.DEFAULT_CURRENCY || "SGD";
  const timezone = env.BOT_TIMEZONE || "Asia/Singapore";
  const now = new Date();
  const loggedAtUtc = now.toISOString();
  const loggedAtLocal = toTimezoneISOString(now, timezone);

  const result = await env.DB.prepare(
    `INSERT INTO expenses (
      telegram_user_id, username, display_name, amount, description, currency,
      category, tags, logged_at_utc, logged_at_local, source_message, deleted_at_utc
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)`
  )
    .bind(
      user.telegramUserId,
      user.username,
      user.displayName,
      parsed.amount,
      parsed.description,
      currency,
      parsed.category,
      parsed.tags.join(","),
      loggedAtUtc,
      loggedAtLocal,
      sourceMessage
    )
    .run();

  const id = Number(result.meta?.last_row_id || 0);
  await refreshDailySummary(env.DB, user.telegramUserId, loggedAtLocal, currency);

  const timeText = loggedAtLocal.slice(0, 16).replace("T", " ");
  const tagText = parsed.tags.length ? ` | tags: ${parsed.tags.map((tag) => `#${tag}`).join(", ")}` : "";
  return {
    text: `Saved #${id} | ${parsed.amount} ${currency} | ${parsed.description} | category: ${parsed.category}${tagText} | ${timeText}`,
  };
}

function parseExpenseText(text) {
  const raw = text.trim().replace(/\s+/g, " ");
  if (!raw) {
    return { error: "Please send an amount followed by a description, for example: 12.50 lunch" };
  }

  const tags = [...new Set([...raw.matchAll(/#([a-zA-Z0-9_-]+)/g)].map((match) => match[1].toLowerCase()))].sort();
  const normalized = raw.replace(/#([a-zA-Z0-9_-]+)/g, "").trim().replace(/\s+/g, " ");
  const parts = normalized.split(" ").filter(Boolean);
  if (parts.length < 2) {
    return { error: "Missing description. Example: 12.50 lunch" };
  }

  const amountIndex = parts.findIndex((part) => /^-?\d+(?:\.\d+)?$/.test(part));
  if (amountIndex === -1) {
    return { error: "Amount must be a valid number. Example: 12.50 lunch" };
  }

  const amount = Number(parts[amountIndex]);
  if (!Number.isFinite(amount)) {
    return { error: "Amount must be a valid number. Example: 12.50 lunch" };
  }
  if (amount <= 0) {
    return { error: "Amount must be greater than 0." };
  }

  const description = parts.filter((_, index) => index !== amountIndex).join(" ").trim();
  if (!description) {
    return { error: "Missing description. Example: 12.50 lunch" };
  }

  return {
    amount: amount.toFixed(2),
    description,
    category: inferCategory(description, tags),
    tags,
  };
}

function inferCategory(description, tags) {
  if (tags.length && CATEGORY_KEYWORDS[tags[0]]) {
    return tags[0];
  }
  const words = new Set((description.match(/[a-zA-Z]+/g) || []).map((word) => word.toLowerCase()));
  for (const [category, keywords] of Object.entries(CATEGORY_KEYWORDS)) {
    for (const keyword of keywords) {
      if (words.has(keyword)) return category;
    }
  }
  return "other";
}

async function recentExpenses(env, userId) {
  const result = await env.DB.prepare(
    `SELECT id, amount, currency, description, category, logged_at_local
     FROM expenses
     WHERE telegram_user_id = ? AND deleted_at_utc IS NULL
     ORDER BY logged_at_local DESC
     LIMIT 5`
  )
    .bind(userId)
    .all();

  if (!result.results.length) {
    return { text: "No expenses found yet." };
  }

  const lines = ["Recent expenses:"];
  for (const row of result.results) {
    lines.push(
      `- #${row.id} | ${String(row.logged_at_local).slice(0, 16).replace("T", " ")} | ${formatAmount(row.amount)} ${row.currency} | ${row.description} | ${row.category}`
    );
  }
  return { text: lines.join("\n") };
}

async function undoExpense(env, userId) {
  const row = await first(
    env.DB,
    `SELECT id, amount, currency, description, logged_at_local
     FROM expenses
     WHERE telegram_user_id = ? AND deleted_at_utc IS NULL
     ORDER BY logged_at_local DESC, id DESC
     LIMIT 1`,
    [userId]
  );
  if (!row) return { text: "No expense found to undo." };

  const deletedAt = new Date().toISOString();
  await env.DB.prepare(
    `UPDATE expenses SET deleted_at_utc = ? WHERE id = ? AND telegram_user_id = ? AND deleted_at_utc IS NULL`
  )
    .bind(deletedAt, row.id, userId)
    .run();
  await refreshDailySummary(env.DB, userId, row.logged_at_local, row.currency);
  return { text: `Deleted expense #${row.id}: ${formatAmount(row.amount)} ${row.currency} for ${row.description}.` };
}

async function deleteExpense(env, userId, rawArgs) {
  if (!rawArgs) return { text: "Usage: /delete <id>" };
  const expenseId = Number(rawArgs.trim());
  if (!Number.isInteger(expenseId)) return { text: "Expense id must be a number. Usage: /delete <id>" };

  const row = await first(
    env.DB,
    `SELECT id, amount, currency, description, logged_at_local
     FROM expenses
     WHERE telegram_user_id = ? AND id = ? AND deleted_at_utc IS NULL`,
    [userId, expenseId]
  );
  if (!row) return { text: `Expense #${expenseId} was not found.` };

  const deletedAt = new Date().toISOString();
  await env.DB.prepare(
    `UPDATE expenses SET deleted_at_utc = ? WHERE id = ? AND telegram_user_id = ? AND deleted_at_utc IS NULL`
  )
    .bind(deletedAt, expenseId, userId)
    .run();
  await refreshDailySummary(env.DB, userId, row.logged_at_local, row.currency);
  return { text: `Deleted expense #${row.id}: ${formatAmount(row.amount)} ${row.currency} for ${row.description}.` };
}

async function editExpense(env, userId, rawArgs) {
  if (!rawArgs) return { text: "Usage: /edit <id> <amount> <description>" };
  const firstSpace = rawArgs.indexOf(" ");
  if (firstSpace === -1) return { text: "Usage: /edit <id> <amount> <description>" };

  const expenseId = Number(rawArgs.slice(0, firstSpace).trim());
  if (!Number.isInteger(expenseId)) return { text: "Expense id must be a number. Usage: /edit <id> <amount> <description>" };

  const existing = await first(
    env.DB,
    `SELECT id, currency, logged_at_local
     FROM expenses
     WHERE telegram_user_id = ? AND id = ? AND deleted_at_utc IS NULL`,
    [userId, expenseId]
  );
  if (!existing) return { text: `Expense #${expenseId} was not found.` };

  const newPayload = rawArgs.slice(firstSpace + 1);
  const parsed = parseExpenseText(newPayload);
  if (parsed.error) return { text: parsed.error };

  await env.DB.prepare(
    `UPDATE expenses
     SET amount = ?, description = ?, category = ?, tags = ?, source_message = ?
     WHERE id = ? AND telegram_user_id = ? AND deleted_at_utc IS NULL`
  )
    .bind(parsed.amount, parsed.description, parsed.category, parsed.tags.join(","), newPayload, expenseId, userId)
    .run();
  await refreshDailySummary(env.DB, userId, existing.logged_at_local, existing.currency);
  return {
    text: `Updated expense #${expenseId}: ${parsed.amount} ${existing.currency} for ${parsed.description} (${parsed.category}).`,
  };
}

async function stats(env, userId, currency, timezone) {
  const month = getDateRange("month", timezone);
  const week = getDateRange("week", timezone);
  const [weekTotal, monthTotal, rowsResult] = await Promise.all([
    sumExpenses(env.DB, userId, week.start, week.end),
    sumExpenses(env.DB, userId, month.start, month.end),
    env.DB
      .prepare(
        `SELECT amount, category, substr(logged_at_local, 1, 10) AS day
         FROM expenses
         WHERE telegram_user_id = ? AND deleted_at_utc IS NULL
           AND logged_at_local >= ? AND logged_at_local < ?`
      )
      .bind(userId, month.start, month.end)
      .all(),
  ]);

  const dayTotals = new Map();
  const categoryTotals = new Map();
  for (const row of rowsResult.results) {
    const amount = Number(row.amount);
    dayTotals.set(row.day, (dayTotals.get(row.day) || 0) + amount);
    categoryTotals.set(row.category, (categoryTotals.get(row.category) || 0) + amount);
  }

  const avgDaily = dayTotals.size ? sumValues(dayTotals) / dayTotals.size : 0;
  const topDay = [...dayTotals.entries()].sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0]))[0];
  const topCategories = [...categoryTotals.entries()]
    .sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0]))
    .slice(0, 5);

  const lines = [
    "Stats:",
    `- This week: ${formatAmount(weekTotal)} ${currency}`,
    `- This month: ${formatAmount(monthTotal)} ${currency}`,
    `- Average daily spend this month: ${formatAmount(avgDaily)} ${currency}`,
  ];
  if (topDay) {
    lines.push(`- Highest spend day this month: ${topDay[0]} (${formatAmount(topDay[1])} ${currency})`);
  }
  if (topCategories.length) {
    lines.push("- Category breakdown this month:");
    for (const [category, total] of topCategories) {
      lines.push(`  - ${category}: ${formatAmount(total)} ${currency}`);
    }
  }
  return { text: lines.join("\n") };
}

async function ensureSchema(db) {
  await db.batch([
    db.prepare(
      `CREATE TABLE IF NOT EXISTS expenses (
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
      )`
    ),
    db.prepare(
      `CREATE TABLE IF NOT EXISTS daily_summary (
        telegram_user_id INTEGER NOT NULL,
        date TEXT NOT NULL,
        currency TEXT NOT NULL,
        total_amount TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL,
        PRIMARY KEY (telegram_user_id, date)
      )`
    ),
  ]);
}

async function refreshDailySummary(db, userId, loggedAtLocal, currency) {
  const date = String(loggedAtLocal).slice(0, 10);
  const nextDay = new Date(`${date}T00:00:00Z`);
  nextDay.setUTCDate(nextDay.getUTCDate() + 1);
  const start = `${date}T00:00:00`;
  const end = `${nextDay.toISOString().slice(0, 10)}T00:00:00`;
  const total = await sumExpenses(db, userId, start, end);
  await db.prepare(
    `INSERT INTO daily_summary (telegram_user_id, date, currency, total_amount, updated_at_utc)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(telegram_user_id, date) DO UPDATE SET
       currency = excluded.currency,
       total_amount = excluded.total_amount,
       updated_at_utc = excluded.updated_at_utc`
  )
    .bind(userId, date, currency, formatAmount(total), new Date().toISOString())
    .run();
}

async function sumExpenses(db, userId, start, end) {
  const row = await first(
    db,
    `SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) AS total
     FROM expenses
     WHERE telegram_user_id = ? AND deleted_at_utc IS NULL
       AND logged_at_local >= ? AND logged_at_local < ?`,
    [userId, start, end]
  );
  return Number(row?.total || 0);
}

async function first(db, sql, bindings) {
  return (await db.prepare(sql).bind(...bindings).first()) || null;
}

async function sendTelegramMessage(token, chatId, text, parseMode) {
  if (!chatId) return;
  const payload = { chat_id: chatId, text };
  if (parseMode) payload.parse_mode = parseMode;

  const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json;charset=UTF-8" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const body = await response.text();
    console.error("Telegram sendMessage failed", response.status, body);
  }
}

function getDateRange(kind, timezone) {
  const now = zonedParts(new Date(), timezone);
  if (kind === "day") {
    return {
      start: localBoundaryIso(now.year, now.month, now.day),
      end: localBoundaryIso(now.year, now.month, now.day + 1),
    };
  }
  if (kind === "week") {
    const weekday = weekdayFromYmd(now.year, now.month, now.day);
    const mondayOffset = weekday === 0 ? -6 : 1 - weekday;
    const startDate = new Date(Date.UTC(now.year, now.month - 1, now.day + mondayOffset));
    const endDate = new Date(Date.UTC(now.year, now.month - 1, now.day + mondayOffset + 7));
    return {
      start: localBoundaryIso(startDate.getUTCFullYear(), startDate.getUTCMonth() + 1, startDate.getUTCDate()),
      end: localBoundaryIso(endDate.getUTCFullYear(), endDate.getUTCMonth() + 1, endDate.getUTCDate()),
    };
  }
  const nextMonth = now.month === 12 ? { year: now.year + 1, month: 1 } : { year: now.year, month: now.month + 1 };
  return {
    start: localBoundaryIso(now.year, now.month, 1),
    end: localBoundaryIso(nextMonth.year, nextMonth.month, 1),
  };
}

function zonedParts(date, timezone) {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const parts = Object.fromEntries(
    formatter
      .formatToParts(date)
      .filter((part) => part.type !== "literal")
      .map((part) => [part.type, part.value])
  );
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: Number(parts.hour),
    minute: Number(parts.minute),
    second: Number(parts.second),
  };
}

function toTimezoneISOString(date, timezone) {
  const parts = zonedParts(date, timezone);
  return `${parts.year}-${pad(parts.month)}-${pad(parts.day)}T${pad(parts.hour)}:${pad(parts.minute)}:${pad(parts.second)}`;
}

function localBoundaryIso(year, month, day) {
  const date = new Date(Date.UTC(year, month - 1, day));
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}T00:00:00`;
}

function weekdayFromYmd(year, month, day) {
  return new Date(Date.UTC(year, month - 1, day)).getUTCDay();
}

function sumValues(map) {
  let total = 0;
  for (const value of map.values()) total += value;
  return total;
}

function formatAmount(value) {
  return Number(value || 0).toFixed(2);
}

function pad(value) {
  return String(value).padStart(2, "0");
}

function json(value, init = {}) {
  return new Response(JSON.stringify(value), {
    ...init,
    headers: { "content-type": "application/json;charset=UTF-8", ...(init.headers || {}) },
  });
}
