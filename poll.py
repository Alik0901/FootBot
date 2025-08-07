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

# Инициализация
init_db()
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
register_handlers(dp)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
