# entry.py
import os
import time
import asyncio
import threading
import logging
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, abort, render_template_string, url_for
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import Dispatcher as AiogramDispatcher

from app.models import init_db, SessionLocal, Subscription
from app.payments import verify_signature
from app.handlers import register_handlers
from app.scheduler import start_scheduler  # <- используем колбэк on_expire

PLAN_TO_DELTA = {
    "Неделя": timedelta(days=7),
    "Месяц": timedelta(days=30),
    "Чат": timedelta(days=1),
    "Тест1м": timedelta(minutes=1),  # ← вот тут магия
}

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("entry")

# ── env ───────────────────────────────────────────────────────────────────────
load_dotenv()
TOKEN      = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
BASE_URL   = (os.getenv("BASE_URL", "").rstrip("/"))
TEST_MODE  = os.getenv("TEST_MODE", "1") == "1"

if not TOKEN or not CHANNEL_ID:
    raise RuntimeError("Не заданы TOKEN или CHANNEL_ID")
log.info("Environment loaded")

# ── db ────────────────────────────────────────────────────────────────────────
init_db()
log.info("Database initialized")

# ── aiogram ───────────────────────────────────────────────────────────────────
bot = Bot(token=TOKEN)
dp  = Dispatcher(bot)
register_handlers(dp)
log.info("Aiogram dispatcher ready")

# ── общий asyncio-loop в отдельном потоке ─────────────────────────────────────
_loop = asyncio.new_event_loop()

async def _process_update_with_ctx(update: types.Update):
    Bot.set_current(bot)
    AiogramDispatcher.set_current(dp)
    await dp.process_update(update)

def _loop_worker():
    asyncio.set_event_loop(_loop)
    log.info("Background asyncio loop started")
    _loop.run_forever()

threading.Thread(target=_loop_worker, name="aiogram-loop", daemon=True).start()

def run_coro(coro):
    return asyncio.run_coroutine_threadsafe(coro, _loop)

# ── Flask (WSGI) ──────────────────────────────────────────────────────────────
app = Flask(__name__)
log.info("Flask app created")


# ── выдача подписки и инвайта ─────────────────────────────────────────────────
def _grant_subscription(user_id: int, plan: str):
    delta = PLAN_TO_DELTA.get(plan)
    if not user_id or not delta:
        log.warning("grant: invalid args user_id=%s plan=%s", user_id, plan)
        return

    expires = datetime.utcnow() + delta
    ...
    invite = await bot.create_chat_invite_link(
        chat_id=CHANNEL_ID,
        name=f"{plan} {user_id}",
        expire_date=expires,
        member_limit=1,
    )

    async def _unban_and_send():
        try:
            await bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        except Exception:
            pass
        invite = await bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            name=f"{plan} {user_id}",
            expire_date=expires,
            member_limit=1,
        )
        text = (
            "✅ Оплата получена!\n\n"
            f"Ссылка в канал:\n{invite.invite_link}\n\n"
            f"Действует до: {expires:%d.%m.%Y %H:%M} UTC"
        )
        try:
            await bot.send_message(chat_id=user_id, text=text)
        except Exception as e:
            log.warning("send_message failed for user %s: %s", user_id, e)

    run_coro(_unban_and_send())
    log.info("Subscription granted: user_id=%s plan=%s until=%s",
             user_id, plan, expires.isoformat() + "Z")


# ── автоотключение (бан→анбан) по завершению подписки ─────────────────────────
def on_expire(user_id: int, plan: str) -> None:
    async def _do():
        try:
            # «выкинуть»: бан, затем сразу анбан
            await bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
            await bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        except Exception as e:
            log.warning("Kick failed user_id=%s: %s", user_id, e)
        try:
            await bot.send_message(
                chat_id=user_id,
                text="⏰ Срок вашей подписки истёк. Доступ к каналу отключён.\n"
                     "Вы можете оформить новую подписку в боте."
            )
        except Exception:
            pass
    run_coro(_do())

# запускаем планировщик ТЕПЕРЬ, когда есть run_coro и bot
start_scheduler(on_expire=on_expire, interval_seconds=60)
log.info("Scheduler started")


# ── Telegram webhook ──────────────────────────────────────────────────────────
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


# ── WATA payment webhook ──────────────────────────────────────────────────────
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
        try:
            user_id = int(data.get("orderId"))
        except (TypeError, ValueError):
            user_id = None
        plan = (data.get("description") or "").split()[0]
        _grant_subscription(user_id, plan)

    return jsonify(ok=True), 200


# ── тестовая заглушка оплаты (/testpay) ───────────────────────────────────────
if TEST_MODE:
    @app.get("/testpay")
    def testpay_page():
        user_id  = request.args.get("user_id", type=int)
        plan     = request.args.get("plan", type=str) or "Не указан"
        amount   = request.args.get("amount", type=float)
        order_id = request.args.get("orderId") or f"tg-{user_id}-{int(time.time())}"

        html = """
        <!doctype html><meta charset="utf-8">
        <title>Тестовая оплата</title>
        <h2>Тестовая оплата</h2>
        <p>Пользователь: <b>{{ user_id }}</b></p>
        <p>План: <b>{{ plan }}</b> — сумма: <b>{{ amount or "?" }} ₽</b></p>
        <p>orderId: <code>{{ order_id }}</code></p>
        <p>
          <a href="{{ url_for('testpay_success', user_id=user_id, plan=plan, orderId=order_id) }}">✅ Оплатить (успех)</a>
          &nbsp;&nbsp;
          <a href="{{ url_for('testpay_fail') }}">❌ Отмена</a>
        </p>
        """
        return render_template_string(html, user_id=user_id, plan=plan, amount=amount, order_id=order_id)

    @app.get("/testpay/success")
    def testpay_success():
        user_id = request.args.get("user_id", type=int)
        plan    = request.args.get("plan", type=str)
        _grant_subscription(user_id, plan)
        return "<h3>Оплата смоделирована как УСПЕШНАЯ. Вернитесь в бота.</h3>", 200

    @app.get("/testpay/fail")
    def testpay_fail():
        return "<h3>Оплата смоделирована как ОТМЕНЁННАЯ.</h3>", 200


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


# ── автоустановка вебхука в TG ────────────────────────────────────────────────
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

    run_coro(asyncio.sleep(0.05))
    _set_webhook_once()
else:
    log.warning("BASE_URL не задан — вебхук не выставляется автоматически.")

log.info("Entry.py loaded, ready to serve")
