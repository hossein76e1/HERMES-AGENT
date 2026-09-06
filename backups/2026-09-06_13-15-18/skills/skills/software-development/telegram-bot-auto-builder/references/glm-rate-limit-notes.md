# GLM rate-limit observed patterns (session 2026-09-05)

## Symptoms
- `Error code: 503 - TeamoRouter wallet balance insufficient`
- `Error code: 502 - fetch connect timeout (reset after 29s)`
- `Error code: 400 - Invalid model format`
- Response returns `0 chars` / empty string
- Long generations (>2000 tokens) reliably fail

## What works
- Short calls (100-600 max_tokens) with `GLM` model
- Calls without `BUILDER_SYSTEM` Persian prompt (English or minimal system)
- `tiny-sys` pattern: `{"role": "system", "content": "فقط JSON برگردان."}` + short user msg

## What fails
- Single prompt with full build instructions (557+ chars + 230 sys)
- `teamrouter/deepseek-v4-flash-free` (also 503)
- Any model when asked to produce complete project in one shot

## Mitigation
- Break into per-file calls (recommended in `telegram-bot-auto-builder` skill)
- Use fallback default files when ALL attempts fail (see `auto_builder.py` fallback logic)
- Retry with 3s pause; 3 attempts per file max
- After 3 file failures, pipeline continues with skeleton project

## Session notes
- User: hossein76e1 (Hossein)
- Date: 2026-09-05
- AI provider: 9Router GLM via openai-compatible endpoint
- Skill that captured this: `telegram-bot-auto-builder`