import os, sys, json
os.chdir('/data/workspace/projects')
# load env
env = '/data/.hermes/.env'
if os.path.exists(env):
    for line in open(env):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import survey_bot as sb

tests = [
    "به مشتری پیام بده و ازش تقدیر و تشکر کنه",
    "به مشتری سفارش 26 بگو ممنون از اعتمادت",
    "از مشتری سفارش 26 تشکر کن",
]
for t in tests:
    print(f"\n=== REQUEST: {t!r} ===")
    d = sb.ai_decide(t)
    print("DECISION:", json.dumps(d, ensure_ascii=False))
    # also show what ai_execute WOULD say for send_customer path
    if (d.get('action') or '').lower() == 'send_customer':
        print("  -> would queue message for order", d.get('args', {}).get('order_id'))
    else:
        print("  -> NOT send_customer -> no message queued")
