# app/handlers.py
import os
import logging
from datetime import datetime
from requests.exceptions import HTTPError

from aiogram import types, Dispatcher
from app.payments import create_invoice
from app.keyboards import main_menu, plans_menu
from app.models import SessionLocal, Subscription

log = logging.getLogger("handlers")

PLAN_MAP = {
    "plan_week":   ("Неделя", 100.0, 7),
    "plan_month":  ("Месяц",  300.0, 30),
    "plan_chat":   ("Чат",     50.0, 1),
    "plan_test1m": ("Тест1м",   1.0, 0),
}

APP_BASE_URL  = os.getenv("APP_BASE_URL", os.getenv("BASE_URL", "")).rstrip("/")
ADMIN_CONTACT = os.getenv("ADMIN_CONTACT", "@YourAdmin")
CLUB_NAME     = os.getenv("CLUB_NAME", "FOOT SECRET CLUB")  # название клуба для заголовка


def _admin_contact_text() -> str:
    # Если дали ссылку — делаем кликабельной; если @username — оставляем как есть
    if ADMIN_CONTACT.startswith("http"):
        return f'<a href="{ADMIN_CONTACT}">{ADMIN_CONTACT}</a>'
    return ADMIN_CONTACT


def _welcome_text() -> str:
    # HTML‑верстка приветствия
    return (
        f'🔥 <b>ДОБРО ПОЖАЛОВАТЬ В «[ {CLUB_NAME} ]»!</b> 🔥\n'
        f'<i>(Твой ежедневный сериал, где главные роли играют… ножки…)</i>\n\n'
        'Каждый день — новый «эпизод» с дерзкими фото и дразнящими описаниями. '
        'Ты узнаешь тайны этих пяточек, почувствуешь напряжение в каждом кадре… и захочешь «продолжения».\n\n'
        '• 📸 Качественные фото — будто кадры из эротического триллера.\n'
        '• 📖 Сочные подписи — мини‑истории, намёки, интрига…\n'
        '• ⏳ Ежедневные «выпуски» — подпишись, чтобы не пропустить развязку!\n\n'
        f'💌 Эксклюзивные заказы — доступны только для избранных (пиши в ЛС { _admin_contact_text() } 👀)'
    )


def register_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, commands=['start'])

    dp.register_callback_query_handler(cb_buy,      lambda c: c.data == 'buy')
    dp.register_callback_query_handler(cb_my_subs,  lambda c: c.data == 'my_subs')
    dp.register_callback_query_handler(cb_bonuses,  lambda c: c.data == 'bonuses')
    dp.register_callback_query_handler(cb_help,     lambda c: c.data == 'help')
    dp.register_callback_query_handler(cb_back,     lambda c: c.data == 'back')

    dp.register_callback_query_handler(process_plan, lambda c: c.data in PLAN_MAP)


async def cmd_start(message: types.Message):
    log.info("cmd_start chat_id=%s", message.chat.id)
    await message.answer(_welcome_text(), reply_markup=main_menu(), parse_mode="HTML")


async def cb_buy(callback: types.CallbackQuery):
    log.info("cb_buy from user=%s", callback.from_user.id)
    await callback.message.edit_text("Выберите тарифный план:", reply_markup=plans_menu())
    await callback.answer()


async def cb_my_subs(callback: types.CallbackQuery):
    """Показывает активные/истёкшие подписки пользователя."""
    log.info("cb_my_subs from user=%s", callback.from_user.id)
    session = SessionLocal()
    try:
        now = datetime.utcnow()
        subs = (
            session.query(Subscription)
            .filter(Subscription.user_id == callback.from_user.id)
            .order_by(Subscription.expires_at.desc())
            .all()
        )

        if not subs:
            text = "У вас нет оформленных подписок."
        else:
            lines = []
            for sub in subs:
                status = "✅ Активна" if sub.expires_at > now else "⏰ Истекла"
                lines.append(f"• {sub.plan} — до {sub.expires_at:%d.%m.%Y %H:%M} UTC ({status})")
            text = "Ваши подписки:\n\n" + "\n".join(lines)

        await callback.message.edit_text(text, reply_markup=main_menu())
    except Exception:
        log.exception("Failed to fetch subscriptions for user=%s", callback.from_user.id)
        await callback.message.edit_text("Ошибка при получении данных о подписках.", reply_markup=main_menu())
    finally:
        session.close()
    await callback.answer()


async def cb_bonuses(callback: types.CallbackQuery):
    """Заглушка под бонусы/акции — можешь заменить на актуальные условия."""
    text = (
        "🎁 <b>Бонусы и акции</b>\n\n"
        "— Приведи друга и получи +1 день к подписке.\n"
        "— Скидка 50% на первый месяц для новых пользователей (по промокоду <b>FIRST50</b>).\n\n"
        "Подробности у администратора: " + _admin_contact_text()
    )
    await callback.message.edit_text(text, reply_markup=main_menu(), parse_mode="HTML")
    await callback.answer()


async def cb_help(callback: types.CallbackQuery):
    """Информация о помощи и контакте администратора."""
    log.info("cb_help from user=%s", callback.from_user.id)
    text = (
        "🆘 <b>Помощь</b>\n\n"
        "Если возникли вопросы или проблемы с подпиской, напишите администратору:\n"
        f"{_admin_contact_text()}"
    )
    await callback.message.edit_text(text, reply_markup=main_menu(), parse_mode="HTML")
    await callback.answer()


async def cb_back(callback: types.CallbackQuery):
    await callback.message.edit_text("Главное меню:", reply_markup=main_menu())
    await callback.answer()


# ----- оплата -----
async def _create_invoice_async(*args, **kwargs):
    import asyncio
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: create_invoice(*args, **kwargs))


async def process_plan(callback: types.CallbackQuery):
    name, amount, _days = PLAN_MAP[callback.data]
    log.info("process_plan user=%s data=%r", callback.from_user.id, callback.data)

    order_id = f"tg-{callback.from_user.id}-{callback.id}"
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
        await callback.answer(); return
    except Exception as e:
        log.exception("create_invoice failed: %s", e)
        await callback.message.answer("❗️ Произошла ошибка при создании счёта.")
        await callback.answer(); return

    if not pay_url:
        await callback.message.answer("❗️ Платёжная ссылка не получена.")
        await callback.answer(); return

    await callback.message.answer(f"Счёт на {amount:.2f}₽:\n{pay_url}")
    await callback.answer()
