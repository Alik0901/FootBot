import os
import asyncio
from multiprocessing import Process
from flask import Flask, request, jsonify, abort

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from app.models import init_db, SessionLocal, Subscription
from app.payments import verify_signature
from app.handlers import register_handlers
from app.scheduler import start_scheduler

# Загрузка переменных окружения из .env (для локального запуска)
load_dotenv()

# Параметры из окружения
TOKEN = os.getenv('TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
BASE_URL = os.getenv('BASE_URL')

if not TOKEN or not CHANNEL_ID or not BASE_URL:
    raise RuntimeError('Не заданы необходимые переменные окружения TOKEN, CHANNEL_ID, BASE_URL')

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Инициализация БД (создание таблиц)
init_db()

# Регистрация хендлеров Aiogram
register_handlers(dp)

# Запуск планировщика (APScheduler) для периодической проверки подписок
scheduler = start_scheduler()

# Flask-приложение для вебхука платежей
app = Flask(__name__)

@app.route('/payment_webhook', methods=['POST'])
def payment_webhook():
    raw_body = request.get_data()
    signature = request.headers.get('X-Signature')
    if not signature or not verify_signature(raw_body, signature):
        abort(400, 'Invalid signature')
    data = request.json
    # Обработка успешной оплаты (Closed)
    if data.get('status') == 'Closed':
        # Параметры из уведомления
        user_id = int(data.get('orderId'))
        description = data.get('description', '')
        plan = description.split()[0]
        # Расчёт срока по плану
        days_map = {'Неделя': 7, 'Месяц': 30, 'Чат': 1}
        days = days_map.get(plan, 0)
        expires_at = asyncio.get_event_loop().time()  # placeholder
        # Сохраняем подписку
        from datetime import datetime, timedelta
        expires = datetime.utcnow() + timedelta(days=days)
        session = SessionLocal()
        sub = Subscription(user_id=user_id, plan=plan, expires_at=expires)
        session.add(sub)
        session.commit()
        session.close()
        # Разбаниваем пользователя
        asyncio.get_event_loop().create_task(
            bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        )
    return jsonify({'status': 'ok'})
 
    # Запуск Aiogram бота
    def run_bot():
        from aiogram.utils import executor
        executor.start_polling(dp, skip_updates=True)

        # В продакшене запуск происходит через Gunicorn, 
        # но для локального dev можно оставить aiogram:
        from aiogram.utils import executor
        executor.start_polling(dp, skip_updates=True)

 
