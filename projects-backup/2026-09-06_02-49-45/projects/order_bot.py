#!/usr/bin/env python3
"""🛒 خودکارسازی ثبت سفارش — Order Automation"""

import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

TOKEN = os.environ.get("ORDER_BOT_TOKEN")
DATA_FILE = "/data/workspace/projects/orders.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"products": [
        {"id": 1, "name": "محصول A", "price": 150000, "stock": 10},
        {"id": 2, "name": "محصول B", "price": 250000, "stock": 5},
        {"id": 3, "name": "محصول C", "price": 350000, "stock": 8},
    ], "orders": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛒 به فروشگاه آنلاین خوش اومدید!\n\n"
        "📌 دستورات:\n"
        "/products - مشاهده محصولات\n"
        "/order - ثبت سفارش\n"
        "/my_orders - سفارشات من\n"
        "/help - راهنما"
    )

async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    text = "📦 لیست محصولات:\n\n"
    buttons = []
    
    for p in data["products"]:
        stock_status = "✅ موجود" if p["stock"] > 0 else "❌ ناموجود"
        text += f"🔹 {p['name']}\n   💰 {p['price']:,} تومان\n   📦 {stock_status} ({p['stock']} عدد)\n\n"
        if p["stock"] > 0:
            buttons.append([InlineKeyboardButton(f"🛒 {p['name']} - {p['price']:,} تومان", callback_data=f"buy_{p['id']}")])
    
    if buttons:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    else:
        await update.message.reply_text(text)

async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    product_id = int(query.data.replace("buy_", ""))
    data = load_data()
    
    product = next((p for p in data["products"] if p["id"] == product_id), None)
    if not product or product["stock"] <= 0:
        await query.edit_message_text("❌ محصول ناموجود است.")
        return
    
    buttons = [
        [InlineKeyboardButton("1️⃣ یک عدد", callback_data=f"qty_{product_id}_1"),
         InlineKeyboardButton("2️⃣ دو عدد", callback_data=f"qty_{product_id}_2")],
        [InlineKeyboardButton("3️⃣ سه عدد", callback_data=f"qty_{product_id}_3")]
    ]
    
    await query.edit_message_text(
        f"🛒 {product['name']}\n💰 قیمت: {product['price']:,} تومان\n\nتعداد مورد نظر:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def qty_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    product_id = int(parts[1])
    qty = int(parts[2])
    
    data = load_data()
    product = next((p for p in data["products"] if p["id"] == product_id), None)
    
    if not product or product["stock"] < qty:
        await query.edit_message_text("❌ موجودی کافی نیست.")
        return
    
    total = product["price"] * qty
    user = update.effective_user
    
    order = {
        "id": len(data["orders"]) + 1,
        "user_id": user.id,
        "username": user.username or "ناشناس",
        "name": user.first_name,
        "product": product["name"],
        "quantity": qty,
        "total": total,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    
    data["orders"].append(order)
    product["stock"] -= qty
    save_data(data)
    
    buttons = [
        [InlineKeyboardButton("✅ تأیید نهایی", callback_data=f"confirm_{order['id']}"),
         InlineKeyboardButton("❌ انصراف", callback_data=f"cancel_{order['id']}")]
    ]
    
    await query.edit_message_text(
        f"📋 خلاصه سفارش:\n\n"
        f"📦 محصول: {product['name']}\n"
        f"🔢 تعداد: {qty}\n"
        f"💰 مبلغ کل: {total:,} تومان\n"
        f"🆔 کد سفارش: #{order['id']}\n\n"
        f"آیا تأیید میکنید؟",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    order_id = int(query.data.replace("confirm_", ""))
    data = load_data()
    
    order = next((o for o in data["orders"] if o["id"] == order_id), None)
    if order:
        order["status"] = "confirmed"
        save_data(data)
        await query.edit_message_text(
            f"✅ سفارش #{order_id} تأیید شد!\n\n"
            f"📦 {order['product']}\n"
            f"🔢 تعداد: {order['quantity']}\n"
            f"💰 مبلغ: {order['total']:,} تومان\n\n"
            f"🙏 ممنون از خرید شما!"
        )

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    user_orders = [o for o in data["orders"] if o["user_id"] == update.effective_user.id]
    
    if not user_orders:
        await update.message.reply_text("📭 سفارشی ثبت نکردید.")
        return
    
    status_emoji = {"pending": "⏳", "confirmed": "✅", "cancelled": "❌"}
    text = "📋 سفارشات شما:\n\n"
    
    for o in user_orders[-5:]:
        emoji = status_emoji.get(o["status"], "❓")
        text += f"{emoji} #{o['id']}: {o['product']} × {o['quantity']} = {o['total']:,} تومان\n"
    
    await update.message.reply_text(text)

if __name__ == "__main__":
    if not TOKEN:
        print("❌ ORDER_BOT_TOKEN not set!")
        exit(1)
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("products", products))
    app.add_handler(CommandHandler("my_orders", my_orders))
    app.add_handler(CallbackQueryHandler(buy_callback, pattern="^buy_"))
    app.add_handler(CallbackQueryHandler(qty_callback, pattern="^qty_"))
    app.add_handler(CallbackQueryHandler(confirm_callback, pattern="^confirm_"))
    
    print("🛒 ربات ثبت سفارش فعال شد!")
    app.run_polling()
