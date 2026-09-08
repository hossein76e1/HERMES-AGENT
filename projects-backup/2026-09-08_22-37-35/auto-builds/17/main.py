import os
import re
import logging
import time

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------------- تنظیمات لاگ ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# توکن ربات از متغیر محیطی خوانده می‌شود (بدون کلید هاردکد)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

if not BOT_TOKEN:
    raise RuntimeError("متغیر محیطی BOT_TOKEN تنظیم نشده است. لطفاً توکن ربات را وارد کنید.")

# الگوی تشخیص لینک پست اینستاگرام
INSTAGRAM_POST_PATTERN = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)/?",
    re.IGNORECASE,
)

# حافظه موقت برای جلوگیری از اسپم (شناسه کاربر -> زمان آخرین درخواست)
user_last_request = {}
RATE_LIMIT_SECONDS = 10


# ---------------- دستورات ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور /start - پیام خوش‌آمدگویی"""
    welcome_text = (
        "👋 سلام! به ربات لایک اینستاگرام خوش آمدید.\n\n"
        "📌 برای دریافت لایک، لینک پست اینستاگرام خود را ارسال کنید.\n"
        "مثال:\n"
        "https://www.instagram.com/p/CxYzAbCdEfG/\n\n"
        "⚡️ دستورات موجود:\n"
        "/start - شروع ربات\n"
        "/help - راهنما\n"
        "/about - درباره ربات"
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("📖 راهنما", callback_data="help")]]
    )
    await update.message.reply_text(welcome_text, reply_markup=keyboard)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور /help - راهنمای استفاده"""
    help_text = (
        "📖 راهنمای استفاده از ربات:\n\n"
        "۱️⃣ لینک پست اینستاگرام خود را کپی کنید.\n"
        "۲️⃣ لینک را در ربات ارسال کنید.\n"
        "۳️⃣ ربات به صورت خودکار لایک‌ها را پردازش می‌کند.\n\n"
        "⚠️ نکته: فاصله بین هر درخواست حداقل ۱۰ ثانیه باشد."
    )
    await update.message.reply_text(help_text)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """دستور /about - درباره ربات"""
    about_text = (
        "🤖 ربات لایک اینستاگرام\n"
        "نسخه: ۱.۰.۰\n\n"
        "این ربات برای پردازش درخواست لایک پست‌های اینستاگرام طراحی شده است."
    )
    await update.message.reply_text(about_text)


# ---------------- پردازش لینک ----------------
def extract_post_shortcode(text: str):
    """استخراج کد پست از لینک اینستاگرام"""
    match = INSTAGRAM_POST_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def simulate_like(shortcode: str) -> dict:
    """
    شبیه‌سازی عملیات لایک.
    در نسخه واقعی، اینجا به سرویس لایک متصل می‌شود.
    """
    # شبیه‌سازی پردازش
    likes_delivered = 50
    return {
        "success": True,
        "shortcode": shortcode,
        "likes": likes_delivered,
        "message": f"✅ {likes_delivered} لایک با موفقیت ارسال شد!",
    }


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پردازش پیام‌های متنی کاربر (لینک اینستاگرام)"""
    user_id = update.effective_user.id
    text = update.message.text

    # بررسی محدودیت نرخ درخواست
    now = time.time()
    last_request = user_last_request.get(user_id, 0)
    if now - last_request < RATE_LIMIT_SECONDS:
        remaining = int(RATE_LIMIT_SECONDS - (now - last_request))
        await update.message.reply_text(
            f"⏳ لطفاً {remaining} ثانیه دیگر دوباره تلاش کنید."
        )
        return

    # بررسی لینک اینستاگرام
    shortcode = extract_post_shortcode(text)
    if not shortcode:
        await update.message.reply_text(
            "❌ لینک ارسالی معتبر نیست.\n"
            "لطفاً لینک پست اینستاگرام را به شکل صحیح ارسال کنید:\n"
            "https://www.instagram.com/p/XXXXXXX/"
        )
        return

    # ثبت زمان درخواست
    user_last_request[user_id] = now

    # ارسال پیام در حال پردازش
    processing_msg = await update.message.reply_text("⏳ در حال پردازش درخواست...")

    # شبیه‌سازی تاخیر پردازش
    await asyncio.sleep(2)

    # انجام عملیات لایک
    result = simulate_like(shortcode)

    if result["success"]:
        response_text = (
            f"🎉 درخواست شما با موفقیت انجام شد!\n\n"
            f"🔗 پست: https://www.instagram.com/p/{result['shortcode']}/\n"
            f"❤️ {result['message']}\n\n"
            f"برای درخواست بعدی، لینک جدید ارسال کنید."
        )
    else:
        response_text = "❌ متأسفانه پردازش با خطا مواجه شد. لطفاً دوباره تلاش کنید."

    await processing_msg.edit_text(response_text)


# ---------------- پردازش دکمه‌های شیشه‌ای ----------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """پردازش کلیک روی دکمه‌های شیشه‌ای"""
    query = update.callback_query
    await query.answer()

    if query.data == "help":
        help_text = (
            "📖 راهنمای استفاده:\n\n"
            "۱️⃣ لینک پست اینستاگرام را کپی کنید.\n"
            "۲️⃣ لینک را در ربات ارسال کنید.\n"
            "۳️⃣ منتظر تأیید بمانید."
        )
        await query.edit_message_text(help_text)


# ---------------- مدیریت خطا ----------------
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """مدیریت خطاهای رخ داده در ربات"""
    logger.error("خطا در پردازش آپدیت: %s", context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ خطایی رخ داد. لطفاً بعداً دوباره تلاش کنید."
        )


# ---------------- اجرای ربات ----------------
def main() -> None:
    """راه‌اندازی و اجرای ربات"""
    application = Application.builder().token(BOT_TOKEN).build()

    # ثبت هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("about", about))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ثبت هندلر خطا
    application.add_error_handler(error_handler)

    # شروع ربات
    logger.info("ربات در حال اجرا است...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    import asyncio
    main()
