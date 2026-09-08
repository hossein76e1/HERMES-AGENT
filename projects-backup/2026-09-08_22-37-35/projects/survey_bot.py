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

# ─── AI assistant (admin's AI helper) ────────────────────────────────────────
from openai import OpenAI

AI_KEY = os.environ.get("OPENAI_API_KEY")
AI_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
AI_MODEL = os.environ.get("AI_MODEL", "GLM")
ai_client = OpenAI(api_key=AI_KEY, base_url=AI_URL) if AI_KEY else None

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


def get_active_orders() -> list:
    """Return orders that still need the admin's attention (not delivered/cancelled)."""
    import sqlite3
    conn = sqlite3.connect(ORDERS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM orders WHERE status NOT IN ('delivered','cancelled') ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Direct admin→customer command (bypasses AI entirely) ────────────────────
async def cmd_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usage: /msg <order_id|order_number> <message>
       If only one active order exists, order_id is optional: /msg <message>"""
    if update.effective_user.id != ADMIN_ID:
        return

    args = context.args
    if not args:
        await update.message.reply_text(
            "📝 استفاده: `/msg <order_id|ORD-...> <پیام>`\n"
            "یا اگر فقط یک سفارش فعال داری: `/msg <پیام>`",
            parse_mode="Markdown",
        )
        return

    # Smart detection: if first arg is not a number/order_number, treat all as message
    # and auto-pick the single active order if exists.
    first = args[0]
    oid = None
    msg_text = ""

    if first.isdigit() or first.startswith("ORD-"):
        # Explicit order_id/order_number given
        if first.isdigit():
            oid = int(first)
        else:
            o_by_num = get_order_by_number(first.strip().replace("\\_", "_"))
            oid = o_by_num["id"] if o_by_num else None
        msg_text = " ".join(args[1:]).strip()
    else:
        # No explicit order — try to find exactly one active order
        active = get_active_orders()
        if len(active) == 1:
            oid = active[0]["id"]
            msg_text = " ".join(args).strip()
        elif len(active) > 1:
            await update.message.reply_text(
                "⚠️ چند سفارش فعال دارید. لطفاً شماره سفارش را مشخص کنید:\n"
                "`/msg <order_id|ORD-...> <پیام>`",
                parse_mode="Markdown",
            )
            return
        else:
            await update.message.reply_text("❌ سفارش فعالی یافت نشد.")
            return

    if not msg_text:
        await update.message.reply_text("⚠️ متن پیام خالیه.")
        return

    o = get_order(oid)
    if not o:
        await update.message.reply_text(f"❌ سفارش `{oid}` پیدا نشد.", parse_mode="Markdown")
        return

    sent = await send_customer(context, oid, f"💬 **پیام تیم پروژه:**\n\n{md_escape(msg_text)}")
    if sent:
        add_message(oid, "admin", f"(مستقیم): {msg_text}", "support")
        await update.message.reply_text(f"✅ پیام برای مشتری سفارش `{o['order_number']}` ارسال شد.", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ ارسال نشد — binding چت نیست (سفارش سایتی).")


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

    # ── 5. START PROJECT (manual — no auto-build, admin does the work) ──
    elif data.startswith("adm:start:"):
        oid = int(data.split(":")[2])
        o = get_order(oid)
        if not o:
            await query.message.reply_text(f"⚠️ سفارش #{oid} دیگه وجود نداره (حذف شده).")
            return
        set_order_status(oid, "in_progress")
        add_message(oid, "system", "پروژه شروع شد", "system")
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

    # ── 9. SUPPORT TRIAGE (post-delivery 7-day window) ──
    elif data.startswith("adm:sfree:"):
        _, _, oid, cust = data.split(":")
        oid = int(oid)
        o = get_order(oid)
        if not o:
            await query.message.reply_text(f"⚠️ سفارش #{oid} وجود نداره.")
            return
        days = flow.support_days_left(oid)
        if not days:
            await query.message.reply_text("⛔️ دورهٔ پشتیبانی این سفارش تموم شده — فقط سفارش جدید.")
            return
        context.user_data["awaiting_swork_for"] = oid
        context.user_data["awaiting_swork_cust"] = int(cust)
        await query.message.reply_text(
            f"🛠 **انجام تغییر رایگان** (سفارش #{oid})\n\n"
            "توضیح کوتاهی که بعد از انجام به مشتری بفرستیم رو بنویس\n"
            "(یا `-` بفرست تا پیام پیش‌فرض بره):\n\n"
            "اگه پروژه خودت رو می‌سازی، بعد از این پیام، لینک/توضیح رو با فرمت زیر بفرست:\n"
            "`لینک | فایل‌ها | توضیح`",
            parse_mode="Markdown",
        )

    elif data.startswith("adm:squote:"):
        _, _, oid, cust = data.split(":")
        oid = int(oid)
        o = get_order(oid)
        if not o:
            await query.message.reply_text(f"⚠️ سفارش #{oid} وجود نداره.")
            return
        context.user_data["awaiting_squote_for"] = (oid, int(cust))
        await query.message.reply_text(
            f"💰 **تغییر اساسی — درخواست پرداخت جدید** (سفارش #{oid})\n\n"
            "پیام قیمت برای مشتری رو بنویس. مثلاً:\n"
            "`تغییر موردنیاز خیلی کلیه و مثل یه پروژهٔ جدیده — ۲٬۰۰۰٬۰۰۰ تومان. بعد از پرداخت، ۷ روز پشتیبانی دوباره فعال می‌شه.`",
            parse_mode="Markdown",
        )

    elif data.startswith("adm:sreply:"):
        _, _, oid, cust = data.split(":")
        context.user_data["awaiting_sreply_for"] = int(cust)
        await query.message.reply_text("💬 پاسخت برای مشتری (مستقیم ارسال می‌شه):")


# ══════════════════════════════════════════════════════════════════════════════
# Admin text: notes / delivery / direct replies
# ══════════════════════════════════════════════════════════════════════════════
async def handle_admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = (update.message.text or "").strip()

    # /reply_<chat_id> message → direct customer reply (fallback → outbox)
    m = re.match(r"^/reply[_ ](\d+)\s+(.+)$", text, re.DOTALL)
    if m:
        chat_id, msg = m.group(1), m.group(2).strip()
        sent = await send_customer_chat(context, chat_id, f"💬 **پشتیبانی:**\n\n{md_escape(msg)}")
        await update.message.reply_text("✅ ارسال شد." if sent else "⚠️ ارسال نشد — چت پیدا نشد.")
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

    # ── support: free change done ──
    swork = context.user_data.get("awaiting_swork_for")
    if swork:
        oid = swork
        cust = context.user_data.pop("awaiting_swork_cust", None)
        context.user_data.pop("awaiting_swork_for", None)
        days = flow.support_days_left(oid)
        if not days:
            await update.message.reply_text("⛔️ دورهٔ پشتیبانی تموم شده — تغییر رایگان فقط در بازهٔ ۷ روزه.")
            return
        msg = "✅ **تغییرت انجام شد!**\n\nفایل/لینک به‌روز شده — بگیر و تست کن. سوالی بود در خدمتیم 🛡" if text == "-" else md_escape(text)
        await send_customer_chat(context, cust, f"🛠 **پشتیبانی (سفارش #{oid})**\n\n{msg}")
        add_message(oid, "admin", f"پشتیبانی رایگان: {text}", "support")
        await update.message.reply_text(f"✅ تغییر رایگان سفارش #{oid} به مشتری اطلاع داده شد ({days} روز باقی‌مانده).")
        return

    # ── support: paid change quote ──
    squote = context.user_data.get("awaiting_squote_for")
    if squote:
        oid, cust = squote
        context.user_data.pop("awaiting_squote_for", None)
        add_message(oid, "admin", f"درخواست پرداخت برای تغییر اساسی: {text}", "support")
        await send_customer_chat(context, cust,
                                 f"💰 **تغییر درخواستی‌ت نیاز به پرداخت داره**\n\n{md_escape(text)}\n\n"
                                 "برای شروع، از دکمهٔ 🛒 سفارش جدید استفاده کن یا همین پیام رو جواب بده.")
        await update.message.reply_text(f"✅ پیام پرداخت جدید برای سفارش #{oid} به مشتری ارسال شد.")
        return

    # ── support: text reply ──
    sreply = context.user_data.get("awaiting_sreply_for")
    if sreply:
        cust = sreply
        context.user_data.pop("awaiting_sreply_for", None)
        await send_customer_chat(context, cust, f"💬 **پشتیبانی:**\n\n{md_escape(text)}")
        await update.message.reply_text("✅ ارسال شد.")
        return

    # ── fallback: plain text → AI assistant (same as /ai) ──
    thinking = await update.message.reply_text("🤖 دارم بررسی می‌کنم...")
    decision = ai_decide(text)
    try:
        result_text = await ai_execute(context, decision)
    except Exception as e:
        logger.error(f"ai_execute failed: {e}")
        result_text = f"⚠️ اجرای دستور شکست خورد: {md_escape(str(e))[:200]}"
    reply = decision.get("reply") or ""
    body = (f"{reply}\n\n" if reply and reply != result_text else "") + result_text
    try:
        await thinking.edit_text(body[:4000], parse_mode="Markdown", disable_web_page_preview=True)
    except Exception:
        await update.message.reply_text(body[:4000], parse_mode="Markdown")


async def send_customer_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int | str, text: str, kb=None) -> bool:
    """Send directly to a customer chat id (support replies) — falls back to outbox queue."""
    try:
        await context.bot.send_message(int(chat_id), text, parse_mode="Markdown", reply_markup=kb)
        return True
    except Exception:
        # queue via outbox (delivered by @ShahbotSupportbot)
        import json as _j
        payload = {"chat_id": str(chat_id), "text": text, "attempts": 0}
        if kb is not None:
            try:
                payload["kb"] = kb.to_dict().get("inline_keyboard")
            except Exception:
                pass
        try:
            conn = flow.sqlite3.connect(flow.ORDERS_DB, timeout=10)
            conn.execute(
                "INSERT INTO order_messages (order_id, sender_type, content, message_type, created_at) VALUES (?,?,?,?,?)",
                (0, "outbox", _j.dumps(payload, ensure_ascii=False), "outbound", flow.now()),
            )
            conn.commit()
            conn.close()
            logger.info(f"send_customer_chat: direct send failed → queued via outbox for chat {chat_id}")
            return True
        except Exception as e:
            logger.error(f"send_customer_chat: outbox fallback failed: {e}")
            return False


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("bot error:", exc_info=context.error)
    try:
        await context.bot.send_message(ADMIN_ID, f"⚠️ خطای ربات ادمین:\n`{md_escape(str(context.error))[:300]}`",
                                       parse_mode="Markdown")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# AI assistant: admin sends /ai <درخواست> → AI decides action & executes
# ══════════════════════════════════════════════════════════════════════════════
AI_SYSTEM_PROMPT = """تو دستیار هوشمند ادمین سیستم سفارشات هستی.
ادمین یه درخواست به فارسی می‌نویسه و تو باید یا جواب بدی یا یه action اجرا کنی.

action های مجاز:
1. order_info — args: {"order_number": "ORD-..."} یا {"order_id": 12} → جزئیات کامل یک سفارش
2. orders_list — args: {"status": "pending|quoted|awaiting_payment|payment_review|paid|in_progress|ready|delivered|cancelled" یا null برای همه, "limit": 10} → لیست سفارش‌ها
3. stats — args: {} → آمار فروش
4. thread — args: {"order_id": 12, "limit": 15} → تاریخچه پیام‌های سفارش
5. set_status — args: {"order_id": 12, "status": "...", "note": "یادداشت اختیاری"} → تغییر وضعیت سفارش
6. send_customer — args: {"order_id": 12, "text": "پیام"} → ارسال پیام به مشتری سفارش
7. help — args: {} → راهنمای ربات

خروجی: فقط JSON با این ساختار:
{"action": "...", "args": {...}, "reply": "متن فارسی کوتاه برای ادمین"}
اگه درخواست‌ها مبهمه، بهترین حدس رو بزن و action بده. هیچ متن خارج از JSON ننویس."""


def ai_decide(request_text: str) -> dict:
    """Ask AI what to do with the admin's request. Returns parsed JSON."""
    if not ai_client:
        logger.info(f"[AI_DECIDE] req={request_text!r} → ai_down (no client)")
        return {"action": "ai_down", "args": {}, "reply": ""}
    for _ in range(3):
        try:
            resp = ai_client.chat.completions.create(
                model=AI_MODEL,
                messages=[
                    {"role": "system", "content": AI_SYSTEM_PROMPT},
                    {"role": "user", "content": request_text},
                ],
                temperature=0.2,
                max_tokens=800,
            )
            text = (resp.choices[0].message.content or "").strip()
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                d = json.loads(m.group(0))
                logger.info(f"[AI_DECIDE] req={request_text!r} → action={d.get('action')} args={json.dumps(d.get('args') or {}, ensure_ascii=False)[:120]}")
                return d
        except json.JSONDecodeError:
            continue
        except Exception as e:
            logger.error(f"admin AI error: {e}")
            break
    logger.info(f"[AI_DECIDE] req={request_text!r} → ai_down (service error after retries)")
    return {"action": "ai_down", "args": {}, "reply": ""}


def _find_order(args: dict):
    oid = args.get("order_id")
    if oid:
        return get_order(int(oid))
    num = args.get("order_number")
    if num:
        return get_order_by_number(str(num).strip().replace("\\_", "_"))
    return None


async def ai_execute(context: ContextTypes.DEFAULT_TYPE, decision: dict) -> str:
    """Execute AI-chosen action → returns result text (markdown) for admin."""
    action = (decision.get("action") or "help").lower()
    args = decision.get("args") or {}

    if action == "ai_down":
        # AI service unavailable (no client or 429/503 after retries)
        return ("⚠️ **سرویس هوش مصنوعی در دسترس نیست** (قطع یا شلوغ).\n\n"
                "دستور اجرا نشد — لطفاً چند دقیقه دیگه دوباره بفرست.\n"
                "اگر عجله داری، از دکمه‌های زیر یا فرمان مستقیم (`/reply_<chat_id> متن`) استفاده کن.")

    if action == "order_info":
        o = _find_order(args)
        if not o:
            return "❌ سفارش پیدا نشد."
        msgs = get_messages(o["id"], limit=10)
        thread = "\n".join(f"  • [{m['sender_type']}] {md_escape(m['content'][:80])}" for m in msgs) or "  —"
        return order_card(o) + f"\n\n💬 آخرین پیام‌ها:\n{thread}"

    if action == "orders_list":
        status = args.get("status") or None
        limit = min(int(args.get("limit") or 10), 20)
        rows = []
        import sqlite3
        conn = sqlite3.connect(ORDERS_DB)
        conn.row_factory = sqlite3.Row
        if status:
            rows = conn.execute("SELECT * FROM orders WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        if not rows:
            return f"📭 سفارشی با این شرایط نیست ({status or 'همه'})."
        lines = [f"📋 {len(rows)} سفارش:"]
        for r in rows:
            d = dict(r)
            lines.append(f"🆔 `{d['order_number']}` | {md_escape(d.get('project_title') or '')} | {STATUS_FA.get(d['status'], d['status'])} | {format_price(d.get('final_price'))}")
        return "\n".join(lines)

    if action == "stats":
        s = await db_stats()
        return ("📊 **آمار فروش:**\n\n"
                f"🛒 کل: {s['total']}\n"
                f"⏳ در انتظار: {s['pending']}\n"
                f"🧾 بررسی رسید: {s['review']}\n"
                f"🔧 در حال انجام: {s['in_progress']}\n"
                f"✅ تحویل شده: {s['delivered']}\n"
                f"💰 درآمد (تحویل‌شده): {format_price(s['revenue'])}")

    if action == "thread":
        oid = int(args.get("order_id") or 0)
        o = get_order(oid)
        if not o:
            return "❌ سفارش پیدا نشد."
        msgs = get_messages(oid, limit=min(int(args.get("limit") or 15), 30))
        if not msgs:
            return "📭 پیامی در این سفارش نیست."
        lines = [f"💬 پیام‌های سفارش `{o['order_number']}`:"]
        for m in msgs:
            lines.append(f"[{m['sender_type']}] {md_escape(m['content'][:120])}")
        return "\n".join(lines)

    if action == "set_status":
        oid = int(args.get("order_id") or 0)
        new_status = str(args.get("status") or "").strip()
        o = get_order(oid)
        if not o:
            return "❌ سفارش پیدا نشد."
        if new_status not in STATUS_FA:
            return (f"⚠️ وضعیت نامعتبر: `{new_status}`\n\nوضعیت‌های مجاز:\n" +
                    "\n".join(f"• `{k}` = {v}" for k, v in STATUS_FA.items()))
        note = args.get("note")
        set_order_status(oid, new_status)
        add_message(oid, "admin", note or f"وضعیت → {STATUS_FA[new_status]} (دستیار AI ادمین)", "system")
        o2 = get_order(oid)
        return f"✅ سفارش `{o['order_number']}` → **{STATUS_FA[new_status]}**\n\n{order_card(o2)}"

    if action == "send_customer":
        oid = int(args.get("order_id") or 0)
        text = str(args.get("text") or "").strip()
        o = get_order(oid)
        if not o:
            return "❌ سفارش پیدا نشد."
        if not text:
            return "⚠️ متن پیام خالیه."
        sent = await send_customer(context, oid, f"💬 **پیام تیم پروژه:**\n\n{md_escape(text)}")
        if sent:
            add_message(oid, "admin", f"(دستیار AI): {text}", "support")
            return f"✅ پیام برای مشتری سفارش `{o['order_number']}` ارسال شد."
        return "⚠️ ارسال نشد — binding چت نیست (سفارش سایتی)."

    # help / unknown
    return ("🤖 **دستیار AI ادمین**\n\n"
            "نمونه درخواست‌ها:\n"
            "• `/ai سفارش ORD-20260905-HR4367 رو نشونم بده`\n"
            "• `/ai سفارش‌های در انتظار بررسی`\n"
            "• `/ai آمار فروش`\n"
            "• `/ai پیام‌های سفارش 25 رو نشون بده`\n"
            "• `/ai وضعیت سفارش 25 رو بذار in_progress`\n"
            "• `/ai به مشتری سفارش 25 بگو فردا تحویل میشه`")


async def cmd_ai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin AI assistant: /ai <request>"""
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text(
            "🤖 دستیار AI — درخواستت رو بنویس:\n`/ai آمار فروش`",
            parse_mode="Markdown",
        )
        return
    request_text = " ".join(context.args).strip()
    thinking = await update.message.reply_text("🤖 دارم بررسی می‌کنم...")
    decision = ai_decide(request_text)
    try:
        result_text = await ai_execute(context, decision)
    except Exception as e:
        logger.error(f"ai_execute failed: {e}")
        result_text = f"⚠️ اجرای دستور شکست خورد: {md_escape(str(e))[:200]}"
    reply = decision.get("reply") or ""
    body = (f"{reply}\n\n" if reply and reply != result_text else "") + result_text
    await thinking.edit_text(body[:4000], parse_mode="Markdown", disable_web_page_preview=True)


def main():
    if not TOKEN:
        print("❌ SURVEY_BOT_TOKEN not set!")
        exit(1)

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ai", cmd_ai))
    app.add_handler(CommandHandler("msg", cmd_msg))
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
