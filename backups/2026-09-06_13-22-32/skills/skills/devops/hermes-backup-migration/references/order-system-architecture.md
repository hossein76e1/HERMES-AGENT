# Order System Architecture

## Overview
Complete full-stack automated order management system for AI freelance services.

## Tech Stack
- **Backend**: FastAPI + SQLAlchemy + SQLite
- **Frontend**: Vanilla HTML/CSS/JS (no framework overhead)
- **Admin**: Separate HTML/JS dashboard
- **Auth**: JWT tokens (RS256)
- **Payments**: Zarinpal ready + Card fallback
- **Real-time**: WebSocket for chat
- **Deploy**: GitHub Pages for frontend

## Database Schema
- **User**: email, phone, hashed_password, is_admin
- **Admin**: username, hashed_password, is_super
- **Order**: project_type, title, description, requirements (JSON), base/final price, status, payment_status
- **Payment**: amount, method (online/card/crypto), status, transaction_id
- **Conversation**: user_id, order_id, current_step, collected_data (JSON)
- **OrderMessage**: order_id, sender_type, content, message_type

## Project Types & Base Pricing (IRR)
| Type | Base Price |
|------|------------|
| Telegram Bot | 5,000,000 |
| WhatsApp Bot | 8,000,000 |
| Data Scraping | 3,000,000 |
| Website | 15,000,000 |
| Automation | 10,000,000 |
| Content Generation | 2,000,000 |
| Email Automation | 5,000,000 |
| Price Comparison | 5,000,000 |
| Dashboard | 12,000,000 |
| Custom | 20,000,000 |

## Pricing Multipliers
- Complexity: simple=1x, medium=1.5x, complex=2.5x, enterprise=4x
- Features: +500,000 per feature
- Timeline: normal=1x, urgent=1.5x, express=2x

## Order Flow
1. **Chat Bot** collects requirements via natural language
2. **Auto-pricing** calculates final price
3. **Order created** with PENDING status
4. **Admin** reviews, sets final price → QUOTED
5. **Customer** pays (Zarinpal/Card) → PAID
6. **Work starts** → IN_PROGRESS
7. **Deliverable uploaded** → READY
8. **Admin approves** → DELIVERED

## Chat Bot Steps
1. welcome → project_type
2. project_title
3. description
3. features (list)
4. complexity
5. timeline
6. budget
7. contact_email
8. contact_phone
9. complete → creates Order

## Admin Dashboard
- Stats: total, pending, in_progress, completed, revenue
- Order list with filters
- Order detail with chat history
- Status updates with timestamps
- Quote sending with notes
- Delivery approval

## Payment Integration
- **Zarinpal**: Request → Redirect → Verify callback
- **Card**: Show card details + amount → Manual verification
- **Crypto**: USDT/TRC20 address

## Real-time Chat
- WebSocket per order
- Broadcast to all connected clients
n- Message types: text, quote, file, system

## Deployment
- Backend: Uvicorn on VPS (port 8000)
- Frontend: GitHub Pages (docs/ folder)
- Admin: Same repo, protected route
- Nginx reverse proxy recommended

## Environment Variables
```
DATABASE_URL=sqlite:///./orders.db
SECRET_KEY=your-secret-key
ZARINPAL_MERCHANT_ID=xxxx
ZARINPAL_CALLBACK_URL=https://domain.com/api/payment/verify
ADMIN_USER=admin
ADMIN_PASS=secure-password
```

## Security
- JWT with 7-day expiry
- Bcrypt password hashing
- CORS configured
- Admin-only routes protected
- SQL injection prevention via ORM

## Scaling Considerations
- Move to PostgreSQL for production
- Add Redis for session/cache
- Celery for background tasks
- Load balancer for multiple instances
