import os
import threading
import asyncio
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

from app.models import init_db, SessionLocal, Subscription
from app.payments import verify_signature
from app.handlers import register_handlers
from app.scheduler import start_scheduler

# ─── Load env ─────────────────────────────────────────────────────────────────
load_dotenv()
TOKEN      = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
if not TOKEN or not CHANNEL_ID:
    raise RuntimeError("Не заданы TOKEN или CHANNEL_ID")

# ─── Init DB & Scheduler ──────────────────────────────────────────────────────
init_db()
start_scheduler()

# ─── Aiogram setup ────────────────────────────────────────────────────────────
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
register_handlers(dp)

# ─── Flask app for payment webhooks ───────────────────────────────────────────
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
        # Unban user asynchronously
        asyncio.get_event_loop().create_task(
            bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        )
    return jsonify(status="ok")

def run_flask():
    # запускаем Flask в отдельном потоке
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

if __name__ == "__main__":
    # 1) Запускаем Flask
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(">>> Flask thread started, now starting polling <<<")

    # 2) Сбрасываем любой webhook (на случай, если он был)
    asyncio.get_event_loop().run_until_complete(bot.delete_webhook(drop_pending_updates=True))

    # 3) Стартуем Aiogram polling, обработку кнопок и /start
    executor.start_polling(dp, skip_updates=True)
