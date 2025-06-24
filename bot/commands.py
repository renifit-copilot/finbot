from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import logging
from core.models import User, Expense
from core.db import SessionLocal
from core.llm import get_advice


# Создаем роутер для команд
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """
    Обрабатывает команду /start:
    - Приветствует пользователя
    - Создает запись в БД, если пользователь новый
    """
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    
    # Создаем сессию БД
    db = SessionLocal()
    try:
        # Проверяем, существует ли пользователь
        user = db.query(User).filter(User.telegram_id == user_id).first()
        
        if not user:
            # Создаем нового пользователя
            user = User(
                telegram_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            db.add(user)
            db.commit()
            logging.info(f"Создан новый пользователь: {user_id}")
        
        # Отправляем приветственное сообщение
        await message.answer(
            f"👋 Привет, {first_name or username or 'друг'}!\n\n"
            f"Я твой персональный финансовый бот. Помогу тебе отслеживать расходы и экономить деньги.\n\n"
            f"🧮 <b>Как добавить трату:</b>\n"
            f"• Напиши сумму и категорию, например: <i>-500 кофе</i>\n"
            f"• Отправь фото чека, и я распознаю сумму\n\n"
            f"📊 <b>Команды:</b>\n"
            f"• /help — справка по боту\n"
            f"• /summary — сводка по тратам\n\n"
            f"Давай начнем учет финансов вместе!",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /start: {e}")
        await message.answer("Произошла ошибка при запуске бота. Попробуйте позже.")
    finally:
        db.close()


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обрабатывает команду /help"""
    await message.answer(
        "📝 <b>Справка по использованию бота:</b>\n\n"
        "🧮 <b>Добавление расходов:</b>\n"
        "• <i>-СУММА КАТЕГОРИЯ</i> — добавить трату\n"
        "   Например: <i>-150 кофе</i> или <i>-2500 продукты</i>\n"
        "• Отправьте фото чека для автоматического распознавания\n\n"
        "📊 <b>Команды:</b>\n"
        "• /summary — сводка по расходам за день, неделю и месяц\n"
        "• /start — перезапустить бота\n"
        "• /help — показать эту справку\n\n"
        "Все данные хранятся локально и доступны только вам.",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("summary"))
async def cmd_summary(message: Message):
    """
    Обрабатывает команду /summary:
    - Показывает сводку по расходам за день, неделю и месяц
    - Добавляет совет по финансам
    """
    user_id = message.from_user.id
    
    # Создаем сессию БД
    db = SessionLocal()
    try:
        # Получаем пользователя из БД
        user = db.query(User).filter(User.telegram_id == user_id).first()
        
        if not user:
            await message.answer("Для начала работы, пожалуйста, используйте команду /start")
            return
        
        # Получаем текущую дату и время
        now = datetime.now()
        today_start = datetime(now.year, now.month, now.day)
        week_start = today_start - timedelta(days=now.weekday())
        month_start = datetime(now.year, now.month, 1)
        
        # Запрашиваем расходы за разные периоды
        day_expenses = db.query(Expense).filter(
            Expense.user_id == user.id,
            Expense.created_at >= today_start
        ).all()
        
        week_expenses = db.query(Expense).filter(
            Expense.user_id == user.id,
            Expense.created_at >= week_start
        ).all()
        
        month_expenses = db.query(Expense).filter(
            Expense.user_id == user.id,
            Expense.created_at >= month_start
        ).all()
        
        # Считаем суммы расходов
        day_sum = sum(expense.amount for expense in day_expenses)
        week_sum = sum(expense.amount for expense in week_expenses)
        month_sum = sum(expense.amount for expense in month_expenses)
        
        # Получаем совет от LLM
        advice = get_advice(user_id, db)
        
        # Формируем сообщение
        await message.answer(
            f"📊 <b>Сводка по расходам:</b>\n\n"
            f"Сегодня: <b>{day_sum:.2f} ₽</b>\n"
            f"Неделя: <b>{week_sum:.2f} ₽</b>\n"
            f"Месяц: <b>{month_sum:.2f} ₽</b>\n\n"
            f"💡 <i>{advice}</i>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /summary: {e}")
        await message.answer("Произошла ошибка при формировании отчета. Попробуйте позже.")
    finally:
        db.close() 