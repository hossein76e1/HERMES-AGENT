#!/usr/local/bin/python3
# telegram_assistant.py — Optimized personal assistant with local intent parsing for speed.
# Reminders/tasks/shopping work WITHOUT AI (PTB JobQueue). AI only for chat/action parsing.
# Catch-up: reminders missed while bot was off fire within 24h with "ببخشید دیر شد"; older ones roll/drop.

import os, json, re, logging
from datetime import datetime, timedelta, timezone
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.environ.get("TELEGRAM_ASSISTANT_TOKEN") or os.environ.get("SUPPORT_BOT_TOKEN", "")
BOT_USERNAME = "Hosseinagentcoderbot"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")
TZ = timezone(timedelta(hours=3, minutes=30))
STEP = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tg_assistant")

AI_MODEL = os.environ.get("AI_MODEL", "GLM")
ai_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""),
                   base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")) \
    if os.environ.get("OPENAI_API_KEY") else None


def load_data():
    try:
        return json.load(open(DATA_FILE))
    except Exception:
        return {"users": {}}


DATA = load_data()


def save_data():
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(DATA, f, ensure_ascii=False, indent=1)
    os.replace(tmp, DATA_FILE)


def user(chat_id):
    return DATA["users"].setdefault(str(chat_id), {"tasks": [], "reminders": [], "shopping": []})


def now():
    return datetime.now(TZ)


def parse_when(s):
    s = str(s).strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=TZ)
        except ValueError:
            pass
    try:
        dt = datetime.fromisoformat(s)
        return dt.astimezone(TZ)
    except ValueError:
        return None


def parse_intent_local(text):
    """Parse common intents locally without AI. Returns (action, args) or None."""
    t = text.strip()
    # Reminder
    if "یادآوری" in t or "یادداشت" in t or "به یاد" in t:
        dt = parse_when(t)
        if dt:
            # Extract reminder text by removing time-related words
            reminder_text = re.sub(r'(ساعت\s*\d{1,2}:\d{2}|\d{1,2}:\d{2}|ساعت\s*\d{1,2}|صبح|ظهر|عصر|شب|فردا|امروز|روز\s*\d+)', '', t, flags=re.IGNORECASE)
            reminder_text = re.sub(r'(یادآوری|یادداشت|به\s*یاد)[\s\u200c]*(کن|کنید|بکن|بگذار|ذخیره|نشانده)?', '', reminder_text, flags=re.IGNORECASE)
            reminder_text = reminder_text.strip(" .،:;")
            if not reminder_text:
                reminder_text = "یادآوری"
            repeat = "none"
            if "هر روز" in t or "روزانه" in t:
                repeat = "daily"
            elif "هر هفته" in t or "هفتگی" in t:
                repeat = "weekly"
            return ("add_reminder", {"text": reminder_text, "when": dt.isoformat(), "repeat": repeat})
    # Task add
    if ("کار" in t and ("افزود" in t or "اضافه" in t)) or "task" in t.lower():
        task_text = re.sub(r'(کار|وظیفه)[\s\u200c]*(افزود|اضافه)( کن)?', '', t, flags=re.IGNORECASE)
        task_text = task_text.strip()
        if task_text:
            return ("add_task", {"text": task_text})
    # Done task
    m = re.search(r'(کار|وظیفه)[\s\u200c]*(\d+)[\s\u200c]*(انجام|done|completed)', t, re.IGNORECASE)
    if m:
        try:
            return ("done_task", {"index": int(m.group(2))})
        except:
            pass
    # List tasks
    if "کارها" in t and ("نمایش" in t or "لیست" in t or "ببین" in t or "نشان" in t):
        return ("list_tasks", {})
    # Shopping add
    if ("لیست خرید" in t or "خرید" in t) and ("افزود" in t or "اضافه" in t):
        shop_text = re.sub(r'(لیست خرید|خرید)[\s\u200c]*(افزود|اضافه)( کن)?', '', t, flags=re.IGNORECASE)
        shop_text = shop_text.strip()
        if shop_text:
            return ("add_shopping", {"text": shop_text})
    # List shopping
    if "لیست خرید" in t and ("نمایش" in t or "لیست" in t or "ببین" in t):
        return ("list_shopping", {})
    # Remove shopping
    if "حذف" in t and ("لیست خرید" in t or "خرید" in t):
        m = re.search(r'(\d+)', t)
        if m:
            try:
                return ("remove_shopping", {"index": int(m.group(1))})
            except:
                pass
    return None


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "👋 <b>سلام! من دستیار شخصی تو هستم.</b>\n\n"
        "⚡ <b>سریع، هوشمند، همیشه در دسترس.</b>\n\n"
        "🔔 <b>یادآوری</b>\n"
        "   «یادآوری کن فردا ۹ صبح دارو بخورم»\n"
        "   «هر روز ساعت ۸ صبح بخیر بگو»\n"
        "   «یادآوری کن روز شنبه خرید کن»\n\n"
        "✅ <b>کارها (Task)</b>\n"
        "   «کار اضافه کن تماس با بانک»\n"
        "   «کارها رو نشون بده»\n"
        "   «کار ۱ انجام شد»\n\n"
        "🛒 <b>لیست خرید</b>\n"
        "   «به لیست خرید شیر اضافه کن»\n"
        "   «لیست خرید رو نشون بده»\n"
        "   «از لیست خرید ۱ حذف کن»\n\n"
        "💬 <b>چت هوشمند</b>\n"
        "   هر سوالی بپرس، پاسخ میدم.\n\n"
        "🔄 <b>ویژگی‌های مخفی:</b>\n"
        "   • یادآوری‌ها حتی در قطعی اینترنت/سرور هم سر وقت می‌آیند\n"
        "   • اگر ربات خاموش بوده، تا ۲۴ ساعت با پیام «ببخشید دیر شد» جبران می‌کند\n"
        "   • بکاپ خودکار هر ۶ ساعت (۵ نسخه اخیر)\n\n"
        "🚀 <b>فقط بنویس، من انجام می‌دهم.</b>"
    )
    await update.message.reply_text(welcome, parse_mode="HTML")


