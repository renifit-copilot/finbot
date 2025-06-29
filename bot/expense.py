from aiogram import Router, types, F
from aiogram.types import Message, FSInputFile
from aiogram.enums import ParseMode
from sqlalchemy.orm import Session
import re
import os
import uuid
from datetime import datetime, timedelta
import logging
from core.models import User, Expense as ExpenseModel, Category, Transaction
from core.db import SessionLocal
from core.ocr import parse_receipt
from core.llm import categorize_transaction
from typing import Optional, Dict, Any
from sqlalchemy import desc, func
from bot.commands import get_main_keyboard  # Импортируем функцию для получения клавиатуры меню
import locale
import calendar

# Устанавливаем русскую локаль для корректного отображения дат
try:
    locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'Russian_Russia.1251')
    except:
        logging.warning("Не удалось установить русскую локаль")

# Создаем роутер для обработки расходов
router = Router()

# Русские названия месяцев
RUSSIAN_MONTHS = {
    1: 'январь',
    2: 'февраль',
    3: 'март',
    4: 'апрель',
    5: 'май',
    6: 'июнь',
    7: 'июль',
    8: 'август',
    9: 'сентябрь',
    10: 'октябрь',
    11: 'ноябрь',
    12: 'декабрь'
}

# Русские названия дней недели
RUSSIAN_WEEKDAYS = {
    0: 'понедельник',
    1: 'вторник',
    2: 'среда',
    3: 'четверг',
    4: 'пятница',
    5: 'суббота',
    6: 'воскресенье'
}

# Функция для форматирования даты на русском языке
def format_date_russian(date):
    """Форматирует дату на русском языке"""
    try:
        day = date.day
        month_num = date.month
        year = date.year
        weekday_num = date.weekday()
        
        month_name = RUSSIAN_MONTHS[month_num]
        weekday_name = RUSSIAN_WEEKDAYS[weekday_num]
        
        return f"{day} {month_name} {year}, {weekday_name}"
    except Exception as e:
        logging.error(f"Ошибка форматирования даты: {e}")
        # В случае ошибки возвращаем простой формат
        return date.strftime("%d.%m.%Y")

