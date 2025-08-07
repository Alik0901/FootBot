import os
import asyncio
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types

from app.models import init_db, SessionLocal, Subscription
from app.payments import verify_signature
from app.handlers import register_handlers
from app.scheduler import start_scheduler

load_dotenv()
TOKEN      = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
# BASE_URL пока не нужен в коде

if not TOKEN or not CHANNEL_ID:
    raise RuntimeError("Не заданы TOKEN или CHANNEL_ID")

# Инициализация
init_db()
start_scheduler()
bot = Bot(token=TOKEN)
dp  = Dispatcher(bot)
register_handlers(dp)

app = Flask(__name__)

@app.route("/telegram_webhook", methods=["POST"])
def telegram_webhook():
    data = request.json or {}
    update = types.Update(**data)
    asyncio.create_task(dp.process_update(update))
    return jsonify(ok=True)

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
        asyncio.create_task(bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id))
    return jsonify(ok=True)

print(">>> Flask entry loaded <<<")
