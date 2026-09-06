#!/usr/bin/env python3
"""
🎨 image_service.py — سرویس تولید تصویر برای سفارش‌های طراحی
Pollinations.ai (رایگان، بدون کلید) + تحویل از طریق outbox بات سفارش‌گیر.
"""
import os
import sys
import json
import time
import urllib.parse
import urllib.request
import sqlite3
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ORDERS_DB = "/data/workspace/order-system/backend/orders.db"
IMG_DIR = "/data/workspace/auto-builds/images"

PROMPT_STYLE = {
    "digital_art": "high quality digital art, vibrant colors, detailed",
    "logo": "minimalist flat logo design, clean vector style, centered on plain background",
    "realistic": "photorealistic, 8k, professional lighting",
    "cartoon": "cute cartoon style, chibi, soft colors",
    "poster": "poster design, bold typography-free composition, eye-catching",
}


def gen_image(prompt: str, style: str = "digital_art", width: int = 1024, height: int = 1024) -> str | None:
    """Generate an image via pollinations.ai; returns local path or None."""
    os.makedirs(IMG_DIR, exist_ok=True)
    styled = f"{prompt}, {PROMPT_STYLE.get(style, PROMPT_STYLE['digital_art'])}"
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(styled)
           + f"?width={width}&height={height}&nologo=true&seed={int(time.time())}")
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(IMG_DIR, f"img-{ts}.jpg")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
            f.write(r.read())
        if os.path.getsize(path) < 5000:  # suspiciously small = error page
            return None
        return path
    except Exception as e:
        print(f"image gen error: {e}")
        return None


def queue_outbox_photo(order_id: int, chat_id: str, caption: str, image_path: str) -> int:
    """Queue an image for delivery by @ShahbotSupportbot's outbox worker."""
    payload = {"chat_id": str(chat_id), "text": caption, "attempts": 0, "image_path": image_path}
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO order_messages (order_id, sender_type, content, message_type, created_at) VALUES (?,?,?,?,?)",
        (order_id, "outbox", json.dumps(payload, ensure_ascii=False), "outbound", datetime.now().isoformat()),
    )
    mid = cur.lastrowid
    conn.commit()
    conn.close()
    return mid


def queue_admin(order_id: int, text: str):
    payload = {"text": text, "attempts": 0}
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    conn.execute(
        "INSERT INTO order_messages (order_id, sender_type, content, message_type, created_at) VALUES (?,?,?,?,?)",
        (order_id, "admin_inbox", json.dumps(payload, ensure_ascii=False), "inbound", datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def db_status(order_id: int, status: str):
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    conn.execute("UPDATE orders SET status=?, updated_at=? WHERE id=?", (status, datetime.now().isoformat(), order_id))
    conn.commit()
    conn.close()


def db_get(order_id: int) -> dict | None:
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return dict(r) if r else None


def build_image_order(order_id: int) -> bool:
    """Full pipeline for an image-design order: gen → deliver → set delivered."""
    o = db_get(order_id)
    if not o:
        return False
    try:
        req = json.loads(o.get("requirements") or "{}")
    except (json.JSONDecodeError, TypeError):
        req = {}
    chat = req.get("chat", {})
    chat_id = chat.get("chat_id", "")
    if isinstance(chat_id, int):
        chat_id = str(chat_id)

    style = req.get("style", "digital_art")
    prompt = o.get("description") or o.get("project_title") or "abstract art"
    features = req.get("features") or []
    if features:
        prompt += ", " + ", ".join(str(f) for f in features)

    print(f"[image] order #{order_id}: prompt={prompt[:80]} style={style}")
    path = gen_image(prompt, style)
    if not path:
        queue_admin(order_id, f"❌ تولید تصویر سفارش #{order_id} شکست خورد — دستی بساز یا دوباره تلاش کن.")
        return False

    caption = (f"🎨 **{o['project_title']}**\n\n"
               f"تصویرت آماده‌ست! 🖼\n"
               f"{(str(req.get('notes', '')) + chr(10)) if req.get('notes') else ''}"
               f"🛡 ۷ روز پشتیبانی — اگه تغییری می‌خوای بگو!")
    queue_outbox_photo(order_id, chat_id, caption, path)
    db_status(order_id, "delivered")
    queue_admin(order_id, f"✅ سفارش #{order_id} (`{o['order_number']}`) تصویر تولید و تحویل شد 🎨\nفایل: `{os.path.basename(path)}`")
    print(f"[image] order #{order_id} delivered: {path}")
    return True


if __name__ == "__main__":
    # CLI test: python3 image_service.py "یک گاو کارتونی"
    if len(sys.argv) > 1:
        p = gen_image(" ".join(sys.argv[1:]))
        print(p or "FAILED")
