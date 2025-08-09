import os
import logging
import asyncio
from requests.exceptions import HTTPError
from aiogram import types, Dispatcher

from app.payments import create_invoice    # sync
from app.keyboards import main_menu, plans_menu

logger = logging.getLogger("handlers")

# Тарифы: callback_data -> (название, сумма, дни)
PLAN_MAP = {
    'plan_week':  ('Неделя', 100.0, 7),
    'plan_month': ('Месяц', 300.0, 30),
    'plan_chat':  ('Чат',   50.0, 1),
}

BASE_URL = os.getenv('BASE_URL', '')


def register_handlers(dp: Dispatcher):
    # /start
    dp.register_message_handler(cmd_start, commands=['start'])

    # Главное меню (инлайн-кнопки!)
    dp.register_callback_query_handler(cb_buy,      lambda c: c.data == 'buy')
    dp.register_callback_query_handler(cb_back,     lambda c: c.data == 'back')
    dp.register_callback_query_handler(cb_my_subs,  lambda c: c.data == 'my_subs')
    dp.register_callback_query_handler(cb_bonuses,  lambda c: c.data == 'bonuses')
    dp.register_callback_query_handler(cb_help,     lambda c: c.data == 'help')

    # Выбор тарифа
    dp.register_callback_query_handler(process_plan, lambda c: (c.data or "") in PLAN_MAP)

    # Общий лог ошибок
    @dp.errors_handler()
    async def _errors(update, error):
        logger.exception("Handler error: %r on %r", error, update)
        return True


async def cmd_start(message: types.Message):
    logger.info("cmd_start chat_id=%s", message.chat.id)
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=main_menu())


# ====== callbacks главного меню ======

async def cb_buy(callback: types.CallbackQuery):
    await callback.answer()  # быстро убираем "часики"
    logger.info("cb_buy from user=%s", callback.from_user.id)
    # чтобы не плодить сообщения — редактируем текущий
    await callback.message.edit_text("Выберите тарифный план:", reply_markup=plans_menu())


async def cb_back(callback: types.CallbackQuery):
    await callback.answer()
    logger.info("cb_back from user=%s", callback.from_user.id)
    await callback.message.edit_text("Добро пожаловать! Выберите действие:", reply_markup=main_menu())


async def cb_my_subs(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Здесь будут ваши подписки 🙂")


async def cb_bonuses(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Здесь будут бонусы 🎁")


async def cb_help(callback: types.CallbackQuery):
    await callback.answer()
    await callback.message.answer("Помощь: напишите нам @support ...")


# ====== обработка тарифов ======

# обёртка, чтобы не блокировать event loop при sync requests
async def _create_invoice_async(*args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: create_invoice(*args, **kwargs))

async def process_plan(callback: types.CallbackQuery):
    await callback.answer()
    data = callback.data or ""
    logger.info("process_plan user=%s data=%r", callback.from_user.id, data)

    name, amount, days = PLAN_MAP[data]
    try:
        invoice = await _create_invoice_async(
            user_id=callback.from_user.id,
            amount=amount,
            plan=name,
            base_url=BASE_URL
        )
        pay_url = (invoice or {}).get("url")
        if not pay_url:
            raise ValueError("Empty pay url in invoice")
    except HTTPError as e:
        logger.warning("create_invoice HTTPError: %s", e, exc_info=True)
        if getattr(e, "response", None) and e.response.status_code == 401:
            pay_url = f"{BASE_URL}/testpay?user_id={callback.from_user.id}&plan={name}"
        else:
            await callback.message.answer("❗️ Не удалось создать счёт. Попробуйте позже.")
            return
    except Exception as e:
        logger.exception("create_invoice failed: %s", e)
        await callback.message.answer("❗️ Не удалось создать счёт. Попробуйте позже.")
        return

    await callback.message.answer(f"Счёт на {amount:.0f}₽:\n{pay_url}")
