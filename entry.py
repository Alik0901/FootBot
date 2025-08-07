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
BASE_URL   = os.getenv("BASE_URL")  # e.g. https://your-project.up.railway.app

if not TOKEN or not CHANNEL_ID or not BASE_URL:
    raise RuntimeError("Не заданы TOKEN, CHANNEL_ID или BASE_URL")

# ─── Init DB & Scheduler ──────────────────────────────────────────────────────
init_db()
start_scheduler()

# ─── Aiogram setup ────────────────────────────────────────────────────────────
bot = Bot(token=TOKEN)
dp  = Dispatcher(bot)
register_handlers(dp)

# ─── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)

@app.route("/payment_webhook", methods=["POST"])
def payment_webhook():
    raw = request.get_data()
    sig = request.headers.get("X-Signature")
    if not sig or not verify_signature(raw, sig):
        abort(400, "Invalid signature")
    data = request.json or {}
    if data.get("status") == "Closed":
        user_id = int(data["orderId"])
        plan    = data.get("description","").split()[0]
        expires = datetime.utcnow() + timedelta(days={'Неделя':7,'Месяц':30,'Чат':1}.get(plan,0))
        session = SessionLocal()
        session.add(Subscription(user_id=user_id, plan=plan, expires_at=expires))
        session.commit()
        session.close()
        asyncio.create_task(
            bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        )
    return jsonify(status="ok")

# Эндпоинт для Telegram webhook
@app.route("/telegram_webhook", methods=["POST"])
def telegram_webhook():
    update = types.Update(**request.json)
    asyncio.create_task(dp.process_update(update))
    return jsonify(status="ok")

# Настройка webhook-констант
WEBHOOK_PATH = "/telegram_webhook"
WEBHOOK_URL  = BASE_URL + WEBHOOK_PATH

if __name__ == "__main__":
    # Для локальной разработки
    from aiogram.utils import executor
    executor.start_polling(dp, skip_updates=True)
else:
    # При production (Gunicorn)
    async def on_startup(_):
        await bot.set_webhook(WEBHOOK_URL)

    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        skip_updates=True,
        app=app
    )
