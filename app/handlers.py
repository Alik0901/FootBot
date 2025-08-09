# app/handlers.py
import os
import logging
from requests.exceptions import HTTPError

from aiogram import types, Dispatcher
from app.payments import create_invoice
from app.keyboards import main_menu, plans_menu

log = logging.getLogger("handlers")

# Тарифы: callback_data -> (Название, Сумма, Дни)
PLAN_MAP = {
    "plan_week":  ("Неделя", 100.0, 7),
    "plan_month": ("Месяц", 300.0, 30),
    "plan_chat":  ("Чат",    50.0,  1),
}

APP_BASE_URL = os.getenv("APP_BASE_URL", os.getenv("BASE_URL", "")).rstrip("/")

def register_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=['start'])

    # Кнопки главного меню
    dp.register_callback_query_handler(cb_buy,   lambda c: c.data == 'buy')
    dp.register_callback_query_handler(cb_back,  lambda c: c.data == 'back')

    # Выбор плана
    dp.register_callback_query_handler(process_plan, lambda c: c.data in PLAN_MAP)

async def cmd_start(message: types.Message):
    log.info("cmd_start chat_id=%s", message.chat.id)
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=main_menu())

async def cb_buy(callback: types.CallbackQuery):
    log.info("cb_buy from user=%s", callback.from_user.id)
    await callback.message.edit_text("Выберите тарифный план:", reply_markup=plans_menu())
    await callback.answer()

async def cb_back(callback: types.CallbackQuery):
    await callback.message.edit_text("Возвращаюсь в главное меню:", reply_markup=main_menu())
    await callback.answer()

# helper: вызвать sync create_invoice без блокировки event loop
async def _create_invoice_async(*args, **kwargs):
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: create_invoice(*args, **kwargs))

async def process_plan(callback: types.CallbackQuery):
    name, amount, days = PLAN_MAP[callback.data]
    log.info("process_plan user=%s data=%r", callback.from_user.id, callback.data)

    # Не обязательно, но красиво иметь order_id
    order_id = f"tg-{callback.from_user.id}-{callback.id}"

    # (опционально) success/fail — страницы подтверждения
    success_url = f"{APP_BASE_URL}/paid/success" if APP_BASE_URL else None
    fail_url    = f"{APP_BASE_URL}/paid/fail"    if APP_BASE_URL else None

    try:
        invoice = await _create_invoice_async(
            user_id=callback.from_user.id,
            amount=amount,
            plan=name,
            success_url=success_url,
            fail_url=fail_url,
            order_id=order_id,
        )
        pay_url = invoice.get("url")
    except HTTPError as e:
        log.warning("create_invoice HTTPError: %s", e, exc_info=True)
        await callback.message.answer("❗️ Не удалось создать счёт. Попробуйте чуть позже.")
        await callback.answer()
        return
    except Exception as e:
        log.exception("create_invoice failed: %s", e)
        await callback.message.answer("❗️ Произошла ошибка при создании счёта.")
        await callback.answer()
        return

    if not pay_url:
        await callback.message.answer("❗️ Платёжная ссылка не получена.")
        await callback.answer()
        return

    await callback.message.answer(f"Счёт на {amount:.2f}₽:\n{pay_url}")
    await callback.answer()
