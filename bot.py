import os
import asyncio
from flask import Flask, request, jsonify, abort

from aiogram import Bot, Dispatcher, types
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

# Запуск планировщика для отзыва просроченных подписок
start_scheduler()

# Flask-приложение для вебхуков
app = Flask(__name__)

@app.route('/payment_webhook', methods=['POST'])
def payment_webhook():
    raw_body = request.get_data()
    signature = request.headers.get('X-Signature')
    if not signature or not verify_signature(raw_body, signature):
        abort(400, 'Invalid signature')

    data = request.json
    if data.get('status') == 'Closed':
        user_id = int(data.get('orderId'))
        description = data.get('description', '')
        plan = description.split()[0]
        days_map = {'Неделя': 7, 'Месяц': 30, 'Чат': 1}
        days = days_map.get(plan, 0)

        from datetime import datetime, timedelta
        expires = datetime.utcnow() + timedelta(days=days)

        session = SessionLocal()
        sub = Subscription(user_id=user_id, plan=plan, expires_at=expires)
        session.add(sub)
        session.commit()
        session.close()

        # Разбаниваем пользователя в канале
        asyncio.get_event_loop().create_task(
            bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        )

    return jsonify({'status': 'ok'})

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    # Получаем апдейт из запроса и передаём в Aiogram
    update = types.Update(**request.json)
    asyncio.get_event_loop().create_task(dp.process_update(update))
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    # Для локальной разработки: поллинг Aiogram
    from aiogram.utils import executor
    executor.start_polling(dp, skip_updates=True)
