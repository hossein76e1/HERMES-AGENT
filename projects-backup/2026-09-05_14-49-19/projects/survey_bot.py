#!/usr/bin/env python3
"""
📦 ربات مدیریت سفارشات — Admin Order Manager (@ShahbotSurveyBot)
چرخه کامل برای ادمین:
۱. سفارش جدید (ربات/سایت) → اعلان → ✅ تأیید → مشتری پیام پرداخت می‌گیره
۲. رسید مشتری → اعلان → ✅/❌ بررسی → تأیید شد: وضعیت paid
۳. شروع پروژه → در حال انجام → تحویل (فایل/لینک) → مشتری تحویل می‌گیره
۴. پاسخ مستقیم به مشتری: /reply_<chat_id> متن
۵. انصراف مشتری → اعلان + امکان بازگشت سفارش
"""

import os
import json
import re
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters,
)

import order_flow as flow
from order_flow import (
    ADMIN_ID, STATUS_FA, format_price, md_escape,
    get_order, get_order_by_number, set_order_status, add_message, get_messages,
    confirm_payment_row, find_pending_payment, bind_chat, get_chat_binding,
    order_card, now, queue_customer_message,
)

load_dotenv("/data/.hermes/.env", override=True)

TOKEN = os.environ.get("SURVEY_BOT_TOKEN")
ORDERS_DB = flow.ORDERS_DB
NEW_ORDER_MARK = "/data/workspace/projects/.last_seen_order_id"

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("admin_orders_bot")

# ─── Admin action sets ───────────────────────────────────────────────────────
ADMIN_ACTIONS = {
    "pending": [("approve", "✅ تأیید سفارش"), ("reject", "❌ رد سفارش")],
    "quoted": [("approve", "✅ تأیید و ارسال پرداخت")],
    "awaiting_payment": [],
    "payment_review": [("payok", "✅ پرداخت تأیید شد"), ("paybad", "❌ رسید نامعتبر")],
    "paid": [("start", "🔧 شروع پروژه")],
    "in_progress": [("deliver", "📦 تحویل"), ("message", "💬 پیام به مشتری")],
    "ready": [("deliver", "📦 تحویل"), ("message", "💬 پیام به مشتری")],
    "delivered": [("message", "💬 پیام به مشتری")],
    "cancelled": [("reopen", "🔄 بازگشت سفارش")],
}


def admin_keyboard(o: dict) -> InlineKeyboardMarkup:
    buttons = []
    row = []
    for action, label in ADMIN_ACTIONS.get(o.get("status"), []):
        row.append(InlineKeyboardButton(label, callback_data=f"adm:{action}:{o['id']}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔄 به‌روزرسانی", callback_data=f"adm:view:{o['id']}")])
    return InlineKeyboardMarkup(buttons)


# ─── New-order poller ────────────────────────────────────────────────────────
async def poll_new_orders(app):
    last_seen = load_last_seen()
    try:
        import sqlite3
        conn = sqlite3.connect(ORDERS_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM orders WHERE id > ? ORDER BY id ASC LIMIT 20", (last_seen,)
        ).fetchall()
        conn.close()
        for o in rows:
            od = dict(o)
            try:
                await app.bot.send_message(
                    ADMIN_ID,
                    "🔔 **سفارش جدید!**\n\n" + order_card(od),
                    parse_mode="Markdown",
                    reply_markup=admin_keyboard(od),
                )
                mark_last_seen(o["id"])
                logger.info(f"notified admin of new order #{o['id']}")
            except Exception as e:
                logger.warning(f"notify failed for order #{o['id']}: {e}")
                break
    except Exception as e:
        logger.error(f"poll error: {e}")


def mark_last_seen(order_id: int):
    with open(NEW_ORDER_MARK, "w") as f:
        f.write(str(order_id))


def load_last_seen() -> int:
    try:
        with open(NEW_ORDER_MARK) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


