#!/usr/bin/env python3
"""🤖 ربات پشتیبانی هوشمند — Smart Support Bot"""

import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

TOKEN = os.environ.get("SUPPORT_BOT_TOKEN")

FAQ = {
    "قیمت": "💰 لطفاً محصول مورد نظرتون رو مشخص کنید تا قیمت رو براتون بفرستم.",
    "ارسال": "📦 ارسال به سراسر کشور. زمان ارسال ۱ تا ۳ روز کاری.",
    "گارانتی": "✅ تمام محصولات ۷ روز گارانتی بازگشت وجه دارن.",
    "پرداخت": "💳 پرداخت اینترنتی، کارت به کارت و پرداخت درب محل امکان‌پذیره.",
    "ساعات کاری": "🕐 شنبه تا پنجشنبه ۹ صبح تا ۹ شب در خدمتتونیم.",
}

KEYBOARD = InlineKeyboardMarkup([
    [InlineKeyboardButton("💰 قیمت", callback_data="faq_قیمت"),
     InlineKeyboardButton("📦 ارسال", callback_data="faq_ارسال")],
    [InlineKeyboardButton("✅ گارانتی", callback_data="faq_گارانتی"),
     InlineKeyboardButton("💳 پرداخت", callback_data="faq_پرداخت")],
    [InlineKeyboardButton("🕐 ساعات کاری", callback_data="faq_ساعات کاری"),
     InlineKeyboardButton("👤 ارتباط با ادمین", callback_data="admin")],
])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 به پشتیبانی ما خوش اومدید!\n\n"
        "از دکمه‌های زیر استفاده کنید یا سوالتون رو بفرستید:",
        reply_markup=KEYBOARD
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "admin":
        await query.edit_message_text("👤 ادمین پاسخگوی شماست. لطفاً پیام بذارید.")
        return

    key = data.replace("faq_", "")
    answer = FAQ.get(key, "❓ سوال شما ثبت شد. به زودی پاسخ داده میشه.")
    await query.edit_message_text(answer, reply_markup=KEYBOARD)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    for key, answer in FAQ.items():
        if key in text:
            await update.message.reply_text(answer, reply_markup=KEYBOARD)
            return
    await update.message.reply_text(
        "📝 پیام شما ثبت شد.\n"
        "ادمین به زودی پاسخ میده.\n\n"
        "یا از دکمه‌های زیر استفاده کنید:",
        reply_markup=KEYBOARD
    )

if __name__ == "__main__":
    if not TOKEN:
        print("❌ SUPPORT_BOT_TOKEN not set!")
        exit(1)

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🤖 ربات پشتیبانی هوشمند فعال شد!")
    app.run_polling()
