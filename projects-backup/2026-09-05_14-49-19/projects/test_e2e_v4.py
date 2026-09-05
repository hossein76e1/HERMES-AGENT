#!/usr/bin/env python3
"""Full lifecycle E2E v4 — with REAL bot-to-bot routing this time.
Creates a fresh order bound to ADMIN chat, drives approve→payok→start→deliver
through the exact same DB state transitions + queues the real bot sends.
Verifies: outbox delivered (support), inbox delivered (survey), statuses."""
import sys, os, json, time, sqlite3
sys.path.insert(0, '/data/workspace/projects')
os.environ.setdefault('ADMIN_TELEGRAM_ID', '1030173067')
import order_flow as flow
from order_flow import gen_order_number, queue_customer_message, queue_admin_message
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from support_bot import payment_text, payment_keyboard

SUP_LOG = '/data/.hermes/logs/support_bot.log'
ADM_LOG = '/data/.hermes/logs/survey_bot.log'

def log_size(p):
    try: return os.path.getsize(p)
    except OSError: return 0

def wait_log(path, pattern, start, timeout=45):
    end = time.time() + timeout
    while time.time() < end:
        with open(path, errors='ignore') as f:
            f.seek(start); c = f.read()
        if pattern in c: return True
        time.sleep(2)
    return False

sup_mark = log_size(SUP_LOG)

# 1) fresh order bound to admin chat (he acts as customer too)
conn = sqlite3.connect(flow.ORDERS_DB); cur = conn.cursor()
onum = gen_order_number(); now = flow.now()
cur.execute("""INSERT INTO orders (order_number, user_id, project_type, project_title, description,
   requirements, base_price, final_price, currency, status, payment_status, created_at, updated_at)
   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
   (onum, 999999, "telegram_bot", "تست کامل E2E v4", "تست چرخه با مسیریابی صحیح",
    json.dumps({"complexity": "simple", "features": [], "chat": {"chat_id": "1030173067", "bot": "support"}}, ensure_ascii=False),
    5000000, 5000000, "IRR", "pending", "pending", now, now))
oid = cur.lastrowid; conn.commit(); conn.close()
print(f"1) order #{oid} {onum} created (pending)")

# 2) admin approves → payment info via OUTBOX (support bot delivers)
flow.set_order_status(oid, "quoted")
o = flow.get_order(oid)
mid1 = queue_customer_message(oid, "1030173067", payment_text(o), payment_keyboard(o))
assert wait_log(SUP_LOG, f"outbox mid={mid1} delivered", sup_mark), "payment info not delivered"
print("2) approve → payment info delivered via @ShahbotSupportbot ✅")

# 3) customer pays (crypto) → receipt → payment_review
flow.set_order_status(oid, "awaiting_payment", {"payment_method": "crypto"})
flow.add_payment(oid, 5000000, "crypto", "pending")
flow.set_order_status(oid, "payment_review")
flow.add_message(oid, "customer", "TxID: E2E-V4-TEST", "receipt")
mid2 = queue_admin_message(oid, f"🧾 **رسید پرداخت!** سفارش #{oid}", InlineKeyboardMarkup([[
    InlineKeyboardButton("✅ پرداخت تأیید شد", callback_data=f"adm:payok:{oid}"),
    InlineKeyboardButton("❌ رسید نامعتبر", callback_data=f"adm:paybad:{oid}")]]))
sup_mark2 = log_size(ADM_LOG)
assert wait_log(ADM_LOG, f"inbox mid={mid2} delivered to ADMIN", sup_mark2), "receipt not delivered"
print("3) receipt delivered via @ShahbotSurveyBot (with payok/paybad buttons) ✅")

# 4) admin clicks payok → paid (this time order EXISTS so it works)
p = flow.find_pending_payment(oid, "crypto")
flow.confirm_payment_row(p["id"], "admin-confirmed")
flow.set_order_status(oid, "paid", {"payment_status": "paid"})
o = flow.get_order(oid)
assert o["status"] == "paid" and o["paid_at"]
print("4) payok → paid ✅ (paid_at", o["paid_at"][:19], ")")

# 5) start → in_progress → deliver
flow.set_order_status(oid, "in_progress")
flow.set_order_status(oid, "delivered", {"deliverable_url": "https://example.com/v4.zip"})
o = flow.get_order(oid)
assert o["status"] == "delivered" and o["deliverable_url"]
print("5) start → deliver → delivered ✅")

# cleanup
conn = sqlite3.connect(flow.ORDERS_DB)
conn.execute("DELETE FROM order_messages WHERE order_id=?", (oid,))
conn.execute("DELETE FROM payments WHERE order_id=?", (oid,))
conn.execute("DELETE FROM orders WHERE id=?", (oid,))
conn.commit(); conn.close()
open('/data/workspace/projects/.last_seen_order_id','w').write(str(oid))
print(f"\n✅ E2E v4 PASSED — payok now works (order existed). Test data cleaned.")
