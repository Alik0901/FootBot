# entry.py
import os
import asyncio
import threading
import logging
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types

from app.models import init_db, SessionLocal, Subscription
from app.payments import verify_signature
from app.handlers import register_handlers
from app.scheduler import start_scheduler


# ── Logging (единая настройка) ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("entry")


# ── ENV ───────────────────────────────────────────────────────────────────────
load_dotenv()
TOKEN      = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not TOKEN or not CHANNEL_ID:
    logger.error("TOKEN or CHANNEL_ID not set")
    raise RuntimeError("Не заданы TOKEN или CHANNEL_ID")

logger.info("Environment loaded")


# ── DB + Scheduler ────────────────────────────────────────────────────────────
init_db()
logger.info("Database initialized")

start_scheduler()
logger.info("Scheduler started")


# ── Aiogram: бот и диспетчер ──────────────────────────────────────────────────
bot = Bot(token=TOKEN)
dp  = Dispatcher(bot)
register_handlers(dp)
logger.info("Aiogram dispatcher ready")


# ── Общий asyncio-loop в отдельном потоке ─────────────────────────────────────
# Один gunicorn worker → один event loop
_loop = asyncio.new_event_loop()

def _loop_worker():
    asyncio.set_event_loop(_loop)
    _loop.run_forever()

_thread = threading.Thread(target=_loop_worker, name="aiogram-loop", daemon=True)
_thread.start()


def run_coro(coro):
    """Планировать корутину в общем loop и получить concurrent.futures.Future."""
    return asyncio.run_coroutine_threadsafe(coro, _loop)


# ── Flask app (WSGI) ──────────────────────────────────────────────────────────
app = Flask(__name__)
logger.info("Flask app created")


@app.post("/telegram_webhook")
def telegram_webhook():
    # Минимум логов в проде, но этого достаточно для отладки
    payload = request.get_json(silent=True) or {}
    logger.debug("Webhook headers=%s", dict(request.headers))
    logger.debug("Webhook payload=%s", payload)

    try:
        update = types.Update(**payload)
    except Exception:
        logger.exception("Bad Telegram update payload")
        # всё равно 200 – чтобы TG не ретраил бесконечно
        return jsonify(ok=False), 200

    try:
        # передаём обработку aiogram в наш loop, не блокируя Flask-поток
        run_coro(dp.process_update(update))
        return jsonify(ok=True), 200
    except Exception:
        logger.exception("Failed to schedule update")
        return jsonify(ok=False), 200


@app.post("/payment_webhook")
def payment_webhook():
    raw = request.get_data()
    sig = request.headers.get("X-Signature")

    if not sig or not verify_signature(raw, sig):
        logger.warning("Invalid signature on /payment_webhook")
        abort(400, "Invalid signature")

    data = request.get_json(silent=True) or {}
    logger.info("Payment webhook: %s", data)

    if data.get("status") == "Closed":
        try:
            user_id = int(data.get("orderId"))
        except (TypeError, ValueError):
            user_id = None

        description = data.get("description", "")
        plan = (description or "").split()[0]

        # Срок по плану (пример)
        days_map = {"Неделя": 7, "Месяц": 30, "Чат": 1}
        days = days_map.get(plan, 0)

        if user_id and days > 0:
            from datetime import datetime, timedelta
            expires = datetime.utcnow() + timedelta(days=days)

            session = SessionLocal()
            try:
                sub = Subscription(user_id=user_id, plan=plan, expires_at=expires)
                session.add(sub)
                session.commit()
            finally:
                session.close()

            # Разбан в канале – в асинхронном loop
            run_coro(bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id))
            logger.info("Subscription granted & unban scheduled: user_id=%s", user_id)

    return jsonify(ok=True), 200


# ── Технические GET-роуты ─────────────────────────────────────────────────────
@app.get("/health")
def health():
    return jsonify(ok=True, ts=datetime.utcnow().isoformat() + "Z"), 200

@app.get("/")
def root():
    return "ok", 200

@app.get("/favicon.ico")
def favicon():
    # чтобы браузерный фавикон не вёл к 502
    return ("", 204, {"Cache-Control": "public, max-age=86400"})


logger.info("Entry.py loaded, ready to serve")
