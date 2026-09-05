#!/usr/bin/env python3
"""
🛒 ربات سفارش‌گیری هوشمند — AI Order Bot (@ShahbotSupportbot)
چرخه کامل سفارش:
۱. چت هوشمند AI → جمع‌آوری مشخصات + قیمت خودکار
۲. ثبت سفارش → اعلان به ادمین (@ShahbotSurveyBot)
۳. ادمین تأیید کرد → پیام پرداخت (کارت به کارت / کریپتو) به مشتری
۴. مشتری رسید/هش فرستاد → اعلان به ادمین برای بررسی
۵. ادمین تأیید کرد → پروژه در حال انجام → تحویل (فایل/لینک)
۶. سوال بودن → مشتری می‌تونه پیام بده؛ ادمین می‌تونه مستقیم جواب بده
۷. لغو/پشیمونی → اعلان به ادمین
"""

import os
import json
import re
import logging
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters,
)

import order_flow as flow
from order_flow import (
    ADMIN_ID, STATUS_FA, format_price, md_escape,
    get_order, set_order_status, add_message, get_messages,
    add_payment, confirm_payment_row, find_pending_payment,
    bind_chat, get_chat_binding, order_card, gen_order_number,
    fetch_outbox, set_outbox_sender, update_outbox_payload,
    queue_admin_message,
)

load_dotenv("/data/.hermes/.env", override=True)

TOKEN = os.environ.get("SUPPORT_BOT_TOKEN")
BOT_NAME = "support"   # chat binding marker

AI_KEY = os.environ.get("OPENAI_API_KEY")
AI_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
AI_MODEL = os.environ.get("AI_MODEL", "GLM")
ai_client = OpenAI(api_key=AI_KEY, base_url=AI_URL) if AI_KEY else None

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("order_bot")

# ─── Pricing (same as website) ───────────────────────────────────────────────
BASE_PRICES = {
    "telegram_bot": 5_000_000, "whatsapp_bot": 8_000_000, "data_scraping": 3_000_000,
    "website": 15_000_000, "automation": 10_000_000, "content_generation": 2_000_000,
    "email_automation": 5_000_000, "price_comparison": 5_000_000,
    "dashboard": 12_000_000, "custom": 20_000_000,
}
MULTIPLIERS = {"simple": 1.0, "medium": 1.5, "complex": 2.5, "enterprise": 4.0}
FEATURE_PRICE = 500_000

PROJECT_LABELS_FA = flow.PROJECT_LABELS_FA


def calculate_price(project_type: str, complexity: str, features: list) -> int:
    price = BASE_PRICES.get(project_type, 10_000_000)
    price *= MULTIPLIERS.get(complexity, 1.0)
    price += len(features) * FEATURE_PRICE
    return round(price)


# ─── AI chat (order intake) ──────────────────────────────────────────────────
SYSTEM_PROMPT = """تو دستیار فروش هوشمند هستی که سفارش پروژه می‌گیره.
کاربر می‌خواد یه پروژه سفارش بده. تو باید طی گفتگوی دوستانه و کوتاه (فارسی)، این اطلاعات رو جمع کنی:

1. project_type — یکی از این‌ها: telegram_bot, whatsapp_bot, data_scraping, website, automation, content_generation, email_automation, price_comparison, dashboard, custom
2. project_title — اسم کوتاه پروژه
3. description — توضیح اینکه پروژه چه کاری انجام میده
4. features — لیست ویژگی‌ها (آرایه رشته)
5. complexity — یکی از: simple, medium, complex, enterprise
6. budget — بودجه تقریبی (اختیاری، متن آزاد)

قوانین:
- فقط فارسی جواب بده، خوش‌برخورد و حرفه‌ای باش.
- هر بار فقط یه سوال بپرس؛ سوالات رو قدم‌به‌قدم بپرس.
- وقتی همه ۶ مورد رو داشتی، خلاصه سفارش رو نشون بده و از کاربر تأیید بگیر.
- اگه کاربر منصرف شد، محترمانه قبول کن.

خروجی: هر جواب باید JSON باشه با این ساختار:
{
  "message": "متن پیام تو به کاربر",
  "collected": {"project_type": ..., "project_title": ..., "description": ..., "features": [...], "complexity": ..., "budget": ...},
  "complete": true/false
}
هیچ متن اضافه‌ای خارج از JSON ننویس."""