SYSTEM = """تو دستیار شخصی فارسی‌زبان کاربر هستی. مستقیم، کوتاه و خودمونی جواب بده؛ بدون مرحله تفکر.
اگر درخواست دربارهٔ یادآوری/کار/لیست خرید است، فقط JSON بده:
{"action":"add_reminder","text":"...","when":"YYYY-MM-DDTHH:MM","repeat":"none|daily|weekly"}
{"action":"add_task","text":"..."} | {"action":"done_task","index":1} | {"action":"list_tasks"}
{"action":"add_shopping","text":"..."} | {"action":"list_shopping"} | {"action":"remove_shopping","index":1}
{"action":"chat","reply":"پاسخ فارسی"}
when به وقت ایران. الان: {NOW}. «فردا ۹ صبح» را خودت محاسبه کن. هیچ متن بیرون از JSON ننویس."""


def ai_decide(text, chat_id):
    if not ai_client:
        return {"action": "chat", "reply": "⚠️ سرویس هوش مصنوعی موقتاً قطعه — ولی یادآوری‌هات بدون AI هم سر وقت کار می‌کنن."}
    u = user(chat_id)
    ctx = ("\nیادآوری‌های فعلی: " + json.dumps([{"text": r["text"], "when": r["when"]} for r in u["reminders"]], ensure_ascii=False)
           + "\nکارها: " + json.dumps(u["tasks"], ensure_ascii=False)
           + "\nلیست خرید: " + json.dumps(u["shopping"], ensure_ascii=False))
    prompt = SYSTEM.replace("{NOW}", now().strftime("%Y-%m-%d %H:%M (%A)")) + ctx
    try:
        resp = ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": text}],
            temperature=0.2, max_tokens=600,
        )
        raw = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        log.warning(f"AI error: {e}")
        return {"action": "chat", "reply": "⚠️ سرویس هوش مصنوعی موقتاً قطعه — چند لحظه دیگه دوباره بفرست. (یادآوری‌ها مستقل از AI کار می‌کنن)"}
    return {"action": "chat", "reply": "نتونستم پردازش کنم — دوباره بفرست."}


def schedule(rem, job_queue):
    dt = parse_when(rem["when"])
    if not dt or dt <= now():
        return
    job_queue.run_once(fire_reminder, when=dt, data=dict(rem), name=f"rem-{rem['id']}")


async def fire_reminder(context: ContextTypes.DEFAULT_TYPE):
    rem = context.job.data
    cid = rem["chat_id"]
    u = user(cid)
    u["reminders"] = [r for r in u["reminders"] if r["id"] != rem["id"]]
    save_data()
    await context.bot.send_message(cid, f"⏰ یادآوری:\n🔔 {rem['text']}")
    rep = rem.get("repeat")
    if rep in STEP:
        nxt = parse_when(rem["when"]) + STEP[rep]
        while nxt <= now():
            nxt += STEP[rep]
        nr = {**rem, "id": rem["id"] + "r", "when": nxt.isoformat()}
        u["reminders"].append(nr)
        save_data()
        schedule(nr, context.job_queue)


