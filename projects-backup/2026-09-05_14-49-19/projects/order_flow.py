#!/usr/bin/env python3
"""
📋 مشترک بین هر دو ربات — دیتابیس و ابزارها
order_flow.py — shared state machine helpers
"""
import os
import json
import sqlite3
import random
import string
from datetime import datetime

ORDERS_DB = "/data/workspace/order-system/backend/orders.db"
ADMIN_ID = int(os.environ.get("ADMIN_TELEGRAM_ID", "1030173067"))

# ─── Payment info shown to customer AFTER admin approval ────────────────────
CARD_INFO = {
    "bank": "ملت",
    "number": "6104-3379-4410-7284",
    "name": "حسین رضایی",
}
CRYPTO_INFO = {
    "network": "TRC20 (Tron)",
    "asset": "USDT",
    "address": "TXk9Lm2pQvR7nJ4hKd8sWfY3aBcE5gUiZq",
}
# Contact for direct talk
SUPPORT_HANDLE = "@Hosseinagentcoderbot"


STATUS_FA = {
    "pending": "⏳ در انتظار بررسی",
    "quoted": "💰 قیمت ارسال شده",
    "awaiting_payment": "💳 در انتظار پرداخت",
    "payment_review": "🧾 در حال بررسی رسید",
    "paid": "💳 پرداخت شده",
    "in_progress": "🔧 در حال انجام",
    "ready": "📦 آماده تحویل",
    "delivered": "✅ تحویل داده شده",
    "cancelled": "❌ لغو شده",
}

STATUS_TIMESTAMPS = {
    "quoted": "quoted_at",
    "paid": "paid_at",
    "in_progress": "started_at",
    "delivered": "delivered_at",
}


def now() -> str:
    return datetime.now().isoformat()


def format_price(p) -> str:
    try:
        return f"{int(p):,}".replace(",", "،") + " تومان"
    except (ValueError, TypeError):
        return str(p)


def md_escape(s) -> str:
    """Escape Markdown special chars in user-provided text."""
    import re
    if s is None or s == "":
        return "—"
    return re.sub(r"([_*\[`])", r"\\\1", str(s))


