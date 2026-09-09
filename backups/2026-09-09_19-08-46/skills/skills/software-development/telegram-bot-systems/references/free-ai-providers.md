# Free AI providers — quirks & recipes

Learned while wiring AI intake, auto-build, and image delivery into the Telegram bots.

## 9Router (OpenAI-compatible, Railway-hosted free router)

- `/v1/models` lists ~95 models even when generation fails — model listing is NOT a health check.
- **Empty responses**: chat.completions frequently returns `content: ""` — intermittent, often on long system prompts or high max_tokens. Mitigation: retry 3x, keep system prompts short, one file/item per call.
- **503 wallet-balance / 502 fetch-timeout**: router-side; transient or account-state. Always ship a deterministic fallback (default files, canned answer) so the product keeps working.
- Image models (gpt-image-2, gemini-*-image) do NOT work: 400 `Provider does not support image generation`, or wallet errors. Don't rely on 9Router for images.
- Client that works: `OpenAI(api_key=..., base_url=..., timeout=120, max_retries=1)`; key/base from `.env` (`OPENAI_API_KEY`, `OPENAI_BASE_URL`), `AI_MODEL` env overrides model.
- **Prompt caching WORKS on 9router/GLM (verified 2026-09-07: cached_tokens ≈ 2240/4273 ≈ 52%)**:
  keep the request prefix byte-identical across calls — fixed system prompt + append-only
  message history. A sliding window (e.g. `history[-8:]`) mutates the prefix every turn and
  destroys the cache. Caching is TTL-based: identical-prefix calls within the window hit;
  after expiry cached_tokens drops to 0 — that's normal, not a regression.

## Pollinations.ai — free image generation, no key (VERIFIED WORKING)

```
GET https://image.pollinations.ai/prompt/<URL-encoded prompt>?width=1024&height=1024&nologo=true&seed=<int>
```

- Returns raw JPEG bytes, ~10–30s. Validate size > ~5KB (error pages are tiny).
- `seed` variation for regen-until-good; styles are prompt-side ('minimalist flat logo design', 'cute cartoon style', ...).
- Quality: good for logos, cartoons, patterns, posters; complex multi-subject scenes can distort. Verify with vision_analyze before delivering to a paying customer; offer regen with different seed/style.
- No free video generation on these providers; video orders need manual tooling.

## Auto-build against flaky LLMs

1. Plan call (JSON file list, max_tokens 600) → 2. per-file calls (JSON `{filename: content}`, max_tokens ≤3500) → 3. py_compile check → 4. zip → 5. deliver. Skip-and-continue on failed files; synthesize a minimal README if missing; default file set if the plan call fails. The order must reach a terminal state (delivered or admin-notified) — never hang in_progress forever.
