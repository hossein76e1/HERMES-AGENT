#!/usr/bin/env python3
"""Unit test: full order lifecycle logic (DB only, no Telegram)"""
import sys, os, json
sys.path.insert(0, '/data/workspace/projects')
os.environ.setdefault('ADMIN_TELEGRAM_ID', '1030173067')

import order_flow as flow
from order_flow import (
    get_order, set_order_status, add_message, get_messages, add_payment,
    confirm_payment_row, find_pending_payment, bind_chat, get_chat_binding,
    gen_order_number, order_card,
)
import sqlite3
from datetime import datetime

# 1) create test order with chat binding
conn = sqlite3.connect(flow.ORDERS_DB)
cur = conn.cursor()
onum = gen_order_number()
now = flow.now()
cur.execute("""INSERT INTO orders (order_number, user_id, project_type, project_title, description,
   requirements, base_price, final_price, currency, status, payment_status, created_at, updated_at)
   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
   (onum, 999999, "telegram_bot", "تست چرخه کامل", "دستور تست lifecycle",
    json.dumps({"complexity": "simple", "features": ["تست"], "chat": {"chat_id": "1030173067", "bot": "support"}}, ensure_ascii=False),
    5000000, 5000000, "IRR", "pending", "pending", now, now))
oid = cur.lastrowid
conn.commit(); conn.close()
print(f"1️⃣ order created #{oid} {onum}")

# 2) binding
b = get_chat_binding(oid)
assert b and b["chat_id"] == "1030173067", "binding failed"
print("2️⃣ chat binding OK:", b)

# 3) approve → quoted
assert set_order_status(oid, "quoted")
assert get_order(oid)["status"] == "quoted"
print("3️⃣ approve → quoted OK")

# 4) payment method → awaiting_payment + pending payment row
assert set_order_status(oid, "awaiting_payment", {"payment_method": "card"})
add_payment(oid, 5000000, "card", "pending")
p = find_pending_payment(oid, "card")
assert p and p["status"] == "pending"
print("4️⃣ awaiting_payment + pending payment OK (payment id", p["id"], ")")

# 5) receipt → payment_review
assert set_order_status(oid, "payment_review")
add_message(oid, "customer", "رسید: TEST-TX-123", "receipt")
print("5️⃣ payment_review + receipt message OK")

# 6) payok → paid + payment confirmed
assert confirm_payment_row(p["id"], "admin-confirmed")
assert set_order_status(oid, "paid", {"payment_status": "paid"})
o = get_order(oid)
assert o["status"] == "paid" and o["payment_status"] == "paid" and o["paid_at"]
print("6️⃣ paid OK (paid_at set)")

# 7) start → in_progress
assert set_order_status(oid, "in_progress")
assert get_order(oid)["status"] == "in_progress" and get_order(oid)["started_at"]
print("7️⃣ in_progress OK")

# 8) deliver → delivered + deliverables
assert set_order_status(oid, "delivered", {"deliverable_url": "https://example.com/x.zip", "deliverable_files": "x.zip"})
o = get_order(oid)
assert o["status"] == "delivered" and o["deliverable_url"] == "https://example.com/x.zip"
print("8️⃣ delivered OK")

# 9) messages thread
msgs = get_messages(oid)
assert len(msgs) >= 1
print(f"9️⃣ message thread OK ({len(msgs)} messages)")

# 10) order_card renders with new statuses
card = order_card(get_order(oid))
assert "تحویل داده شده" in card
print("🔟 order_card OK")

# 11) cancel + reopen flow
assert set_order_status(oid, "cancelled")
assert set_order_status(oid, "quoted")
print("1️⃣1️⃣ cancel/reopen OK")

print("\n✅ ALL LIFECYCLE TESTS PASSED (11/11)")
