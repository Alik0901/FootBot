# poll.py

import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.utils import executor

from app.models import init_db
from app.handlers import register_handlers

load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN is not set")

# Инициализация БД и бота
init_db()
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
register_handlers(dp)

if __name__ == "__main__":
    # Сбрасываем webhook, чтобы не было конфликта с polling
    import asyncio
    asyncio.get_event_loop().run_until_complete(bot.delete_webhook(drop_pending_updates=True))
    print(">>> Webhook deleted, starting polling worker <<<")
    executor.start_polling(dp, skip_updates=True)
