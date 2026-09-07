#!/usr/bin/env python3
"""Full API test suite for Order System — v2 with unique emails"""
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

# 1. Health
test("GET /docs", lambda: "Swagger OK" if client.get("/docs").status_code == 200 else (_ for _ in ()).throw(Exception("fail")))

# 2. Register
def t_register():
    r = client.post("/api/auth/register", json={"email": test_email, "password": "test1234", "full_name": "API Tester"})
    assert r.status_code == 200, f"{r.status_code}: {r.text}"
    return "Token OK"
test("POST /api/auth/register", t_register)

# 3. Login user
def t_login_user():
    r = client.post("/api/auth/login", data={"username": test_email, "password": "test1234"})
    assert r.status_code == 200
    return "User token OK"
test("POST /api/auth/login (user)", t_login_user)

# 4. Login admin
def t_login_admin():
    r = client.post("/api/admin/login", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    return "Admin token OK"
test("POST /api/admin/login", t_login_admin)

# Get tokens
ut = client.post("/api/auth/login", data={"username": test_email, "password": "test1234"}).json()["access_token"]
at = client.post("/api/admin/login", data={"username": "admin", "password": "admin123"}).json()["access_token"]
uh = {"Authorization": f"Bearer {ut}"}
ah = {"Authorization": f"Bearer {at}"}

# 5. User me
test("GET /api/auth/me", lambda: f"User: {client.get('/api/auth/me', headers=uh).json()['email']}")

# 6. Admin me
test("GET /api/admin/me", lambda: f"Admin: {client.get('/api/admin/me', headers=ah).json()['username']}")

# 7. Create order
def t_create():
    r = client.post("/api/orders", json={
        "project_type": "telegram_bot", "project_title": "ربات فروشگاه",
        "description": "ربات تلگرامی فروش", "requirements": {"complexity": "medium", "features": ["پرداخت"]}
    }, headers=uh)
    assert r.status_code == 200, f"{r.status_code}: {r.text}"
    d = r.json()
    return f"#{d['order_number']} — {d['final_price']:,.0f} تومان"
test("POST /api/orders (create)", t_create)

# 8. List orders
test("GET /api/orders", lambda: f"{len(client.get('/api/orders', headers=uh).json())} order(s)")

# 9. Order detail
def t_detail():
    oid = client.get("/api/orders", headers=uh).json()[0]["id"]
    r = client.get(f"/api/orders/{oid}", headers=uh)
    assert r.status_code == 200, f"{r.status_code}: {r.text}"
    return f"Order #{oid} detail OK"
test("GET /api/orders/{id}", t_detail)

# 10. Send message
def t_send_msg():
    oid = client.get("/api/orders", headers=uh).json()[0]["id"]
    r = client.post(f"/api/orders/{oid}/messages", json={"content": "پیگیری سفارش"}, headers=uh)
    assert r.status_code == 200, f"{r.status_code}: {r.text}"
    return "Message sent"
test("POST /api/orders/{id}/messages", t_send_msg)

# 11. Get messages
def t_get_msgs():
    oid = client.get("/api/orders", headers=uh).json()[0]["id"]
    r = client.get(f"/api/orders/{oid}/messages", headers=uh)
    assert r.status_code == 200
    return f"{len(r.json())} message(s)"
test("GET /api/orders/{id}/messages", t_get_msgs)

# 12. Admin list orders
test("GET /api/admin/orders", lambda: f"{len(client.get('/api/admin/orders', headers=ah).json())} orders")

# 13. Admin quote
def t_quote():
    oid = client.get("/api/orders", headers=uh).json()[0]["id"]
    r = client.post(f"/api/admin/orders/{oid}/quote", json={"final_price": 8000000, "notes": "قیمت نهایی"}, headers=ah)
    assert r.status_code == 200
    return "Quoted 8M"
test("POST /api/admin/orders/{id}/quote", t_quote)

# 14. Admin status
def t_status():
    oid = client.get("/api/orders", headers=uh).json()[0]["id"]
    r = client.patch(f"/api/admin/orders/{oid}/status", json={"new_status": "in_progress"}, headers=ah)
    assert r.status_code == 200
    return "→ in_progress"
test("PATCH /api/admin/orders/{id}/status", t_status)

# 15. Admin stats
def t_stats():
    r = client.get("/api/admin/stats", headers=ah)
    assert r.status_code == 200
    d = r.json()
    return f"Total:{d['total_orders']} Pending:{d['pending']} Revenue:{d['total_revenue']:,.0f}"
test("GET /api/admin/stats", t_stats)

# 16. Admin messages
def t_admin_msg():
    oid = client.get("/api/orders", headers=uh).json()[0]["id"]
    r = client.post(f"/api/admin/orders/{oid}/messages", json={"content": "در حال انجام"}, headers=ah)
    assert r.status_code == 200
    return "Admin msg sent"
test("POST /api/admin/orders/{id}/messages (admin)", t_admin_msg)

# 17. Chat start
def t_chat():
    r = client.post("/api/chat/start", headers=uh)
    assert r.status_code == 200
    d = r.json()
    return f"Conv #{d['conversation_id']}, step:{d['step']}"
test("POST /api/chat/start", t_chat)

# 18. Frontend
test("GET /static/index.html", lambda: "Frontend OK" if "سفارش پروژه" in client.get("/static/index.html").text else (_ for _ in ()).throw(Exception("missing")))

# 19. Admin panel
test("GET /admin/index.html", lambda: "Admin OK" if "پنل ادمین" in client.get("/admin/index.html").text else (_ for _ in ()).throw(Exception("missing")))

passed = sum(1 for _, s, _ in results if s == "✅")
print(f"\n{'='*60}")
print(f"📋 API Test Results — {passed}/{len(results)} passed")
print(f"{'='*60}")
for name, status, detail in results:
    print(f"  {status} {name}: {detail}")
print(f"{'='*60}")
