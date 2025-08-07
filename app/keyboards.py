from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu() -> InlineKeyboardMarkup:
    """
    Возвращает основное меню бота с кнопками:
    - Купить
    - Мои подписки
    - Бонусы
    - Помощь
    """
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton('💳 Купить', callback_data='buy')
    )
    keyboard.add(
        InlineKeyboardButton('📋 Мои подписки', callback_data='my_subs')
    )
    keyboard.add(
        InlineKeyboardButton('🎁 Бонусы', callback_data='bonuses')
    )
    keyboard.add(
        InlineKeyboardButton('❓ Помощь', callback_data='help')
    )
    return keyboard


def plans_menu() -> InlineKeyboardMarkup:
    """
    Возвращает меню выбора тарифного плана:
    - Неделя — 100₽
    - Месяц — 300₽
    - Чат 1 день — 50₽
    - Назад
    """
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.insert(
        InlineKeyboardButton('Неделя — 100₽', callback_data='plan_week')
    )
    keyboard.insert(
        InlineKeyboardButton('Месяц — 300₽', callback_data='plan_month')
    )
    keyboard.insert(
        InlineKeyboardButton('Чат 1 день — 50₽', callback_data='plan_chat')
    )
    keyboard.insert(
        InlineKeyboardButton('Назад', callback_data='back')
    )
    return keyboard
