# Telegram Bot Token Conflicts (409 Error)

## Problem

When multiple Hermes instances or multiple bots try to use the same Telegram token, you get:

```
Conflict: terminated by other getUpdates request
```

This happens because Telegram only allows one active `getUpdates` polling connection per bot token.

## Causes in This Session

1. **Hermes's own bot token** was being used by the scraper bot instead of its own `SCRAPER_BOT_TOKEN`
2. **Multiple bot processes** started simultaneously on the same token
3. **Old cloudflared processes** weren't cleaned up before starting new ones

## Solution Pattern

### 1. Each bot gets its own token
```bash
# .env pattern
HERMES_BOT_TOKEN=xxx          # Hermes's main bot
SCRAPER_BOT_TOKEN=yyy         # Smart Scraper bot (@Hosseinagentcoderbot)
SUPPORT_BOT_TOKEN=zzz         # Support bot (@ShahbotSupportbot)
SURVEY_BOT_TOKEN=aaa          # Survey bot (@ShahbotSurveyBot)
APPOINTMENT_BOT_TOKEN=bbb     # Appointment bot (needs token)
REPLY_BOT_TOKEN=ccc           # Auto-reply bot (needs token)
ORDER_BOT_TOKEN=ddd           # Order bot (needs token)
```

### 2. Bot code must use its specific env var
```python
# Wrong - uses Hermes's token
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# Right - uses its own token
TOKEN = os.environ.get('SCRAPER_BOT_TOKEN')
```

### 3. Kill existing processes before starting new ones
```bash
# Check and kill existing bot processes
for pid in /proc/*/cmdline; do
    cat $pid 2>/dev/null | grep -q 'bot_name' && kill $(basename $(dirname $pid))
done

# Or use pgrep if available
pgrep -f 'scraper_bot' | xargs kill
```

### 4. Verify no other instance is polling
```bash
# Test with curl before starting
curl -s "https://api.telegram.org/bot${TOKEN}/getMe"
# If it returns ok:true, token is valid and no other polling
```

## Best Practices

1. **One token per bot** — never share tokens across bots
2. **Kill before start** — always clean up old processes
3. **Use distinct env var names** — `SCRAPER_BOT_TOKEN`, `SUPPORT_BOT_TOKEN`, etc.
4. **Don't use dotenv** for Hermes bots — Hermes loads `.env` globally; bots read from `os.environ` directly
5. **Start bots sequentially** with verification between each
6. **Background with process_manage** — use `background=true, notify_on_complete=true` for monitoring

## Recovery When Conflict Occurs

```bash
# 1. Kill ALL Telegram bot processes
pkill -f 'telegram'
pkill -f 'bot.py'
# Or manually via /proc
for pid in /proc/*/cmdline; do
    cat $pid 2>/dev/null | grep -qE 'telegram|bot\.py' && kill $(basename $(dirname $pid))
done

# 2. Wait 5 seconds for Telegram to release the lock
sleep 5

# 3. Start bots ONE BY ONE with their correct tokens
# 4. Verify each with /start before starting next
```

## Related Files

- `/data/workspace/smart-scraper/telegram_bot.py` — uses `SCRAPER_BOT_TOKEN`
- `/data/workspace/projects/support_bot.py` — uses `SUPPORT_BOT_TOKEN`
- `/data/workspace/projects/survey_bot.py` — uses `SURVEY_BOT_TOKEN`
- `/data/workspace/projects/appointment_bot.py` — needs `APPOINTMENT_BOT_TOKEN`
- `/data/workspace/projects/auto_reply_bot.py` — needs `REPLY_BOT_TOKEN`
- `/data/.hermes/.env` — contains all tokens