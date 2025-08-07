import os
import logging
from requests.exceptions import HTTPError

from aiogram import types, Dispatcher

from app.payments import create_invoice
from app.keyboards import main_menu, plans_menu

# Тарифы: callback_data -> (название, сумма, дни)
PLAN_MAP = {
    'plan_week': ('Неделя', 100.0, 7),
    'plan_month': ('Месяц', 300.0, 30),
    'plan_chat': ('Чат', 50.0, 1),
}

# Базовый URL (для тестовой платежной заглушки)
BASE_URL = os.getenv('BASE_URL', '')

def register_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=['start'])
    dp.register_message_handler(show_plans, text='💳 Купить')
    dp.register_callback_query_handler(process_plan, lambda c: c.data in PLAN_MAP)
    # другие регистрации: мои подписки, бонусы, помощь…

async def cmd_start(message: types.Message):
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=main_menu())

async def show_plans(message: types.Message):
    await message.answer("Выберите тарифный план:", reply_markup=plans_menu())

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
            # тестовый режим: возвращаем заглушку
            pay_url = f"{BASE_URL}/testpay?user_id={callback.from_user.id}&plan={name}"
        else:
            logging.exception("Ошибка при создании счёта")
            await callback.message.answer("❗️ Не удалось создать счёт. Попробуйте позже.")
            await callback.answer()
            return

    await callback.message.answer(f"Счёт на {amount}₽:\n{pay_url}")
    await callback.answer()
