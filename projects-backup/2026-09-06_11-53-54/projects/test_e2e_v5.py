#!/usr/bin/env python3
"""E2E v5 — full auto-build pipeline test.
Simulates: paid order → adm:start → auto_build flag → builder builds → zip → outbox deliver.
Does NOT hit real AI (monkeypatches ai_build) unless REAL_AI=1.
"""
import os
import sys
import json
import sqlite3
import shutil
from datetime import datetime

sys.path.insert(0, "/data/workspace/projects")
import auto_builder as ab

DB = ab.ORDERS_DB


def reset_flag():
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("UPDATE orders SET requirements=json_set(requirements,'$.auto_build',json('true')) WHERE requirements LIKE '%\"chat\"%' AND id=? ", (ORDER_ID,))
    conn.commit()
    conn.close()


def create_test_order():
    conn = sqlite3.connect(DB, timeout=10)
    cur = conn.cursor()
    now = "2026-09-05T15:00:00"
    order_number = f"ORD-TEST-{int(datetime.now().timestamp()) % 100000}"
    cur.execute(
        """INSERT INTO orders (order_number, user_id, project_type, project_title, description, final_price, status,
           requirements, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (order_number, 999, "telegram_bot", "ربات یادآور آب خوردن", "ربات تلگرامی که هر ۲ ساعت یادآوری آب خوردن بفرستد با دکمه تایید",
         500000, "paid",
         json.dumps({
             "project_type": "telegram_bot",
             "project_title": "ربات یادآور آب خوردن",
             "description": "هر ۲ ساعت پیام یادآوری آب با دکمه ✅ نوشیدم بفرستد؛ آمار روزانه با /stats",
             "features": ["یادآوری هر ۲ ساعت", "دکمه نوشیدم", "آمار /stats"],
             "complexity": "simple",
             "chat": {"chat_id": "1030173067", "username": "hossein_test"}
         }, ensure_ascii=False),
         now, now),
    )
    oid = cur.lastrowid
    conn.commit()
    conn.close()
    return oid


def set_auto_build(oid):
    conn = sqlite3.connect(DB, timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT requirements FROM orders WHERE id=?", (oid,))
    req = json.loads(cur.fetchone()[0])
    req["auto_build"] = True
    cur.execute("UPDATE orders SET requirements=? WHERE id=?", (json.dumps(req, ensure_ascii=False), oid))
    conn.commit()
    conn.close()


def check_outbox_delivered(oid):
    conn = sqlite3.connect(DB, timeout=10)
    rows = conn.execute(
        "SELECT sender_type, content FROM order_messages WHERE order_id=? AND sender_type='outbox' ORDER BY id DESC LIMIT 3",
        (oid,),
    ).fetchall()
    conn.close()
    return rows


def cleanup(oid):
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("UPDATE orders SET status='cancelled' WHERE id=?", (oid,))
    conn.commit()
    conn.close()
    shutil.rmtree(os.path.join(ab.BUILD_DIR, str(oid)), ignore_errors=True)
    conn = sqlite3.connect(DB, timeout=10)
    conn.execute("DELETE FROM order_messages WHERE order_id=?", (oid,))
    conn.commit()
    conn.close()


print("=" * 50)
print("TEST: auto-build pipeline (mock AI)" if os.environ.get("REAL_AI") != "1" else "TEST: auto-build pipeline (REAL AI)")
print("=" * 50)

# 1) create order
oid = create_test_order()
print(f"1️⃣ order #{oid} created (status=paid)")

# 2) set auto_build flag (what survey_bot does on adm:start)
set_auto_build(oid)
conn = sqlite3.connect(DB, timeout=10)
flag = json.loads(conn.execute("SELECT requirements FROM orders WHERE id=?", (oid,)).fetchone()[0]).get("auto_build")
conn.close()
assert flag is True, "auto_build flag not set!"
print("2️⃣ auto_build flag set ✅")

# 3) mock or real AI
if os.environ.get("REAL_AI") != "1":
    ab.ai_build = lambda collected: {
        "files": {
            "README.md": "# ربات یادآور آب\n\nBOT_TOKEN را در .env بگذار و `python main.py` را اجرا کن.",
            "requirements.txt": "python-telegram-bot==22.8\napscheduler==3.10.4",
            "main.py": "import os\nprint('water bot placeholder')\n",
        },
        "entry_command": "python main.py",
        "notes": "ربات یادآور آب با AMHourly scheduler.",
    }
    print("3️⃣ AI mocked (use REAL_AI=1 for real build)")

# 4) run build_order
print("4️⃣ building...")
ok = ab.build_order(oid)
assert ok, "build_order returned False!"
print("   build_order returned True ✅")

# 5) verify DB state
o = ab.db_get(oid)
assert o["status"] == "delivered", f"status is {o['status']}, expected delivered"
print(f"5️⃣ status = delivered ✅")

# 6) verify zip exists
zip_path = os.path.join(ab.BUILD_DIR, "deliverables", f"{o['order_number']}.zip")
assert os.path.exists(zip_path), f"zip not found: {zip_path}"
sz = os.path.getsize(zip_path)
print(f"6️⃣ zip exists ({sz} bytes) ✅")

# 7) verify outbox messages queued (start + delivery w/ document_path)
rows = check_outbox_delivered(oid)
assert len(rows) >= 2, f"expected >=2 outbox rows, got {len(rows)}"
doc_msg = json.loads(rows[0][1])
assert doc_msg.get("document_path") == zip_path, "delivery message missing document_path!"
assert "پروژه‌ت ساخته شد" in doc_msg["text"], "delivery text missing!"
print(f"7️⃣ outbox has {len(rows)} msgs; delivery msg has document_path ✅")

# 8) verify admin notifications queued
conn = sqlite3.connect(DB, timeout=10)
admin_rows = conn.execute(
    "SELECT COUNT(*) FROM order_messages WHERE order_id=? AND sender_type='admin_inbox'", (oid,)
).fetchone()[0]
conn.close()
assert admin_rows >= 2, f"expected >=2 admin_inbox rows, got {admin_rows}"
print(f"8️⃣ admin notified ({admin_rows} msgs) ✅")

print("=" * 50)
print("✅ ALL AUTO-BUILD PIPELINE TESTS PASSED")
print("=" * 50)

# cleanup
cleanup(oid)
print(f"🧹 test order #{oid} cleaned up")
