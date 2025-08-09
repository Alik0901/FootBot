# app/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu() -> InlineKeyboardMarkup:
    """
    Главное меню:
    - Купить
    - Мои подписки
    - Бонусы
    - Помощь
    """
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton('💳 Купить', callback_data='buy'))
    kb.add(InlineKeyboardButton('📋 Мои подписки', callback_data='my_subs'))
    kb.add(InlineKeyboardButton('🎁 Бонусы', callback_data='bonuses'))
    kb.add(InlineKeyboardButton('❓ Помощь', callback_data='help'))
    return kb


def plans_menu() -> InlineKeyboardMarkup:
    """
    Меню выбора тарифного плана:
    - Неделя — 100₽
    - Месяц — 300₽
    - Чат 1 день — 50₽
    - Тест 1 мин — 1₽
    - Назад
    """
    kb = InlineKeyboardMarkup(row_width=1)
    kb.insert(InlineKeyboardButton('Неделя — 100₽', callback_data='plan_week'))
    kb.insert(InlineKeyboardButton('Месяц — 300₽', callback_data='plan_month'))
    kb.insert(InlineKeyboardButton('Чат 1 день — 50₽', callback_data='plan_chat'))
    kb.insert(InlineKeyboardButton('Тест 1 мин — 1₽', callback_data='plan_test1m'))
    kb.insert(InlineKeyboardButton('⬅️ Назад', callback_data='back'))
    return kb
