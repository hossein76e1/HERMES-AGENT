---
name: telegram-bot-systems
description: Use when building or operating multi-bot Telegram systems.
---

# Telegram Bot Systems (multi-bot business automation)

Patterns for running a business flow (orders, delivery, support) over Telegram with python-telegram-bot: a separate customer bot + admin bot, DB-queued message routing, an AI code-building pipeline, and a post-delivery support window. A live instance of this class exists at `/data/workspace/projects` (order-system) — its concrete schema, callbacks, and paths are in `references/order-system.md`.

## Disk Management & Project Cleanup

- When freeing disk space, the `order-system` (admin + backend) must always be preserved — it is the core business flow. Other project modules (appointment_bot, content_generator, email_automation, competitor_monitor, dashboard, price_comparison, survey_bot, etc.) are safe to remove en masse.
- Mass file deletion triggers Hermes's security approval: a burst of >10 deletions within 20s requires explicit approval (`approval: "Command required approval (Security scan …)"`). Always verify the reduced tree with `ls` after deletion.
- After cleanup, verify: `/data/workspace/projects/` should contain only `.last_seen_order_id`, `order_flow.py`, and `support_bot.py` (plus the `order-system/` directory).
- The `.hermes/` directory (112M total) is the primary disk-user; key subdirs: `cache/` (7.9M), `logs/` (15M), `state.db` (11.5M), `models_dev_cache.json` (4.5M). Regular cleanup of caches frees significant space.
- When removing project files, always check `/data/workspace/projects/` structure first; the order-system folder at `/data/workspace/order-system/` is never touched.

## Architecture: two bots + DB queues

- **Customer bot** (AI intake, receipts) and **admin bot** (panel, notifications) run as separate processes with separate tokens. Each bot can only message chats that started *it* — never send customer-bound content through the admin bot's token (wrong bot appears in the customer's chat).
- **Outbox pattern** (customer-bound): any component inserts a JSON payload `{chat_id, text, kb, document_path, attempts}` into a shared messages table with `sender_type='outbox'`. The customer bot runs a JobQueue worker every ~5s that sends with its own token, marks the row delivered, retries up to 5, then notifies the admin. Use `send_document` when `document_path` is set (zip/file delivery with caption + keyboard), `send_photo` when `image_path` is set (design-order delivery).
- **Admin-inbox pattern** (admin-bound: new orders, payment receipts, support requests): same table, `sender_type='admin_inbox'`, delivered by the admin bot's worker. Photo receipts: download via `get_file`, save to disk, store path, re-send as photo.
- Keyboards travel as JSON (rows of `{text, callback_data|url}`); rebuild `InlineKeyboardMarkup` on delivery.
- Escape user-derived strings before `parse_mode="Markdown"`; lowercase/normalize enums (an unescaped `_` in `TELEGRAM_BOT` crashes send).

## Silent worker death: JobQueue needs an interpreter with APScheduler

PTB's JobQueue is an optional extra (`pip install "python-telegram-bot[job-queue]"` → APScheduler).
If the interpreter that launched the bot lacks APScheduler, `app.job_queue is None` and every
`run_repeating` worker **silently never runs** — no exception, no log line. The bot looks
perfectly healthy (polling, callbacks, AI replies all work) while the DB-queue workers
(`outbox_worker`, `admin_inbox_worker`, `poll_new_orders`) are dead: orders/receipts pile up
in the queue table and the admin never hears about them. Incident 2026-09-07: keeper/cron
resolved bare `python3` to `/opt/venv/bin/python3` (no APScheduler) while the agent's shell
had `/usr/local/bin/python3` (has it) — same code, opposite behavior.

- **Symptom signature**: rows sit in the messages table with correct `sender_type`, zero
  delivery log lines, error logs clean. Always verify under the *exact interpreter running
  the process* (read `/proc/<pid>/cmdline`/`exe`) — multiple pythons (system vs venv)
  commonly diverge: `import apscheduler` + `import telegram` must BOTH succeed there.
- **Fix**: pin one known-good interpreter in keeper/restart scripts (`PYTHON=/usr/local/bin/python3`),
  never a bare `python3` — which resolves per-cron-PATH and can be a different venv.
- **Backlog self-heals**: after restarting with the right interpreter, queued rows drain
  automatically and deliver late (in order) — no replay needed.
- **Verify after ANY restart**: within ~10s the log must show the worker's periodic line
  (e.g. `inbox mid=… delivered` every 5s). Absent = worker not running; do not report
  the bot as fixed until this line appears.

## Single-instance discipline (409 Conflict)

`Conflict: terminated by other getUpdates request` = two processes polling the same token. Orphans (ppid=1) survive Ctrl-C and even normal `kill`. Restart ritual:
1. Scan `/proc/*/cmdline` for the script names (pgrep may be absent on minimal images), `kill -9` **all** matches, verify zero remain.
2. Clear logs, then start via the restart script (tokens sourced from the secret store, not .env).
3. Confirm one instance per token and `getUpdates` returning 200 in the logs.

Also: register a global error handler that DMs the admin the exception text — silent callback crashes look like "button does nothing". None-guard every admin callback (`if not o: reply("not found"); return`) because the order may be deleted between keyboard render and click.

