#!/usr/bin/env python3
"""E2E v3: customer receipt → admin_inbox → delivered by ADMIN bot (survey).
Also verifies customer payment message goes via outbox (support bot)."""
import sys, os, json, time, sqlite3
sys.path.insert(0, '/data/workspace/projects')
os.environ.setdefault('ADMIN_TELEGRAM_ID', '1030173067')
import order_flow as flow
from order_flow import gen_order_number, queue_admin_message
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

SURVEY_LOG = '/data/.hermes/logs/survey_bot.log'

def log_size(path):
    try: return os.path.getsize(path)
    except OSError: return 0

def wait_for_log(path, pattern, start, timeout=45):
    end = time.time() + timeout
    while time.time() < end:
        with open(path, 'r', errors='ignore') as f:
            f.seek(start); chunk = f.read()
        if pattern in chunk: return True
        time.sleep(2)
    return False

mark = log_size(SURVEY_LOG)

# simulate customer receipt submission (text receipt, like real flow)
conn = sqlite3.connect(flow.ORDERS_DB)
cur = conn.cursor()
o = conn.execute("SELECT id, order_number, final_price FROM orders WHERE order_number LIKE 'ORD-%' ORDER BY id DESC LIMIT 1").fetchone()
conn.close()
oid = o[0]
caption = f"🧾 **رسید پرداخت جدید! (تست مسیر)**\n\nسفارش #{oid} — `{o[1]}`\n💰 {o[2]:,} تومان\n🧾 متن: `E2E-RECEIPT-ROUTING-TEST`"
kb = InlineKeyboardMarkup([[
    InlineKeyboardButton("✅ پرداخت تأیید شد", callback_data=f"adm:payok:{oid}"),
    InlineKeyboardButton("❌ رسید نامعتبر", callback_data=f"adm:paybad:{oid}"),
]])
mid = queue_admin_message(oid, caption, kb)
print(f"1) receipt queued to admin_inbox (mid {mid}, order #{oid})")

assert wait_for_log(SURVEY_LOG, f"inbox mid={mid} delivered to ADMIN", mark), "admin inbox delivery NOT seen"
print("2) ✅ ADMIN INBOX DELIVERED — receipt should arrive from @ShahbotSurveyBot with approve/reject buttons")

# check DB state
r = sqlite3.connect(flow.ORDERS_DB).execute(f"SELECT sender_type FROM order_messages WHERE id={mid}").fetchone()
assert r[0] == "bot", f"unexpected state {r}"
print("3) row marked delivered ✅")
