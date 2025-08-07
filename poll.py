import os, asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

from app.models import init_db
from app.handlers import register_handlers

load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN is not set")

# Сбрасываем webhook, чтобы polling работал
bot = Bot(token=TOKEN)
asyncio.get_event_loop().run_until_complete(
    bot.delete_webhook(drop_pending_updates=True)
)

init_db()
dp = Dispatcher(bot)
register_handlers(dp)

if __name__ == "__main__":
    print(">>> POLLING WORKER ACTIVE <<<")
    executor.start_polling(dp, skip_updates=True)
