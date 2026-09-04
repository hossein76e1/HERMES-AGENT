# GitHub Pages Setup for Hermes Backup Repo

## Prerequisites

- Repo must be **public** (free plan)
- Token with `repo` scope
- `docs/` folder with `index.html`

## Enable via API

```bash
export GH_TOKEN="your_token_here"

# 1. Make repo public if private
curl -X PATCH -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  -d '{"private":false}' \
  https://api.github.com/repos/OWNER/REPO

# 2. Enable Pages with docs folder
curl -X POST -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  -d '{"source":{"branch":"main","path":"/docs"}}' \
  https://api.github.com/repos/OWNER/REPO/pages

# 3. Poll build status
curl -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/OWNER/REPO/pages/builds/latest

# Wait for status: "built"

# 4. Verify
curl -I https://USERNAME.github.io/REPO/
```

## Common Issues

| Error | Cause | Fix |
|-------|-------|-----|
| 422 "plan does not support" | Repo is private | Make public: `curl -X PATCH ... -d '{"private":false}'` |
| 401 Bad credentials | Token invalid/expired | Generate new token with `repo` scope |
| 422 Invalid input | Wrong JSON format | Use `{"source":{"branch":"main","path":"/docs"}}` not string |
| 404 Not Found | Pages not enabled yet | Run the POST command first |
| 404 on live URL | Build not finished | Poll builds/latest until status="built" |
| `gh api` 401 but `curl` works | gh auth token mismatch | Use curl directly with Bearer token, not gh api |
| Empty response from curl | Silent failure | Always capture and check full response body |
| Build stuck in "building" | Large site or queue | Wait 2-5 minutes, then re-poll |

## Token Requirements

- Scope: `repo` (covers Pages API)
- No separate `pages` scope needed
- Store in GH_TOKEN env var
- Token must not be expired (90 days default)
- If `gh auth status` says "Bad credentials" but curl works, the gh config token differs from GH_TOKEN env var

## Folder Structure

```
repo/
  docs/
    index.html          # Required
    assets/             # Optional
  ...other files...
```

## Verify Deployment

```bash
# Check build status
curl -s -H "Authorization: Bearer $GH_TOKEN" \
  https://api.github.com/repos/OWNER/REPO/pages/builds/latest | jq -r '.status'

# When status="built", check live
curl -I https://USERNAME.github.io/REPO/
# Should return HTTP 200
```

## Full Working Example (from session)

```bash
# Token setup
export GH_TOKEN="ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

# 1. Make repo public (if needed)
curl -s -X PATCH -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  -d '{"private":false}' \
  https://api.github.com/repos/hossein76e1/HERMES-AGENT

# 2. Enable Pages
curl -s -X POST -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  -d '{"source":{"branch":"main","path":"/docs"}}' \
  https://api.github.com/repos/hossein76e1/HERMES-AGENT/pages

# 3. Poll until built
for i in {1..30}; do
  status=$(curl -s -H "Authorization: Bearer $GH_TOKEN" \
    https://api.github.com/repos/hossein76e1/HERMES-AGENT/pages/builds/latest | jq -r '.status')
  echo "Build status: $status"
  [[ "$status" == "built" ]] && break
  sleep 10
done

# 4. Verify live
curl -I https://hossein76e1.github.io/HERMES-AGENT/
```

## Troubleshooting Checklist

- [ ] Repo is public
- [ ] Token has `repo` scope
- [ ] `docs/index.html` exists and committed
- [ ] Pages enabled via API (not just Settings UI)
- [ ] Build status shows "built"
- [ ] Live URL returns HTTP 200
- [ ] Content loads correctly