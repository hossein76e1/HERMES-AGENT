# Order-system instance (live at /data/workspace/projects)

Concrete implementation the patterns in SKILL.md are running on. Files: `order_flow.py` (shared helpers), `support_bot.py` (customer bot), `survey_bot.py` (admin bot), `auto_builder.py` (AI code pipeline), `image_service.py` (design-order image generation), tests `test_support.py` / `test_e2e_v5.py`.

## Bots & identity
- Customer: @ShahbotSupportbot (id 8823286946) — AI intake, receipts, outbox worker (5s).
- Admin: @ShahbotSurveyBot (id 8681968795) — admin panel, admin_inbox worker (5s), poll_new_orders (30s).
- ADMIN_ID = 1030173067 (Hossein's Telegram). Tokens are NOT in .env — read dynamically from Hermes state.db by `/data/.hermes/scripts/restart_bots.sh`.
- Backend: FastAPI at `/data/workspace/order-system/backend/` (run as `uvicorn api:app`), DB `orders.db`.

## DB
- `orders` columns include status, requirements (JSON with `$.chat.chat_id` binding, `$.auto_build` flag), deliverable_url/files/notes, timestamps, `support_until` (added via ALTER TABLE — make the add idempotent on boot).
- `order_messages`: shared queue/thread table. Thread logs use sender_type customer/admin/system; queues use `outbox` (customer-bound) and `admin_inbox` (admin-bound) with JSON payload content; workers flip to delivered and log `outbox/inbox mid=N delivered`.
- Status flow: pending→quoted→awaiting_payment→payment_review→paid→in_progress→delivered (+cancelled, ready). `set_order_status` stamps `support_until` on delivered.
- `order_flow.support_days_left(order_id)` → None before delivery, N days after, 0 expired.

## Callbacks
- Admin: `adm:approve|reject|payok|paybad|start|deliver|message|view|reopen:<order_id>` + support triage `adm:sfree|squote|sreply:<order_id>:<customer_chat_id>`.
- Customer: `new_order`, `confirm_order`, `cancel_order`, `pay:<method>:<oid>`, `receipt:<oid>`, `ask_admin:<oid>`, `cancelme:<oid>`, `getdelivery:<oid>`, `supp:<oid>`.
- Admin direct reply: `/reply_<chat_id> <text>`. Delivery text format: `link | files | notes` (`-` = empty).

## Support-routing fixes (2026-09-05 session)
- Bug "customer messages after delivery get the new-order prompt": `handle_message` now has a section-0 intercept — `support_bot._active_support_orders(chat_id)` returns `[(order_id, days_left)]` for delivered orders of the chat with `support_until` still in the future (IN query on both str and int chat_id — bindings are inconsistent in the JSON); if non-empty and no other mode is set, sets `mode=support_change` + `support_order_id` and asks what change they want. Literal «سفارش جدید» in the text clears mode and falls through to AI intake.
- Bug "admin replies never reach the customer": admin-bot direct sends fail for customers who never started the admin bot. `send_customer_chat(context, chat_id, text, kb)` in survey_bot.py = try direct → on exception queue outbox row (order_id=0 is fine; the worker doesn't need a binding). All admin reply paths (sfree/squote/sreply callbacks, `/reply_<chat_id>` command) go through it. NOTE: a function-local `_s3` alias that doesn't exist raises NameError inside a bare `except:` — the handler then silently returns empty results; alias inside the function (`import sqlite3 as _s3x`) and test the lookup standalone before trusting it.
- Verify routing with a fake-context harness (FakeUpdate/FakeCtx dicts) driving `handle_message` directly — no live bot needed; check the reply text and that admin_inbox/outbox rows appear.

## auto_builder.py
- Polls status='paid' (60s); `adm:start` sets `$.auto_build` + in_progress.
- `ai_build()`: plan call → per-file calls (GLM via 9router; `AI_MODEL`/`OPENAI_BASE_URL` env) → fallback minimal plan on failure; writes `/data/workspace/auto-builds/<oid>/`, zips to `auto-builds/deliverables/<order_number>.zip`, queues outbox delivery with `document_path`.
- Build ~6 min when GLM retries; pipeline still delivers via fallback.

## image_service.py (design orders)
- Project types `image_design` (1.5M), `logo_design` (2.5M), `graphic_design` (2M) — added to intake SYSTEM_PROMPT, PROJECT_LABELS_FA, and BASE_PRICES (all three, or intake prices are wrong).
- `adm:start` branches: code types → auto_builder, image types → `build_image_order(order_id)` in a thread. Generation via Pollinations.ai, ~10–30s, no key (see references/free-ai-providers.md); output `/data/workspace/auto-builds/images/img-YYYYMMDD-HHMMSS.jpg`; validate >5KB before delivering.
- Delivery: outbox payload with `image_path` (customer bot send_photo + caption + support days) + status `delivered` + admin notification — same terminal flow as code builds. 9Router image models (gpt-image-2, gemini-image) do NOT work (400 provider-unsupported / wallet errors) — Pollinations is the working free path. Free video generation: none available; video orders need manual work.
- Quality: verify with vision_analyze before delivering; regenerate with a different seed/style if bad (free engine struggles with complex multi-subject scenes).

## Adding a new project type — checklist

1. SYSTEM_PROMPT type list (support_bot.py) 2. PROJECT_LABELS_FA (order_flow.py) 3. BASE_PRICES (support_bot.py) 4. if auto-buildable: auto_ok tuple in adm:start (survey_bot.py) 5. if image-type: image_ok tuple + image_service style

## Pricing (BASE_PRICES in support_bot.py)

telegram_bot 5M, whatsapp_bot 8M, data_scraping 3M, website 15M, automation 10M, content_generation 2M, email_automation 5M, price_comparison 5M, dashboard 12M, image_design 1.5M, logo_design 2.5M, graphic_design 2M, custom 20M; ×complexity multiplier (1.0/1.5/2.5/4.0) + 500k per feature.

## Ops
- Restart: `kill -9` all `/proc` cmdline matches of the bot scripts, verify zero, `bash /data/.hermes/scripts/restart_bots.sh`, check logs for 200 getUpdates and zero Conflict. Safe kill: `scripts/kill_bot_instances.sh` — a bare `bash -c` scan whose cmdline contains the bot name kills ITSELF (SIGKILL mid-loop); anchor on python processes / exclude self-PID. Outbox payload keys now: chat_id, text, kb, attempts, document_path, image_path.
- Logs: `/data/.hermes/logs/support_bot.log`, `survey_bot.log`, `bots_keeper.log` (keeper cron 5m auto-restarts; cron service must be running).
- Test pattern: insert synthetic order bound to ADMIN chat, drive statuses via order_flow, assert queue rows, cancel+delete test rows.
