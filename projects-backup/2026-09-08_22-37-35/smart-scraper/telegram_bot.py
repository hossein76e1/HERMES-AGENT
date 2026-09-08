#!/usr/bin/env python3
"""
Telegram Bot interface for Smart Scraper
Commands:
  /start       — Welcome message
  /scrape <url>       — AI-powered extraction (paid)
  /scrape_free <url>  — Free BeautifulSoup extraction
"""

import os
import sys
import json
import logging

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ── Load env ──────────────────────────────────────────────────────────────
# BOT_TOKEN, OPENAI_API_KEY, OPENAI_BASE_URL come from the shell environment
# (exported before this script runs). No dotenv loading.
TELEGRAM_BOT_TOKEN = os.environ.get("SCRAPER_BOT_TOKEN", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

# ── Import scraper ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper import scrape

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Handlers ──────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message."""
    text = (
        "🕷️ *Smart Scraper Bot*\n\n"
        "I extract structured data from any website.\n\n"
        "*Commands:*\n"
        "• `/scrape <url>` — AI-powered extraction (uses API credits)\n"
        "• `/scrape_free <url>` — Free BeautifulSoup extraction\n\n"
        "Example:\n"
        "`/scrape https://news.ycombinator.com`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def scrape_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """AI-powered scrape."""
    if not context.args:
        await update.message.reply_text("Usage: `/scrape <url>`", parse_mode="Markdown")
        return

    url = context.args[0]
    await update.message.reply_text(f"🔍 Scraping (AI mode)…\n{url}")

    try:
        result = await scrape_to_thread(url, ai_mode=True)
        await send_result(update, result)
    except Exception as e:
        logger.exception("scrape error")
        await update.message.reply_text(f"❌ Error: {e}")


async def scrape_free_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Free BeautifulSoup scrape."""
    if not context.args:
        await update.message.reply_text("Usage: `/scrape_free <url>`", parse_mode="Markdown")
        return

    url = context.args[0]
    await update.message.reply_text(f"🔍 Scraping (free mode)…\n{url}")

    try:
        result = await scrape_to_thread(url, ai_mode=False)
        await send_result(update, result)
    except Exception as e:
        logger.exception("scrape_free error")
        await update.message.reply_text(f"❌ Error: {e}")


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback for unknown commands."""
    await update.message.reply_text(
        "Unknown command. Use /start to see available commands."
    )


# ── Helpers ───────────────────────────────────────────────────────────────
async def scrape_to_thread(url: str, ai_mode: bool = True) -> dict:
    """Run the blocking scrape() in a thread to avoid blocking the event loop."""
    import asyncio
    return await asyncio.get_event_loop().run_in_executor(
        None, lambda: scrape(url, ai_mode=ai_mode)
    )


def _format_result(result: dict) -> str:
    """Format scrape output for Telegram."""
    if "error" in result:
        return f"❌ Error: {result['error']}"

    lines = []
    data_type = result.get("data_type", "unknown")
    type_emoji = {
        "products": "🛍️",
        "articles": "📰",
        "contacts": "📇",
        "prices": "💰",
        "listings": "📋",
        "mixed": "📦",
        "other": "📄",
    }
    lines.append(f"{type_emoji.get(data_type, '📄')} Data type: {data_type}")
    lines.append(f"📝 {result.get('summary', 'N/A')}\n")

    extracted = result.get("extracted_data", {})
    if isinstance(extracted, list):
        lines.append(f"📦 {len(extracted)} items found:")
        for i, item in enumerate(extracted[:5], 1):
            if isinstance(item, dict):
                preview = json.dumps(item, ensure_ascii=False)[:180]
                lines.append(f"  {i}. {preview}")
            else:
                lines.append(f"  {i}. {str(item)[:180]}")
        if len(extracted) > 5:
            lines.append(f"  … and {len(extracted) - 5} more")
    elif isinstance(extracted, dict):
        for key, value in extracted.items():
            if isinstance(value, list) and value:
                lines.append(f"📎 {key}: {len(value)} items")

    json_file = result.get("output_json", "")
    csv_file = result.get("output_csv", "")
    if json_file:
        lines.append(f"\n📁 Saved: {os.path.basename(json_file)}")
    if csv_file:
        lines.append(f"📁 Saved: {os.path.basename(csv_file)}")

    return "\n".join(lines)


async def send_result(update: Update, result: dict):
    """Send formatted result back to the user (split if too long)."""
    text = _format_result(result)

    # Telegram limit is 4096 chars; split if needed
    max_len = 4000
    if len(text) <= max_len:
        await update.message.reply_text(text)
    else:
        for i in range(0, len(text), max_len):
            await update.message.reply_text(text[i : i + max_len])


# ── Main ──────────────────────────────────────────────────────────────────
def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not found in env. Check /data/.hermes/.env")
        sys.exit(1)

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("scrape", scrape_cmd))
    app.add_handler(CommandHandler("scrape_free", scrape_free_cmd))

    # Catch-all for unrecognized commands
    app.add_handler(MessageHandler(filters.COMMAND, handle_unknown))

    print("🚀 Smart Scraper Bot is running…")
    app.run_polling()


if __name__ == "__main__":
    main()
