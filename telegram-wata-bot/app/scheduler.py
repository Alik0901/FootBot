import asyncio
import os
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.models import SessionLocal, Subscription
from aiogram import Bot

# Telegram Bot token from environment
token = os.getenv('TOKEN')
bot = Bot(token=token)


def remove_expired_subscriptions():
    """
    Проверяет базу на истёкшие подписки и банит пользователей в канале.
    Запускается по расписанию.
    """
    session = SessionLocal()
    now = datetime.utcnow()
    expired = session.query(Subscription).filter(Subscription.expires_at <= now).all()
    for sub in expired:
        try:
            # Баним пользователя в канале
            asyncio.get_event_loop().create_task(
                bot.ban_chat_member(chat_id=os.getenv('CHANNEL_ID'), user_id=sub.user_id)
            )
        except Exception:
            pass
        session.delete(sub)
    session.commit()
    session.close()


def start_scheduler():
    """
    Инициализирует и запускает AsyncIOScheduler для периодической проверки подписок.
    """
    scheduler = AsyncIOScheduler()
    # Проверяем каждый час
    scheduler.add_job(remove_expired_subscriptions, 'interval', hours=1)
    scheduler.start()

    # Возвращаем объект, чтобы при желании можно было shut down
    return scheduler