def ai_reply(history: list) -> dict:
    if not ai_client:
        return {"message": "⚠️ موقتاً نمی‌تونم جواب بدم. لطفاً بعداً تلاش کنید.", "collected": {}, "complete": False}
    for attempt in range(3):
        try:
            resp = ai_client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}] + history,
                temperature=0.4,
                max_tokens=1000,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                continue
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                continue
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        except Exception as e:
            logger.error(f"AI error: {e}")
            break
    return {"message": "⚠️ یه مشکل فنی پیش اومد. لطفاً دوباره تلاش کنید.", "collected": {}, "complete": False}


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT INSTRUCTIONS (sent AFTER admin approval)
# ══════════════════════════════════════════════════════════════════════════════
def payment_text(o: dict) -> str:
    return (
        f"✅ **سفارش شما تأیید شد!**\n\n"
        f"🆔 `{o['order_number']}`\n"
        f"📦 {md_escape(o.get('project_title'))}\n"
        f"💰 مبلغ قابل پرداخت: **{format_price(o.get('final_price'))}**\n\n"
        f"💳 **روش پرداخت را انتخاب کنید:**\n\n"
        f"۱) کارت به کارت:\n"
        f"    🏦 بانک {flow.CARD_INFO['bank']}\n"
        f"    💳 `{flow.CARD_INFO['number']}`\n"
        f"    👤 {flow.CARD_INFO['name']}\n\n"
        f"۲) کریپتو (USDT — {flow.CRYPTO_INFO['network']}):\n"
        f"    💵 آدرس:\n    `{flow.CRYPTO_INFO['address']}`\n\n"
        f"بعد از پرداخت، **عکس رسید یا هش تراکنش** رو همین‌جا بفرست تا بررسی کنیم ✅"
    )


def payment_keyboard(o: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 کارت به کارت", callback_data=f"pay:card:{o['id']}"),
         InlineKeyboardButton("🪙 کریپتو", callback_data=f"pay:crypto:{o['id']}")],
        [InlineKeyboardButton("🧾 ارسال رسید / هش", callback_data=f"receipt:{o['id']}")],
        [InlineKeyboardButton("💬 صحبت با پشتیبانی", callback_data=f"ask_admin:{o['id']}")],
        [InlineKeyboardButton("❌ انصراف از سفارش", callback_data=f"cancelme:{o['id']}")],
    ])


def customer_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛒 ثبت سفارش جدید", callback_data="new_order")],
        [InlineKeyboardButton("📋 سفارش‌های من", callback_data="my_orders")],
        [InlineKeyboardButton("❓ سوالات متداول", callback_data="faq")],
        [InlineKeyboardButton("💬 صحبت با پشتیبانی", callback_data="support")],
    ])


# ══════════════════════════════════════════════════════════════════════════════
# Notify admin (via survey bot's chat is the admin's own chat; use ADMIN_ID on this bot too)
# ══════════════════════════════════════════════════════════════════════════════
async def notify_admin(context: ContextTypes.DEFAULT_TYPE, text: str, kb=None, photo_file_id=None):
    """Queue admin notification → delivered by @ShahbotSurveyBot (admin bot)."""
    queue_admin_message(0, text, kb)
    # note: photo receipts handled separately with queue_admin_photo()


# ══════════════════════════════════════════════════════════════════════════════
# Handlers
# ══════════════════════════════════════════════════════════════════════════════
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "سلام! 👋 به **ربات سفارش‌گیری پروژه** خوش اومدی.\n\n"
        "من با هوش مصنوعی کار می‌کنم و طی یه گفتگوی کوتاه، مشخصات پروژه‌ت رو "
        "دقیق درمیارم و **قیمت خودکار** بهت میدم.\n\n"
        "🛒 برای شروع روی دکمه زیر بزن یا مستقیم بنویس پروژه‌ت چیه!",
        parse_mode="Markdown",
        reply_markup=customer_home_kb(),
    )


