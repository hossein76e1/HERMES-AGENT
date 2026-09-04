---
name: autonomous-execution
description: "Execute autonomously, report results briefly."
---
# Autonomous Execution Patterns

Core principle: **do the work, then report.** Not the other way around.

## User Corrections (CRITICAL)

Hossein explicitly corrected multiple times:
1. "اوتومات پشت صحنه انجام بده و گهگاهی بهم بگو که داری انجام میدی" — Do it autonomously, occasionally tell me it's happening.
2. "سریعتر باش" / "پرقدرت با دقت و سریع" — Be faster, work powerfully and accurately.
3. "اگر بهت بگم سریعتر باش؛ سریعتر میشی؟" — User noticed speed was correlated with their explicit ask, meaning the agent was NOT defaulting to fast execution.
4. "هی مینویسم گزارش دیگه خودت برای هر پروژه هر مرحلرو شروع و تمام کردی گزارش بده" — Auto-report each stage without being asked.
5. "اگر همرو باهم همزمان انجام بدی سرعتت کم میشه؟" — User wants to know if parallelism helps; answer honestly.

## Rules

### 1. Start immediately, explain later
- User gives a task → execute RIGHT NOW
- Do NOT ask "shall I start?" or "do you want me to..."
- Do NOT explain what you're about to do before doing it
- Just do it, then report the result

### 2. "دارم روش کار میکنم" NOT "دارم شروع میکنم"
- CRITICAL: User interpreted "دارم شروع میکنم" as "nothing has happened yet"
- "دارم روش کار میکنم" = work is in progress
- "دارم شروع میکنم" = implies zero progress, feels like a delay
- Only say "دارم شروع میکنم" if you genuinely have done nothing yet

### 3. Auto-report every stage (CRITICAL)
- For multi-step projects: report EACH stage start AND completion automatically
- Format: `مرحله X/Y: [what] — [status]`
- User should NOT have to ask for updates
- Example: `مرحله ۱/۳: ساخت فایل — ✅ تموم شد` → `مرحله ۲/۳: تست — دارم روش کار میکنم`

### 4. Brief progress signals
- Every 30-60 seconds during long operations, send ONE short line
- Do NOT explain what each step does unless asked

### 5. Parallel by default
- When 2+ independent tasks exist, use `delegate_task` for parallelism
- Do NOT serialize what can be parallelized
- Report all results at once when all finish
- Caveat: delegation can timeout on large file generation (>10KB HTML). Write directly if delegation fails.

### 6. No unnecessary questions
- Do NOT ask for permission to do obvious tasks
- Do NOT ask "which do you prefer?" when you can decide reasonably
- Make a decision and execute — user can correct after
- EXCEPTION: genuine trade-offs with no clear winner

### 7. Match verbosity to the ask
- One-line question → one-line answer
- Complex task → work silently, report summary
- User asks for detail → then go deep
- Default: concise, action-oriented

### 8. If user says "do it" — just do it
- No "alright, I'll start now" preamble
- No "let me check" followed by another message
- Action output IS the response

## Anti-patterns (things NOT to do)

- ❌ "عالی! الان شروع میکنم" → just start, no announcement
- ❌ "بذار بررسی کنم..." → check silently, report finding
- ❌ "چند تا سوال دارم" → ask them ALL at once, not one by one
- ❌ Explaining what a tool does before using it
- ❌ Listing steps before executing them (just execute)
- ❌ "دارم انجام میدم" without actually having started
- ❌ Saying "دارم شروع میکنم" when work is already underway
- ❌ Going silent for 2+ minutes without a status update

## Language & Communication

- ALL user-facing text must be in Farsi (فارسی) unless user specifically asks for English
- Technical terms in English are OK, but translate unfamiliar ones in parentheses
- Code comments can stay English

## Project Execution Mode

- When user says "دونه دونه" (one by one) → build each project sequentially, complete one before starting the next
- If a project is stuck or blocking, STOP it and move to the next — user explicitly said: "اگر پروژه قبلی خیلی ازش مونده استپ کن که سرعتت گرفته نشه"
- Report completion of EACH project immediately: "پروژه X تموم شد ✅"
- User does NOT want to wait for all to finish before hearing results

## Good patterns

- ✅ Execute tool → "انجام شد: [result]"
- ✅ Multiple tools in parallel → "تموم شد: [summary]"
- ✅ Long task → brief status every 30s, final result at end
- ✅ Error → "خطا: [what happened]. دارم فیکس میکنم." → fix immediately
- ✅ Multi-step project → auto-report each stage without being asked
- ✅ "دارم روش کار میکنم" while actively executing
- ✅ If something blocks → stop it, move on, report

