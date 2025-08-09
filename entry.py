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


# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("entry")

# ── env ───────────────────────────────────────────────────────────────────────
load_dotenv()
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")  # напр. https://footbot-production.up.railway.app

if not TOKEN or not CHANNEL_ID:
    raise RuntimeError("Не заданы TOKEN или CHANNEL_ID")
log.info("Environment loaded")

# ── db + scheduler ────────────────────────────────────────────────────────────
init_db()
log.info("Database initialized")
start_scheduler()
log.info("Scheduler started")

# ── aiogram ───────────────────────────────────────────────────────────────────
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
register_handlers(dp)
log.info("Aiogram dispatcher ready")

# ── общий asyncio-loop в отдельном потоке ─────────────────────────────────────
_loop = asyncio.new_event_loop()

def _loop_worker():
    asyncio.set_event_loop(_loop)
    log.info("Background asyncio loop started")
    _loop.run_forever()

threading.Thread(target=_loop_worker, name="aiogram-loop", daemon=True).start()

def run_coro(coro):
    """Планирует корутину в общем loop (thread-safe)."""
    return asyncio.run_coroutine_threadsafe(coro, _loop)

# ── Flask (WSGI) ──────────────────────────────────────────────────────────────
app = Flask(__name__)
log.info("Flask app created")

@app.post("/telegram_webhook")
def telegram_webhook():
    payload = request.get_json(silent=True) or {}
    try:
        update = types.Update(**payload)
    except Exception:
        log.exception("Bad Telegram update payload")
        return jsonify(ok=False), 200

    try:
        run_coro(dp.process_update(update))
    except Exception:
        log.exception("Failed to schedule update")
        return jsonify(ok=False), 200

    return jsonify(ok=True), 200


@app.post("/payment_webhook")
def payment_webhook():
    raw = request.get_data()
    sig = request.headers.get("X-Signature")
    if not sig or not verify_signature(raw, sig):
        log.warning("Invalid signature on /payment_webhook")
        abort(400, "Invalid signature")

    data = request.get_json(silent=True) or {}
    log.info("Payment webhook: %s", data)

    if data.get("status") == "Closed":
        # orderId → ваш user_id
        try:
            user_id = int(data.get("orderId"))
        except (TypeError, ValueError):
            user_id = None

        plan = (data.get("description") or "").split()[0]
        days = {"Неделя": 7, "Месяц": 30, "Чат": 1}.get(plan, 0)

        if user_id and days > 0:
            expires = datetime.utcnow() + timedelta(days=days)
            session = SessionLocal()
            try:
                sub = Subscription(user_id=user_id, plan=plan, expires_at=expires)
                session.add(sub)
                session.commit()
            finally:
                session.close()

            # Разбаним в канале асинхронно
            run_coro(bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id))
            log.info("Subscription granted & unban scheduled: user_id=%s", user_id)

    return jsonify(ok=True), 200


# ── тех. эндпойнты ────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return jsonify(ok=True, ts=datetime.utcnow().isoformat() + "Z"), 200

@app.get("/")
def root():
    return "ok", 200

@app.get("/favicon.ico")
def favicon():
    return ("", 204, {"Cache-Control": "public, max-age=86400"})


# ── автосоздание вебхука (опционально) ────────────────────────────────────────
# Если BASE_URL задан, выставим вебхук на /telegram_webhook при старте воркера.
WEBHOOK_URL = f"{BASE_URL}/telegram_webhook" if BASE_URL else ""

if WEBHOOK_URL:
    def _set_webhook_once():
        async def _do():
            try:
                ok = await bot.set_webhook(
                    WEBHOOK_URL,
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=True,
                )
                log.info("Webhook set to %s (ok=%s)", WEBHOOK_URL, ok)
            except Exception:
                log.exception("Failed to set webhook")

        run_coro(_do())

    # Планируем сразу после запуска loop’а (маленькая задержка — чтобы loop точно поднялся)
    run_coro(asyncio.sleep(0.05))
    _set_webhook_once()
else:
    log.warning("BASE_URL не задан — вебхук не выставляется автоматически.")

log.info("Entry.py loaded, ready to serve")
