import os
import asyncio
from flask import Flask, request, jsonify, abort
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from dotenv import load_dotenv

from app.models import init_db, SessionLocal, Subscription
from app.payments import verify_signature
from app.handlers import register_handlers
from app.scheduler import start_scheduler

# Загрузка .env (для локалки) и переменных окружения
load_dotenv()

TOKEN = os.getenv('TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
BASE_URL = os.getenv('BASE_URL')  # например https://your-project.up.railway.app

if not TOKEN or not CHANNEL_ID or not BASE_URL:
    raise RuntimeError("Не заданы необходимые переменные окружения TOKEN, CHANNEL_ID, BASE_URL")

# --- Aiogram setup ---
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
register_handlers(dp)

# --- Database setup ---
init_db()

# --- Scheduler ---
start_scheduler()

# --- Flask app for webhooks ---
app = Flask(__name__)

@app.route('/payment_webhook', methods=['POST'])
def payment_webhook():
    raw = request.get_data()
    sig = request.headers.get('X-Signature')
    if not sig or not verify_signature(raw, sig):
        abort(400, 'Invalid signature')

    data = request.json
    if data.get('status') == 'Closed':
        user_id = int(data.get('orderId'))
        desc = data.get('description', '')
        plan = desc.split()[0]
        days_map = {'Неделя': 7, 'Месяц': 30, 'Чат': 1}
        days = days_map.get(plan, 0)

        from datetime import datetime, timedelta
        expires = datetime.utcnow() + timedelta(days=days)

        session = SessionLocal()
        session.add(Subscription(user_id=user_id, plan=plan, expires_at=expires))
        session.commit()
        session.close()

        asyncio.get_event_loop().create_task(
            bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        )

    return jsonify({'status': 'ok'})

# Константы для webhook
WEBHOOK_PATH = '/telegram_webhook'
WEBHOOK_URL  = BASE_URL + WEBHOOK_PATH

# --- Entrypoint for production via Gunicorn ---
if __name__ == '__main__':
    # Локальный режим: fallback на polling
    from aiogram.utils import executor
    executor.start_polling(dp, skip_updates=True)
else:
    # При старте Gunicorn: регистрируем и запускаем webhook-сервер
    # (этот блок не выполняется при импорте, только при gunicorn bot:app)
    async def on_startup(_):
        # Удаляем старый webhook и ставим новый
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.set_webhook(WEBHOOK_URL)

    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        skip_updates=True,
        app=app
    )
