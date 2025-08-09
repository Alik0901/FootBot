# app/keyboards.py
import os
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

NEWS_URL = os.getenv("NEWS_URL")  # ссылка на ваш новостной канал/чат

def main_menu() -> InlineKeyboardMarkup:
    """
    Красивое главное меню в 2 колонки + блок "Наши новости" отдельной строкой.
    """
    kb = InlineKeyboardMarkup(row_width=2)

    # 1 ряд
    kb.add(
        InlineKeyboardButton('💳 Купить', callback_data='buy'),
        InlineKeyboardButton('📜 Мои подписки', callback_data='my_subs'),
    )
    # 2 ряд
    kb.add(
        InlineKeyboardButton('💰 Бонусы', callback_data='bonuses'),
        InlineKeyboardButton('🆘 Помощь', callback_data='help'),
    )
    # 3 ряд — внешняя ссылка
    if NEWS_URL:
        kb.add(InlineKeyboardButton('📣 Наши новости', url=NEWS_URL))

    return kb


def plans_menu() -> InlineKeyboardMarkup:
    """
    Меню выбора тарифного плана (один столбец) + назад.
    """
    kb = InlineKeyboardMarkup(row_width=1)
    kb.insert(InlineKeyboardButton('Неделя — 100₽', callback_data='plan_week'))
    kb.insert(InlineKeyboardButton('Месяц — 300₽', callback_data='plan_month'))
    kb.insert(InlineKeyboardButton('Чат 1 день — 50₽', callback_data='plan_chat'))
    kb.insert(InlineKeyboardButton('Тест 1 мин — 1₽', callback_data='plan_test1m'))
    kb.insert(InlineKeyboardButton('⬅️ Назад', callback_data='back'))
    return kb
