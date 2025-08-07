import os, asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.utils import executor

from app.models import init_db
from app.handlers import register_handlers

print(">>> LOADED poll.py <<<")

load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN is not set")

# Delete any webhook so polling can work
bot = Bot(token=TOKEN)
asyncio.get_event_loop().run_until_complete(
    bot.delete_webhook(drop_pending_updates=True)
)

init_db()
dp = Dispatcher(bot)
register_handlers(dp)

if __name__ == "__main__":
    print(">>> POLLING WORKER START <<<")
    executor.start_polling(dp, skip_updates=True)
