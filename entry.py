import os
import asyncio
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.utils.exceptions import TelegramAPIError

from app.models import init_db, SessionLocal, Subscription
from app.payments import verify_signature
from app.handlers import register_handlers
from app.scheduler import start_scheduler

load_dotenv()
TOKEN      = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
BASE_URL   = os.getenv("BASE_URL")  # https://your-app.up.railway.app

if not TOKEN or not CHANNEL_ID or not BASE_URL:
    raise RuntimeError("Не заданы TOKEN, CHANNEL_ID или BASE_URL")

# Инициализация
init_db()
start_scheduler()
bot = Bot(token=TOKEN)
dp  = Dispatcher(bot)
register_handlers(dp)

app = Flask(__name__)
WEBHOOK_PATH = "/telegram_webhook"
WEBHOOK_URL  = BASE_URL + WEBHOOK_PATH

@app.before_first_request
def setup_webhook():
    """Устанавливаем Telegram-webhook при первом HTTP-запросе к Flask."""
    try:
        print(">>> Deleting old webhook (if any)")
        asyncio.run(bot.delete_webhook(drop_pending_updates=True))
        print(f">>> Setting new webhook: {WEBHOOK_URL}")
        asyncio.run(bot.set_webhook(WEBHOOK_URL))
        print(">>> Webhook setup complete")
    except TelegramAPIError as e:
        print(f">>> Failed to setup webhook: {e}")

@app.route("/telegram_webhook", methods=["POST"])
def telegram_webhook():
    print(">>> /telegram_webhook called")
    update_data = request.json
    print(f">>> Update payload: {update_data}")
    update = types.Update(**update_data)
    asyncio.create_task(dp.process_update(update))
    return jsonify(ok=True)

@app.route("/payment_webhook", methods=["POST"])
def payment_webhook():
    print(">>> /payment_webhook called")
    raw = request.get_data()
    sig = request.headers.get("X-Signature")
    if not sig or not verify_signature(raw, sig):
        print(">>> Invalid signature")
        abort(400, "Invalid signature")
    data = request.json or {}
    print(f">>> Payment payload: {data}")
    if data.get("status") == "Closed":
        user_id = int(data["orderId"])
        plan    = data.get("description","").split()[0]
        expires = datetime.utcnow() + timedelta(days={'Неделя':7,'Месяц':30,'Чат':1}.get(plan,0))
        session = SessionLocal()
        session.add(Subscription(user_id=user_id, plan=plan, expires_at=expires))
        session.commit()
        session.close()
        print(f">>> Subscription created: user={user_id}, plan={plan}")
        asyncio.create_task(bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id))
    return jsonify(ok=True)

print(">>> Flask entry.py loaded, awaiting requests <<<")
