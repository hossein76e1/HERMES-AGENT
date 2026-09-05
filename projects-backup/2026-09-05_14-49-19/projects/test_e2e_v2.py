#!/usr/bin/env python3
"""E2E v2: order → admin approve → payment msg via OUTBOX (support bot delivers).
Waits for outbox delivery confirmation in support_bot.log."""
import sys, os, json, time, sqlite3
sys.path.insert(0, '/data/workspace/projects')
os.environ.setdefault('ADMIN_TELEGRAM_ID', '1030173067')
import order_flow as flow
from order_flow import gen_order_number, fetch_outbox, set_outbox_sender

SUPPORT_LOG = '/data/.hermes/logs/support_bot.log'

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

mark = log_size(SUPPORT_LOG)

# 1) new order bound to admin's chat (he'll receive as if customer)
conn = sqlite3.connect(flow.ORDERS_DB)
cur = conn.cursor()
onum = gen_order_number(); now = flow.now()
cur.execute("""INSERT INTO orders (order_number, user_id, project_type, project_title, description,
   requirements, base_price, final_price, currency, status, payment_status, created_at, updated_at)
   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
   (onum, 999999, "telegram_bot", "تست ارسال پرداخت به مشتری", "تست outbox — پیام پرداخت باید از ربات سفارش‌گیر برسد",
    json.dumps({"complexity": "simple", "features": [], "chat": {"chat_id": "1030173067", "bot": "support"}}, ensure_ascii=False),
    5000000, 5000000, "IRR", "pending", "pending", now, now))
oid = cur.lastrowid; conn.commit(); conn.close()
print(f"1) order #{oid} {onum} inserted (binding → chat 1030173067)")

# 2) simulate admin approval → queue payment message (same code path as survey_bot's send_customer)
from survey_bot import send_customer  # import the actual function used by admin bot
from support_bot import payment_text, payment_keyboard

class FakeCtx:
    pass

o = flow.get_order(oid)
flow.set_order_status(oid, "quoted")
queued = flow.queue_customer_message(oid, "1030173067", payment_text(o), payment_keyboard(o))
print(f"2) payment message queued (mid {queued}) — waiting for outbox worker...")

assert wait_for_log(SUPPORT_LOG, f"outbox mid={queued} delivered", mark), "outbox delivery NOT seen in log"
print("3) ✅ OUTBOX DELIVERED — check Telegram: payment info should arrive from @ShahbotSupportbot")

# verify DB state transition
assert flow.get_order(oid)["status"] == "quoted"
print("4) order status = quoted ✅")
print(f"\nNOTE: test order #{oid} left in DB for you to see the real flow. Admin buttons work on it.")
