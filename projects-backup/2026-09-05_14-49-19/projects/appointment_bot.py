#!/usr/bin/env python3
"""📅 ربات رزرو نوبت — Appointment Booking Bot"""

import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

TOKEN = os.environ.get("APPOINTMENT_BOT_TOKEN")
DATA_FILE = "/data/workspace/projects/appointments.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"slots": {}, "bookings": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📅 به ربات رزرو نوبت خوش اومدید!\n\n"
        "📌 دستورات:\n"
        "/book - رزرو نوبت جدید\n"
        "/my_bookings - نوبت‌های من\n"
        "/cancel - لغو نوبت\n"
        "/help - راهنما"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 راهنمای ربات رزرو نوبت:\n\n"
        "/book - رزرو نوبت جدید\n"
        "/my_bookings - مشاهده نوبت‌های رزرو شده\n"
        "/cancel - لغو نوبت\n"
        "/help - این راهنما"
    )

async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("🕐 فردا صبح (۹-۱۲)", callback_data="slot_tomorrow_morning"),
         InlineKeyboardButton("🕐 فردا عصر (۱۴-۱۷)", callback_data="slot_tomorrow_afternoon")],
        [InlineKeyboardButton("🕐 پس‌فردا صبح (۹-۱۲)", callback_data="slot_dayafter_morning"),
         InlineKeyboardButton("🕐 پس‌فردا عصر (۱۴-۱۷)", callback_data="slot_dayafter_afternoon")],
        [InlineKeyboardButton("📆 هفته آینده", callback_data="slot_nextweek")]
    ]
    await update.message.reply_text(
        "📅 ساعت مورد نظرتون رو انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("slot_"):
        slot_type = data.replace("slot_", "")
        slot_labels = {
            "tomorrow_morning": "فردا صبح (۹-۱۲)",
            "tomorrow_afternoon": "فردا عصر (۱۴-۱۷)",
            "dayafter_morning": "پس‌فردا صبح (۹-۱۲)",
            "dayafter_afternoon": "پس‌فردا عصر (۱۴-۱۷)",
            "nextweek": "هفته آینده"
        }
        label = slot_labels.get(slot_type, slot_type)
        
        user = update.effective_user
        db = load_data()
        
        booked = [b for b in db["bookings"] if b["slot"] == slot_type and b["status"] == "active"]
        if len(booked) >= 5:
            await query.edit_message_text("❌ این سرو بیش از حد رزرو شده. لطفاً زمان دیگه‌ای انتخاب کنید.")
            return
        
        db["bookings"].append({
            "user_id": user.id,
            "username": user.username or "ناشناس",
            "name": user.first_name,
            "slot": slot_type,
            "slot_label": label,
            "status": "active",
            "created_at": datetime.now().isoformat()
        })
        save_data(db)
        
        await query.edit_message_text(
            f"✅ نوبت شما با موفقیت رزرو شد!\n\n"
            f"📅 زمان: {label}\n"
            f"👤 نام: {user.first_name}\n"
            f"🆔 کد رزرو: #{len(db['bookings'])}\n\n"
            f"🙏 منتظر حضور شما هستیم!"
        )
    
    elif data == "confirm_delete":
        context.user_data["delete_confirmed"] = True
        await query.edit_message_text("✅ نوبت شما لغو شد.")

async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_data()
    user_bookings = [b for b in db["bookings"] if b["user_id"] == update.effective_user.id and b["status"] == "active"]
    
    if not user_bookings:
        await update.message.reply_text("📭 شما هیچ نوبت فعالی ندارید.")
        return
    
    text = "📋 نوبت‌های فعال شما:\n\n"
    for i, b in enumerate(user_bookings, 1):
        text += f"{i}. 📅 {b['slot_label']}\n   🆔 کد: #{db['bookings'].index(b)+1}\n\n"
    
    await update.message.reply_text(text)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = load_data()
    user_bookings = [b for b in db["bookings"] if b["user_id"] == update.effective_user.id and b["status"] == "active"]
    
    if not user_bookings:
        await update.message.reply_text("📭 نوبت فعالی برای لغو ندارید.")
        return
    
    buttons = [[InlineKeyboardButton(f"❌ لغو #{db['bookings'].index(b)+1}: {b['slot_label']}", callback_data=f"cancel_{db['bookings'].index(b)}")] for b in user_bookings]
    await update.message.reply_text("کدوم نوبت رو میخواید لغو کنید؟", reply_markup=InlineKeyboardMarkup(buttons))

async def cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("cancel_"):
        index = int(query.data.replace("cancel_", ""))
        db = load_data()
        if index < len(db["bookings"]):
            db["bookings"][index]["status"] = "cancelled"
            save_data(db)
            await query.edit_message_text(f"✅ نوبت #{index+1} با موفقیت لغو شد.")

if __name__ == "__main__":
    if not TOKEN:
        print("❌ APPOINTMENT_BOT_TOKEN not set!")
        exit(1)
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("book", book))
    app.add_handler(CommandHandler("my_bookings", my_bookings))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(cancel_callback, pattern="^cancel_"))
    app.add_handler(CallbackQueryHandler(callback_handler, pattern="^slot_"))
    
    print("📅 ربات رزرو نوبت فعال شد!")
    app.run_polling()
