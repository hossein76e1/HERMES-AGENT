#!/usr/bin/env python3
"""📊 ربات نظرسنجی هوشمند — Smart Survey Bot"""

import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.environ.get("SURVEY_BOT_TOKEN")
DATA_FILE = "/data/workspace/projects/surveys_data.json"

DEFAULT_SURVEY = {
    "title": "📊 نظرسنجی رضایت مشتری",
    "questions": [
        {"q": "از خدمات ما راضی بودید؟", "options": ["خیلی راضی", "راضی", "متوسط", "ناراضی"]},
        {"q": "چه چیزی رو بهبود بدیم؟", "options": ["کیفیت محصول", "سرعت ارسال", "قیمت", "پشتیبانی"]},
        {"q": "ما رو به دوستانتون معرفی می‌کنید؟", "options": ["حتماً", "شاید", "نه"]}
    ]
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"surveys": [DEFAULT_SURVEY], "responses": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 به ربات نظرسنجی خوش اومدید!\n\n"
        "📌 دستورات:\n"
        "/survey - شروع نظرسنجی\n"
        "/results - مشاهده نتایج\n"
        "/help - راهنما"
    )

async def survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    survey_data = data["surveys"][0]
    context.user_data["survey_index"] = 0
    context.user_data["answers"] = []
    await ask_question(update, context, 0)

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE, q_index):
    data = load_data()
    survey_data = data["surveys"][0]
    questions = survey_data["questions"]
    
    if q_index >= len(questions):
        await finish_survey(update, context)
        return
    
    q = questions[q_index]
    buttons = [[InlineKeyboardButton(opt, callback_data=f"ans_{q_index}_{i}")] for i, opt in enumerate(q["options"])]
    keyboard = InlineKeyboardMarkup(buttons)
    
    await update.message.reply_text(
        f"❓ سوال {q_index+1}/{len(questions)}:\n\n{q['q']}",
        reply_markup=keyboard
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("ans_"):
        parts = query.data.split("_")
        q_index = int(parts[1])
        a_index = int(parts[2])
        
        data = load_data()
        survey_data = data["surveys"][0]
        questions = survey_data["questions"]
        answer = questions[q_index]["options"][a_index]
        
        context.user_data.setdefault("answers", []).append(answer)
        
        next_q = q_index + 1
        if next_q < len(questions):
            q = questions[next_q]
            buttons = [[InlineKeyboardButton(opt, callback_data=f"ans_{next_q}_{i}")] for i, opt in enumerate(q["options"])]
            keyboard = InlineKeyboardMarkup(buttons)
            await query.edit_message_text(
                f"✅ ثبت شد!\n\n❓ سوال {next_q+1}/{len(questions)}:\n{q['q']}",
                reply_markup=keyboard
            )
        else:
            await finish_survey(update, context)

async def finish_survey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answers = context.user_data.get("answers", [])
    user = update.effective_user
    
    data = load_data()
    data["responses"].append({
        "user_id": user.id,
        "username": user.username or "ناشناس",
        "name": user.first_name,
        "answers": answers,
        "timestamp": datetime.now().isoformat()
    })
    save_data(data)
    
    result_text = "✅ پاسخ شما ثبت شد!\n\n📋 خلاصه پاسخ‌ها:\n"
    for i, ans in enumerate(answers):
        result_text += f"  {i+1}. {ans}\n"
    result_text += "\n🙏 ممنون از مشارکت شما!"
    
    await update.callback_query.edit_message_text(result_text)

async def results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    responses = data["responses"]
    
    if not responses:
        await update.message.reply_text("📭 هنوز پاسخی ثبت نشده.")
        return
    
    survey_data = data["surveys"][0]
    text = f"📊 نتایج نظرسنجی ({len(responses)} پاسخ):\n\n"
    
    for i, q in enumerate(survey_data["questions"]):
        text += f"❓ {q['q']}\n"
        counts = {}
        for r in responses:
            if i < len(r["answers"]):
                ans = r["answers"][i]
                counts[ans] = counts.get(ans, 0) + 1
        
        for opt, count in sorted(counts.items(), key=lambda x: -x[1]):
            bar = "█" * count + "░" * (len(responses) - count)
            text += f"  {opt}: {bar} ({count})\n"
        text += "\n"
    
    await update.message.reply_text(text)

if __name__ == "__main__":
    import os
    TOKEN = os.environ.get("SURVEY_BOT_TOKEN")
    if not TOKEN:
        print("❌ SURVEY_BOT_TOKEN not set!")
        exit(1)
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("survey", survey))
    app.add_handler(CommandHandler("results", results))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    print("📊 ربات نظرسنجی هوشمند فعال شد!")
    app.run_polling()