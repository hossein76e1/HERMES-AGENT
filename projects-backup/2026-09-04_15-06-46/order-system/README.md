# 🤖 سیستم سفارش هوشمند

سیستم کامل دریافت و مدیریت سفارشات با هوش مصنوعی

## ✨ امکانات

### مشتری:
- 🔐 ثبت‌نام و ورود
- 💬 چت هوشمند برای ثبت سفارش
- 📋 مشاهده وضعیت سفارش
- 💰 پرداخت آنلاین (زرین‌پال) + کارت به کارت
- 📧 دریافت پیش‌فاکتور

### ادمین:
- 📊 داشبورد مدیریت با آمار لحظه‌ای
- 💰 ارسال پیش‌فاکتور
- 🔄 مدیریت وضعیت سفارشات
- ✅ تأیید تحویل
- 💬 چت با مشتری

## 🚀 نصب و اجرا

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn api:app --host 0.0.0.0 --port 8000
```

## 🌐 آدرس‌ها

- 🛒 فروشگاه مشتری: http://localhost:8000/static/index.html
- 📊 پنل ادمین: http://localhost:8000/admin/index.html
- 📖 مستندات API: http://localhost:8000/docs

## 🔑 پیش‌فرض ادمین

- نام کاربری: `admin`
- رمز عبور: `admin123`

## 📦 تکنولوژی‌ها

- **Backend:** FastAPI + SQLAlchemy + SQLite
- **Auth:** JWT (python-jose) + bcrypt
- **Frontend:** HTML/CSS/JS (RTL Farsi)
- **UI:** Dark theme مدرن

## 📋 API Endpoints

### Auth
- `POST /api/auth/register` - ثبت‌نام
- `POST /api/auth/login` - ورود کاربر
- `GET /api/auth/me` - اطلاعات کاربر

### Orders
- `POST /api/orders` - ایجاد سفارش
- `GET /api/orders` - لیست سفارشات
- `GET /api/orders/{id}` - جزئیات سفارش

### Admin
- `POST /api/admin/login` - ورود ادمین
- `GET /api/admin/stats` - آمار
- `GET /api/admin/orders` - لیست سفارشات
- `PATCH /api/admin/orders/{id}/status` - تغییر وضعیت
- `POST /api/admin/orders/{id}/quote` - ارسال پیش‌فاکتور
- `POST /api/admin/orders/{id}/approve-delivery` - تأیید تحویل

### Chat
- `POST /api/chat/start` - شروع چت
- `POST /api/chat/{id}/respond` - پاسخ به چت
