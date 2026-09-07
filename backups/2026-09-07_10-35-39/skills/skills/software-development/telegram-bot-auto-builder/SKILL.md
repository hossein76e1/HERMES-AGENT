---
name: telegram-bot-auto-builder
description: "Automatic project generation for Telegram bots with AI, including graceful fallbacks when the LLM is unavailable or rate-limited."
category: software-development
version: 1.0.0
author: Hermes Agent
license: MIT
---

# telegram-bot-auto-builder

**Class-level skill**: Automatic project generation for Telegram bots with AI, including graceful fallbacks when the LLM is unavailable or rate-limited.

## When to use
- User creates a paid order for a Telegram bot project
- Need to generate project files (code, README, requirements) via AI
- AI (GLM via 9Router) is rate-limited, returning empty, or timing out

## Core Pattern
1. **File-by-file generation** (NOT single long-generation prompt)
   - Break the build prompt into separate calls per file
   - Each call: ~600 max_tokens, much more reliable
2. **3-attempt retry** with 3s pause between attempts per file
3. **Graceful fallback** if ALL AI attempts fail:
   - Generate default minimal project files:
     - `README.md` — installation + usage notes in Persian + English
     - `requirements.txt` — python-telegram-bot==22.8
     - `main.py` — simple echo/start bot skeleton
   - Log: `⚠️ AI plan failed — using default minimal project`
   - Pipeline continues → zip → outbox → deliver

## Triggers (from survey_bot.py)
- `adm:start:` callback with `auto_build=True` in order requirements JSON
- OR manual `auto_build` flag set in `orders.db` requirements column

## Output
- `build_order(order_id)` returns `True` if pipeline reaches `delivered` status
- If AI fails: still returns `True` after writing default files and queuing delivery
- Admin notified of both success and fallback

## Supported project types
- `telegram_bot` — python-telegram-bot based bots
- `content_generation` — HTML/email/template projects
- `automation` — script/tools projects
- `data_scraping` — parser/crawler projects

## Known Pits
- GLM on 9Router free tier drops long generations (>2000 tokens)
- Always set `auto_build=True` in requirements JSON before calling `build_order`
- Fallback files are minimal but functional — user can later replace via manual upload

## References (session-specific)
- This skill was created during session 2026-09-05 for user hossein76e1
- Key files: `/data/workspace/projects/auto_builder.py`
- Tested: `test_e2e_v5.py` with mock AI passes all 8 checks
- Real GLM: short calls work; long gens reliably fail (503/502/400)
- Fallback delivers functional skeleton to customer even when AI unavailable

## Templates
- `templates/telegram-bot-skeleton.py` — copy-and-modify starter bot
- `references/glm-rate-limit-notes.md` — observed GLM failure patterns

**Skill-level**: Class-level umbrella — future sessions will load this automatically when `auto_build` flag is set on a paid order.