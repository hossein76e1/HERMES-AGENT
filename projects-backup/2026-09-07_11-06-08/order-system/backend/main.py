import os
import json
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from passlib.context import CryptContext
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from typing import List as PyList

# Config
DATABASE_URL = "sqlite:///./orders.db"
SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Database
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Enums
class ProjectType(str, Enum):
    TELEGRAM_BOT = "telegram_bot"
    WHATSAPP_BOT = "whatsapp_bot"
    DATA_SCRAPING = "data_scraping"
    WEBSITE = "website"
    AUTOMATION = "automation"
    CONTENT = "content_generation"
    EMAIL_AUTOMATION = "email_automation"
    PRICE_COMPARISON = "price_comparison"
    DASHBOARD = "dashboard"
    CUSTOM = "custom"

class OrderStatus(str, Enum):
    PENDING = "pending"           # در انتظار بررسی
    QUOTED = "quoted"             # قیمت ارسال شده
    PAID = "paid"                 # پرداخت شده
    IN_PROGRESS = "in_progress"   # در حال انجام
    READY = "ready"               # آماده تحویل
    DELIVERED = "delivered"       # تحویل داده شده
    CANCELLED = "cancelled"       # لغو شده

class PaymentMethod(str, Enum):
    ONLINE = "online"     # زرین‌پال
    CARD = "card"         # کارت به کارت
    CRYPTO = "crypto"     # ارز دیجیتال

class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"

# Models
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    orders = relationship("Order", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")

class Admin(Base):
    __tablename__ = "admins"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_super = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, index=True, nullable=False)
    
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="orders")
    
    # Project details
    project_type = Column(SQLEnum(ProjectType), nullable=False)
    project_title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    requirements = Column(Text, nullable=True)  # JSON string
    
    # Pricing
    base_price = Column(Float, default=0)
    final_price = Column(Float, default=0)
    currency = Column(String, default="IRR")
    
    # Status
    status = Column(SQLEnum(OrderStatus), default=OrderStatus.PENDING)
    payment_status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING)
    payment_method = Column(SQLEnum(PaymentMethod), nullable=True)
    payment_id = Column(String, nullable=True)  # Transaction ID
    
    # Delivery
    deliverable_url = Column(String, nullable=True)
    deliverable_files = Column(Text, nullable=True)  # JSON
    delivery_notes = Column(Text, nullable=True)
    approved_by_admin = Column(Boolean, default=False)
    approved_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    quoted_at = Column(DateTime, nullable=True)
    paid_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    
    payments = relationship("Payment", back_populates="order")
    messages = relationship("OrderMessage", back_populates="order")

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    order = relationship("Order", back_populates="payments")
    
    amount = Column(Float, nullable=False)
    currency = Column(String, default="IRR")
    method = Column(SQLEnum(PaymentMethod), nullable=False)
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING)
    transaction_id = Column(String, nullable=True, unique=True)
    gateway_response = Column(Text, nullable=True)  # JSON
    
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="conversations")
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    
    session_data = Column(Text, nullable=True)  # JSON for chat state
    current_step = Column(String, default="welcome")
    collected_data = Column(Text, nullable=True)  # JSON
    is_complete = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

class OrderMessage(Base):
    __tablename__ = "order_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    order = relationship("Order", back_populates="messages")
    
    sender_type = Column(String, nullable=False)  # user, admin, system
    sender_id = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    message_type = Column(String, default="text")  # text, file, system
    
    created_at = Column(DateTime, default=datetime.utcnow)

# Create tables
def init_db():
    Base.metadata.create_all(bind=engine)
    
    # Create default admin
    db = SessionLocal()
    try:
        admin = db.query(Admin).filter(Admin.username == "admin").first()
        if not admin:
            admin = Admin(
                username="admin",
                hashed_password=pwd_context.hash("admin123"),
                full_name="System Admin",
                is_super=True
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()

# Auth functions
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# Pydantic models
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    phone: Optional[str] = None
    full_name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class OrderCreate(BaseModel):
    project_type: ProjectType
    project_title: str = Field(min_length=3, max_length=200)
    description: Optional[str] = None
    requirements: Optional[dict] = None

class OrderResponse(BaseModel):
    id: int
    order_number: str
    project_type: ProjectType
    project_title: str
    final_price: float
    currency: str
    status: OrderStatus
    payment_status: PaymentStatus
    created_at: datetime
    
    class Config:
        from_attributes = True

class OrderDetail(BaseModel):
    id: int
    order_number: str
    project_type: ProjectType
    project_title: str
    description: Optional[str]
    requirements: Optional[dict]
    base_price: float
    final_price: float
    currency: str
    status: OrderStatus
    payment_status: PaymentStatus
    payment_method: Optional[PaymentMethod]
    deliverable_url: Optional[str]
    delivery_notes: Optional[str]
    approved_by_admin: bool
    created_at: datetime
    quoted_at: Optional[datetime]
    paid_at: Optional[datetime]
    delivered_at: Optional[datetime]
    
    @classmethod
    def from_orm_model(cls, obj):
        data = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
        if isinstance(data.get("requirements"), str):
            try:
                data["requirements"] = json.loads(data["requirements"])
            except (json.JSONDecodeError, TypeError):
                data["requirements"] = None
        if isinstance(data.get("deliverable_files"), str):
            try:
                data["deliverable_files"] = json.loads(data["deliverable_files"])
            except (json.JSONDecodeError, TypeError):
                data["deliverable_files"] = None
        return cls(**data)
    
    class Config:
        from_attributes = True

class PaymentCreate(BaseModel):
    order_id: int
    method: PaymentMethod

class AdminLogin(BaseModel):
    username: str
    password: str

class MessageCreate(BaseModel):
    content: str
    message_type: str = "text"

# Helper functions
def generate_order_number() -> str:
    import random
    import string
    timestamp = datetime.now().strftime("%Y%m%d")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD-{timestamp}-{random_part}"

def calculate_price(project_type: ProjectType, requirements: dict) -> float:
    """Calculate price based on project type and requirements"""
    base_prices = {
        ProjectType.TELEGRAM_BOT: 5_000_000,
        ProjectType.WHATSAPP_BOT: 8_000_000,
        ProjectType.DATA_SCRAPING: 3_000_000,
        ProjectType.WEBSITE: 15_000_000,
        ProjectType.AUTOMATION: 10_000_000,
        ProjectType.CONTENT: 2_000_000,
        ProjectType.EMAIL_AUTOMATION: 5_000_000,
        ProjectType.PRICE_COMPARISON: 5_000_000,
        ProjectType.DASHBOARD: 12_000_000,
        ProjectType.CUSTOM: 20_000_000,
    }
    
    price = base_prices.get(project_type, 10_000_000)
    
    # Add complexity multipliers
    if requirements:
        complexity = requirements.get("complexity", "simple")
        if complexity == "medium":
            price *= 1.5
        elif complexity == "complex":
            price *= 2.5
        elif complexity == "enterprise":
            price *= 4
        
        # Features
        features = requirements.get("features", [])
        price += len(features) * 500_000
        
        # Timeline
        timeline = requirements.get("timeline", "normal")
        if timeline == "urgent":
            price *= 1.5
        elif timeline == "express":
            price *= 2
    
    return round(price)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()