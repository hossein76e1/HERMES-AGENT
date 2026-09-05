from fastapi import FastAPI, Depends, HTTPException, status, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import List, Optional
import json
from datetime import datetime

from main import (
    init_db, get_db, SessionLocal, User, Admin, Order, Payment, Conversation, OrderMessage,
    ProjectType, OrderStatus, PaymentMethod, PaymentStatus,
    pwd_context, create_access_token, decode_token, verify_password, get_password_hash,
    generate_order_number, calculate_price,
    UserCreate, UserLogin, Token, OrderCreate, OrderResponse, OrderDetail,
    PaymentCreate, AdminLogin, MessageCreate,
    BaseModel, User, Admin, Order, Payment, Conversation, OrderMessage
)

app = FastAPI(title="Order System API", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
import os
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend")
admin_path = os.path.join(os.path.dirname(__file__), "..", "admin")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")
if os.path.exists(admin_path):
    app.mount("/admin", StaticFiles(directory=admin_path), name="admin")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# Initialize DB on startup
@app.on_event("startup")
async def startup():
    init_db()

# Auth helpers
async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == int(payload.get("sub", 0))).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def get_current_admin(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = decode_token(token)
    if not payload or not payload.get("is_admin"):
        raise HTTPException(status_code=401, detail="Admin access required")
    admin = db.query(Admin).filter(Admin.id == int(payload.get("sub", 0))).first()
    if not admin:
        raise HTTPException(status_code=401, detail="Admin not found")
    return admin

# ============ AUTH ROUTES ============
@app.post("/api/auth/register", response_model=Token)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed = get_password_hash(user_data.password)
    user = User(
        email=user_data.email,
        phone=user_data.phone,
        full_name=user_data.full_name,
        hashed_password=hashed
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "phone": current_user.phone,
        "full_name": current_user.full_name,
        "is_admin": current_user.is_admin
    }

# Admin auth
@app.post("/api/admin/login", response_model=Token)
def admin_login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.username == form_data.username).first()
    if not admin or not verify_password(form_data.password, admin.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    access_token = create_access_token(data={"sub": str(admin.id), "is_admin": True})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/admin/me")
def admin_me(current_admin: Admin = Depends(get_current_admin)):
    return {"id": current_admin.id, "username": current_admin.username, "full_name": current_admin.full_name}

# ============ ORDER ROUTES ============
@app.post("/api/orders", response_model=OrderResponse)
def create_order(order_data: OrderCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Calculate price
    base_price = calculate_price(order_data.project_type, order_data.requirements or {})
    
    order = Order(
        order_number=generate_order_number(),
        user_id=current_user.id,
        project_type=order_data.project_type,
        project_title=order_data.project_title,
        description=order_data.description,
        requirements=json.dumps(order_data.requirements or {}),
        base_price=calculate_price(ProjectType.CUSTOM, {}),  # base without extras
        final_price=calculate_price(order_data.project_type, order_data.requirements or {}),
        status=OrderStatus.PENDING,
        payment_status=PaymentStatus.PENDING,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    
    # Create conversation for this order
    conv = Conversation(
        user_id=current_user.id,
        order_id=order.id,
        current_step="welcome",
        collected_data=json.dumps({})
    )
    db.add(conv)
    db.commit()
    
    return order

@app.get("/api/orders", response_model=List[OrderResponse])
def get_my_orders(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.user_id == current_user.id).order_by(Order.created_at.desc()).all()
    result = []
    for o in orders:
        d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
        if isinstance(d.get("requirements"), str):
            try: d["requirements"] = json.loads(d["requirements"])
            except: d["requirements"] = None
        result.append(d)
    return result

@app.get("/api/orders/{order_id}", response_model=OrderDetail)
def get_order(order_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderDetail.from_orm_model(order)

@app.get("/api/orders/{order_id}/messages")
def get_order_messages(order_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    messages = db.query(OrderMessage).filter(OrderMessage.order_id == order_id).order_by(OrderMessage.created_at).all()
    return [{"id": m.id, "sender_type": m.sender_type, "content": m.content, "message_type": m.message_type, "created_at": m.created_at.isoformat() if m.created_at else None} for m in messages]

@app.post("/api/orders/{order_id}/messages")
def send_message(order_id: int, msg: MessageCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    msg_obj = OrderMessage(
        order_id=order_id,
        sender_type="user",
        sender_id=current_user.id,
        content=msg.content,
        message_type=msg.message_type
    )
    db.add(msg_obj)
    db.commit()
    return {"success": True}

# Payment
@app.post("/api/orders/{order_id}/payment")
def create_payment(order_id: int, payment_data: PaymentCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == current_user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.status != OrderStatus.QUOTED:
        raise HTTPException(status_code=400, detail="Order must be quoted first")
    
    # TODO: Integrate with Zarinpal for online payments
    # For now, create pending payment
    payment = Payment(
        order_id=order.id,
        amount=order.final_price,
        method=payment_data.method,
        status=PaymentStatus.PENDING,
        transaction_id=generate_order_number().replace("ORD", "PAY")
    )
    db.add(payment)
    order.payment_method = payment_data.method
    order.payment_status = PaymentStatus.PENDING
    db.commit()
    
    return {"payment_id": payment.id, "amount": order.final_price, "method": payment_data.method}

# WebSocket for real-time chat
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, order_id: int):
        await websocket.accept()
        if order_id not in self.active_connections:
            self.active_connections[order_id] = []
        self.active_connections[order_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, order_id: int):
        if order_id in self.active_connections:
            self.active_connections[order_id].remove(websocket)
    
    async def broadcast(self, order_id: int, message: dict):
        if order_id in self.active_connections:
            for conn in self.active_connections[order_id]:
                try:
                    await conn.send_json(message)
                except:
                    pass

manager = ConnectionManager()

@app.websocket("/ws/orders/{order_id}")
async def websocket_endpoint(websocket: WebSocket, order_id: int):
    await manager.connect(websocket, order_id)
    try:
        while True:
            data = await websocket.receive_json()
            # Echo back for now
            await manager.broadcast(order_id, data)
    except WebSocketDisconnect:
        manager.disconnect(websocket, order_id)

# ============ ADMIN ROUTES ============
@app.get("/api/admin/orders")
def admin_get_orders(status: Optional[str] = None, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    from sqlalchemy.orm import joinedload
    query = db.query(Order)
    if status:
        query = query.filter(Order.status == OrderStatus(status))
    orders = query.order_by(Order.created_at.desc()).all()
    result = []
    for o in orders:
        d = {c.name: getattr(o, c.name) for c in o.__table__.columns}
        if isinstance(d.get("requirements"), str):
            try: d["requirements"] = json.loads(d["requirements"])
            except: d["requirements"] = None
        d["user"] = {"id": o.user.id, "email": o.user.email, "full_name": o.user.full_name} if o.user else None
        result.append(d)
    return result

@app.get("/api/admin/orders/{order_id}", response_model=OrderDetail)
def admin_get_order(order_id: int, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return OrderDetail.from_orm_model(order)

class StatusUpdate(BaseModel):
    new_status: OrderStatus

@app.patch("/api/admin/orders/{order_id}/status")
def admin_update_status(order_id: int, body: StatusUpdate, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):

    new_status = body.new_status
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    old_status = order.status
    order.status = new_status
    
    # Update timestamps
    if new_status == OrderStatus.QUOTED:
        order.quoted_at = datetime.utcnow()
    elif new_status == OrderStatus.PAID:
        order.paid_at = datetime.utcnow()
    elif new_status == OrderStatus.IN_PROGRESS:
        order.started_at = datetime.utcnow()
    elif new_status == OrderStatus.DELIVERED:
        order.delivered_at = datetime.utcnow()
    
    db.commit()
    
    # Add system message
    msg = OrderMessage(
        order_id=order.id,
        sender_type="system",
        content=f"وضعیت سفارش از {old_status.value} به {new_status.value} تغییر یافت",
        message_type="system"
    )
    db.add(msg)
    db.commit()
    
    return {"success": True, "new_status": new_status.value}

class QuoteRequest(BaseModel):
    final_price: float
    notes: str = ""

@app.post("/api/admin/orders/{order_id}/quote")
def admin_send_quote(order_id: int, body: QuoteRequest, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order.final_price = body.final_price
    order.status = OrderStatus.QUOTED
    order.quoted_at = datetime.utcnow()
    db.commit()
    
    msg = OrderMessage(
        order_id=order.id,
        sender_type="admin",
        content=f"قیمت نهایی پروژه: {body.final_price:,.0f} تومان\n{body.notes}",
        message_type="quote"
    )
    db.add(msg)
    db.commit()
    
    return {"success": True, "final_price": body.final_price}

@app.post("/api/admin/orders/{order_id}/approve-delivery")
def admin_approve_delivery(order_id: int, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.status != OrderStatus.READY:
        raise HTTPException(status_code=400, detail="Order must be ready for delivery")
    
    order.approved_by_admin = True
    order.approved_at = datetime.utcnow()
    order.status = OrderStatus.DELIVERED
    order.delivered_at = datetime.utcnow()
    db.commit()
    
    return {"success": True}

@app.get("/api/admin/orders/{order_id}/messages")
def admin_get_messages(order_id: int, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    messages = db.query(OrderMessage).filter(OrderMessage.order_id == order_id).order_by(OrderMessage.created_at).all()
    return [{"id": m.id, "sender_type": m.sender_type, "content": m.content, "message_type": m.message_type, "created_at": m.created_at.isoformat() if m.created_at else None} for m in messages]

@app.post("/api/admin/orders/{order_id}/messages")
def admin_send_message(order_id: int, msg: MessageCreate, db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    msg_obj = OrderMessage(
        order_id=order_id,
        sender_type="admin",
        sender_id=current_admin.id,
        content=msg.content,
        message_type=msg.message_type
    )
    db.add(msg_obj)
    db.commit()
    return {"success": True}

@app.get("/api/admin/stats")
def admin_stats(db: Session = Depends(get_db), current_admin: Admin = Depends(get_current_admin)):
    total = db.query(Order).count()
    pending = db.query(Order).filter(Order.status == OrderStatus.PENDING).count()
    in_progress = db.query(Order).filter(Order.status == OrderStatus.IN_PROGRESS).count()
    completed = db.query(Order).filter(Order.status == OrderStatus.DELIVERED).count()
    revenue = db.query(Order).filter(Order.payment_status == PaymentStatus.PAID).all()
    total_revenue = sum(o.final_price for o in revenue)
    
    return {
        "total_orders": total,
        "pending": pending,
        "in_progress": in_progress,
        "completed": completed,
        "total_revenue": total_revenue
    }

# ============ CONVERSATION / CHAT BOT ============
@app.post("/api/chat/start")
def start_conversation(project_type: Optional[ProjectType] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    conv = Conversation(
        user_id=current_user.id,
        current_step="welcome",
        collected_data=json.dumps({})
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    
    return {
        "conversation_id": conv.id,
        "message": "سلام! 👋 به سیستم سفارش‌گذاری خوش اومدی.\n\nمن اینجا هستم تا پروژه‌ی رویات رو دقیق بفهمم و بهترین پیشنهاد رو بدم.\n\nاول بگو: **چه نوع پروژه‌ای مد نظرته؟**",
        "options": [p.value for p in ProjectType],
        "step": "project_type"
    }

@app.post("/api/chat/{conv_id}/respond")
def chat_respond(conv_id: int, response: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == current_user.id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    data = json.loads(conv.collected_data or "{}")
    step = conv.current_step
    
    # Process response based on current step
    next_step, reply, options = process_chat_step(step, response, data)
    
    conv.current_step = next_step
    conv.collected_data = json.dumps(data)
    conv.updated_at = datetime.utcnow()
    
    if next_step == "complete":
        conv.is_complete = True
        conv.completed_at = datetime.utcnow()
        # Create order from collected data
        create_order_from_conversation(conv, db)
    
    db.commit()
    
    return {"reply": reply, "options": options, "step": next_step, "is_complete": next_step == "complete"}

def process_chat_step(step: str, response: str, data: dict) -> tuple:
    """Process chat step and return next step, reply, and options"""
    
    steps = [
        "welcome", "project_type", "project_title", "description", 
        "features", "complexity", "timeline", "budget", 
        "contact_email", "contact_phone", "complete"
    ]
    
    if step == "welcome":
        data["project_type"] = response
        return "project_title", "عالیه! 🎯\n\n**اسم پروژه رو چیه می‌خوای بزاری؟**\n(مثلاً: ربات پشتیبانی فروشگاه، اسکرپر قیمت دیجی‌کالا، وب‌سایت شرکتی)", None
    
    elif step == "project_title":
        data["project_title"] = response
        return "description", "عالی! 📝\n\n**توضیح کوتاه بدید که این پروژه دقیقاً چه کاری باید انجام بده؟**\n(مثلا: رباتی که خرید رو اتومات کنه، یا اسکریپتی که قیمت‌ها رو هر روز چک کنه)", None
    
    elif step == "description":
        data["description"] = response
        return "features", "بسیار خوب! ⚡\n\n**چه ویژگی‌هایی لازم داری؟** (هر خط یک ویژگی)\nمثال:\n- پاسخ خودکار ۲۴ ساعته\n- دکمه‌های شیشه‌ای\n- اتصال به درگاه پرداخت\n- پنل ادمین", None
    
    elif step == "features":
        data["features"] = [f.strip("- ").strip() for f in response.split("\n") if f.strip()]
        return "complexity", "عالیه! 🎯\n\n**پیچیدگی پروژه چقدر هست؟**", ["simple (ساده)", "medium (متوسط)", "complex (پیچیده)", "enterprise (بزرگ)"]
    
    elif step == "complexity":
        data["complexity"] = response.split(" ")[0]
        return "timeline", "بسیار عالی! ⏱\n\n**مدت زمان تحویل چقدر می‌خواد باشه؟**", ["normal (معمولی)", "urgent (فوری)", "express (بسیار فوری)"]
    
    elif step == "timeline":
        data["timeline"] = response.split(" ")[0]
        return "budget", "بسیار عالی! 💰\n\n**بازت تقریبی چقدره؟**\n(این فقط برای درک محدودیت‌هاست، قیمت نهایی بر اساس پیچیدگی محاسبه میشه)", ["کمتر از ۵ میلیون", "۵ تا ۱۵ میلیون", "۱۵ تا ۳۰ میلیون", "۳۰ میلیون به بالا", "مهم نیست"]
    
    elif step == "budget":
        data["budget"] = response
        return "contact_email", "تقریبا تموم شد! 📧\n\n**ایمیلت رو بنویس تا پیش‌فاکتور و آپدیت‌ها برات بیاد:**", None
    
    elif step == "contact_email":
        data["email"] = response
        return "contact_phone", "بسیار عالی! 📱\n\n**شماره تماس (اختیاری) - برای هماهنگی سریع‌تر:**", ["ندارم / نمی‌خوام بدم", "09xxxxxxxxx"]
    
    elif step == "contact_phone":
        data["phone"] = response if "ندارم" not in response else None
        return "complete", "🎉 **سفارش ثبت شد!**\n\nتیم ما جزئیات رو بررسی می‌کنه و در کمتر از ۲ ساعت پیش‌فاکتور برات ارسال میشه.\n\nمی‌تونی از همین چت پیگیری کنی.", None
    
    return "complete", "مرسی! سفارش ثبت شد ✅", None

def create_order_from_conversation(conv: Conversation, db: Session):
    data = json.loads(conv.collected_data or "{}")
    
    # Map project type
    pt_map = {
        "تلگرام": ProjectType.TELEGRAM_BOT,
        "واتساپ": ProjectType.WHATSAPP_BOT,
        "اسکرپر": ProjectType.DATA_SCRAPING,
        "داده": ProjectType.DATA_SCRAPING,
        "وب‌سایت": ProjectType.WEBSITE,
        "اتوماسیون": ProjectType.AUTOMATION,
        "محتوا": ProjectType.CONTENT,
        "ایمیل": ProjectType.EMAIL_AUTOMATION,
        "قیمت": ProjectType.PRICE_COMPARISON,
        "داشبورد": ProjectType.DASHBOARD,
    }
    
    pt = ProjectType.CUSTOM
    for k, v in pt_map.items():
        if k in data.get("project_type", ""):
            pt = v
            break
    
    requirements = {
        "features": data.get("features", []),
        "complexity": data.get("complexity", "medium"),
        "timeline": data.get("timeline", "normal"),
    }
    
    price = calculate_price(pt, requirements)
    
    order = Order(
        order_number=generate_order_number(),
        user_id=conv.user_id,
        project_type=pt,
        project_title=data.get("project_title", "سفارش چت"),
        description=data.get("description"),
        requirements=json.dumps(requirements),
        base_price=price,
        final_price=price,
        status=OrderStatus.PENDING,
        payment_status=PaymentStatus.PENDING,
    )
    db.add(order)
    db.flush()
    
    conv.order_id = order.id
    conv.is_complete = True
    conv.completed_at = datetime.utcnow()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)