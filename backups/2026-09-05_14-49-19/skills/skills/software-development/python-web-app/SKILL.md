---
name: python-web-app
version: 1.0.0
description: "Build FastAPI web apps: auth, CRUD, DB, deploy, pitfalls."
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [fastapi, web, api, sqlalchemy, sqlite, jwt, auth, deployment, python]
    related_skills: [python-debugpy, systematic-debugging, github]
---

# Python Web App Development (FastAPI + SQLAlchemy)

## When to Use

Building or maintaining a Python web application — API server, dashboard, order system, admin panel, or any CRUD web app with authentication.

## Stack Reference

| Component | Package | Notes |
|---|---|---|
| Web framework | `fastapi` | Async-ready, auto-docs at `/docs` |
| Server | `uvicorn` | `python -m uvicorn app:app --host 0.0.0.0 --port 8000` |
| ORM | `sqlalchemy` | Use `declarative_base()` for models |
| DB (dev) | SQLite | stdlib `sqlite3` — **do NOT pip install sqlite3** |
| Auth (JWT) | `python-jose[cryptography]` | See Critical Pitfalls below |
| Password hashing | `passlib[bcrypt]` | Pin `bcrypt==4.0.1` — see pitfall |
| Forms | `python-multipart` | Required for OAuth2 form login |
| Email validation | `pydantic[email]` | `EmailStr` type |

## Requirements.txt Pattern

```txt
fastapi==0.109.0
uvicorn==0.27.0
sqlalchemy==2.0.25
pydantic==2.5.3
pydantic[email]==2.5.3
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6
httpx==0.26.0
python-dotenv==1.0.0
jinja2==3.1.3
aiofiles==23.2.1
```

**Never include `sqlite3`** — it's part of Python's standard library.

## Critical Pitfalls

### 1. JWT `sub` claim must be a string (python-jose ≥3.0)

**Wrong:** `create_access_token(data={"sub": user.id})` — `user.id` is an int.
**Right:** `create_access_token(data={"sub": str(user.id)})`

Then when decoding, cast back: `db.query(User).filter(User.id == int(payload.get("sub", 0))).first()`

`python-jose` 3.x raises `JWTClaimsError: Subject must be a string` if `sub` is an integer. This causes silent auth failures (token created but decode returns `None`).

### 2. passlib + bcrypt version incompatibility

Newer `bcrypt` (≥4.1) removed `bcrypt.__about__.__version__` which passlib depends on. Fix:

```bash
pip install 'bcrypt==4.0.1'
```

Symptom: `AttributeError: module 'bcrypt' has no attribute '__about__'` at startup.

### 3. JSON strings in SQLite need manual pydantic deserialization

SQLAlchemy stores `Column(Text)` as raw strings. When a pydantic model has `requirements: Optional[dict]`, returning the ORM object directly fails:

```
ResponseValidationError: Input should be a valid dictionary
```

**Fix — manual pre-processing in endpoint:**
```python
def get_order_detail(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    d = {c.name: getattr(order, c.name) for c in order.__table__.columns}
    if isinstance(d.get("requirements"), str):
        try: d["requirements"] = json.loads(d["requirements"])
        except: d["requirements"] = None
    return d  # Return dict, not ORM object
```

### 4. Admin endpoints: JSON body vs query params

FastAPI treats `def endpoint(param: SomeEnum)` as a query parameter, but the frontend sends JSON body. Use explicit Pydantic models:

```python
# Wrong — reads from query string
def admin_update(order_id: int, new_status: OrderStatus):

# Right — reads from JSON body
class StatusUpdate(BaseModel):
    new_status: OrderStatus

def admin_update(order_id: int, body: StatusUpdate):
```

### 5. Static file mount conflicts with API routes

Mounting `/admin` for static files conflicts with `/api/admin` routes because FastAPI gives the mount priority over API routes.

**Wrong:** `app.mount("/admin", StaticFiles(directory="admin"), name="admin")`
**Right:** `app.mount("/static/admin", StaticFiles(directory="admin"), name="admin")`

### 6. Frontend must actually call the API

A common mistake is building a frontend that simulates order flow client-side without API calls. The frontend must:
- Auto-register/login users via `POST /api/auth/register`
- Create orders via `POST /api/orders`
- Store JWT in `localStorage`, include `Authorization: Bearer` header

### 7. Don't delete DB while server is running

Deleting `orders.db` while uvicorn is running causes `sqlite3.OperationalError: attempt to write a readonly database`. Always stop the server first.

### 8. Pydantic datetime serialization in dict responses

Returning `datetime` objects directly in dict/list responses causes `TypeError: Object of type datetime is not JSON serializable`. Always convert:

```python
# Wrong — crashes with 500
return [{"created_at": msg.created_at} for msg in messages]

# Right
return [{"created_at": msg.created_at.isoformat() if msg.created_at else None} for msg in messages]
```

This only happens when returning raw dicts. Pydantic `response_model` with `from_attributes = True` handles it automatically.

### 9. ASGI module name: the file with `app = FastAPI(...)` is the entry point

`uvicorn main:app` only works if `main.py` defines `app = FastAPI(...)`. If the FastAPI instance lives in a different file (e.g. `api.py`), use `api:app` instead. Check which file contains `app = FastAPI(` before starting uvicorn.

### 9. Port conflicts: kill old process before restart

Starting a new uvicorn on the same port fails with `Address already in use`. Fix:

```bash
fuser -k 8000/tcp 2>/dev/null
sleep 2
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

### 10. VPS Environment Quirks

- **`ps` may be missing** — use `pgrep -f <pattern>` or read `/proc/*/cmdline`
- **All inbound ports blocked** — only Cloudflare Tunnel / ngrok / Tailscale work for external access
- **Background `&` doesn't persist** in terminal tool — use `terminal(background=true)` then `process_manage(action='poll')` for output
- **Cloudflare quick tunnel URLs are ephemeral** — each restart = new subdomain. For stable URLs, use named tunnels with a custom domain
- **Long-running terminal commands hang** — use `execute_code` with `subprocess` for commands with timeouts, or `terminal(background=true)` for servers
- **Beware Python scripts with heredocs in shell commands** — `cat <<'EOF'` blocks containing file redirections (`> file`) can corrupt shell parsing and append to wrong files. Use `write_file` tool instead.

## Serving Static Files (FastAPI)

```python
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="frontend"), name="static")
app.mount("/static/admin", StaticFiles(directory="admin"), name="admin")
```

## Deployment: Cloudflare Tunnel

When VPS firewall blocks all ports, use Cloudflare Quick Tunnel:

```bash
curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared
cloudflared tunnel --url http://localhost:8000
```

Outputs a temporary `https://xxx.trycloudflare.com` URL. No account needed.

⚠️ **Rate Limit Warning**: Quick Tunnels have strict rate limits (429 after ~20 rapid requests). See `references/cloudflare-tunnel-rate-limits.md` for mitigation.

**Production**: Use named tunnels with a Cloudflare account + custom domain — no rate limits, stable URL.

## Testing Pattern

Use `fastapi.testclient.TestClient` for in-process tests (no server needed):

```python
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)

r = client.post("/api/auth/register", json={"email": "test@example.com", "password": "123456"})
token = r.json()["access_token"]

r = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
assert r.status_code == 200
```

## Project Structure

```
project/
├── backend/
│   ├── main.py          # DB models, auth, config
│   ├── api.py           # API endpoints, FastAPI app
│   ├── requirements.txt
│   └── app.db           # SQLite (auto-created)
├── frontend/
│   └── index.html       # Customer-facing UI
├── admin/
│   └── index.html       # Admin panel
└── README.md
```