async def cmd_myorders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_my_orders(update, context)


async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id=None):
    conn = __import__("sqlite3").connect(flow.ORDERS_DB)
    conn.row_factory = __import__("sqlite3").Row
    rows = conn.execute(
        "SELECT id, order_number, project_title, final_price, status FROM orders "
        "WHERE json_extract(requirements, '$.chat.chat_id') = ? ORDER BY id DESC LIMIT 10",
        (str(chat_id or update.effective_chat.id),),
    ).fetchall()
    conn.close()
    if not rows:
        await (update.callback_query.message.reply_text if update.callback_query else update.message.reply_text)(
            "📭 هنوز سفارشی ثبت نکردی. روی 🛒 ثبت سفارش جدید بزن!"
        )
        return
    lines = ["📋 **سفارش‌های تو:**\n"]
    for o in rows:
        lines.append(
            f"🆔 `{o['order_number']}`\n"
            f"   📦 {md_escape(o['project_title'])}\n"
            f"   💰 {format_price(o['final_price'])}\n"
            f"   🔖 {STATUS_FA.get(o['status'], o['status'])}\n"
            f"   🔍 جزئیات: /order\\_{o['order_number']}"
        )
    await (update.callback_query.message.reply_text if update.callback_query else update.message.reply_text)(
        "\n".join(lines), parse_mode="Markdown"
    )


