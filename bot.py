print(">>> WEB PROCESS STARTING bot.py <<<")
import os, asyncio
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv

from aiogram import Bot
from app.models import init_db, SessionLocal, Subscription
from app.payments import verify_signature

load_dotenv()
TOKEN      = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not TOKEN or not CHANNEL_ID:
    raise RuntimeError("Не заданы TOKEN или CHANNEL_ID")

# Только для unban:
bot = Bot(token=TOKEN)

# DB
init_db()

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
        plan = data.get("description","").split()[0]
        days_map = {"Неделя":7,"Месяц":30,"Чат":1}
        expires = datetime.utcnow() + timedelta(days=days_map.get(plan,0))

        session = SessionLocal()
        session.add(Subscription(user_id=user_id, plan=plan, expires_at=expires))
        session.commit()
        session.close()

        asyncio.get_event_loop().create_task(
            bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        )

    return jsonify(status="ok")
    
if __name__ == '__main__':
    print(">>> FALLBACK POLLING STARTING <<<")
    from aiogram.utils import executor
    executor.start_polling(dp, skip_updates=True)