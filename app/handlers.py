import os
from datetime import datetime
from aiogram import types, Dispatcher

from app.keyboards import main_menu, plans_menu
from app.payments import create_invoice
from app.models import SessionLocal, Subscription

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
        plan_key = callback.data
        name, amount, days = PLAN_MAP[plan_key]
        invoice = create_invoice(
            user_id=callback.from_user.id,
            amount=amount,
            plan=name,
            base_url=BASE_URL
        )
        await callback.message.answer(
            f"Создан счёт на {amount}₽. Оплатите по ссылке: {invoice.get('url')}"
        )
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