**Keeper traps (grep-based restart scripts):**
- A keeper whose "already running" check greps `python.*support_bot.py`-style patterns matches
  its OWN heredoc/wrapper cmdline (the script text contains the pattern) → false positive
  "already running" → a crashed bot is never restarted. Match exactly `python3 <script>` against
  `/proc/*/cmdline`, or scan only `python*` processes (see `scripts/kill_bot_instances.sh`).
- After killing, wait ≥5s and re-verify zero remain before starting: a keeper with a 2s sleep
  double-started bots (two instances → 409 conflict loop) because the dying process had not
  left /proc yet.

## AI build pipeline over flaky free routers

Free/open router models drop long generations (empty content, 502/503, wallet-403s). Never send one giant "build the project" prompt:
- Step 1: short call for a file-list plan as JSON. Steps 2..N: one file per call (`{"<fname>": "<full content>"}`), 3 retries with pauses each.
- Always fall back to a default minimal project (README/requirements/main) so the business flow still delivers instead of stalling; tell the admin the fallback was used.
- Sanity-check before delivery: `python -m py_compile` each `.py`; package with `zipfile`; deliver as an outbox document; on failure notify the admin with the error. Design orders (image/logo/graphic) bypass the code builder: an image service generates via a free image API and delivers through the same outbox (see references/order-system.md and references/free-ai-providers.md). New order types must be added in THREE places: intake system prompt, PROJECT_LABELS_FA, BASE_PRICES.

## Post-delivery support window

- Stamp `support_until = now + 7d` inside the status-change helper when status becomes delivered (single write path = no missed stamp). Compute days-left on read.
- **Message routing after delivery:** any customer text from a chat that has a delivered order with an active window must route to the support flow, not AI order intake (that's the "my message became a new-order prompt" bug). Intercept at the top of the message router: look up active delivered orders for the chat; if found, set support mode and ask what change they want. Only an explicit new-order intent ("سفارش جدید") escapes back to intake.
- Customer sees days remaining plus a "request change" entry point; expired → hide free changes and push a new-order CTA — a new payment refreshes the 7-day window.
- Admin triage keyboard per request: **free fix** (guidance, minor changes) / **paid change** (admin writes the quote; framed as "major change needs payment") / **text reply**. Log both sides in the order thread.
- **Every admin→customer path (triage replies, quotes, /reply_ commands) must send via a fallback helper**: try direct send with the admin bot's token, on ANY exception queue through the customer bot's outbox. Customers rarely started the admin bot, so raw direct sends silently vanish; a helper that swallows nothing and falls back keeps replies deliverable.

## AI admin assistant (added 2026-09-07)
- The admin bot accepts natural-language requests (`/ai <request>` AND plain
  text fallback when no pending action) and an LLM decides the action as JSON
  (`{"action", "args", "reply"}`): order_info, orders_list, stats, thread,
  set_status (validated against STATUS_FA), send_customer (via outbox), help.
- **Wire the natural path, not just the command path** — owner first tried
  plain text, got silence, reported "AI جوابی نمیده". The `handle_admin_text`
  fallback (runs only when no awaiting_* state is set, so notes/deliveries/
  replies keep priority) routes everything else to the same AI executor.
- Decision call: temperature 0.2, 3 JSON-parse retries, regex `\{.*\}` DOTALL
  extraction. Execute → markdown result → edit the "🤖 دارم بررسی می‌کنم..."
  placeholder message (fallback to new message on edit failure).
- Same env/model as the customer bot (`OPENAI_API_KEY`/`OPENAI_BASE_URL`/
  `AI_MODEL` from the Hermes .env).

## Restoring deleted-but-still-running bots (2026-09-07 incident)
- A bot whose source file was deleted keeps running from the deleted inode —
  the process looks healthy but the file is gone; a later restart would fail
  with no source. After any mass deletion, diff live processes against the
  files on disk and restore missing sources **from git history**, not from
  the pruned local backup dirs: `git -C <backup-repo> show <commit>:<path>`
  (commit `8f05700` had `projects-backup/2026-09-06_11-53-54/projects/…`).
- Restart the restored bot so it runs from a real file, not the inode.
- Removing a pipeline stage (e.g. auto-build) means FOUR touchpoints:
  the admin callback branch, the running daemon, the keeper/restart scripts
  that resurrect it, and DB rows still carrying the trigger flag
  (`$.auto_build = 1`) — clear active flags or the daemon picks them up.
- Bot tokens may not exist in `.env`; restart scripts fall back to regex
  extraction from `state.db` messages (`<bot_id>:[A-Za-z0-9_-]{30,50}`).
  When relaunching from an agent, put that lookup in a SCRIPT FILE —
  inline `python3 -c` with nested quotes gets mangled/truncated.

## References

- `references/order-system.md` — the live order-system instance: schema, callbacks, paths, pricing, image pipeline, project-type checklist
- `references/free-ai-providers.md` — 9Router quirks (empty responses, wallet errors) and the working free image recipe (Pollinations.ai)
- `references/project-cleanup.md` — project cleanup reference: disk management, mass-deletion procedure, verified post-cleanup state
- `scripts/kill_bot_instances.sh` — safe single-instance kill (self-excluding /proc scan)
