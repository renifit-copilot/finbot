from aiogram import Router, types, F
from aiogram.types import Message, FSInputFile
from aiogram.enums import ParseMode
from sqlalchemy.orm import Session
import re
import os
import uuid
from datetime import datetime
import logging
from core.models import User, Expense as ExpenseModel
from core.db import SessionLocal
from core.ocr import parse_receipt


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
        category = match.group(2).strip().lower()
        
        # Создаем сессию БД
        db = SessionLocal()
        try:
            # Получаем пользователя из БД
            user = db.query(User).filter(User.telegram_id == user_id).first()
            
            if not user:
                # Если пользователя нет в базе, предлагаем начать с /start
                await message.answer("Для начала работы, пожалуйста, используйте команду /start")
                return
            
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
        amount, category = parse_receipt(photo_path)
        
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
from core.models import Category, Transaction


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
    """Возвращает эмодзи для категории"""
    category_name = category_name.lower()
    for key, emoji in CATEGORY_EMOJI.items():
        if key in category_name:
            return emoji
    return "💰"  # Эмодзи по умолчанию


def format_amount(amount: float, currency: str = "RUB") -> str:
    """Форматирует сумму в стиле Cointry"""
    if currency == "RUB":
        return f"`{amount:.2f}`"
    return f"`{amount:.2f} {currency}`"


async def get_or_create_category(db: Session, user_id: int, category_name: str, is_expense: bool = True) -> Category:
    """Получает или создает категорию расходов/доходов"""
    # Нормализация имени категории
    category_name = category_name.lower().strip()
    
    # Ищем существующую категорию
    category = db.query(Category).filter(
        Category.user_id == user_id,
        func.lower(Category.name) == category_name,
        Category.is_expense == (1 if is_expense else 0)
    ).first()
    
    if not category:
        # Создаем новую категорию
        emoji = get_category_emoji(category_name)
        category = Category(
            user_id=user_id,
            name=category_name,
            emoji=emoji,
            is_expense=1 if is_expense else 0
        )
        db.add(category)
        db.commit()
        db.refresh(category)
        
    return category


def parse_transaction_message(text: str) -> Dict:
    """
    Парсит сообщение о транзакции и извлекает детали.
    
    Форматы:
    - [сумма] [категория] - расход
    - +[сумма] [категория] - доход
    - [сумма] [валюта] [категория] - расход с указанием валюты
    - [сумма] [категория] [дата] - расход с указанием даты
    - [сумма] [категория] @[пользователь] - расход с указанием пользователя
    """
    result = {
        "amount": 0.0,
        "original_amount": None,
        "currency": "RUB",
        "category": "другое",
        "is_expense": True,
        "date": datetime.now(),
        "mentioned_user": None,
    }
    
    # Удаляем лишние пробелы и бэктики
    text = text.strip().replace('`', '')
    
    # Проверяем, является ли это доходом или расходом
    if text.startswith('+'):
        result["is_expense"] = False
        text = text[1:]  # Убираем символ +
    
    # Парсим сумму (обязательное поле)
    amount_match = re.search(AMOUNT_PATTERN, text)
    if not amount_match:
        return None
    
    amount_str = amount_match.group(1).replace(',', '.')
    result["amount"] = abs(float(amount_str))  # Всегда храним положительное число
    
    # Убираем сумму из текста
    text = text.replace(amount_match.group(0), '', 1).strip()
    
    # Парсим валюту (опциональное поле)
    currency_match = re.search(CURRENCY_PATTERN, text)
    if currency_match:
        result["currency"] = currency_match.group(1).upper()
        # Убираем валюту из текста
        text = text.replace(currency_match.group(0), '', 1).strip()
        # Сохраняем оригинальную сумму перед конвертацией
        result["original_amount"] = result["amount"]
    
    # Парсим упоминание пользователя (опциональное поле)
    if "@" in text:
        at_index = text.find('@')
        if at_index >= 0:
            # Извлекаем имя пользователя, предполагая, что оно заканчивается пробелом или концом строки
            user_end = text.find(' ', at_index)
            if user_end == -1:  # Если пробела после @ нет, значит имя до конца строки
                user_end = len(text)
            username = text[at_index+1:user_end]
            result["mentioned_user"] = username
            
            # Убираем упоминание из текста
            text = text.replace("@" + username, '', 1).strip()
    
    # Парсим дату (опциональное поле)
    date_match = re.search(DATE_PATTERN, text)
    if date_match:
        date_str = date_match.group(1)
        try:
            if date_str == "вчера":
                result["date"] = datetime.now() - timedelta(days=1)
            elif date_str == "позавчера":
                result["date"] = datetime.now() - timedelta(days=2)
            elif '.' in date_str:  # Формат DD.MM.YYYY или DD.MM.YY
                parts = date_str.split('.')
                day = int(parts[0])
                month = int(parts[1])
                year = int(parts[2])
                if year < 100:  # Если год двузначный
                    year += 2000
                result["date"] = datetime(year, month, day)
            elif '-' in date_str:  # Формат YYYY-MM-DD
                parts = date_str.split('-')
                year = int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                result["date"] = datetime(year, month, day)
        except (ValueError, IndexError):
            # В случае ошибки при парсинге даты, используем текущую дату
            pass
        
        # Убираем дату из текста
        text = text.replace(date_match.group(0), '', 1).strip()
    
    # Оставшийся текст считаем категорией/описанием
    if text:
        result["category"] = text
        
    return result


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
            
            # Получаем или создаем категорию
            category = await get_or_create_category(
                db, 
                user.id, 
                transaction_data["category"], 
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
                    category=transaction_data["category"],
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