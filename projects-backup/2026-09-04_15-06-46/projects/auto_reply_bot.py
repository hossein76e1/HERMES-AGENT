#!/usr/bin/env python3
"""💬 ربات پاسخ خودکار هوشمند — Auto Reply Bot"""

import os
import json
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("REPLY_BOT_TOKEN")
DATA_FILE = "/data/workspace/projects/reply_rules.json"

def load_rules():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    default = {
        "rules": [
            {"trigger": "سلام", "reply": "سلام! 👋 خوش اومدید. چطور میتونم کمکتون کنم؟"},
            {"trigger": "قیمت", "reply": "💰 لطفاً محصول مورد نظرتون رو مشخص کنید."},
            {"trigger": "ارسال", "reply": "📦 ارسال به سراسر کشور. زمان: ۱ تا ۳ روز کاری."},
            {"trigger": "تماس", "reply": "📞 شماره تماس: ۰۲۱-XXXXXXXX\n🕐 ساعت کاری: ۹ صبح تا ۹ شب"},
            {"trigger": "ممنون", "reply": "🙏 خواهش میکنم! در خدمتتونیم."},
        ],
        "default_reply": "📝 پیام شما دریافت شد. به زودی پاسخ داده میشه.",
        "welcome": "👋 به پشتیبانی هوشمند خوش اومدید!\n\nسوالتون رو بفرستید تا خودکار پاسخ بدم.\nاگه جواب پیدا نشد، ادمین پاسخ میده."
    }
    save_rules(default)
    return default

def save_rules(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules = load_rules()
    await update.message.reply_text(rules["welcome"])

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 دستورات:\n\n"
        "/start - شروع\n"
        "/add_rule <کلمه> <پاسخ> - اضافه کردن قانون\n"
        "/rules - مشاهده قوانین\n"
        "/set_default <پاسخ> - تنظیم پاسخ پیش‌فرض\n"
        "/set_welcome <متن> - تنظیم پیام خوش‌آمدگویی"
    )

async def add_rule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("❌ فرمت: /add_rule کلمه پاسخ مورد نظر")
        return
    
    trigger = context.args[0]
    reply = " ".join(context.args[1:])
    
    rules = load_rules()
    rules["rules"].append({"trigger": trigger, "reply": reply})
    save_rules(rules)
    
    await update.message.reply_text(f"✅ قانون جدید اضافه شد:\n\n🔍 کلمه: {trigger}\n💬 پاسخ: {reply}")

async def rules_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules = load_rules()
    
    if not rules["rules"]:
        await update.message.reply_text("📭 هیچ قانونی تنظیم نشده.")
        return
    
    text = "📋 قوانین پاسخ خودکار:\n\n"
    for i, r in enumerate(rules["rules"], 1):
        text += f"{i}. 🔍 {r['trigger']}\n   💬 {r['reply']}\n\n"
    
    text += f"\n📝 پاسخ پیش‌فرض: {rules['default_reply']}"
    await update.message.reply_text(text)

async def set_default(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ فرمت: /set_default متن پاسخ پیش‌فرض")
        return
    
    reply = " ".join(context.args)
    rules = load_rules()
    rules["default_reply"] = reply
    save_rules(rules)
    await update.message.reply_text(f"✅ پاسخ پیش‌فرض تنظیم شد:\n{reply}")

async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ فرمت: /set_welcome متن خوش‌آمدگویی")
        return
    
    welcome = " ".join(context.args)
    rules = load_rules()
    rules["welcome"] = welcome
    save_rules(rules)
    await update.message.reply_text(f"✅ پیام خوش‌آمدگویی تنظیم شد:\n{welcome}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    rules = load_rules()
    
    for rule in rules["rules"]:
        if rule["trigger"].lower() in text:
            await update.message.reply_text(rule["reply"])
            return
    
    await update.message.reply_text(rules["default_reply"])

if __name__ == "__main__":
    if not TOKEN:
        print("❌ REPLY_BOT_TOKEN not set!")
        exit(1)
    
    rules = load_rules()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("add_rule", add_rule))
    app.add_handler(CommandHandler("rules", rules_list))
    app.add_handler(CommandHandler("set_default", set_default))
    app.add_handler(CommandHandler("set_welcome", set_welcome))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("💬 ربات پاسخ خودکار هوشمند فعال شد!")
    app.run_polling()
