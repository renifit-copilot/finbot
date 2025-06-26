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


# Создаем роутер для обработки расходов
router = Router()


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
from sqlalchemy import desc, func


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
            
            # Форматируем сумму в стиле Cointry
            formatted_amount = format_amount(transaction_data["amount"], transaction_data["currency"])
            
            # Определяем тип транзакции
            transaction_type = "расход" if transaction_data["is_expense"] else "доход"
            icon = "➖" if transaction_data["is_expense"] else "➕"
            
            # Формируем дату для отображения
            date_str = ""
            if transaction_data["date"].date() != datetime.now().date():
                date_str = f" ({transaction_data['date'].strftime('%d.%m.%Y')})"
            
            # Формируем упоминание пользователя
            mention_str = ""
            if transaction_data["mentioned_user"]:
                mention_str = f" для @{transaction_data['mentioned_user']}"
            
            # Отправляем подтверждение в стиле Cointry
            await message.answer(
                f"<b>{category.emoji} {category.name.capitalize()}</b>{date_str}{mention_str}\n"
                f"{icon} {formatted_amount} {transaction_data['currency']}",
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