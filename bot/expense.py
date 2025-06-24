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
            
            # Отправляем подтверждение
            await message.answer(
                f"✅ Добавлен расход:\n"
                f"💰 Сумма: <b>{amount:.2f} ₽</b>\n"
                f"🏷️ Категория: <b>{category}</b>",
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
            
            # Отправляем подтверждение
            await message.answer(
                f"✅ Чек успешно обработан:\n"
                f"💰 Сумма: <b>{amount:.2f} ₽</b>\n"
                f"🏷️ Категория: <b>{category}</b>\n\n"
                f"Если данные распознаны неверно, вы можете добавить расход вручную в формате:\n"
                f"<i>-СУММА КАТЕГОРИЯ</i>",
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