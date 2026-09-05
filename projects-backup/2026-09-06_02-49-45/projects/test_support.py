#!/usr/bin/env python3
"""Test 7-day support window logic end-to-end (DB level)."""
import sys, sqlite3, json
sys.path.insert(0, '/data/workspace/projects')
from datetime import datetime, timedelta
from order_flow import set_order_status, support_days_left, ORDERS_DB

print("=== support window tests ===")

# 1) fresh delivered order gets 7-day window
conn = sqlite3.connect(ORDERS_DB, timeout=10)
now = datetime.now().isoformat()
num = f"ORD-SEVEN-{int(datetime.now().timestamp())%100000}"
cur = conn.cursor()
cur.execute("""INSERT INTO orders (order_number,user_id,project_type,project_title,description,base_price,final_price,currency,status,requirements,created_at,updated_at)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
(num, 999, "telegram_bot", "پشتیبانی تست", "تست", 100000, 100000, "toman", "in_progress",
 json.dumps({"chat": {"chat_id": "1030173067"}}, ensure_ascii=False), now, now))
oid = cur.lastrowid
conn.commit(); conn.close()

# before delivery: no window
assert support_days_left(oid) is None, "should be None before delivery"
print("1. before delivery → None ✅")

# set delivered → 7 days
set_order_status(oid, "delivered", {"deliverable_url": "https://example.com/x.zip", "deliverable_files": "x.zip"})
d = support_days_left(oid)
assert d == 7, f"expected 7, got {d}"
print(f"2. after delivery → {d} days ✅")

# window stored in DB
conn = sqlite3.connect(ORDERS_DB, timeout=10)
su = conn.execute("SELECT support_until, deliverable_url FROM orders WHERE id=?", (oid,)).fetchone()
conn.close()
assert su[0] and su[1], f"support_until={su[0]}, url={su[1]}"
print(f"3. DB stored support_until={su[0][:19]} ✅")

# simulate 8 days passing → expired
conn = sqlite3.connect(ORDERS_DB, timeout=10)
past = (datetime.now() - timedelta(days=8)).isoformat()
conn.execute("UPDATE orders SET support_until=? WHERE id=?", (past, oid))
conn.commit(); conn.close()
assert support_days_left(oid) == 0, "should be 0 after 8 days"
print("4. after 8 days → 0 (expired) ✅")

# simulate 3 days left
conn = sqlite3.connect(ORDERS_DB, timeout=10)
soon = (datetime.now() + timedelta(days=3)).isoformat()
conn.execute("UPDATE orders SET support_until=? WHERE id=?", (soon, oid))
conn.commit(); conn.close()
d = support_days_left(oid)
assert d in (3, 4), f"expected 3-4, got {d}"
print(f"5. 3 days later boundary → {d} days ✅")

# cleanup
conn = sqlite3.connect(ORDERS_DB, timeout=10)
conn.execute("UPDATE orders SET status='cancelled' WHERE id=?", (oid,))
conn.execute("DELETE FROM order_messages WHERE order_id=?", (oid,))
conn.commit(); conn.close()
print("6. cleanup ✅")
print("=== ALL SUPPORT TESTS PASSED ===")
