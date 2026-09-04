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

## Token Requirements

- Scope: `repo` (covers Pages API)
- No separate `pages` scope needed
- Store in GH_TOKEN env var

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

## Troubleshooting Checklist

- [ ] Repo is public
- [ ] Token has `repo` scope
- [ ] `docs/index.html` exists and committed
- [ ] Pages enabled via API (not just Settings UI)
- [ ] Build status shows "built"
- [ ] Live URL returns HTTP 200
- [ ] Content loads correctly