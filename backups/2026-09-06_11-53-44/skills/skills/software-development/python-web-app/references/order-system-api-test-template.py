#!/usr/bin/env python3
"""Full API test suite template for FastAPI projects.
Unique emails per run via uuid to avoid 'Email already registered' on re-runs."""
import httpx
import uuid

BASE = "http://localhost:8000"
results = []
client = httpx.Client(base_url=BASE, timeout=10)
test_email = f"test_{uuid.uuid4().hex[:8]}@test.com"

def test(name, func):
    try:
        result = func()
        results.append((name, "✅", result))
    except Exception as e:
        results.append((name, "❌", str(e)[:120]))

# Health
test("GET /docs", lambda: "Swagger OK" if client.get("/docs").status_code == 200 else (_ for _ in ()).throw(Exception("fail")))

# Register/Login
def t_register():
    r = client.post("/api/auth/register", json={"email": test_email, "password": "test1234", "full_name": "Test"})
    assert r.status_code == 200, f"{r.status_code}: {r.text}"
    return "Token OK"
test("POST /api/auth/register", t_register)

def t_login():
    r = client.post("/api/auth/login", data={"username": test_email, "password": "test1234"})
    assert r.status_code == 200
    return "User token OK"
test("POST /api/auth/login", t_login)

# Get tokens for auth headers
token = client.post("/api/auth/login", data={"username": test_email, "password": "test1234"}).json()["access_token"]
auth = {"Authorization": f"Bearer {token}"}

# CRUD tests (customize per project)
test("GET /api/auth/me", lambda: f"User: {client.get('/api/auth/me', headers=auth).json()['email']}")

# Print results
passed = sum(1 for _, s, _ in results if s == "✅")
print(f"\n{'='*60}")
print(f"📋 Test Results — {passed}/{len(results)} passed")
print(f"{'='*60}")
for name, status, detail in results:
    print(f"  {status} {name}: {detail}")
print(f"{'='*60}")