async def fire_late(context: ContextTypes.DEFAULT_TYPE):
    rem = context.job.data
    await context.bot.send_message(rem["chat_id"], f"⏰ یادآوری (ببخشید دیر شد — ربات لحظه‌ای آفلاین بود):\n🔔 {rem['text']}")


def catch_up(app):
    """On startup: future → schedule; missed ≤24h → fire now + roll if repeating; older → roll recurring, drop one-offs."""
    jq = app.job_queue
    delay = 3
    for cid, u in DATA["users"].items():
        keep = []
        for r in u["reminders"]:
            dt = parse_when(r["when"])
            if not dt:
                continue
            late = (now() - dt).total_seconds()
            r = {**r, "chat_id": int(cid)}
            if late <= 0:
                keep.append(r)
                schedule(r, jq)
            elif late <= 86400:
                jq.run_once(fire_late, when=delay, data=dict(r), name=f"late-{r['id']}")
                delay += 2
                if r.get("repeat") in STEP:
                    nxt = dt + STEP[r["repeat"]]
                    while nxt <= now():
                        nxt += STEP[r["repeat"]]
                    nr = {**r, "when": nxt.isoformat()}
                    keep.append(nr)
                    schedule(nr, jq)
            else:
                if r.get("repeat") in STEP:
                    nxt = dt + STEP[r["repeat"]]
                    while nxt <= now():
                        nxt += STEP[r["repeat"]]
                    nr = {**r, "when": nxt.isoformat()}
                    keep.append(nr)
                    schedule(nr, jq)
                else:
                    log.info(f"dropped stale one-off (>24h late): {r['text'][:30]}")
        u["reminders"] = keep
    save_data()


