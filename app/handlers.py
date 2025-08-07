from aiogram import types
from aiogram.dispatcher import Dispatcher
from requests.exceptions import HTTPError
import logging

from app.payments import create_invoice
from app.keyboards import main_menu, plans_menu
from app.config import BASE_URL, PLAN_MAP  # или как у вас хранятся константы

def register_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=['start'])
    dp.register_message_handler(show_plans, text='💳 Купить')
    dp.register_callback_query_handler(process_plan, lambda c: c.data.startswith('plan_'))
    # … остальные регистрации …

async def cmd_start(message: types.Message):
    await message.answer("Добро пожаловать!", reply_markup=main_menu())

async def show_plans(message: types.Message):
    await message.answer("Выберите тариф:", reply_markup=plans_menu())

async def process_plan(callback: types.CallbackQuery):
    name, amount, days = PLAN_MAP[callback.data]
    try:
        invoice = create_invoice(
            user_id=callback.from_user.id,
            amount=amount,
            plan=name,
            base_url=BASE_URL
        )
        pay_url = invoice.get("url")
    except HTTPError as e:
        if e.response.status_code == 401:
            pay_url = f"{BASE_URL}/testpay?user_id={callback.from_user.id}&plan={name}"
        else:
            logging.exception("Ошибка при создании счёта")
            await callback.message.answer("❗️ Не удалось создать счёт. Попробуйте позже.")
            return

    await callback.message.answer(f"Счёт на {amount}₽: {pay_url}")
    await callback.answer()