## Technical Patterns (from this session)

### CSV export with dynamic AI fields
AI returns varying field structures. Use dynamic fieldnames:
```python
all_keys = set()
for item in extracted:
    if isinstance(item, dict):
        all_keys.update(item.keys())
fieldnames = list(all_keys)
writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
```

### OpenAI custom provider model detection
Not all providers support standard model names. Detect available models first:
```bash
curl -s "$OPENAI_BASE_URL/models" -H "Authorization: Bearer $OPENAI_API_KEY" \
  | python3 -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin).get('data',[])]"
```

### Telegram bot token isolation
Each Telegram bot needs its own unique token. Hermes .env may contain
multiple bot tokens. When launching a new bot, use a SEPARATE env var
(e.g. SUPPORT_BOT_TOKEN) rather than TELEGRAM_BOT_TOKEN.

### Delegation timeout on large files
Subagents can timeout (90s) generating large HTML files. For HTML >10KB,
write directly with write_file instead of delegating.

### GitHub Pages deployment with curl (not gh api)
When `gh api` returns 401 but token is valid, use curl directly:
```bash
export GH_TOKEN="your_token"
curl -X POST -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  -d '{"source":{"branch":"main","path":"/docs"}}' \
  https://api.github.com/repos/OWNER/REPO/pages
```
Poll `/pages/builds/latest` until `status: "built"` before checking live URL.

### Multi-project token management
Store each bot token with clear naming in .env:
```
HERMES_BOT_TOKEN=xxx
SCRAPER_BOT_TOKEN=xxx
SUPPORT_BOT_TOKEN=xxx
SURVEY_BOT_TOKEN=xxx
APPOINTMENT_BOT_TOKEN=xxx
REPLY_BOT_TOKEN=xxx
ORDER_BOT_TOKEN=xxx
```
Create a `bots.json` manifest mapping names to tokens for easy restore.

### python-jose JWT: sub must be string
jose 3.3.0 raises `JWTClaimsError: Subject must be a string` if `sub` claim is an integer.
Always use `str(id)` when creating tokens and `int(payload.get("sub", 0))` when reading:
```python
# CREATE
create_access_token({"sub": str(user.id)})
create_access_token({"sub": str(admin.id), "is_admin": True})
# DECODE
user = db.query(User).filter(User.id == int(payload.get("sub", 0))).first()
```

### passlib + bcrypt version pinning
passlib is incompatible with bcrypt>=4.1. Must pin: `pip install 'bcrypt==4.0.1'`

### FastAPI SQLAlchemy JSON serialization
When storing JSON as `Text` column in SQLAlchemy, pydantic `response_model` expects `dict`.
Must parse before returning:
```python
d = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
if isinstance(d.get("requirements"), str):
    d["requirements"] = json.loads(d["requirements"])
return MyModel(**d)
```
or use `@model_validator` / `@field_validator` in pydantic v2.

### sqlite3 is Python stdlib
Do NOT include `sqlite3` in requirements.txt — it's built into Python.

### Git push when token fails but gh auth works
When `git push` with a token in the URL returns 'Invalid username or token' but `gh auth status` shows a valid session, configure git to use gh's credential helper:
```bash
gh auth setup-git
git push origin main
```
This works even when the explicit token is expired. Prefer this over embedding tokens in remote URLs.

### Background server duplication pitfall
Before starting a background server, ALWAYS kill existing processes on that port first:
```bash
pkill -f 'uvicorn.*api:app' 2>/dev/null; sleep 1
fuser -k 8000/tcp 2>/dev/null  # optional fallback
```
Then start ONE instance. Running `terminal(background=true)` multiple times without killing creates orphaned servers causing port conflicts.

### Full-stack order system pricing engine
Auto-pricing based on project type + complexity + features + timeline:
- Base prices defined per project type (IRR)
- Multipliers for complexity (1x-4x), timeline (1x-2x)
- Feature add-ons (+500K per feature)
- Admin can override final price before sending quote

### Admin approval workflow for delivery
Order flow: PENDING → QUOTED → PAID → IN_PROGRESS → READY → DELIVERED
Admin must approve at QUOTED (price) and READY (delivery) stages.
Customer only pays after admin sends quote.
Deliverable only released after admin approves delivery.