async def cmd_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View one order by number: /order_ORD-XXXX"""
    if not context.args:
        await update.message.reply_text("کد سفارش رو بنویس: `/order_ORD-XXXXXX`", parse_mode="Markdown")
        return
    o = flow.get_order_by_number(context.args[0])
    if not o:
        await update.message.reply_text("❌ سفارش پیدا نشد.")
        return
    binding = get_chat_binding(o["id"])
    if not binding or str(binding.get("chat_id")) != str(update.effective_chat.id):
        await update.message.reply_text("🔒 این سفارش متعلق به این چت نیست.")
        return
    await update.message.reply_text(order_card(o), parse_mode="Markdown")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user
    chat_id = update.effective_chat.id

    # ── new order (AI chat) ──
    if data == "new_order":
        context.user_data["mode"] = "ai_order"
        context.user_data["chat_history"] = [{"role": "user", "content": "میخوام سفارش بدم."}]
        result = ai_reply(context.user_data["chat_history"])
        context.user_data["chat_history"].append({"role": "assistant", "content": json.dumps(result, ensure_ascii=False)})
        context.user_data["pending_order"] = result.get("collected", {})
        await query.message.reply_text(result["message"])

    elif data == "my_orders":
        await show_my_orders(update, context)

    elif data == "faq":
        await query.message.reply_text(
            "❓ **سوالات متداول**\n\n"
            "💰 **قیمت‌ها چطوره؟**\nقیمت خودکار بر اساس نوع پروژه، پیچیدگی و تعداد ویژگی‌ها محاسبه میشه.\n\n"
            "💳 **روش پرداخت؟**\nکارت به کارت یا کریپتو (USDT).\n\n"
            "⏱ **زمان تحویل؟**\nبعد از تأیید پرداخت اعلام میشه.\n\n"
            "🔁 **پشتیبانی بعد از تحویل؟**\n۷ روز پشتیبانی رایگان.",
            parse_mode="Markdown",
        )

    elif data == "support":
        context.user_data["mode"] = "free_support"
        await query.message.reply_text(
            "💬 سوالت رو بنویس — تیم پشتیبانی در اسرع وقت جواب میده.\n"
            "برای برگشتن به منوی اصلی /start بزن."
        )

    elif data == "confirm_order":
        collected = context.user_data.get("pending_order", {})
        price = calculate_price(collected.get("project_type", "custom"),
                                collected.get("complexity", "simple"), collected.get("features", []))
        order_number = gen_order_number()
        user_info = {"id": user.id, "username": "@" + user.username if user.username else user.first_name}
        conn = __import__("sqlite3").connect(flow.ORDERS_DB)
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO orders (order_number, user_id, project_type, project_title, description,
               requirements, base_price, final_price, currency, status, payment_status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (order_number, user.id, collected.get("project_type", "custom"),
             collected.get("project_title", "بدون عنوان"), collected.get("description", ""),
             json.dumps({**collected, "chat": {"chat_id": chat_id, "bot": BOT_NAME}}, ensure_ascii=False),
             price, price, "IRR", "pending", "pending", flow.now(), flow.now()),
        )
        order_id = cur.lastrowid
        conn.commit()
        conn.close()
        add_message(order_id, "system", f"سفارش از طریق ربات تلگرام ثبت شد ({user_info['username']})", "system")

        o = get_order(order_id)
        await notify_admin(context, "🔔 **سفارش جدید از ربات!**\n\n" + order_card(o),
                           kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأیید سفارش", callback_data=f"adm:approve:{order_id}")]]))
        await query.message.reply_text(
            "🎉 **سفارش ثبت شد!**\n\n"
            f"🆔 کد سفارش: `{order_number}`\n\n"
            "سفارشت داره بررسی میشه. بعد از تأیید، اطلاعات پرداخت رو همین‌جا برات می‌فرستم 📩",
            parse_mode="Markdown",
        )
        context.user_data.clear()

    elif data == "cancel_order":
        context.user_data.clear()
        await query.message.reply_text("باشه، سفارش لغو شد. هر وقت آماده بودی /start بزن! 🙂")

    # ── payment method chosen ──
    elif data.startswith("pay:"):
        _, method, oid = data.split(":")
        oid = int(oid)
        o = get_order(oid)
        if not o:
            await query.message.reply_text("❌ سفارش پیدا نشد.")
            return
        add_payment(oid, o["final_price"], method, "pending")
        set_order_status(oid, "awaiting_payment", {"payment_method": method})
        add_message(oid, "system", f"مشتری روش پرداخت {'کارت به کارت' if method == 'card' else 'کریپتو (USDT)'} رو انتخاب کرد", "system")
        if method == "card":
            detail = (f"💳 **کارت به کارت**\n\n"
                      f"🏦 بانک: {flow.CARD_INFO['bank']}\n"
                      f"💳 شماره کارت:\n`{flow.CARD_INFO['number']}`\n"
                      f"👤 به نام: {flow.CARD_INFO['name']}\n"
                      f"💰 مبلغ: **{format_price(o['final_price'])}**\n\n"
                      f"بعد از واریز، **عکس رسید** رو بفرست 📩")
        else:
            detail = (f"🪙 **کریپتو — USDT ({flow.CRYPTO_INFO['network']})**\n\n"
                      f"💵 آدرس کیف پول:\n`{flow.CRYPTO_INFO['address']}`\n"
                      f"💰 مبلغ: معادل **{format_price(o['final_price'])}** تومان\n\n"
                      f"بعد از واریز، **هش تراکنش (TxID)** رو بفرست 📩")
        await query.message.reply_text(detail, parse_mode="Markdown")

    # ── customer wants to send receipt ──
    elif data.startswith("receipt:"):
        oid = int(data.split(":")[1])
        context.user_data["mode"] = "awaiting_receipt"
        context.user_data["receipt_order_id"] = oid
        await query.message.reply_text(
            "🧾 **عکس رسید یا متن هش تراکنش** رو بفرست\n(برای کارت به کارت: عکس رسید — برای کریپتو: TxID)",
            parse_mode="Markdown",
        )

    # ── customer wants to talk to admin ──
    elif data.startswith("ask_admin:"):
        oid = int(data.split(":")[1])
        context.user_data["mode"] = "talk_to_admin"
        context.user_data["talk_order_id"] = oid
        await query.message.reply_text(
            "💬 پیامت رو بنویس — مستقیم برای تیم ما ارسال میشه و همین‌جا جواب می‌گیری."
        )

    # ── customer cancels (refund/regret) ──
    elif data.startswith("cancelme:"):
        oid = int(data.split(":")[1])
        o = get_order(oid)
        if o and o["status"] in ("pending", "quoted", "awaiting_payment"):
            set_order_status(oid, "cancelled")
            add_message(oid, "system", "مشتری از سفارش انصراف داد", "system")
            await notify_admin(context,
                               f"⚠️ **مشتری از سفارش منصرف شد!**\n\n{order_card(o)}",
                               kb=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 بازگشت سفارش", callback_data=f"adm:reopen:{oid}")]]))
            await query.message.reply_text(
                "متوجه شدم 🙂 سفارش لغو شد.\n"
                "اگه پرداختی داشتی، تا ۲۴ ساعت بررسی و برگشت داده میشه.\n"
                "هر وقت آماده بودی در خدمتتیم!",
                reply_markup=customer_home_kb(),
            )
        else:
            await query.message.reply_text("⚠️ این سفارش در مرحله‌ای هست که لغو آنلاین نداره — با پشتیبانی صحبت کن.")

    # ── customer picks deliverable ──
    elif data.startswith("getdelivery:"):
        oid = int(data.split(":")[1])
        o = get_order(oid)
        if not o:
            return
        files = o.get("deliverable_files") or ""
        url = o.get("deliverable_url") or ""
        txt = "📦 **تحویل پروژه**\n\n"
        if files:
            txt += f"📎 فایل‌ها: {files}\n"
        if url:
            txt += f"🔗 لینک: {url}\n"
        txt += "\n۷ روز پشتیبانی رایگان داری — سوالی بود در خدمتیم! 🎉"
        kb = []
        if url:
            kb.append([InlineKeyboardButton("🔗 باز کردن لینک", url=url)])
        await query.message.reply_text(txt, parse_mode="Markdown",
                                       reply_markup=InlineKeyboardMarkup(kb) if kb else None)


# ══════════════════════════════════════════════════════════════════════════════
# Message router: receipt / talk / AI order / free support
# ══════════════════════════════════════════════════════════════════════════════
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    user = update.effective_user
    chat_id = update.effective_chat.id
    mode = context.user_data.get("mode")

    # ── 1. receipt pending → forward to admin ──
    if mode == "awaiting_receipt":
        oid = context.user_data.get("receipt_order_id")
        o = get_order(oid)
        if not o:
            await update.message.reply_text("❌ سفارش پیدا نشد. دوباره تلاش کن.")
            context.user_data.clear()
            return
        receipt_text = text
        photo_file_id = None
        if update.message.photo:
            photo_file_id = update.message.photo[-1].file_id

        method = o.get("payment_method") or "card"
        pid_row = find_pending_payment(oid, method)
        pid = pid_row["id"] if pid_row else None
        add_payment(oid, o["final_price"], method, "pending",
                    transaction_id=receipt_text[:200] if receipt_text else None,
                    gateway_response="customer-submitted")
        # note: keep last pending payment as the receipt row
        set_order_status(oid, "payment_review")
        if photo_file_id:
            add_message(oid, "customer", "[عکس رسید ارسال شد]", "receipt_photo")
        elif receipt_text:
            add_message(oid, "customer", f"رسید: {receipt_text}", "receipt")

        caption = (f"🧾 **رسید پرداخت جدید!**\n\n{order_card(o)}\n\n"
                   f"👤 کاربر: {'@' + user.username if user.username else user.first_name} ({user.id})\n"
                   + (f"🔗 عکس رسید ضمیمه است" if photo_file_id else f"🧾 متن: `{md_escape(receipt_text)}`"))
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ پرداخت تأیید شد", callback_data=f"adm:payok:{oid}"),
            InlineKeyboardButton("❌ رسید نامعتبر", callback_data=f"adm:paybad:{oid}"),
        ]])
        if photo_file_id:
            # download photo to temp file so admin bot can re-send it
            try:
                tg_file = await context.bot.get_file(photo_file_id)
                os.makedirs("/data/workspace/projects/receipts", exist_ok=True)
                photo_path = f"/data/workspace/projects/receipts/{oid}_{int(datetime.now().timestamp())}.jpg"
                await tg_file.download_to_drive(custom_path=photo_path)
                queue_admin_message(oid, caption, kb, photo_path=photo_path)
            except Exception as e:
                logger.warning(f"photo download failed: {e}")
                queue_admin_message(oid, caption + "\n⚠️ (دانلود عکس شکست خورد — از مشتری بخواه دوباره بفرستد)", kb)
        else:
            queue_admin_message(oid, caption, kb)
        await update.message.reply_text("✅ رسیدت رسید! تا چند دقیقه بررسی می‌کنیم و نتیجه رو همین‌جا می‌گم 🙏")
        context.user_data.clear()
        return

    # ── 2. talking to admin ──
    if mode == "talk_to_admin":
        oid = context.user_data.get("talk_order_id")
        o = get_order(oid) if oid else None
        label = f"`{o['order_number']}`" if o else "بدون سفارش"
        await notify_admin(context,
                           f"💬 **پیام مستقیم مشتری** (سفارش {label})\n"
                           f"👤 {'@' + user.username if user.username else user.first_name} ({user.id})\n"
                           f"━━━━━━━━━━━\n{md_escape(text)}\n━━━━━━━━━━━\n"
                           f"برای پاسخ: /reply\\_{user.id} پیام")
        # store in order thread too
        if o:
            add_message(o["id"], "customer", text, "support")
        await update.message.reply_text("✅ پیامت رسید! به‌زودی جواب میدم.")
        context.user_data.clear()
        return

    # ── 3. free support chat (AI small talk / FAQ) ──
    if mode == "free_support":
        history = context.user_data.setdefault("support_history", [])
        history.append({"role": "user", "content": text})
        # simple AI answer w/ FAQ knowledge
        answer = ai_faq(history)
        history.append({"role": "assistant", "content": answer})
        await update.message.reply_text(answer)
        return

    # ── 4. AI order flow ──
    history = context.user_data.get("chat_history")
    if not history:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🛒 ثبت سفارش جدید", callback_data="new_order")]])
        await update.message.reply_text(
            "سلام! 👋 برای سفارش پروژه روی دکمه زیر بزن،\n"
            "یا مستقیم بنویس چه پروژه‌ای می‌خوای تا شروع کنیم!",
            reply_markup=kb,
        )
        context.user_data["mode"] = "ai_order"
        context.user_data["chat_history"] = [{"role": "user", "content": text}]
        result = ai_reply(context.user_data["chat_history"])
        context.user_data["chat_history"].append({"role": "assistant", "content": json.dumps(result, ensure_ascii=False)})
        context.user_data["pending_order"] = result.get("collected", {})
        await update.message.reply_text(result["message"])
        return

    history.append({"role": "user", "content": text})
    result = ai_reply(history)
    history.append({"role": "assistant", "content": json.dumps(result, ensure_ascii=False)})

    collected = result.get("collected", {})
    prev = context.user_data.get("pending_order", {})
    prev.update(collected)
    context.user_data["pending_order"] = prev

    if result.get("complete") and prev.get("project_title"):
        price = calculate_price(prev.get("project_type", "custom"), prev.get("complexity", "simple"), prev.get("features", []))
        features_text = "\n".join(f"  • {md_escape(f)}" for f in prev.get("features", [])) or "  • —"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ تأیید و ثبت", callback_data="confirm_order"),
            InlineKeyboardButton("❌ انصراف", callback_data="cancel_order"),
        ]])
        await update.message.reply_text(
            f"📋 **خلاصه سفارش:**\n\n"
            f"📦 پروژه: {md_escape(prev.get('project_title'))}\n"
            f"🗂 نوع: {PROJECT_LABELS_FA.get(prev.get('project_type'), prev.get('project_type'))}\n"
            f"📝 توضیح: {md_escape(prev.get('description', '—'))}\n"
            f"⚡️ ویژگی‌ها:\n{features_text}\n"
            f"🎯 پیچیدگی: {prev.get('complexity', 'simple')}\n"
            f"💰 **قیمت تخمینی: {format_price(price)}**\n\n"
            f"ثبت کنم؟",
            parse_mode="Markdown",
            reply_markup=kb,
        )
    else:
        await update.message.reply_text(result["message"])


def ai_faq(history: list) -> str:
    """Small AI-backed support chat with fallback."""
    if not ai_client:
        return "برای پاسخ دقیق‌تر لطفاً بعداً تلاش کن یا از دکمه «صحبت با پشتیبانی» استفاده کن."
    try:
        resp = ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "system", "content":
                       "تو پشتیبانی فروش پروژه هستی. فقط فارسی، کوتاه و مفید جواب بده. "
                       "روش پرداخت: کارت به کارت یا کریپتو USDT. قیمت‌گذاری خودکاره. "
                       "اگه سوال فنی پیچیده بود بگو تیم فنی بررسی کنه و جواب میدن."}] + history[-8:],
            temperature=0.5, max_tokens=400,
        )
        return (resp.choices[0].message.content or "").strip() or "چیزی نگفتم — دوباره بپرس 🙂"
    except Exception as e:
        logger.error(f"ai_faq error: {e}")
        return "⚠️ الان نمی‌تونم جواب بدم — پیامت ثبت شد، به‌زودی جواب میدم."


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Photo while awaiting receipt = receipt image."""
    if context.user_data.get("mode") == "awaiting_receipt":
        # reuse the same logic by faking text handler
        update.message.text = None
        await handle_message(update, context)
    else:
        await update.message.reply_text("عکس رسید رو از دکمه «🧾 ارسال رسید / هش» بفرست تا ثبتش کنم 📩")