@router.message(F.text.regexp(r'^-\d+(?:[.,]\d+)?\s+\w+.*$'))
async def process_expense_message(message: Message):
    """
    Обрабатывает сообщения о расходах в формате: -СУММА КАТЕГОРИЯ
    Например: -150 кофе, -2500 продукты
    """
    user_id = message.from_user.id
    
    try:
        # Парсим сообщение с помощью регулярного выражения
        match = re.match(r'^-(\d+(?:[.,]\d+)?)\s+(.+)$', message.text)
        if not match:
            await message.answer("Неверный формат. Используйте: -СУММА КАТЕГОРИЯ")
            return
        
        # Извлекаем сумму и категорию
        amount_str = match.group(1).replace(',', '.')
        amount = float(amount_str)
        category_input = match.group(2).strip().lower()
        
        # Создаем сессию БД
        db = SessionLocal()
        try:
            # Получаем пользователя из БД
            user = db.query(User).filter(User.telegram_id == user_id).first()
            
            if not user:
                # Если пользователя нет в базе, предлагаем начать с /start
                await message.answer("Для начала работы, пожалуйста, используйте команду /start")
                return
            
            # Используем LLM для определения категории
            category = categorize_transaction(category_input, db, user.id)
            
            # Если категория не определена, используем введенную пользователем
            if not category:
                category = category_input
            
            # Создаем новую запись о расходе
            expense = ExpenseModel(
                user_id=user.id,
                amount=amount,
                category=category,
                description=message.text
            )
            
            db.add(expense)
            db.commit()
            
            # Получаем эмодзи для категории
            category_emoji = get_category_emoji(category)
            
            # Форматируем сумму в стиле Cointry
            formatted_amount = f"`{amount:.2f}`"
            
            # Отправляем подтверждение в стиле Cointry
            await message.answer(
                f"<b>{category_emoji} {category.capitalize()}</b>\n"
                f"➖ {formatted_amount} ₽",
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            db.rollback()
            logging.error(f"Ошибка при сохранении расхода: {e}")
            await message.answer("Произошла ошибка при сохранении расхода. Попробуйте позже.")
        finally:
            db.close()
            
    except Exception as e:
        logging.error(f"Ошибка при обработке сообщения о расходе: {e}")
        await message.answer("Произошла ошибка при обработке сообщения. Попробуйте позже.")


@router.message(F.photo)
async def process_receipt_photo(message: Message):
    """
    Обрабатывает фотографии чеков:
    - Сохраняет фото во временный файл
    - Распознает текст с помощью OCR
    - Извлекает сумму и категорию
    - Сохраняет расход в БД
    """
    user_id = message.from_user.id
    
    try:
        # Отправляем сообщение о начале обработки
        processing_msg = await message.answer("🔍 Обрабатываю чек...")
        
        # Создаем директорию для сохранения чеков, если её нет
        receipts_dir = "receipts"
        os.makedirs(receipts_dir, exist_ok=True)
        
        # Генерируем уникальное имя файла
        file_uuid = uuid.uuid4()
        photo_path = os.path.join(receipts_dir, f"{file_uuid}.jpg")
        
        # Получаем информацию о самом большом размере фото
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        
        # Скачиваем фото
        await message.bot.download_file(file_info.file_path, destination=photo_path)
        
        # Распознаем текст с помощью OCR
        amount, category_input = parse_receipt(photo_path)
        
        if amount <= 0:
            await message.answer(
                "❌ Не удалось распознать сумму на чеке.\n"
                "Попробуйте отправить более четкую фотографию или введите расход вручную в формате: -СУММА КАТЕГОРИЯ"
            )
            return
        
        # Создаем сессию БД
        db = SessionLocal()
        try:
            # Получаем пользователя из БД
            user = db.query(User).filter(User.telegram_id == user_id).first()
            
            if not user:
                await message.answer("Для начала работы, пожалуйста, используйте команду /start")
                return
            
            # Используем LLM для определения категории на основе информации из чека
            receipt_info = f"Чек на сумму {amount} руб. Магазин: {category_input}"
            category = categorize_transaction(receipt_info, db, user.id)
            
            # Если категория не определена, используем распознанную из OCR
            if not category:
                category = recognize_category(category_input)
            
            # Создаем новую запись о расходе
            expense = ExpenseModel(
                user_id=user.id,
                amount=amount,
                category=category,
                description=f"Чек на сумму {amount} руб.",
                receipt_path=photo_path
            )
            
            db.add(expense)
            db.commit()
            
            # Получаем эмодзи для категории
            category_emoji = get_category_emoji(category)
            
            # Форматируем сумму в стиле Cointry
            formatted_amount = f"`{amount:.2f}`"
            
            # Отправляем подтверждение в стиле Cointry
            await message.answer(
                f"<b>{category_emoji} {category.capitalize()}</b>\n"
                f"➖ {formatted_amount} ₽\n\n"
                f"<i>Если данные распознаны неверно, вы можете добавить расход вручную</i>",
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            db.rollback()
            logging.error(f"Ошибка при сохранении расхода из чека: {e}")
            await message.answer("Произошла ошибка при сохранении расхода. Попробуйте позже.")
        finally:
            db.close()
            
    except Exception as e:
        logging.error(f"Ошибка при обработке чека: {e}")
        await message.answer("Произошла ошибка при обработке чека. Попробуйте еще раз или введите расход вручную.")
    finally:
        # Удаляем сообщение о процессе обработки
        try:
            await processing_msg.delete()
        except:
            pass 

# === NEW CODE ===
import re
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, List
import json


# Словарь эмодзи для категорий расходов
CATEGORY_EMOJI = {
    "продукты": "🛒",
    "кафе": "🍔",
    "транспорт": "🚗",
    "такси": "🚕",
    "развлечения": "🎭",
    "кино": "🎬",
    "здоровье": "💊",
    "одежда": "👕",
    "обувь": "👟",
    "связь": "📞",
    "интернет": "🌐",
    "образование": "📚",
    "спорт": "🏋️",
    "подарки": "🎁",
    "путешествия": "✈️",
    "дом": "🏠",
    "техника": "📱",
    "зарплата": "💼",
    "канцтовары": "✏️",
    "бытовая химия": "🧼",
    "рестораны": "🍽️",
    "другое": "💰"
}

# Регулярные выражения для парсинга транзакций
# Паттерн для суммы: число с оp будем обрабатывать цитат-блоки в стиле Cointryциональной десятичной частью
AMOUNT_PATTERN = r'(-?\d+(?:[.,]\d+)?)'

# Паттерн для валюты: три буквы после суммы (например, USD или RUB)
CURRENCY_PATTERN = r'([A-Za-z]{3})'

# Паттерн для упоминания пользователя: @username
MENTION_PATTERN = r'@(\w+)'

# Паттерн для даты в двух форматах: цифровой (01.01.2024 или 2024-01-01) или текстовый (вчера, позавчера)
DATE_PATTERN = r'(\d{1,2}[.-]\d{1,2}[.-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2}|вчера|позавчера)'


def get_category_emoji(category_name: str) -> str:
    """
    Возвращает эмодзи для указанной категории
    
    Args:
        category_name: название категории
        
    Returns:
        str: эмодзи для категории
    """
    # Словарь с эмодзи для популярных категорий
    category_emojis = {
        "продукты": "🛒",
        "еда": "🍔",
        "кафе": "☕",
        "ресторан": "🍽️",
        "транспорт": "🚗",
        "такси": "🚕",
        "одежда": "👕",
        "обувь": "👟",
        "развлечения": "🎮",
        "кино": "🎬",
        "подарки": "🎁",
        "здоровье": "💊",
        "аптека": "💊",
        "связь": "📱",
        "интернет": "🌐",
        "коммуналка": "🏠",
        "образование": "📚",
        "спорт": "🏋️",
        "путешествия": "✈️",
        "зарплата": "💵",
        "доход": "💰",
        "другое": "📋"
    }
    
    # Приводим название категории к нижнему регистру
    category_name = category_name.lower()
    
    # Проверяем, есть ли категория в словаре
    for key, emoji in category_emojis.items():
        if key in category_name:
            return emoji
    
    # Если категория не найдена, возвращаем эмодзи по умолчанию
    return "📋"


def format_amount(amount: float, currency: str = "RUB") -> str:
    """Форматирует сумму в стиле Cointry"""
    if currency == "RUB":
        return f"`{amount:.2f}`"
    return f"`{amount:.2f} {currency}`"


def recognize_category(text: str) -> str:
    """
    Распознает категорию расхода по ключевым словам
    
    Args:
        text: текст для анализа
        
    Returns:
        str: распознанная категория
    """
    # Словарь категорий и соответствующих им ключевых слов
    category_keywords = {
        "продукты": [
            # Магазины продуктов
            "магнит", "пятерочка", "перекресток", "перекрёсток", "ашан", "лента", "дикси", 
            "окей", "метро", "азбука вкуса", "вкусвилл", "спар", "spar", "auchan",
            "магнолия", "мираторг", "карусель", "глобус", "billa", "билла", "верный",
            "лавка", "продуктовый", "супермаркет", "гипермаркет", "продукты",
            # Продукты
            "еда", "молоко", "хлеб", "овощи", "фрукты", "мясо", "рыба",
            "сыр", "яйца", "масло", "йогурт", "творог", "кефир", "сметана", "колбаса",
            "сосиски", "курица", "картошка", "картофель", "морковь", "лук", "чеснок",
            "помидоры", "огурцы", "капуста", "макароны", "крупа", "рис", "гречка",
            "сахар", "соль", "мука", "печенье", "конфеты", "шоколад", "вода", "сок"
        ],
        "кафе": [
            "кафе", "кофе", "кофейня", "старбакс", "starbucks", "шоколадница", "кофеин", "чай", 
            "кондитерская", "пекарня", "булочная", "завтрак", "обед", "ужин", 
            "пицца", "фастфуд", "бургер", "шаурма", "макдоналдс", "kfc", "бургер кинг",
            "costa coffee", "subway", "сабвей"
        ],
        "рестораны": [
            "ресторан", "бар", "паб", "суши", "пицца", "доставка еды", "яндекс еда", "деливери"
        ],
        "транспорт": [
            "метро", "автобус", "трамвай", "троллейбус", "маршрутка", "электричка", 
            "проезд", "транспорт", "проездной", "тройка", "карта метро", "бензин", "парковка"
        ],
        "такси": [
            "такси", "яндекс такси", "uber", "убер", "ситимобил", "didi", "поездка"
        ],
        "одежда": [
            "одежда", "zara", "h&m", "uniqlo", "adidas", "nike", "reebok", "lamoda",
            "wildberries", "ozon", "куртка", "брюки", "джинсы", "футболка", "рубашка",
            "платье", "юбка", "носки", "нижнее белье", "шапка", "шарф", "перчатки"
        ],
        "обувь": [
            "обувь", "туфли", "ботинки", "кроссовки", "сапоги", "кеды", "ecco", 
            "ralf ringer", "chester", "rendez-vous", "сандалии", "тапочки"
        ],
        "развлечения": [
            "развлечения", "игры", "кино", "театр", "концерт", "выставка", "музей", 
            "парк", "аттракционы", "боулинг", "бильярд", "квест", "стрим", "подписка",
            "караоке", "клуб"
        ],
        "здоровье": [
            "здоровье", "аптека", "лекарства", "врач", "доктор", "клиника", "больница", 
            "стоматолог", "анализы", "витамины", "36.6", "озерки", "столички", "массаж"
        ],
        "связь": [
            "связь", "телефон", "мтс", "билайн", "мегафон", "теле2", "yota", "сотовый", 
            "мобильный", "интернет", "wi-fi", "роутер", "модем", "телевидение"
        ],
        "коммуналка": [
            "коммуналка", "жкх", "квартплата", "электричество", "вода", "газ", "отопление", 
            "квартира", "дом", "жилье", "аренда", "съем", "найм"
        ],
        "образование": [
            "образование", "учеба", "школа", "институт", "университет", "курсы", "тренинг", 
            "книги", "учебники", "репетитор", "семинар", "вебинар"
        ],
        "канцтовары": [
            "канцтовары", "ручка", "карандаш", "тетрадь", "блокнот", "бумага", "степлер",
            "скрепки", "папка", "файлы", "маркер", "ластик", "линейка", "калькулятор"
        ],
        "бытовая химия": [
            "бытовая химия", "мыло", "шампунь", "гель для душа", "зубная паста", "зубная щетка",
            "стиральный порошок", "кондиционер для белья", "средство для мытья посуды",
            "чистящее средство", "туалетная бумага", "салфетки", "бумажные полотенца"
        ]
    }
    
    text = text.lower()
    
    # Проверяем наличие ключевых слов в тексте
    for category, keywords in category_keywords.items():
        for keyword in keywords:
            if keyword in text:
                return category
    
    # Если категория не распознана, возвращаем "другое"
    return "другое"


async def get_or_create_category(db: Session, user_id: int, category_name: str, is_expense: bool = True) -> Category:
    """Получает или создает категорию расходов/доходов"""
    # Нормализация имени категории
    category_name = category_name.lower().strip()
    
    # Пытаемся использовать LLM для категоризации
    try:
        recognized_category = categorize_transaction(category_name, db, user_id)
        if recognized_category:
            category_to_use = recognized_category
        else:
            # Если LLM не смог определить категорию, используем регулярные выражения
            recognized_category = recognize_category(category_name)
            category_to_use = recognized_category if recognized_category != "другое" else category_name
    except Exception as e:
        logging.error(f"Ошибка при использовании LLM для категоризации: {e}")
        # В случае ошибки используем регулярные выражения
        recognized_category = recognize_category(category_name)
        category_to_use = recognized_category if recognized_category != "другое" else category_name
    
    # Ищем существующую категорию
    category = db.query(Category).filter(
        Category.user_id == user_id,
        func.lower(Category.name) == category_to_use,
        Category.is_expense == (1 if is_expense else 0)
    ).first()
    
    if not category:
        # Создаем новую категорию
        emoji = get_category_emoji(category_to_use)
        category = Category(
            user_id=user_id,
            name=category_to_use,
            emoji=emoji,
            is_expense=1 if is_expense else 0
        )
        db.add(category)
        db.commit()
        db.refresh(category)
        
    return category


def parse_transaction_message(text: str) -> Optional[Dict[str, Any]]:
    """
    Парсит сообщение о транзакции в расширенных форматах.
    
    Поддерживаемые форматы:
    - 500 обед
    - -500 такси
    - +50000 зарплата
    - 100 USD книги
    - 250 ресторан вчера
    - 1500 подарок @иван
    
    Returns:
        Dict с данными о транзакции или None, если не удалось распознать
    """
    try:
        # Разбиваем сообщение на части
        parts = text.strip().split()
        
        if len(parts) < 2:
            return None
        
        # Определяем сумму и знак
        amount_str = parts[0].replace(',', '.')
        is_expense = True
        
        if amount_str.startswith('+'):
            is_expense = False
            amount_str = amount_str[1:]
        elif amount_str.startswith('-'):
            amount_str = amount_str[1:]
        
        # Проверяем, является ли первая часть числом
        try:
            amount = float(amount_str)
        except ValueError:
            return None
        
        # Проверяем валюту (если указана)
        currency = "RUB"  # По умолчанию рубли
        currency_idx = 1
        
        if len(parts) > 1 and parts[1].upper() in ["USD", "EUR", "RUB"]:
            currency = parts[1].upper()
            currency_idx = 2
        
        # Получаем описание транзакции (всё, что после суммы и валюты)
        description = " ".join(parts[currency_idx:])
        
        # Проверяем наличие даты в описании
        date_keywords = ["вчера", "позавчера", "сегодня"]
        transaction_date = datetime.now()
        
        for keyword in date_keywords:
            if keyword in description.lower():
                if keyword == "вчера":
                    transaction_date = datetime.now() - timedelta(days=1)
                elif keyword == "позавчера":
                    transaction_date = datetime.now() - timedelta(days=2)
                # Удаляем ключевое слово даты из описания
                description = description.replace(keyword, "").strip()
                break
        
        # Проверяем наличие упоминания пользователя
        mentioned_user = None
        if "@" in description:
            parts = description.split()
            for part in parts:
                if part.startswith("@"):
                    mentioned_user = part[1:]  # Убираем символ @
                    # Удаляем упоминание пользователя из описания
                    description = description.replace(part, "").strip()
                    break
        
        # Оригинальная сумма (в указанной валюте)
        original_amount = amount
        
        # Конвертируем в рубли, если валюта не рубли (упрощенно)
        if currency == "USD":
            amount *= 90  # Примерный курс
        elif currency == "EUR":
            amount *= 100  # Примерный курс
        
        return {
            "amount": amount,
            "original_amount": original_amount,
            "currency": currency,
            "description": description,
            "date": transaction_date,
            "is_expense": is_expense,
            "mentioned_user": mentioned_user
        }
        
    except Exception as e:
        logging.error(f"Ошибка при парсинге сообщения о транзакции: {e}")
        return None


@router.message(F.text.regexp(r'^(-|\+)?\d+(?:[.,]\d+)?(?:\s+\S+)+$'))
async def process_transaction(message: Message):
    """
    Обрабатывает сообщения о транзакциях в расширенных форматах:
    - 500 обед
    - -500 такси
    - +50000 зарплата
    - 100 USD книги
    - 250 ресторан вчера
    - 1500 подарок @иван
    """
    user_id = message.from_user.id
    
    try:
        # Парсим сообщение
        transaction_data = parse_transaction_message(message.text)
        
        if not transaction_data:
            # Если не удалось распознать транзакцию, возвращаемся к обычному обработчику
            return
        
        # Создаем сессию БД
        db = SessionLocal()
        try:
            # Получаем пользователя из БД
            user = db.query(User).filter(User.telegram_id == user_id).first()
            
            if not user:
                # Если пользователя нет в базе, предлагаем начать с /start
                await message.answer("Для начала работы, пожалуйста, используйте команду /start")
                return
            
            # Определяем стандартные категории
            default_categories = [
                "продукты", "кафе", "рестораны", "транспорт", "такси", 
                "одежда", "развлечения", "здоровье", "связь", "коммуналка", 
                "образование", "спорт", "путешествия", "подарки", "техника",
                "зарплата", "доход", "другое"
            ]
            
            # Получаем список категорий пользователя
            user_categories = db.query(Category).filter(
                Category.user_id == user.id,
                Category.is_expense == (1 if transaction_data["is_expense"] else 0)
            ).all()
            
            # Если у пользователя есть категории, используем их, иначе используем стандартные
            if user_categories:
                categories_list = [category.name for category in user_categories]
            else:
                categories_list = default_categories
            
            # Получаем описание транзакции для определения категории
            description = transaction_data["description"]
            
            # Используем LLM для определения категории на основе описания
            llm_category = categorize_transaction(description, db, user.id)
            
            # Если LLM определила категорию как "другое", предлагаем пользователю уточнить категорию
            if llm_category == "другое":
                # Получаем список доступных категорий для отображения
                categories_text = ", ".join(categories_list)
                
                await message.answer(
                    f"Не удалось точно определить категорию для транзакции: <b>{description}</b>\n\n"
                    f"Пожалуйста, укажите категорию из списка для улучшения категоризации:\n"
                    f"<i>{categories_text}</i>\n\n"
                    f"Или оставьте категорию <b>другое</b>.",
                    parse_mode=ParseMode.HTML
                )
                
                # Добавляем транзакцию с категорией "другое"
                category_name = "другое"
            else:
                # Дополнительная проверка, что категория из LLM находится в списке разрешенных
                if llm_category in categories_list:
                    category_name = llm_category
                else:
                    logging.warning(f"LLM вернула недопустимую категорию: '{llm_category}'. Используем 'другое'")
                    category_name = "другое"
            
            # Получаем или создаем категорию
            category = await get_or_create_category(
                db, 
                user.id, 
                category_name, 
                transaction_data["is_expense"]
            )
            
            # Создаем новую запись о транзакции
            transaction = Transaction(
                user_id=user.id,
                amount=transaction_data["amount"],
                original_amount=transaction_data["original_amount"],
                currency=transaction_data["currency"],
                category_id=category.id,
                description=message.text,
                transaction_date=transaction_data["date"],
                is_expense=1 if transaction_data["is_expense"] else 0,
                mentioned_user=transaction_data["mentioned_user"]
            )
            
            db.add(transaction)
            
            # Для обратной совместимости также добавляем в таблицу expenses
            if transaction_data["is_expense"]:
                expense = ExpenseModel(
                    user_id=user.id,
                    amount=transaction_data["amount"],
                    category=category_name,
                    description=message.text,
                    created_at=transaction_data["date"]
                )
                db.add(expense)
                
            db.commit()
            
            # Округляем сумму до целого, если она целая
            amount = transaction_data["amount"]
            if amount == int(amount):
                amount = int(amount)
            
            # Определяем тип транзакции
            action_text = "потратил" if transaction_data["is_expense"] else "получил"
            
            # Формируем дату для отображения на русском языке
            current_date = datetime.now()
            transaction_date = transaction_data["date"]
            date_str = format_date_russian(transaction_date)
            
            # Получаем имя пользователя для отображения
            user_display_name = user.first_name or user.username or "Пользователь"
            
            # Рассчитываем баланс за текущий месяц
            month_start = datetime(current_date.year, current_date.month, 1)
            
            # Получаем все расходы за месяц
            month_expenses = db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user.id,
                Transaction.is_expense == 1,
                Transaction.transaction_date >= month_start
            ).scalar() or 0
            
            # Получаем все доходы за месяц
            month_incomes = db.query(func.sum(Transaction.amount)).filter(
                Transaction.user_id == user.id,
                Transaction.is_expense == 0,
                Transaction.transaction_date >= month_start
            ).scalar() or 0
            
            # Рассчитываем баланс
            month_balance = month_incomes - month_expenses
            
            # Определяем текущий месяц на русском
            current_month = RUSSIAN_MONTHS[current_date.month]
            
            # Определяем индикатор баланса в зависимости от положительный/отрицательный
            if month_balance < 0:
                balance_indicator = "❗"
                balance_text = f"Баланс за {current_month}: (<b>{abs(month_balance)}</b> ₽)"
            else:
                balance_indicator = "✅"
                balance_text = f"Баланс за {current_month}: <b>{month_balance}</b> ₽"
            
            # Формируем описание транзакции для отображения
            transaction_description = description.lower()
            
            # Отправляем подтверждение в улучшенном стиле
            await message.answer(
                f"{user_display_name} {action_text} <b>{amount}</b> RUB на <b>{category.emoji} {category.name.capitalize()}</b>\n"
                f"{date_str}\n\n"
                f"{transaction_description}\n\n"
                f"{balance_indicator} Баланс за {current_month}: <b>{'-' if month_balance < 0 else ''}{abs(month_balance)}</b> ₽",
                parse_mode=ParseMode.HTML
            )
            
        except Exception as e:
            db.rollback()
            logging.error(f"Ошибка при сохранении транзакции: {e}")
            await message.answer("Произошла ошибка при сохранении транзакции. Попробуйте позже.")
        finally:
            db.close()
            
    except Exception as e:
        logging.error(f"Ошибка при обработке сообщения о транзакции: {e}")
        await message.answer("Произошла ошибка при обработке сообщения. Попробуйте позже.") 