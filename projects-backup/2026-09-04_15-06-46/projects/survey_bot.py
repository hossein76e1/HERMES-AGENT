#!/usr/bin/env python3
"""
🤖 ربات نظرسنجی تلگرام - Telegram Survey Bot (Farsi)
Professional survey/poll bot with JSON persistence and admin features.
"""

import os
import json
import logging
import uuid
from datetime import datetime
from collections import Counter
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ─── Configuration ───────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("SURVEY_BOT_TOKEN", "")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "survey_data")
SURVEYS_FILE = os.path.join(DATA_DIR, "surveys.json")
RESPONSES_FILE = os.path.join(DATA_DIR, "responses.json")
ADMIN_IDS: list[int] = []  # Set via environment or add here

os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("survey_bot")

# ─── Conversation states for /create_survey ──────────────────────────────────
(
    CS_TITLE,
    CS_NUM_QUESTIONS,
    CS_Q_TEXT,
    CS_Q_TYPE,
    CS_Q_OPTIONS,
    CS_CONFIRM,
) = range(6)

# ─── Default surveys ─────────────────────────────────────────────────────────
DEFAULT_SURVEYS = {
    "satisfaction": {
        "id": "satisfaction",
        "title": "📊 نظرسنجی رضایت کاربران",
        "description": "لطفاً در این نظرسنجی شرکت کنید تا خدمات بهتری ارائه دهیم 🙏",
        "created_at": datetime.now().isoformat(),
        "created_by": "system",
        "questions": [
            {
                "id": "q1",
                "text": "❓ از خدمات ما چقدر راضی هستید؟",
                "type": "choice",
                "options": ["⭐ عالی", "👍 خوب", "😐 متوسط", "👎 بد", "❌ خیلی بد"],
            },
            {
                "id": "q2",
                "text": "🕐 چند وقت یک‌بار از خدمات ما استفاده می‌کنید؟",
                "type": "choice",
                "options": [
                    "📅 روزانه",
                    "📆 هفتگی",
                    "🗓 ماهانه",
                    "🔘 به‌ندرت",
                ],
            },
            {
                "id": "q3",
                "text": "💡 چه پیشنهادی برای بهبود خدمات دارید؟",
                "type": "text",
            },
        ],
    },
    "tech_survey": {
        "id": "tech_survey",
        "title": "💻 نظرسنجی علاقه‌مندی‌های فناوری",
        "description": "ببینیم علاقه‌مندی‌های شما در دنیای فناوری چیست! 🚀",
        "created_at": datetime.now().isoformat(),
        "created_by": "system",
        "questions": [
            {
                "id": "q1",
                "text": "🛠 زبان برنامه‌نویسی مورد علاقه شما کدام است؟",
                "type": "choice",
                "options": [
                    "🐍 Python",
                    "☕ Java",
                    "🌐 JavaScript",
                    "🦀 Rust",
                    "💎 Other",
                ],
            },
            {
                "id": "q2",
                "text": "📱 سیستم‌عامل موبایل شما چیست؟",
                "type": "choice",
                "options": ["🤖 Android", "🍎 iOS", ".other"],
            },
            {
                "id": "q3",
                "text": "💬 نظر شما درباره هوش مصنوعی چیست؟",
                "type": "text",
            },
        ],
    },
}


