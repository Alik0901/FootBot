import os
import asyncio
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook

from app.models import init_db, SessionLocal, Subscription
from app.payments import verify_signature
from app.handlers import register_handlers
from app.scheduler import start_scheduler

# ─── Load env ──────────────────────────────────────────────────────────────────
load_dotenv()
TOKEN      = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
BASE_URL   = os.getenv("BASE_URL")

if not TOKEN or not CHANNEL_ID or not BASE_URL:
    raise RuntimeError("Не заданы TOKEN, CHANNEL_ID или BASE_URL")

print(">>> ENV loaded: TOKEN, CHANNEL_ID, BASE_URL")

# ─── Init DB & Scheduler ──────────────────────────────────────────────────────
init_db()
print(">>> Database initialized")
start_scheduler()
print(">>> Scheduler started")

# ─── Aiogram setup ────────────────────────────────────────────────────────────
bot = Bot(token=TOKEN)
dp  = Dispatcher(bot)
register_handlers(dp)
print(">>> Aiogram Dispatcher ready and handlers registered")

# ─── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
print(">>> Flask app instance created")

@app.route("/payment_webhook", methods=["POST"])
def payment_webhook():
    print(">>> /payment_webhook called")
    raw = request.get_data()
    sig = request.headers.get("X-Signature")
    if not sig or not verify_signature(raw, sig):
        print(">>> Invalid signature on payment_webhook")
        abort(400, "Invalid signature")

    data = request.json or {}
    print(f">>> payment_webhook payload: {data}")
    if data.get("status") == "Closed":
        user_id = int(data["orderId"])
        plan    = data.get("description","").split()[0]
        expires = datetime.utcnow() + timedelta(days={'Неделя':7,'Месяц':30,'Чат':1}.get(plan,0))

        session = SessionLocal()
        session.add(Subscription(user_id=user_id, plan=plan, expires_at=expires))
        session.commit()
        session.close()

        print(f">>> Subscription created for user {user_id}, plan {plan}")
        asyncio.create_task(
            bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        )
        print(f">>> Unban task scheduled for user {user_id}")

    return jsonify(status="ok")

@app.route("/telegram_webhook", methods=["POST"])
def telegram_webhook():
    print(">>> /telegram_webhook called")
    update_data = request.json
    print(f">>> telegram_webhook payload: {update_data}")
    update = types.Update(**update_data)
    asyncio.create_task(dp.process_update(update))
    print(">>> Update dispatched to Aiogram")
    return jsonify(status="ok")

# ─── Webhook config ────────────────────────────────────────────────────────────
WEBHOOK_PATH = "/telegram_webhook"
WEBHOOK_URL  = BASE_URL + WEBHOOK_PATH

print(f">>> Configured WEBHOOK_URL={WEBHOOK_URL}")

async def on_startup(dispatcher):
    print(">>> on_startup: deleting existing Telegram webhook")
    await bot.delete_webhook(drop_pending_updates=True)
    print(">>> on_startup: setting new Telegram webhook")
    result = await bot.set_webhook(WEBHOOK_URL)
    print(f">>> on_startup: set_webhook result={result}")

print(">>> Calling start_webhook()")

start_webhook(
    dispatcher   = dp,
    webhook_path = WEBHOOK_PATH,
    on_startup   = on_startup,
    host         = "0.0.0.0",
    port         = int(os.getenv("PORT", 5000)),
    skip_updates = True,
    wsgi_app     = app,    # либо web_app или application — подставьте правильный параметр
)
print(">>> start_webhook() call complete (this line may not execute if run_webhook blocks)")
