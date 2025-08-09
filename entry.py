# entry.py
import os
import asyncio
import threading
import logging
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import Dispatcher as AiogramDispatcher

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
TOKEN        = os.getenv("TOKEN")
CHANNEL_ID   = os.getenv("CHANNEL_ID")
BASE_URL     = (os.getenv("BASE_URL", "").strip().rstrip("/"))          # публичный домен для вебхука
APP_BASE_URL = (os.getenv("APP_BASE_URL", BASE_URL).strip().rstrip("/"))  # для редиректов/заглушки
MODE         = os.getenv("PAYMENTS_MODE", "real").lower()                # 'real' | 'mock'

def _ensure_https(url: str) -> str:
    if not url:
        return ""
    if not (url.startswith("http://") or url.startswith("https://")):
        return "https://" + url
    return url

BASE_URL     = _ensure_https(BASE_URL)
APP_BASE_URL = _ensure_https(APP_BASE_URL)

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
dp  = Dispatcher(bot)
register_handlers(dp)
log.info("Aiogram dispatcher ready")

# ── общий asyncio-loop в отдельном потоке ─────────────────────────────────────
_loop = asyncio.new_event_loop()

async def _process_update_with_ctx(update: types.Update):
    # Привязываем текущие экземпляры к контексту aiogram
    Bot.set_current(bot)
    AiogramDispatcher.set_current(dp)
    await dp.process_update(update)

def _loop_worker():
    asyncio.set_event_loop(_loop)
    # Привяжем контекст и здесь на всякий случай
    Bot.set_current(bot)
    AiogramDispatcher.set_current(dp)
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
        run_coro(_process_update_with_ctx(update))
    except Exception:
        log.exception("Failed to schedule update")
        return jsonify(ok=False), 200

    return jsonify(ok=True), 200


# ── реальный вебхук оплаты от WATA ───────────────────────────────────────────
@app.post("/payment_webhook")
def payment_webhook():
    raw = request.get_data()
    sig = request.headers.get("X-Signature")
    if not sig or not verify_signature(raw, sig):
        log.warning("Invalid signature on /payment_webhook")
        abort(400, "Invalid signature")

    data = request.get_json(silent=True) or {}
    log.info("Payment webhook (real): %s", data)

    # Если пришло успешное событие — активируем подписку
    status = data.get("transactionStatus") or data.get("status")  # поддержим оба поля
    if status in ("Paid", "Closed"):
        try:
            user_id = int(data.get("orderId"))
        except (TypeError, ValueError):
            user_id = None

        plan = (data.get("orderDescription") or data.get("description") or "").split()[0]
        _activate_subscription_and_unban(user_id, plan)

    return jsonify(ok=True), 200


# ── MOCK-режим: тестовая страница и тестовый вебхук ──────────────────────────
@app.get("/testpay")
def testpay_page():
    """Простейшая html-страница для имитации оплаты в mock-режиме."""
    if MODE != "mock":
        return "Mock disabled", 404

    user_id = request.args.get("user_id", "")
    plan    = request.args.get("plan", "")
    amount  = request.args.get("amount", "0")
    orderId = request.args.get("orderId", user_id)
    html = f"""
    <html><body style="font-family:sans-serif">
      <h3>Тестовая оплата</h3>
      <p>Пользователь: <b>{user_id}</b></p>
      <p>План: <b>{plan}</b></p>
      <p>Сумма: <b>{amount}</b> RUB</p>
      <form method="post" action="/payment_webhook_test">
        <input type="hidden" name="user_id" value="{user_id}">
        <input type="hidden" name="plan" value="{plan}">
        <input type="hidden" name="orderId" value="{orderId}">
        <button type="submit">Оплата успешна</button>
      </form>
    </body></html>
    """
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}

@app.post("/payment_webhook_test")
def payment_webhook_test():
    """Тестовый вебхук (без подписи), имитирующий success от WATA."""
    if MODE != "mock":
        return jsonify(ok=False, reason="mock disabled"), 404

    user_id = request.form.get("user_id", type=int)
    plan    = request.form.get("plan", "")
    _activate_subscription_and_unban(user_id, plan)
    return jsonify(ok=True, mock=True), 200


def _activate_subscription_and_unban(user_id: int | None, plan: str):
    days = {"Неделя": 7, "Месяц": 30, "Чат": 1}.get(plan, 0)
    if not user_id or days <= 0:
        log.warning("Activation skipped (user_id=%s, plan=%r)", user_id, plan)
        return

    expires = datetime.utcnow() + timedelta(days=days)
    session = SessionLocal()
    try:
        sub = Subscription(user_id=user_id, plan=plan, expires_at=expires)
        session.add(sub)
        session.commit()
    finally:
        session.close()

    # Разбан в канале асинхронно
    run_coro(bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id))
    log.info("Subscription granted & unban scheduled: user_id=%s plan=%s until=%s",
             user_id, plan, expires.isoformat()+"Z")


# ── тех. эндпойнты ────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return jsonify(ok=True, ts=datetime.utcnow().isoformat() + "Z", mode=MODE), 200

@app.get("/")
def root():
    return "ok", 200

@app.get("/favicon.ico")
def favicon():
    return ("", 204, {"Cache-Control": "public, max-age=86400"})

@app.get("/paid/success")
def paid_success():
    return "Оплата прошла успешно. Можете вернуться в Telegram 👍", 200

@app.get("/paid/fail")
def paid_fail():
    return "Оплата не прошла. Попробуйте позже.", 200


# ── автосоздание вебхука ──────────────────────────────────────────────────────
WEBHOOK_URL = f"{BASE_URL}/telegram_webhook" if BASE_URL else ""
if WEBHOOK_URL:
    async def _set_webhook():
        try:
            ok = await bot.set_webhook(
                WEBHOOK_URL,
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
            )
            log.info("Webhook set to %s (ok=%s)", WEBHOOK_URL, ok)
        except Exception:
            log.exception("Failed to set webhook")

    # немного подождём, чтобы loop точно поднялся
    run_coro(asyncio.sleep(0.05))
    run_coro(_set_webhook())
else:
    log.warning("BASE_URL не задан — вебхук не выставляется автоматически.")

log.info("Entry.py loaded, ready to serve")