# ─── DB ──────────────────────────────────────────────────────────────────────
def get_order(order_id: int) -> dict | None:
    conn = sqlite3.connect(ORDERS_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_order_by_number(order_number: str) -> dict | None:
    conn = sqlite3.connect(ORDERS_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM orders WHERE order_number=?", (order_number,)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_order_status(order_id: int, status: str, extra: dict | None = None) -> bool:
    conn = sqlite3.connect(ORDERS_DB)
    cur = conn.cursor()
    ts_field = STATUS_TIMESTAMPS.get(status)
    sets = ["status=?", "updated_at=?"]
    vals = [status, now()]
    if ts_field:
        sets.append(f"{ts_field}=?")
        vals.append(now())
    if extra:
        for k, v in extra.items():
            sets.append(f"{k}=?")
            vals.append(v)
    vals.append(order_id)
    cur.execute(f"UPDATE orders SET {', '.join(sets)} WHERE id=?", vals)
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def add_message(order_id: int, sender_type: str, content: str, message_type: str = "text") -> int:
    conn = sqlite3.connect(ORDERS_DB)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO order_messages (order_id, sender_type, content, message_type, created_at) VALUES (?,?,?,?,?)",
        (order_id, sender_type, content, message_type, now()),
    )
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return mid


def get_messages(order_id: int, limit: int = 20) -> list:
    conn = sqlite3.connect(ORDERS_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM order_messages WHERE order_id=? ORDER BY id ASC LIMIT ?",
        (order_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_payment(order_id: int, amount: int, method: str, status: str = "pending",
                transaction_id: str = None, gateway_response: str = None) -> int:
    conn = sqlite3.connect(ORDERS_DB)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO payments (order_id, amount, currency, method, status, transaction_id,
           gateway_response, created_at) VALUES (?,?,?,?,?,?,?,?)""",
        (order_id, amount, "IRR", method, status, transaction_id, gateway_response, now()),
    )
    pid = cur.lastrowid
    conn.commit()
    conn.close()
    return pid


def confirm_payment_row(payment_id: int, gateway_response: str) -> bool:
    conn = sqlite3.connect(ORDERS_DB)
    cur = conn.cursor()
    cur.execute(
        "UPDATE payments SET status='paid', paid_at=?, gateway_response=? WHERE id=?",
        (now(), gateway_response, payment_id),
    )
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def find_pending_payment(order_id: int, method: str) -> dict | None:
    conn = sqlite3.connect(ORDERS_DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM payments WHERE order_id=? AND method=? AND status='pending' ORDER BY id DESC LIMIT 1",
        (order_id, method),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ─── Order↔chat binding (per-bot user_data handles the live chat; DB row for cross-bot) ──
def bind_chat(order_id: int, chat_id: int, bot: str):
    """Store chat binding inside order requirements JSON (no schema change)."""
    o = get_order(order_id)
    if not o:
        return
    try:
        req = json.loads(o.get("requirements") or "{}")
    except (json.JSONDecodeError, TypeError):
        req = {}
    req["chat"] = {"chat_id": chat_id, "bot": bot}
    conn = sqlite3.connect(ORDERS_DB)
    cur = conn.cursor()
    cur.execute("UPDATE orders SET requirements=?, updated_at=? WHERE id=?",
                (json.dumps(req, ensure_ascii=False), now(), order_id))
    conn.commit()
    conn.close()


def get_chat_binding(order_id: int) -> dict | None:
    o = get_order(order_id)
    if not o:
        return None
    try:
        req = json.loads(o.get("requirements") or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    return req.get("chat")


# ─── Outbox: customer-facing messages delivered via @ShahbotSupportbot ──────
def queue_customer_message(order_id, chat_id, text: str, kb=None) -> int:
    """Enqueue a message for delivery by the customer-facing bot (support_bot).
    kb: InlineKeyboardMarkup or None — serialized to dict rows."""
    payload = {"chat_id": str(chat_id), "text": text, "attempts": 0}
    if kb is not None:
        try:
            payload["kb"] = kb.to_dict().get("inline_keyboard")
        except Exception:
            payload["kb"] = None
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO order_messages (order_id, sender_type, content, message_type, created_at) VALUES (?,?,?,?,?)",
        (order_id, "outbox", json.dumps(payload, ensure_ascii=False), "outbound", now()),
    )
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return mid


def fetch_outbox(limit: int = 10) -> list:
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, order_id, content FROM order_messages WHERE sender_type='outbox' ORDER BY id ASC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_outbox_sender(mid: int, sender_type: str):
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    conn.execute("UPDATE order_messages SET sender_type=? WHERE id=?", (sender_type, mid))
    conn.commit()
    conn.close()


def update_outbox_payload(mid: int, payload: dict):
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    conn.execute("UPDATE order_messages SET content=? WHERE id=?",
                 (json.dumps(payload, ensure_ascii=False), mid))
    conn.commit()
    conn.close()


# ─── Admin Inbox: admin-bound notifications delivered via @ShahbotSurveyBot ─
def queue_admin_message(order_id, text: str, kb=None, photo_path: str | None = None) -> int:
    """Enqueue a message for delivery to ADMIN by the admin bot (survey_bot)."""
    payload = {"text": text, "attempts": 0}
    if photo_path:
        payload["photo_path"] = photo_path
    if kb is not None:
        try:
            payload["kb"] = kb.to_dict().get("inline_keyboard")
        except Exception:
            payload["kb"] = None
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO order_messages (order_id, sender_type, content, message_type, created_at) VALUES (?,?,?,?,?)",
        (order_id, "admin_inbox", json.dumps(payload, ensure_ascii=False), "inbound", now()),
    )
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return mid


def fetch_admin_inbox(limit: int = 10) -> list:
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, order_id, content FROM order_messages WHERE sender_type='admin_inbox' ORDER BY id ASC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_outbox(mid: int, state: str):
    set_outbox_sender(mid, state)


# ─── Order card ──────────────────────────────────────────────────────────────
def order_card(o: dict) -> str:
    req = {}
    try:
        req = json.loads(o.get("requirements") or "{}")
    except (json.JSONDecodeError, TypeError):
        pass
    features = req.get("features", [])
    features_text = "\n".join(f"    • {md_escape(f)}" for f in features) if features else "    • —"
    pt = (o.get("project_type") or "").lower()
    pt_label = md_escape(PROJECT_LABELS_FA.get(pt, pt or "—"))
    status_raw = (o.get("status") or "").lower()
    status_label = STATUS_FA.get(status_raw, md_escape(o.get("status") or "—"))

    desc = (o.get("description") or "—")
    if len(desc) > 300:
        desc = desc[:300] + "..."

    return (
        f"🆔 سفارش #{o['id']} — `{o['order_number']}`\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📦 {md_escape(o.get('project_title', '—'))}\n"
        f"🗂 {pt_label}  |  🎯 {md_escape(req.get('complexity', '—'))}\n"
        f"💰 {format_price(o.get('final_price', 0))}\n"
        f"🔖 {status_label}\n"
        f"📅 {o.get('created_at', '')[:16]}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📝 {md_escape(desc)}\n"
        f"⚡️ ویژگی‌ها:\n{features_text}"
    )


PROJECT_LABELS_FA = {
    "telegram_bot": "🤖 ربات تلگرام",
    "whatsapp_bot": "💬 ربات واتساپ",
    "data_scraping": "🕷 اسکرپینگ داده",
    "website": "🌐 وب‌سایت",
    "automation": "⚙️ اتوماسیون",
    "content_generation": "✍️ تولید محتوا",
    "email_automation": "📧 ایمیل اتوماتیک",
    "price_comparison": "💹 مقایسه قیمت",
    "dashboard": "📊 داشبورد",
    "custom": "🛠 پروژه سفارشی",
}


def gen_order_number() -> str:
    ts = datetime.now().strftime("%Y%m%d")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD-{ts}-{suffix}"