# ─── Admin-inbox worker: deliver messages queued by support bot ─────────────
async def admin_inbox_worker(context: ContextTypes.DEFAULT_TYPE):
    from order_flow import fetch_admin_inbox, mark_outbox, update_outbox_payload
    for row in fetch_admin_inbox(5):
        mid, order_id, content = row["id"], row["order_id"], row["content"]
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            mark_outbox(mid, "inbox_error")
            continue
        text = payload["text"]
        kb = None
        if payload.get("kb"):
            try:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(str(b.get("text", "•")), **{k: v for k, v in b.items() if k != "text"}) for b in r] for r in payload["kb"]])
            except Exception as e:
                logger.warning(f"inbox kb parse failed mid={mid}: {e}")
        attempts = int(payload.get("attempts", 0))
        try:
            photo_path = payload.get("photo_path")
            if photo_path and os.path.exists(photo_path):
                with open(photo_path, "rb") as ph:
                    await context.bot.send_photo(ADMIN_ID, photo=ph, caption=text, parse_mode="Markdown", reply_markup=kb)
            else:
                await context.bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=kb)
            mark_outbox(mid, "bot")  # delivered
            logger.info(f"inbox mid={mid} delivered to ADMIN")
        except Exception as e:
            attempts += 1
            if attempts >= 5:
                mark_outbox(mid, "inbox_failed")
            else:
                payload["attempts"] = attempts
                update_outbox_payload(mid, payload)
            logger.warning(f"inbox mid={mid} attempt {attempts} failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Customer-facing sends (through chat binding recorded in requirements JSON)
# ══════════════════════════════════════════════════════════════════════════════
async def send_customer(context: ContextTypes.DEFAULT_TYPE, order_id: int, text: str, kb=None) -> bool:
    """Queue customer message for delivery by @ShahbotSupportbot (outbox pattern)."""
    binding = get_chat_binding(order_id)
    if not binding:
        logger.warning(f"no chat binding for order #{order_id}")
        return False
    queue_customer_message(order_id, binding["chat_id"], text, kb)
    logger.info(f"queued customer message for order #{order_id} → chat {binding['chat_id']}")
    return True


async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str, kb=None):
    try:
        await context.bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        logger.warning(f"admin notify failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# /start & lists
# ══════════════════════════════════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🔒 این ربات مخصوص ادمینه.")
        return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 همه سفارش‌ها", callback_data="list:all")],
        [InlineKeyboardButton("⏳ در انتظار بررسی", callback_data="list:pending"),
         InlineKeyboardButton("🧾 بررسی رسید", callback_data="list:payment_review")],
        [InlineKeyboardButton("🔧 در حال انجام", callback_data="list:in_progress")],
        [InlineKeyboardButton("📊 آمار", callback_data="stats")],
    ])
    await update.message.reply_text(
        "📦 **پنل مدیریت سفارشات**\n\n"
        "سفارش‌های جدید خودکار اینجا میان.\n"
        "چرخه: تأیید ← پرداخت ← بررسی رسید ← ساخت ← تحویل\n"
        "پاسخ مستقیم به مشتری: `/reply_<chat_id> پیام`",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def db_all_orders(status: str = None, limit: int = 15) -> list:
    import sqlite3
    conn = sqlite3.connect(ORDERS_DB)
    conn.row_factory = sqlite3.Row
    if status:
        rows = conn.execute(
            "SELECT * FROM orders WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def db_stats() -> dict:
    import sqlite3
    conn = sqlite3.connect(ORDERS_DB)
    cur = conn.cursor()
    s = {}
    s["total"] = cur.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    s["pending"] = cur.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
    s["review"] = cur.execute("SELECT COUNT(*) FROM orders WHERE status='payment_review'").fetchone()[0]
    s["in_progress"] = cur.execute("SELECT COUNT(*) FROM orders WHERE status='in_progress'").fetchone()[0]
    s["delivered"] = cur.execute("SELECT COUNT(*) FROM orders WHERE status='delivered'").fetchone()[0]
    s["revenue"] = cur.execute("SELECT COALESCE(SUM(final_price),0) FROM orders WHERE status='delivered'").fetchone()[0]
    conn.close()
    return s


# ══════════════════════════════════════════════════════════════════════════════
# Callback router
# ══════════════════════════════════════════════════════════════════════════════
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    if update.effective_user.id != ADMIN_ID:
        await query.answer("🔒 مخصوص ادمین")
        return
    await query.answer()

    if data.startswith("list:"):
        status = data.split(":")[1]
        orders = await db_all_orders(None if status == "all" else status)
        if not orders:
            await query.message.reply_text("📭 سفارشی با این وضعیت نیست.")
            return
        await query.message.reply_text(f"📋 {len(orders)} سفارش:")
        for o in orders[:10]:
            await query.message.reply_text(order_card(o), parse_mode="Markdown", reply_markup=admin_keyboard(o))

    elif data == "stats":
        s = await db_stats()
        await query.message.reply_text(
            "📊 **آمار فروش:**\n\n"
            f"🛒 کل: {s['total']}\n"
            f"⏳ در انتظار: {s['pending']}\n"
            f"🧾 بررسی رسید: {s['review']}\n"
            f"🔧 در حال انجام: {s['in_progress']}\n"
            f"✅ تحویل شده: {s['delivered']}\n"
            f"💰 درآمد (تحویل‌شده): {format_price(s['revenue'])}",
            parse_mode="Markdown",
        )

    elif data.startswith("adm:view:"):
        oid = int(data.split(":")[2])
        o = get_order(oid)
        if o:
            await query.message.reply_text(order_card(o), parse_mode="Markdown", reply_markup=admin_keyboard(o))

    # ── 1. APPROVE ORDER → send payment info to customer ──
    elif data.startswith("adm:approve:"):
        oid = int(data.split(":")[2])
        o = get_order(oid)
        if not o:
            await query.message.reply_text(f"⚠️ سفارش #{oid} پیدا نشد.")
            return
        set_order_status(oid, "quoted")
        add_message(oid, "admin", "سفارش تأیید شد — در انتظار پرداخت", "system")
        from support_bot import payment_text, payment_keyboard  # reuse exact same texts
        sent = await send_customer(context, oid, payment_text(o), payment_keyboard(o))
        await query.message.reply_text(
            ("✅ تأیید شد و اطلاعات پرداخت برای مشتری ارسال شد." if sent
             else "⚠️ تأیید شد ولی ارسال به مشتری شکست خورد (binding نداریم — سفارش سایتی)."),
            parse_mode="Markdown",
        )

    # ── 2. REJECT ORDER ──
    elif data.startswith("adm:reject:"):
        oid = int(data.split(":")[2])
        o = get_order(oid)
        if not o:
            await query.message.reply_text(f"⚠️ سفارش #{oid} دیگه وجود نداره (حذف شده).")
            return
        set_order_status(oid, "cancelled")
        add_message(oid, "admin", "سفارش توسط ادمین رد شد", "system")
        context.user_data["awaiting_note_for"] = ("reject", oid)
        await query.message.reply_text("📝 دلیل رد رو بنویس (برای مشتری ارسال میشه؛ «-» = بدون پیام):")

    # ── 3. PAYMENT CONFIRMED → status paid ──
    elif data.startswith("adm:payok:"):
        oid = int(data.split(":")[2])
        o = get_order(oid)
        if not o:
            await query.message.reply_text(f"⚠️ سفارش #{oid} دیگه وجود نداره (حذف شده).")
            return
        method = o.get("payment_method") or "card"
        p = find_pending_payment(oid, method)
        if p:
            confirm_payment_row(p["id"], "admin-confirmed")
        set_order_status(oid, "paid", {"payment_status": "paid"})
        add_message(oid, "admin", "پرداخت تأیید شد", "system")
        sent = await send_customer(context, oid,
                                   "✅ **پرداختت تأیید شد!**\n\nپروژه‌ت وارد صف ساخت می‌شه — به‌زودی شروع می‌کنیم 🔧")
        o2 = get_order(oid)
        await query.message.reply_text(
            f"✅ پرداخت سفارش #{oid} تأیید شد" + (" و به مشتری اطلاع داده شد." if sent else ".") +
            f"\n\nدکمه 🔧 شروع پروژه رو بزن:\n\n{order_card(o2)}",
            parse_mode="Markdown",
            reply_markup=admin_keyboard(o2),
        )

    # ── 4. RECEIPT REJECTED ──
    elif data.startswith("adm:paybad:"):
        oid = int(data.split(":")[2])
        set_order_status(oid, "awaiting_payment")
        add_message(oid, "admin", "رسید نامعتبر بود — اصلاح شد", "system")
        context.user_data["awaiting_note_for"] = ("paybad", oid)
        await query.message.reply_text("📝 توضیح برای مشتری (چرا رسید قبول نشد؛ «-» = پیام پیش‌فرض):")

    # ── 5. START PROJECT ──
    elif data.startswith("adm:start:"):
        oid = int(data.split(":")[2])
        o = get_order(oid)
        if not o:
            await query.message.reply_text(f"⚠️ سفارش #{oid} دیگه وجود نداره (حذف شده).")
            return
        # check if auto-build applies (bot orders from support bot with chat binding)
        import json as _json
        try:
            req = _json.loads(o.get("requirements") or "{}")
        except (json.JSONDecodeError, TypeError):
            req = {}
        auto_ok = bool(req.get("chat")) and (o.get("project_type") or "") in (
            "telegram_bot", "data_scraping", "automation", "content_generation",
            "email_automation", "price_comparison", "whatsapp_bot", "custom",
        )
        set_order_status(oid, "in_progress")
        add_message(oid, "system", "پروژه شروع شد", "system")
        if auto_ok:
            # auto_builder picks it up (status paid→picked, or in_progress→build flag)
            import sqlite3 as _s3
            conn2 = _s3.connect(ORDERS_DB, timeout=10)
            conn2.execute("UPDATE orders SET requirements=? WHERE id=?",
                          (_json.dumps({**req, "auto_build": True}, ensure_ascii=False), oid))
            conn2.commit(); conn2.close()
            await send_customer(context, oid, "🔧 **ساخت پروژه‌ت شروع شد!**\n\nهوش مصنوعی داره پروژه‌ت رو می‌سازه — به‌زودی فایل آماده رو همین‌جا می‌گیری ⏳")
            await query.message.reply_text(
                f"🏗 ساخت خودکار سفارش #{oid} فعال شد — auto_builder خودش می‌سازه و تحویل میده.\n"
                f"(اگه شکست بخوره بهت اطلاع میده تا دستی بری)",
                parse_mode="Markdown",
            )
            return
        await send_customer(context, oid, "🔧 **پروژه‌ت شروع شد!**\n\nپیشرفت کار رو همین‌جا بهت اطلاع میدم. سوالی بود در خدمتم 💬")
        o = get_order(oid)
        await query.message.reply_text(
            f"🔧 سفارش #{oid} → در حال انجام\n\nوقتی آماده شد، دکمه 📦 تحویل رو بزن:\n\n" + order_card(o),
            parse_mode="Markdown",
            reply_markup=admin_keyboard(o),
        )

    # ── 6. DELIVER ──
    elif data.startswith("adm:deliver:"):
        oid = int(data.split(":")[2])
        context.user_data["awaiting_delivery_for"] = oid
        await query.message.reply_text(
            "📦 تحویل — بنویس:\n"
            "`لینک | فایل‌ها | توضیح`\n"
            "مثلاً: `https://... | bot.zip | سورس کامل`",
            parse_mode="Markdown",
        )

    # ── 7. MESSAGE CUSTOMER ──
    elif data.startswith("adm:message:"):
        oid = int(data.split(":")[2])
        context.user_data["awaiting_msg_for"] = oid
        await query.message.reply_text("💬 پیامت برای مشتری (ارسال مستقیم):")

    # ── 8. REOPEN CANCELLED ──
    elif data.startswith("adm:reopen:"):
        oid = int(data.split(":")[2])
        o = get_order(oid)
        if not o:
            await query.message.reply_text(f"⚠️ سفارش #{oid} دیگه وجود نداره (حذف شده).")
            return
        set_order_status(oid, "quoted")
        add_message(oid, "admin", "سفارش بازگشایی شد", "system")
        from support_bot import payment_text, payment_keyboard
        await send_customer(context, oid, payment_text(o), payment_keyboard(o))
        await query.message.reply_text(f"🔄 سفارش #{oid} بازگشایی شد و دوباره اطلاعات پرداخت رفت.")


# ══════════════════════════════════════════════════════════════════════════════
# Admin text: notes / delivery / direct replies
# ══════════════════════════════════════════════════════════════════════════════
async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = (update.message.text or "").strip()

    # /reply_<chat_id> message → direct customer reply
    m = re.match(r"^/reply[_ ](\d+)\s+(.+)$", text, re.DOTALL)
    if m:
        chat_id, msg = m.group(1), m.group(2).strip()
        try:
            await context.bot.send_message(int(chat_id), f"💬 **پشتیبانی:**\n\n{md_escape(msg)}", parse_mode="Markdown")
            await update.message.reply_text("✅ ارسال شد.")
        except Exception as e:
            await update.message.reply_text(f"⚠️ ارسال شکست خورد: {e}")
        return

    note = context.user_data.get("awaiting_note_for")
    if note:
        kind, oid = note
        context.user_data.pop("awaiting_note_for", None)
        o = get_order(oid)
        if kind == "reject":
            msg = "سفارش شما قابل قبول نیست." if text == "-" else text
            if o:
                await send_customer(context, oid, f"❌ **سفارش شما رد شد**\n\n{md_escape(msg)}\n\nبرای گفتگو: {flow.SUPPORT_HANDLE}")
            await update.message.reply_text(f"✅ سفارش #{oid} رد شد.")
        elif kind == "paybad":
            msg = "رسید پرداخت تأیید نشد — لطفاً مجدداً رسید درست رو بفرست." if text == "-" else text
            if o:
                await send_customer(context, oid, f"⚠️ **رسید پرداخت تأیید نشد**\n\n{md_escape(msg)}")
            await update.message.reply_text(f"✅ به مشتری اطلاع داده شد (سفارش #{oid}).")
        return

    delivery = context.user_data.get("awaiting_delivery_for")
    if delivery:
        oid = delivery
        context.user_data.pop("awaiting_delivery_for", None)
        parts = [p.strip() for p in text.split("|")]
        url = parts[0] if len(parts) > 0 and parts[0] != "-" else ""
        files = parts[1] if len(parts) > 1 and parts[1] != "-" else ""
        notes = parts[2] if len(parts) > 2 and parts[2] != "-" else ""
        set_order_status(oid, "delivered", {
            "deliverable_url": url, "deliverable_files": files, "delivery_notes": notes,
        })
        add_message(oid, "admin", f"تحویل: {url or files}", "delivery")
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📥 دریافت", callback_data=f"getdelivery:{oid}")]] if url else None)
        sent = await send_customer(context, oid,
                                   "🎉 **پروژه‌ت آماده‌ست!**\n\n" + (f"🔗 {url}\n" if url else "") + (f"📎 {files}\n" if files else "") + (f"\n📝 {md_escape(notes)}" if notes else ""),
                                   kb)
        await update.message.reply_text(
            f"📦 سفارش #{oid} تحویل داده شد" + (" و مشتری مطلع شد." if sent else "."),
            parse_mode="Markdown",
        )
        return

    msg_for = context.user_data.get("awaiting_msg_for")
    if msg_for:
        oid = msg_for
        context.user_data.pop("awaiting_msg_for", None)
        add_message(oid, "admin", text, "support")
        sent = await send_customer(context, oid, f"💬 **پیام تیم پروژه:**\n\n{md_escape(text)}")
        await update.message.reply_text("✅ ارسال شد." if sent else "⚠️ ارسال نشد (binding نیست).")
        return

    await update.message.reply_text("برای شروع: /start")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("bot error:", exc_info=context.error)
    try:
        await context.bot.send_message(ADMIN_ID, f"⚠️ خطای ربات ادمین:\n`{md_escape(str(context.error))[:300]}`",
                                       parse_mode="Markdown")
    except Exception:
        pass


def main():
    if not TOKEN:
        print("❌ SURVEY_BOT_TOKEN not set!")
        exit(1)

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_text))
    app.add_error_handler(on_error)

    if app.job_queue:
        app.job_queue.run_repeating(poll_new_orders, interval=30, first=5)
        app.job_queue.run_repeating(admin_inbox_worker, interval=5, first=3)

    print("📦 ربات مدیریت سفارشات فعال شد! (full lifecycle + admin inbox)")
    app.run_polling()


if __name__ == "__main__":
    main()
