#!/usr/bin/env python3
"""
🏗 auto_builder.py — سازنده خودکار پروژه با هوش مصنوعی
جریان: سفارش پرداخت‌شده → AI کد می‌سازد → تست → بسته‌بندی zip → تحویل
استفاده توسط build_worker.py (فرایند پس‌زمینه مستقل از بات‌ها).
"""
import os
import sys
import json
import shutil
import zipfile
import sqlite3
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv("/data/.hermes/.env", override=True)

from openai import OpenAI

ORDERS_DB = "/data/workspace/order-system/backend/orders.db"
BUILD_DIR = "/data/workspace/auto-builds"
RECEIPTS = "/data/workspace/projects/receipts"
ADMIN_ID = "1030173067"

AI_KEY = os.environ.get("OPENAI_API_KEY")
AI_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
AI_MODEL = os.environ.get("AI_MODEL", "GLM")
client = OpenAI(api_key=AI_KEY, base_url=AI_URL) if AI_KEY else None

BUILDER_SYSTEM = """تو یک مهندس نرم‌افزار ارشد هستی که پروژه‌های سفارشی می‌سازد.
کاربر یک پروژه سفارش داده. تو باید کد کامل، آماده اجرا و باکیفیت بسازی.

قوانین ساخت:
- کد کاملاً کاربردی و اجراشدنی بنویس، نه شبه‌کد.
- ساختار پروژه: پوشه اصلی + فایل‌های منطقی + README.md فارسی (نصب و اجرا) + requirements.txt اگر پایتون است.
- برای ربات تلگرام: python-telegram-bot (نسخه 22+) با توکن از متغیر محیطی BOT_TOKEN.
- برای اسکرپر: requests + beautifulsoup4 با مدیریت خطا.
- برای وب‌سایت: HTML/CSS/JS آماده باز شدن در مرورگر.
- فارسی بودن پیام‌های کاربری و کامنت‌های کلیدی.
- هیچ کلید API واقعی در کد نگذار — از os.environ بخوان.
- کد را ساده و مستند نگه دار؛ کیفیت مهم‌تر از حجم است."""

BUILD_PROMPT = """سفارش مشتری:
نوع: {ptype}
عنوان: {title}
توضیح: {description}
ویژگی‌ها: {features}
پیچیدگی: {complexity}

حالا پروژه را کامل بساز. خروجی را دقیقاً در این قالب JSON بده:
{{
  "files": {{
    "README.md": "...",
    "requirements.txt": "...",
    "main.py": "..."
  }},
  "entry_command": "python main.py",
  "notes": "توضیح کوتاه فارسی برای مشتری درباره چیزی که ساخته شد"
}}
نکته: مقدار هر فایل، محتوای کامل آن فایل است. حداقل فایل‌های لازم برای اجرا را بده."""


