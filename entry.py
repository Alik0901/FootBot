import os
import asyncio
import logging
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types

from app.models import init_db, SessionLocal, Subscription
from app.payments import verify_signature
from app.handlers import register_handlers
from app.scheduler import start_scheduler

import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("entry")
logger.setLevel(logging.DEBUG)

# ─── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# ─── Load env ──────────────────────────────────────────────────────────────────
load_dotenv()
TOKEN      = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
BASE_URL   = os.getenv("BASE_URL")  # if needed

if not TOKEN or not CHANNEL_ID:
    logger.error("TOKEN or CHANNEL_ID not set")
    raise RuntimeError("Не заданы TOKEN или CHANNEL_ID")

logger.info("Environment loaded")

# ─── Init DB & Scheduler ──────────────────────────────────────────────────────
init_db()
logger.info("Database initialized")
start_scheduler()
logger.info("Scheduler started")

# ─── Aiogram setup ────────────────────────────────────────────────────────────
bot = Bot(token=TOKEN)
dp  = Dispatcher(bot)
register_handlers(dp)
logger.info("Aiogram dispatcher ready")

# ─── Flask app ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
logger.info("Flask app created")

@app.post("/telegram_webhook")
def telegram_webhook():
    logger.debug("Webhook hit: headers=%s", dict(request.headers))
    payload = request.get_json(silent=True, force=True) or {}
    logger.debug("Webhook payload: %s", payload)

    try:
        update = types.Update(**payload)
        # Выполняем корутину синхронно в этом запросе
        asyncio.run(dp.process_update(update))
        logger.debug("Update processed OK")
        # Telegram важно просто получить 200 быстро
        return jsonify({"ok": True}), 200
    except Exception as e:
        logger.exception("Webhook processing error: %s", e)
        # Всё равно отвечаем 200, чтобы TG не ретраил бесконечно,
        # иначе вас могут заддосить ретраями
        return jsonify({"ok": False}), 200

@app.route("/payment_webhook", methods=["POST"])
def payment_webhook():
    raw = request.get_data()
    sig = request.headers.get("X-Signature")
    logger.debug(f"/payment_webhook headers: X-Signature={sig}")
    if not sig or not verify_signature(raw, sig):
        logger.warning("Invalid signature on payment_webhook")
        abort(400, "Invalid signature")

    data = request.json or {}
    logger.debug(f"Payment payload: {data}")
    if data.get("status") == "Closed":
        # handle subscription…
        logger.info(f"Closed payment for orderId={data.get('orderId')}")
    return jsonify(ok=True)

logger.info("Entry.py loaded, ready to serve")