# ══════════════════════════════════════════════════════════════════════════════
# Outbox worker: deliver messages queued by the admin bot to customers
# ══════════════════════════════════════════════════════════════════════════════
async def outbox_worker(context: ContextTypes.DEFAULT_TYPE):
    for row in fetch_outbox(5):
        mid, order_id, content = row["id"], row["order_id"], row["content"]
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            set_outbox_sender(mid, "outbox_error")
            continue
        chat_id = int(payload["chat_id"])
        text = payload["text"]
        kb = None
        if payload.get("kb"):
            try:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(str(b.get("text", "•")), **{k: v for k, v in b.items() if k != "text"}) for b in r] for r in payload["kb"]])
            except Exception as e:
                logger.warning(f"outbox kb parse failed mid={mid}: {e}")
        attempts = int(payload.get("attempts", 0))
        document_path = payload.get("document_path")
        try:
            if document_path and os.path.exists(document_path):
                with open(document_path, "rb") as doc:
                    await context.bot.send_document(chat_id, document=doc, caption=text, parse_mode="Markdown", reply_markup=kb)
            else:
                await context.bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=kb)
            set_outbox_sender(mid, "bot")  # delivered
            logger.info(f"outbox mid={mid} delivered to chat {chat_id}")
        except Exception as e:
            attempts += 1
            if attempts >= 5:
                set_outbox_sender(mid, "outbox_failed")
                await notify_admin(context, f"⚠️ ارسال پیام به مشتری شکست خورد (سفارش #{order_id}):\n{md_escape(str(e))}")
            else:
                payload["attempts"] = attempts
                update_outbox_payload(mid, payload)
            logger.warning(f"outbox mid={mid} attempt {attempts} failed: {e}")


def main():
    if not TOKEN:
        print("❌ SUPPORT_BOT_TOKEN not set!")
        exit(1)
    if not ai_client:
        print("❌ OPENAI_API_KEY not set (AI disabled)")
        exit(1)

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("myorders", cmd_myorders))
    app.add_handler(CommandHandler("order", cmd_order))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Outbox worker: deliver admin-queued messages to customers every 5s
    if app.job_queue:
        app.job_queue.run_repeating(outbox_worker, interval=5, first=3)

    print("🛒 ربات سفارش‌گیری هوشمند فعال شد! (full flow + outbox)")
    app.run_polling()


if __name__ == "__main__":
    main()
