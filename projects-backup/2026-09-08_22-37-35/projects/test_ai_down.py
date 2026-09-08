import os, sys, json
os.chdir('/data/workspace/projects')
env = '/data/.hermes/.env'
if os.path.exists(env):
    for line in open(env):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import survey_bot as sb

# Simulate AI down: point base url to a dead host so the client errors out
os.environ['OPENAI_BASE_URL'] = 'http://127.0.0.1:1/v1'  # connection refused → ai_down
# force re-create client with bad url
import openai
sb.ai_client = openai.OpenAI(api_key='x', base_url='http://127.0.0.1:1/v1')

tests = [
    "به مشتری پیام بده و ازش تقدیر و تشکر کنه",
    "آمار فروش",
]
for t in tests:
    print(f"\n=== REQUEST: {t!r} ===")
    d = sb.ai_decide(t)
    print("DECISION:", json.dumps(d, ensure_ascii=False)[:200])
    # simulate what cmd_ai / fallback would show
    res = sb.ai_execute(None, d) if False else None
    print("  -> action:", d.get('action'))
    print("  -> would show ai_down message:", d.get('action') == 'ai_down')