async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    ts = now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(BASE_DIR, f"data.backup.{ts}.json")
    json.dump(DATA, open(dst, "w"), ensure_ascii=False, indent=1)
    backups = sorted(f for f in os.listdir(BASE_DIR) if f.startswith("data.backup.") and f.endswith(".json"))
    for old in backups[:-5]:
        os.remove(os.path.join(BASE_DIR, old))


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    chat = msg.chat
    text = (msg.text or "").strip()
    if not text:
        return
    if chat.type != "private":
        is_reply_to_bot = msg.reply_to_message and msg.reply_to_message.from_user.id == context.bot.id
        if not is_reply_to_bot and f"@{BOT_USERNAME}" not in text:
            return

    # 1) Try local parsing first (instant, no AI)
    local_res = parse_intent_local(text)
    if local_res is not None:
        act, args = local_res
        reply = None
        u = user(chat.id)

        if act == "add_reminder":
            dt = parse_when(args["when"])
            rtext = args["text"].strip()
            if dt and rtext:
                rep = args.get("repeat") if args.get("repeat") in STEP else "none"
                rem = {"id": f"{chat.id}-{int(now().timestamp())}", "chat_id": chat.id,
                       "text": rtext, "when": dt.isoformat(), "repeat": rep}
                u["reminders"].append(rem)
                save_data()
                schedule(rem, context.job_queue)
                tag = " (هر روز)" if rep == "daily" else " (هر هفته)" if rep == "weekly" else ""
                reply = f"✅ یادآوری ثبت شد:\n🔔 {rtext}\n🕐 {dt.strftime('%Y-%m-%d %H:%M')}{tag}"
            else:
                reply = "⏰ زمانش رو متوجه نشدم. مثلاً: «یادآوری کن فردا ساعت ۹ دارو بخورم»"

        elif act == "add_task":
            t = args.get("text", "").strip()
            if t:
                u["tasks"].append(t)
                save_data()
                reply = f"✅ کار اضافه شد ({len(u['tasks'])}): {t}"
            else:
                reply = "متن کار خالی بود."

        elif act == "done_task":
            try:
                i = int(args.get("index", 0)) - 1
                t = u["tasks"].pop(i)
                save_data()
                reply = f"🎉 انجام شد! «{t}» حذف شد از لیست."
            except (ValueError, IndexError):
                reply = "شمارهٔ کار معتبر نیست. بگو «کارها رو نشون بده»."

        elif act == "list_tasks":
            reply = "📋 کارها:\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(u["tasks"])) if u["tasks"] else "📭 کاری ثبت نشده."

        elif act == "add_shopping":
            t = args.get("text", "").strip()
            if t:
                u["shopping"].append(t)
                save_data()
                reply = f"🛒 به لیست خرید اضافه شد: {t}"
            else:
                reply = "مثل این بگو: «به لیست خرید شیر اضافه کن»"

        elif act == "list_shopping":
            reply = "🛒 لیست خرید:\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(u["shopping"])) if u["shopping"] else "🛒 لیست خرید خالیه."

        elif act == "remove_shopping":
            try:
                i = int(args.get("index", 0)) - 1
                t = u["shopping"].pop(i)
                save_data()
                reply = f"🗑 «{t}» از لیست خرید حذف شد."
            except (ValueError, IndexError):
                reply = "شماره معتبر نیست."

        if reply is not None:
            await msg.reply_text(reply)
            return

    # 2) Fallback to AI for complex / chat requests
    d = ai_decide(text, chat.id)
    act = (d.get("action") or "chat").lower()
    u = user(chat.id)
    reply = None

    if act == "add_reminder":
        dt = parse_when(d.get("when", ""))
        rtext = (d.get("text") or text).strip()
        if not dt or not rtext:
            reply = "⏰ زمانش رو متوجه نشدم. مثلاً: «یادآوری کن فردا ساعت ۹ دارو بخورم»"
        else:
            rep = d.get("repeat") if d.get("repeat") in STEP else "none"
            rem = {"id": f"{chat.id}-{int(now().timestamp())}", "chat_id": chat.id,
                   "text": rtext, "when": dt.isoformat(), "repeat": rep}
            u["reminders"].append(rem)
            save_data()
            schedule(rem, context.job_queue)
            tag = " (هر روز)" if rep == "daily" else " (هر هفته)" if rep == "weekly" else ""
            reply = f"✅ یادآوری ثبت شد:\n🔔 {rtext}\n🕐 {dt.strftime('%Y-%m-%d %H:%M')}{tag}"

    elif act == "add_task":
        t = (d.get("text") or "").strip()
        if t:
            u["tasks"].append(t)
            save_data()
            reply = f"✅ کار اضافه شد ({len(u['tasks'])}): {t}"
        else:
            reply = "متن کار خالی بود."

    elif act == "done_task":
        try:
            i = int(d.get("index", 0)) - 1
            t = u["tasks"].pop(i)
            save_data()
            reply = f"🎉 انجام شد! «{t}» حذف شد از لیست."
        except (ValueError, IndexError):
            reply = "شمارهٔ کار معتبر نیست. بگو «کارها رو نشون بده»."

    elif act == "list_tasks":
        reply = "📋 کارها:\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(u["tasks"])) if u["tasks"] else "📭 کاری ثبت نشده."

    elif act == "add_shopping":
        t = (d.get("text") or "").strip()
        if t:
            u["shopping"].append(t)
            save_data()
            reply = f"🛒 به لیست خرید اضافه شد: {t}"
        else:
            reply = "مثل این بگو: «به لیست خرید شیر اضافه کن»"

    elif act == "list_shopping":
        reply = "🛒 لیست خرید:\n" + "\n".join(f"{i+1}. {t}" for i, t in enumerate(u["shopping"])) if u["shopping"] else "🛒 لیست خرید خالیه."

    elif act == "remove_shopping":
        try:
            i = int(d.get("index", 0)) - 1
            t = u["shopping"].pop(i)
            save_data()
            reply = f"🗑 «{t}» از لیست خرید حذف شد."
        except (ValueError, IndexError):
            reply = "شماره معتبر نیست."

    else:
        reply = d.get("reply") or "چیزی متوجه نشدم — دوباره بگو."

    await msg.reply_text(reply)


async def backup_job(context: ContextTypes.DEFAULT_TYPE):
    ts = now().strftime("%Y%m%d-%H%M%S")
    dst = os.path.join(BASE_DIR, f"data.backup.{ts}.json")
    json.dump(DATA, open(dst, "w"), ensure_ascii=False, indent=1)
    backups = sorted(f for f in os.listdir(BASE_DIR) if f.startswith("data.backup.") and f.endswith(".json"))
    for old in backups[:-5]:
        os.remove(os.path.join(BASE_DIR, old))


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error("bot error:", exc_info=context.error)


def main():
    if not TOKEN:
        print("❌ TELEGRAM_ASSISTANT_TOKEN not set!")
        exit(1)
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(on_error)
    if app.job_queue:
        app.job_queue.run_repeating(backup_job, interval=21600, first=60)
        catch_up(app)
    else:
        print("❌ job_queue is None! Run with /usr/local/bin/python3")
        exit(1)
    print("🤖 دستیار شخصی تلگرام (بهینه) فعال شد!")
    app.run_polling()


if __name__ == "__main__":
    main()