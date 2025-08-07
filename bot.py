import os
import asyncio
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, abort
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from dotenv import load_dotenv

from app.models import init_db, SessionLocal, Subscription
from app.payments import verify_signature
from app.handlers import register_handlers
from app.scheduler import start_scheduler

# ─── Load env ──────────────────────────────────────────────────────────────────
load_dotenv()
TOKEN      = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
BASE_URL   = os.getenv("BASE_URL")  # e.g. https://myproject.up.railway.app

if not TOKEN or not CHANNEL_ID or not BASE_URL:
    raise RuntimeError("Не заданы переменные TOKEN, CHANNEL_ID, BASE_URL")

# ─── Aiogram setup ────────────────────────────────────────────────────────────
bot = Bot(token=TOKEN)
dp  = Dispatcher(bot)
register_handlers(dp)

# ─── Database & Scheduler ─────────────────────────────────────────────────────
init_db()
start_scheduler()

# ─── Flask app for WATA & Telegram webhooks ────────────────────────────────────
app = Flask(__name__)

@app.route("/payment_webhook", methods=["POST"])
def payment_webhook():
    raw = request.get_data()
    sig = request.headers.get("X-Signature")
    if not sig or not verify_signature(raw, sig):
        abort(400, "Invalid signature")

    data = request.json or {}
    if data.get("status") == "Closed":
        user_id     = int(data.get("orderId"))
        plan        = data.get("description", "").split()[0]
        days        = {"Неделя":7, "Месяц":30, "Чат":1}.get(plan, 0)
        expires_at  = datetime.utcnow() + timedelta(days=days)

        session = SessionLocal()
        session.add(Subscription(user_id=user_id, plan=plan, expires_at=expires_at))
        session.commit()
        session.close()

        # Unban in channel asynchronously
        asyncio.get_event_loop().create_task(
            bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        )

    return jsonify(status="ok")

# ─── Configuration for Telegram webhook ────────────────────────────────────────
WEBHOOK_PATH = "/telegram_webhook"
WEBHOOK_URL  = BASE_URL + WEBHOOK_PATH

# ─── Entrypoint for Gunicorn ──────────────────────────────────────────────────
# Expose `app` for Gunicorn  
# Gunicorn will import this module, see `app`, and then run start_webhook below.

async def on_startup(dp: Dispatcher):
    # Clear any previous webhook & set new one
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(WEBHOOK_URL)

# This call ties Aiogram dispatcher into Flask under Gunicorn
start_webhook(
    dispatcher   = dp,
    webhook_path = WEBHOOK_PATH,
    on_startup   = on_startup,
    host         = "0.0.0.0",
    port         = int(os.getenv("PORT", 5000)),
    skip_updates = True,
    web_app          = app,
)