# ─── Data helpers ─────────────────────────────────────────────────────────────
def load_surveys() -> dict:
    if os.path.exists(SURVEYS_FILE):
        with open(SURVEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # First run: seed defaults
    save_surveys(DEFAULT_SURVEYS)
    return DEFAULT_SURVEYS


def save_surveys(data: dict):
    with open(SURVEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_responses() -> dict:
    if os.path.exists(RESPONSES_FILE):
        with open(RESPONSES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_responses(data: dict):
    with open(RESPONSES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_admin(user_id: int) -> bool:
    if not ADMIN_IDS:
        return True  # No restriction if none set
    return user_id in ADMIN_IDS


# ─── /start ──────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"سلام {user.first_name} 👋✨\n"
        f"به **ربات نظرسنجی تلگرام** خوش آمدید!\n\n"
        f"🔷 با استفاده از دستورات زیر می‌توانید:\n\n"
        f"📋 /survey — شروع یک نظرسنجی\n"
        f"📊 /results — مشاهده نتایج\n"
        f"📝 /list — لیست نظرسنجی‌های موجود\n"
        f"ℹ️ /help — راهنمای دستورات\n"
    )
    if is_admin(user.id):
        text += (
            f"\n🔒 دستورات مدیریتی:\n"
            f"➕ /create_survey — ساخت نظرسنجی جدید\n"
            f"🗑 /delete_survey — حذف نظرسنجی\n"
        )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── /help ───────────────────────────────────────────────────────────────────
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 **راهنمای ربات نظرسنجی**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔹 **/start** — شروع مجدد و نمایش پیام خوش‌آمدگویی\n"
        "🔹 **/survey** — لیست نظرسنجی‌ها و شرکت در آن‌ها\n"
        "🔹 **/list** — مشاهده تمام نظرسنجی‌های موجود\n"
        "🔹 **/results** — مشاهده خلاصه نتایج نظرسنجی‌ها\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 نکته: پاسخ‌های شما به‌صورت ناشناس ذخیره می‌شوند.\n"
        "🛡 حریم خصوصی شما برای ما مهم است!\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── /list ───────────────────────────────────────────────────────────────────
async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    surveys = load_surveys()
    if not surveys:
        await update.message.reply_text("📭 هیچ نظرسنجی‌ای موجود نیست.")
        return
    lines = ["📋 **لیست نظرسنجی‌های موجود**\n━━━━━━━━━━━━━━━━━━━━━\n"]
    for sid, s in surveys.items():
        q_count = len(s.get("questions", []))
        lines.append(f"🔹 *{s['title']}*\n   📝 تعداد سوالات: {q_count}\n")
    lines.append("💡 برای شرکت در نظرسنجی: /survey")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─── /survey — pick a survey ─────────────────────────────────────────────────
async def cmd_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    surveys = load_surveys()
    if not surveys:
        await update.message.reply_text("📭 در حال حاضر نظرسنجی فعالی وجود ندارد.")
        return
    buttons = []
    for sid, s in surveys.items():
        buttons.append([InlineKeyboardButton(s["title"], callback_data=f"take:{sid}")])
    kb = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "📋 **یک نظرسنجی را انتخاب کنید:**\n\n"
        "روی دکمه مورد نظر کلیک کنید 👇",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def survey_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("take:"):
        sid = data.split(":", 1)[1]
        surveys = load_surveys()
        if sid not in surveys:
            await query.edit_message_text("❌ نظرسنجی یافت نشد.")
            return
        survey = surveys[sid]
        context.user_data["current_survey"] = sid
        context.user_data["current_q_idx"] = 0
        context.user_data["answers"] = {}
        await send_question(update, context, query)


async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE, query):
    sid = context.user_data["current_survey"]
    q_idx = context.user_data["current_q_idx"]
    surveys = load_surveys()
    survey = surveys[sid]
    questions = survey["questions"]

    if q_idx >= len(questions):
        # Survey complete — save
        uid = str(update.effective_user.id)
        responses = load_responses()
        if sid not in responses:
            responses[sid] = []
        responses[sid].append(
            {
                "user_id": uid,
                "timestamp": datetime.now().isoformat(),
                "answers": context.user_data["answers"],
            }
        )
        save_responses(responses)
        await query.edit_message_text(
            "✅ **ممنون از مشارکت شما!** 🎉\n\n"
            "پاسخ‌های شما با موفقیت ذخیره شد.\n"
            "📎 برای مشاهده نتایج: /results"
        )
        context.user_data.clear()
        return

    q = questions[q_idx]
    progress = f"[{q_idx + 1}/{len(questions)}]"
    header = f"{survey['title']}\n━━━━━━━━━━━━━━━━━━━━━\n\n"

    if q["type"] == "choice":
        text = f"{header}🔄 سوال {progress}\n\n{q['text']}\n\n🔹 یکی از گزینه‌ها را انتخاب کنید:"
        buttons = []
        for i, opt in enumerate(q["options"]):
            buttons.append(
                [InlineKeyboardButton(opt, callback_data=f"ans:{q_idx}:{i}")]
            )
        kb = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        text = (
            f"{header}🔄 سوال {progress}\n\n{q['text']}\n\n"
            f"⌨️ پاسخ خود را به‌صورت متنی ارسال کنید:"
        )
        context.user_data["awaiting_text"] = True
        await query.edit_message_text(text, parse_mode="Markdown")


async def choice_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if not data.startswith("ans:"):
        return
    await query.answer()
    parts = data.split(":")
    q_idx = int(parts[1])
    opt_idx = int(parts[2])

    surveys = load_surveys()
    sid = context.user_data.get("current_survey")
    survey = surveys.get(sid)
    if not survey:
        return
    q = survey["questions"][q_idx]
    chosen = q["options"][opt_idx]

    context.user_data["answers"][q["id"]] = chosen
    context.user_data["current_q_idx"] = q_idx + 1
    context.user_data.pop("awaiting_text", None)

    await query.edit_message_text(
        f"✅ پاسخ شما ثبت شد: **{chosen}**\n\n⏳ در حال بارگذاری سوال بعدی..."
    )
    # Small delay effect
    import asyncio
    await asyncio.sleep(0.5)
    await send_question(update, context, query)


async def text_answer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_text"):
        return  # Not in survey text mode

    sid = context.user_data.get("current_survey")
    q_idx = context.user_data.get("current_q_idx", 0)
    surveys = load_surveys()
    survey = surveys.get(sid)
    if not survey:
        return
    q = survey["questions"][q_idx]
    answer_text = update.message.text

    context.user_data["answers"][q["id"]] = answer_text
    context.user_data["current_q_idx"] = q_idx + 1
    context.user_data.pop("awaiting_text", None)

    await update.message.reply_text(
        f"✅ پاسخ شما ثبت شد.\n\n⏳ در حال بارگذاری سوال بعدی..."
    )
    import asyncio
    await asyncio.sleep(0.5)

    # For text answers we need to simulate a callback query-like flow
    # Send next question as a new message
    questions = survey["questions"]
    next_idx = context.user_data["current_q_idx"]
    if next_idx >= len(questions):
        # Complete
        uid = str(update.effective_user.id)
        responses = load_responses()
        if sid not in responses:
            responses[sid] = []
        responses[sid].append(
            {
                "user_id": uid,
                "timestamp": datetime.now().isoformat(),
                "answers": context.user_data["answers"],
            }
        )
        save_responses(responses)
        await update.message.reply_text(
            "✅ **ممنون از مشارکت شما!** 🎉\n\n"
            "پاسخ‌های شما با موفقیت ذخیره شد.\n"
            "📎 برای مشاهده نتایج: /results"
        )
        context.user_data.clear()
        return

    q = questions[next_idx]
    progress = f"[{next_idx + 1}/{len(questions)}]"
    header = f"{survey['title']}\n━━━━━━━━━━━━━━━━━━━━━\n\n"

    if q["type"] == "choice":
        text = f"{header}🔄 سوال {progress}\n\n{q['text']}\n\n🔹 یکی از گزینه‌ها را انتخاب کنید:"
        buttons = []
        for i, opt in enumerate(q["options"]):
            buttons.append(
                [InlineKeyboardButton(opt, callback_data=f"ans:{next_idx}:{i}")]
            )
        kb = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        context.user_data["awaiting_text"] = True
        text = (
            f"{header}🔄 سوال {progress}\n\n{q['text']}\n\n"
            f"⌨️ پاسخ خود را به‌صورت متنی ارسال کنید:"
        )
        await update.message.reply_text(text, parse_mode="Markdown")


# ─── /results ────────────────────────────────────────────────────────────────
async def cmd_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    surveys = load_surveys()
    responses = load_responses()

    if not responses:
        await update.message.reply_text(
            "📭 هنوز هیچ پاسخی ثبت نشده است.\n"
            "💡 برای شرکت در نظرسنجی: /survey"
        )
        return

    lines = ["📊 **خلاصه نتایج نظرسنجی‌ها**\n━━━━━━━━━━━━━━━━━━━━━\n"]

    for sid, res_list in responses.items():
        survey = surveys.get(sid, {})
        title = survey.get("title", sid)
        lines.append(f"\n🔹 **{title}**")
        lines.append(f"👥 تعداد پاسخ‌دهندگان: **{len(res_list)}**\n")

        # Aggregate answers
        q_answers: dict[str, list] = {}
        for resp in res_list:
            for qid, ans in resp.get("answers", {}).items():
                if qid not in q_answers:
                    q_answers[qid] = []
                q_answers[qid].append(ans)

        questions = survey.get("questions", [])
        for q in questions:
            qid = q["id"]
            answers = q_answers.get(qid, [])
            lines.append(f"  📝 *{q['text']}*")

            if q["type"] == "choice" and answers:
                counter = Counter(answers)
                total = len(answers)
                for opt, count in counter.most_common():
                    pct = round(count / total * 100)
                    bar_len = min(10, max(1, pct // 10))
                    bar = "█" * bar_len + "░" * (10 - bar_len)
                    lines.append(f"    {opt}: {bar} {pct}% ({count})")
            elif q["type"] == "text" and answers:
                lines.append(f"    📎 {len(answers)} پاسخ متنی دریافت شده:")
                for ans in answers[:5]:
                    snippet = ans[:80] + ("..." if len(ans) > 80 else "")
                    lines.append(f"    • {snippet}")
                if len(answers) > 5:
                    lines.append(f"    • ... و {len(answers) - 5} پاسخ دیگر")
            else:
                lines.append(f"    ⚪ پاسخی ثبت نشده")
            lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─── /create_survey (Admin) ─────────────────────────────────────────────────
async def cmd_create_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🔒 شما دسترسی مدیریت ندارید.")
        return CS_TITLE

    context.user_data["new_survey"] = {
        "questions": [],
        "created_at": datetime.now().isoformat(),
    }
    await update.message.reply_text(
        "➕ **ساخت نظرسنجی جدید**\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📝 لطفاً **عنوان** نظرسنجی را وارد کنید:",
        parse_mode="Markdown",
    )
    return CS_TITLE


async def cs_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_survey"]["title"] = update.message.text
    await update.message.reply_text(
        "✅ عنوان ثبت شد!\n\n🔢 تعداد سوالات را وارد کید:",
        parse_mode="Markdown",
    )
    return CS_NUM_QUESTIONS


async def cs_num_questions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        num = int(update.message.text)
        if num < 1 or num > 20:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ لطفاً عددی بین ۱ تا ۲۰ وارد کنید:")
        return CS_NUM_QUESTIONS

    context.user_data["new_survey"]["num_questions"] = num
    context.user_data["new_survey"]["current_q"] = 0
    await update.message.reply_text(f"📝 **سوال ۱ از {num}:**\n\nمتن سوال را وارد کنید:", parse_mode="Markdown")
    return CS_Q_TEXT


async def cs_q_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ns = context.user_data["new_survey"]
    q_idx = ns["current_q"]
    q = {"id": f"q{q_idx + 1}", "text": update.message.text, "type": None, "options": []}
    ns["questions"].append(q)

    buttons = [
        [InlineKeyboardButton("🔘 Multiple Choice (چندگزینه‌ای)", callback_data="qtype:choice")],
        [InlineKeyboardButton("⌨️ Text (متنی)", callback_data="qtype:text")],
    ]
    kb = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        f"🎯 نوع سوال **{q_idx + 1}** را انتخاب کنید:", parse_mode="Markdown", reply_markup=kb
    )
    return CS_Q_TYPE


async def cs_q_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    qtype = query.data.split(":", 1)[1]
    ns = context.user_data["new_survey"]
    current_q = ns["questions"][-1]

    if qtype == "text":
        current_q["type"] = "text"
        ns["current_q"] += 1
        if ns["current_q"] >= ns["num_questions"]:
            return await cs_confirm_survey(update, context)
        await query.edit_message_text(
            f"✅ نوع سوال: متنی\n\n📝 **سوال {ns['current_q'] + 1} از {ns['num_questions']}:**\n\nمتن سوال را وارد کنید:",
            parse_mode="Markdown",
        )
        return CS_Q_TEXT
    else:
        current_q["type"] = "choice"
        await query.edit_message_text(
            "📝 گزینه‌ها را **هر کدام در یک خط** وارد کنید:\n\n"
            "مثال:\nگزینه اول\nگزینه دوم\nگزینه سوم",
            parse_mode="Markdown",
        )
        return CS_Q_OPTIONS


async def cs_q_options(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ns = context.user_data["new_survey"]
    options = [line.strip() for line in update.message.text.strip().split("\n") if line.strip()]
    if len(options) < 2:
        await update.message.reply_text("⚠️ حداقل ۲ گزینه لازم است. دوباره وارد کنید:")
        return CS_Q_OPTIONS

    ns["questions"][-1]["options"] = options
    ns["current_q"] += 1

    if ns["current_q"] >= ns["num_questions"]:
        return await cs_confirm_survey(update, context)

    await update.message.reply_text(
        f"✅ {len(options)} گزینه ثبت شد.\n\n"
        f"📝 **سوال {ns['current_q'] + 1} از {ns['num_questions']}:**\n\nمتن سوال را وارد کنید:",
        parse_mode="Markdown",
    )
    return CS_Q_TEXT


async def cs_confirm_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ns = context.user_data["new_survey"]
    lines = [f"📋 **پیش‌نمایش نظرسنجی:**\n\n🔹 عنوان: {ns['title']}\n"]
    for i, q in enumerate(ns["questions"], 1):
        t = "🔘" if q["type"] == "choice" else "⌨️"
        lines.append(f"{t} سوال {i}: {q['text']}")
        if q["type"] == "choice":
            for opt in q["options"]:
                lines.append(f"   • {opt}")
    lines.append("\nآیا ذخیره شود؟")

    buttons = [
        [InlineKeyboardButton("✅ ذخیره", callback_data="csave:yes"), InlineKeyboardButton("❌ لغو", callback_data="csave:no")]
    ]
    kb = InlineKeyboardMarkup(buttons)
    # Use reply_text since callback_query.edit won't work here cleanly
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text("\n".join(lines), parse_mode="Markdown", reply_markup=kb)
    return CS_CONFIRM


async def cs_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    choice = query.data.split(":", 1)[1]

    if choice == "yes":
        ns = context.user_data["new_survey"]
        sid = str(uuid.uuid4())[:8]
        ns["id"] = sid
        ns["created_by"] = str(update.effective_user.id)

        surveys = load_surveys()
        surveys[sid] = ns
        save_surveys(surveys)

        await query.edit_message_text(
            f"🎉 **نظرسنجی با موفقیت ساخته شد!**\n\n"
            f"📌 عنوان: {ns['title']}\n"
            f"📝 تعداد سوالات: {len(ns['questions'])}\n"
            f"🔑 شناسه: `{sid}`\n\n"
            f"💡 کاربران می‌توانند با /survey در آن شرکت کنند.",
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text("❌ ساخت نظرسنجی لغو شد.")

    context.user_data.pop("new_survey", None)
    return ConversationHandler.END


async def cs_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_survey", None)
    await update.message.reply_text("❌ ساخت نظرسنجی لغو شد.")
    return ConversationHandler.END


# ─── /delete_survey (Admin) ─────────────────────────────────────────────────
async def cmd_delete_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🔒 شما دسترسی مدیریت ندارید.")
        return
    surveys = load_surveys()
    if not surveys:
        await update.message.reply_text("📭 نظرسنجی‌ای برای حذف وجود ندارد.")
        return
    buttons = []
    for sid, s in surveys.items():
        buttons.append(
            [InlineKeyboardButton(f"🗑 {s['title']}", callback_data=f"del:{sid}")]
        )
    kb = InlineKeyboardMarkup(buttons)
    await update.message.reply_text(
        "🗑 **نظرسنجی مورد نظر برای حذف را انتخاب کنید:**",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if not data.startswith("del:"):
        return
    sid = data.split(":", 1)[1]
    surveys = load_surveys()
    if sid in surveys:
        title = surveys[sid]["title"]
        del surveys[sid]
        save_surveys(surveys)
        # Also remove responses
        responses = load_responses()
        responses.pop(sid, None)
        save_responses(responses)
        await query.edit_message_text(f"✅ نظرسنجی **{title}** حذف شد.", parse_mode="Markdown")
    else:
        await query.edit_message_text("❌ نظرسنجی یافت نشد.")


# ─── Handle unknown commands ─────────────────────────────────────────────────
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ دستور نامعتبر!\n💡 برای راهنمایی: /help"
    )


# ─── Main ────────────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        print("❌ خطا: توکن ربات تنظیم نشده است!")
        print("💡 متغیر SURVEY_BOT_TOKEN را تنظیم کنید.")
        return

    # Initialize data
    load_surveys()
    load_responses()

    app = Application.builder().token(BOT_TOKEN).build()

    # Create survey conversation handler
    cs_handler = ConversationHandler(
        entry_points=[CommandHandler("create_survey", cmd_create_survey)],
        states={
            CS_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, cs_title)],
            CS_NUM_QUESTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cs_num_questions)
            ],
            CS_Q_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cs_q_text)],
            CS_Q_TYPE: [CallbackQueryHandler(cs_q_type_callback, pattern="^qtype:")],
            CS_Q_OPTIONS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cs_q_options)
            ],
            CS_CONFIRM: [CallbackQueryHandler(cs_confirm_callback, pattern="^csave:")],
        },
        fallbacks=[CommandHandler("cancel", cs_cancel)],
    )

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("survey", cmd_survey))
    app.add_handler(CommandHandler("results", cmd_results))
    app.add_handler(CommandHandler("delete_survey", cmd_delete_survey))
    app.add_handler(cs_handler)
    app.add_handler(
        CallbackQueryHandler(choice_answer_callback, pattern=r"^ans:")
    )
    app.add_handler(
        CallbackQueryHandler(survey_callback, pattern=r"^take:")
    )
    app.add_handler(
        CallbackQueryHandler(delete_callback, pattern=r"^del:")
    )
    # Text message handler for survey text answers (must be last)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_answer_handler)
    )
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Set bot commands menu
    async def post_init(application: Application):
        await application.bot.set_my_commands(
            [
                BotCommand("start", "شروع ربات"),
                BotCommand("help", "راهنما"),
                BotCommand("list", "لیست نظرسنجی‌ها"),
                BotCommand("survey", "شرکت در نظرسنجی"),
                BotCommand("results", "مشاهده نتایج"),
                BotCommand("create_survey", "ساخت نظرسنجی (مدیر)"),
                BotCommand("delete_survey", "حذف نظرسنجی (مدیر)"),
            ]
        )

    app.post_init = post_init

    print("🤖 ربات نظرسنجی در حال راه‌اندازی...")
    print("📡 در حال اتصال به تلگرام...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
