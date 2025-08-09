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
# entry.py
import os
import asyncio
import logging
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, abort
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types

# your imports...
# from app.models import ...
# from app.payments import ...
# from app.handlers import ...
# from app.scheduler import ...

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

@app.route("/telegram_webhook", methods=["POST"])
def telegram_webhook():
    data = request.json or {}
    logger.debug(f"/telegram_webhook payload: {data}")
    try:
        update = types.Update(**data)
        asyncio.create_task(dp.process_update(update))
        logger.debug("Dispatched update to Aiogram")
    except Exception as e:
        logger.exception("Failed to process update")
    return jsonify(ok=True)

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
