# Cloudflare Quick Tunnel Rate Limits

## Issue

When creating multiple Cloudflare Quick Tunnels in rapid succession, you hit a **429 Too Many Requests** error:

```
ERR Error unmarshaling QuickTunnel response: error code: 1015
 error="invalid character 'e' looking for beginning of value" status_code="429 Too Many Requests"
failed to unmarshal quick Tunnel: invalid character 'e' looking for beginning of value
```

## Root Cause

Cloudflare's free Quick Tunnels have strict rate limits on tunnel creation. Each `cloudflared tunnel --url` request counts against the limit.

## Mitigation

1. **Wait between tunnel creations** — at least 30-60 seconds between attempts
2. **Keep a single tunnel running** — don't kill and restart; reuse the existing process
3. **Use named tunnels for production** — create a Cloudflare account, add a domain, and use `cloudflared tunnel run <tunnel-name>` (no rate limits)
4. **Check existing processes first** — use `ps aux | grep cloudflared` or check `/proc/*/cmdline` before starting new ones

## VPS-Specific Notes

- `ps` command may not be available on minimal VPS images — use `/proc/*/cmdline` or `pgrep` instead
- Firewall typically blocks all inbound ports (80, 443, 8000, etc.) — Cloudflare Tunnel is the only way to expose services
- Quick tunnel URLs change on every restart (e.g., `mainly-kernel-vii-basically.trycloudflare.com` → new subdomain each time)
- Background `&` in terminal doesn't persist — use `process_manage` with `background=true` and `notify_on_complete=true`

## Recovery After Rate Limit

```bash
# Kill all existing cloudflared processes
pkill -f cloudflared
# Or manually via /proc
for pid in /proc/*/cmdline; do cat $pid 2>/dev/null | grep -q cloudflared && kill $(basename $(dirname $pid)); done

# Wait 60+ seconds
sleep 60

# Start single tunnel
cloudflared tunnel --url http://localhost:8000
```

## Alternative: ngrok / localtunnel

If Cloudflare rate limits are persistent:
```bash
# ngrok (requires auth token)
ngrok http 8000

# localtunnel (no auth, but less reliable)
npx localtunnel --port 8000
```