def ai_build(collected: dict) -> dict:
    """Ask AI to generate the full project. Returns dict with files/json or error."""
    if not client:
        return {"error": "AI client unavailable"}
    prompt = BUILD_PROMPT.format(
        ptype=collected.get("project_type", "custom"),
        title=collected.get("project_title", ""),
        description=collected.get("description", ""),
        features=", ".join(collected.get("features", [])) or "—",
        complexity=collected.get("complexity", "simple"),
    )
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=AI_MODEL,
                messages=[{"role": "system", "content": BUILDER_SYSTEM},
                          {"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=6000,
            )
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                continue
            import re
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                continue
            data = json.loads(m.group(0))
            if "files" not in data or not isinstance(data["files"], dict) or not data["files"]:
                continue
            return data
        except json.JSONDecodeError:
            continue
        except Exception as e:
            return {"error": str(e)}
    return {"error": "AI produced no valid project after 3 attempts"}


def sanity_check(project_dir: str, entry: str) -> dict:
    """Compile-check python files; return {ok: bool, details}"""
    py_files = []
    for root, _, files in os.walk(project_dir):
        for f in files:
            if f.endswith(".py"):
                py_files.append(os.path.join(root, f))
    if not py_files and entry.startswith("python"):
        return {"ok": False, "details": "no python files but entry is python"}
    for pf in py_files:
        r = subprocess.run([sys.executable, "-m", "py_compile", pf], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return {"ok": False, "details": f"compile error in {os.path.basename(pf)}: {r.stderr[:300]}"}
    return {"ok": True, "details": f"{len(py_files)} python files compile OK"}


def package_project(order_id: int, order_number: str) -> str | None:
    """Zip the build dir into deliverables dir. Returns zip path."""
    src = os.path.join(BUILD_DIR, str(order_id))
    if not os.path.isdir(src):
        return None
    out_dir = os.path.join(BUILD_DIR, "deliverables")
    os.makedirs(out_dir, exist_ok=True)
    zip_path = os.path.join(out_dir, f"{order_number}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(src):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, src)
                zf.write(full, rel)
    return zip_path


def queue_outbox(order_id: int, chat_id: str, text: str, kb=None, document_path: str | None = None):
    payload = {"chat_id": str(chat_id), "text": text, "attempts": 0}
    if document_path:
        payload["document_path"] = document_path
    if kb is not None:
        try:
            payload["kb"] = kb.to_dict().get("inline_keyboard")
        except Exception:
            payload["kb"] = None
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO order_messages (order_id, sender_type, content, message_type, created_at) VALUES (?,?,?,?,?)",
        (order_id, "outbox", json.dumps(payload, ensure_ascii=False), "outbound", datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def queue_admin(order_id: int, text: str, kb=None):
    payload = {"text": text, "attempts": 0}
    if kb is not None:
        try:
            payload["kb"] = kb.to_dict().get("inline_keyboard")
        except Exception:
            payload["kb"] = None
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO order_messages (order_id, sender_type, content, message_type, created_at) VALUES (?,?,?,?,?)",
        (order_id, "admin_inbox", json.dumps(payload, ensure_ascii=False), "inbound", datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def db_status(order_id: int, status: str):
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    cur = conn.cursor()
    now = datetime.now().isoformat()
    ts = {"in_progress": "started_at", "delivered": "delivered_at"}.get(status)
    if ts:
        cur.execute(f"UPDATE orders SET status=?, {ts}=?, updated_at=? WHERE id=?", (status, now, now, order_id))
    else:
        cur.execute("UPDATE orders SET status=?, updated_at=? WHERE id=?", (status, now, order_id))
    conn.commit()
    conn.close()


def db_get(order_id: int) -> dict | None:
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    conn.close()
    return dict(r) if r else None


def build_order(order_id: int) -> bool:
    """Full build pipeline for one paid order. Returns True if delivered."""
    o = db_get(order_id)
    if not o:
        return False
    try:
        req = json.loads(o.get("requirements") or "{}")
    except (json.JSONDecodeError, TypeError):
        req = {}
    chat = req.get("chat", {})
    chat_id = str(chat.get("chat_id", ""))
    collected = {k: v for k, v in req.items() if k != "chat"}

    # 1) status → in_progress + notify customer & admin
    db_status(order_id, "in_progress")
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup  # local import for kb dicts
    kb_none = None
    queue_outbox(order_id, chat_id,
                 "🔧 **ساخت پروژه‌ت شروع شد!**\n\nهوش مصنوعی الان داره پروژه‌ت رو می‌سازه — چند دقیقه صبر کن ⏳")
    queue_admin(order_id, f"🏗 ساخت خودکار سفارش #{order_id} (`{o['order_number']}`) شروع شد...")

    # 2) AI builds
    result = ai_build(collected)
    if "error" in result:
        queue_admin(order_id,
                    f"❌ **ساخت خودکار شکست خورد!** سفارش #{order_id}\nخطا: `{result['error']}`\n\nنیاز به ساخت دستی داری — در چت اصلی اطلاع بده.")
        return False

    # 3) write files
    proj_dir = os.path.join(BUILD_DIR, str(order_id))
    shutil.rmtree(proj_dir, ignore_errors=True)
    os.makedirs(proj_dir, exist_ok=True)
    for fname, content in result["files"].items():
        fpath = os.path.join(proj_dir, fname)
        os.makedirs(os.path.dirname(fpath), exist_ok=True) if "/" in fname else None
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)

    # 4) sanity check
    check = sanity_check(proj_dir, result.get("entry_command", "python main.py"))

    # 5) package
    zip_path = package_project(order_id, o["order_number"])
    if not zip_path:
        queue_admin(order_id, f"❌ بسته‌بندی سفارش #{order_id} شکست خورد.")
        return False

    # 6) deliver to customer
    notes = result.get("notes", "")
    entry = result.get("entry_command", "")
    readme = result["files"].get("README.md", "")
    deliver_text = (
        "🎉 **پروژه‌ت ساخته شد و آماده‌ست!**\n\n"
        f"📦 {o['project_title']}\n"
        + (f"\n📝 {notes}\n" if notes else "")
        + f"\n🚀 نحوه اجرا:\n`{entry}`\n"
        + "\nفایل zip را دانلود کن، باز کن و طبق README اجرا کن.\n"
        + "۷ روز پشتیبانی رایگان — سوالی بود در خدمتم 💬"
    )
    if check["ok"]:
        db_status(order_id, "delivered")
        queue_outbox(order_id, chat_id, deliver_text, kb_none, document_path=zip_path)
        queue_admin(order_id,
                    f"✅ **سفارش #{order_id} خودکار ساخته و تحویل داده شد!**\n"
                    f"🧪 تست: {check['details']}\n📦 فایل: `{os.path.basename(zip_path)}`")
    else:
        # failed check → notify admin, keep in_progress
        queue_admin(order_id,
                    f"⚠️ **ساخت سفارش #{order_id} نیاز به بررسی دارد**\n"
                    f"🧪 تست: `{check['details']}`\n"
                    f"پروژه ساخته شد ولی تست کامپایل رد شد. یا اصلاح کن و دوباره بساز، یا دستی تحویل بده.",
                    kb=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 ساخت مجدد", callback_data=f"adm:rebuild:{order_id}")]]))
        return False
    return True


def fetch_paid_orders() -> list:
    conn = sqlite3.connect(ORDERS_DB, timeout=10)
    rows = conn.execute("SELECT id FROM orders WHERE status='paid' ORDER BY id ASC").fetchall()
    conn.close()
    return [r[0] for r in rows]


if __name__ == "__main__":
    import time
    print("🏗 auto_builder running (poll every 60s)...")
    while True:
        try:
            for oid in fetch_paid_orders():
                print(f"[{datetime.now():%H:%M:%S}] building order #{oid}...")
                try:
                    build_order(oid)
                except Exception as e:
                    print(f"build error for #{oid}: {e}")
                    queue_admin(oid, f"❌ خطای ساخت سفارش #{oid}: `{str(e)[:200]}`")
        except Exception as e:
            print(f"poll error: {e}")
        time.sleep(60)
