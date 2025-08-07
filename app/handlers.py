import os
import logging
from datetime import datetime
from aiogram import types, Dispatcher

from app.keyboards import main_menu, plans_menu
from app.payments import create_invoice
from app.models import SessionLocal, Subscription
from requests.exceptions import HTTPError


# Тарифы: ключ -> (название, цена, дни)
PLAN_MAP = {
    'plan_week': ('Неделя', 100, 7),
    'plan_month': ('Месяц', 300, 30),
    'plan_chat': ('Чат', 50, 1)
}

BASE_URL = os.getenv('BASE_URL')


def register_handlers(dp: Dispatcher):
    @dp.message_handler(commands=['start'])
    async def cmd_start(message: types.Message):
        await message.answer(
            'Привет! Добро пожаловать.',
            reply_markup=main_menu()
        )

    @dp.callback_query_handler(lambda c: c.data == 'buy')
    async def process_buy(callback: types.CallbackQuery):
        await callback.message.edit_text(
            'Выберите тариф:',
            reply_markup=plans_menu()
        )
        await callback.answer()

    @dp.callback_query_handler(lambda c: c.data.startswith('plan_'))
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
            # Тестовый режим без токена — возвращаем простую тестовую ссылку
            pay_url = f"{BASE_URL}/testpay?user_id={callback.from_user.id}&plan={name}"
        else:
            logging.exception("Ошибка при создании счёта")
            await callback.message.answer("❗️ Не удалось создать счёт. Попробуйте позже.")
            return

    await callback.message.answer(f"Счёт на {amount}₽: {pay_url}")
    await callback.answer()

    @dp.callback_query_handler(lambda c: c.data == 'my_subs')
    async def process_my_subs(callback: types.CallbackQuery):
        session = SessionLocal()
        subs = session.query(Subscription).filter(
            Subscription.user_id == callback.from_user.id,
            Subscription.expires_at > datetime.utcnow()
        ).all()
        session.close()
        if not subs:
            text = 'У вас нет активных подписок.'
        else:
            lines = [
                f"{s.plan}: до {s.expires_at.strftime('%Y-%m-%d %H:%M')} UTC"
                for s in subs
            ]
            text = 'Ваши подписки:\n' + '\n'.join(lines)
        await callback.message.answer(text)
        await callback.answer()

    @dp.callback_query_handler(lambda c: c.data == 'bonuses')
    async def process_bonuses(callback: types.CallbackQuery):
        await callback.message.answer('Функционал бонусов в разработке.')
        await callback.answer()

    @dp.callback_query_handler(lambda c: c.data == 'help')
    async def process_help(callback: types.CallbackQuery):
        await callback.message.answer(
            'По всем вопросам пишите @admin_username'
        )
        await callback.answer()
