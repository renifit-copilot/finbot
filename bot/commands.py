from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import logging
from core.models import User, Expense, Transaction, Category, CategoryCache
from core.db import SessionLocal
from core.llm import get_advice, update_category_cache
from sqlalchemy import func, desc, and_, extract
import calendar
from collections import defaultdict
from aiogram.utils.markdown import code
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import matplotlib.pyplot as plt
import io
import os
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Tuple


# Создаем роутер для команд
router = Router()


class FeedbackStates(StatesGroup):
    """Состояния для процесса обратной связи по категоризации"""
    waiting_for_category = State()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """
    Обрабатывает команду /start:
    - Приветствует пользователя
    - Создает запись в БД, если пользователь новый
    - Предоставляет полную справку по использованию бота
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
        
        # Отправляем приветственное сообщение с полной справкой
        await message.answer(
            f"👋 <b>Привет, {first_name or username or 'друг'}! Я помошник Finbot! </b>\n\n"
            f"<b>Просто напишите мне свои расходы в следующем формате, и я запишу их:</b>\n\n"
            f"<blockquote>[сколько] [на что]</blockquote>\n\n"
            f"Например:\n"
            f"<blockquote>2500 продукты</blockquote>\n\n"
            f"А чтобы записать доход, добавьте впереди + без пробела:\n"
            f"<blockquote>+10000 аванс</blockquote>\n\n"
            f"Добавить или изменить категории можно командой <b>Категории</b> или /categories.\n\n"
            f"Получить статистику доходов и расходов можно командой <b>Статистика</b> или /stats.\n\n"
            f"Для удаления последней записи, отправьте команду <b>Удалить</b> или /delete.\n\n"
            f"Краткую сводку по расходам можно получить командой <b>Отчет</b> или /summary.\n\n"
            f"Посмотреть все записи можно командой /list или открыв мини-приложение /open.\n\n"
            f"Для обучения бота правильной категоризации используйте команду /learn товар категория.\n\n"
            f"Все данные хранятся локально и доступны только вам.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /start: {e}")
        await message.answer("Произошла ошибка при запуске бота. Попробуйте позже.")
    finally:
        db.close()


# Создаем алиас для команды /help, чтобы она вызывала тот же обработчик, что и /start
@router.message(Command("help"))
async def cmd_help(message: Message):
    """Алиас для команды /start"""
    await cmd_start(message)


@router.message(Command("summary"))
async def cmd_summary(message: Message):
    """
    Обрабатывает команду /summary:
    - Показывает сводку по расходам за день, неделю и месяц
    - Добавляет визуализацию прогресса по бюджету
    - Показывает тенденцию расходов (рост/снижение)
    - Добавляет персонализированный совет по финансам
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
        yesterday_start = today_start - timedelta(days=1)
        week_start = today_start - timedelta(days=now.weekday())
        prev_week_start = week_start - timedelta(days=7)
        month_start = datetime(now.year, now.month, 1)
        
        # Запрашиваем расходы за текущие периоды
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
        
        # Запрашиваем расходы за предыдущие периоды для сравнения
        yesterday_expenses = db.query(Expense).filter(
            Expense.user_id == user.id,
            Expense.created_at >= yesterday_start,
            Expense.created_at < today_start
        ).all()
        
        prev_week_expenses = db.query(Expense).filter(
            Expense.user_id == user.id,
            Expense.created_at >= prev_week_start,
            Expense.created_at < week_start
        ).all()
        
        # Считаем суммы расходов
        day_sum = sum(expense.amount for expense in day_expenses)
        yesterday_sum = sum(expense.amount for expense in yesterday_expenses)
        week_sum = sum(expense.amount for expense in week_expenses)
        prev_week_sum = sum(expense.amount for expense in prev_week_expenses)
        month_sum = sum(expense.amount for expense in month_expenses)
        
        # Рассчитываем средние значения
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        days_passed = now.day
        
        # Прогнозируем расходы на месяц, если прошло хотя бы 3 дня
        monthly_forecast = 0
        if days_passed >= 3:
            daily_avg = month_sum / days_passed
            monthly_forecast = daily_avg * days_in_month
        
        # Определяем тенденции (рост/снижение)
        day_trend = "➡️" # нейтральный тренд по умолчанию
        if yesterday_sum > 0:
            day_trend = "📉" if day_sum < yesterday_sum else "📈" if day_sum > yesterday_sum else "➡️"
            
        week_trend = "➡️"
        if prev_week_sum > 0:
            week_trend = "📉" if week_sum < prev_week_sum else "📈" if week_sum > prev_week_sum else "➡️"
        
        # Создаем визуальный прогресс по месячному бюджету
        # Предположим, что месячный бюджет - это прогноз или 2x от текущих расходов, если прогноза нет
        monthly_budget = monthly_forecast if monthly_forecast > 0 else month_sum * 2
        if monthly_budget == 0:  # Если нет расходов, установим минимальный бюджет
            monthly_budget = 10000
            
        progress_percent = min(100, int((month_sum / monthly_budget) * 100))
        
        # Создаем визуальный индикатор прогресса
        progress_bar_length = 10
        filled_blocks = int((progress_percent / 100) * progress_bar_length)
        progress_bar = "█" * filled_blocks + "▒" * (progress_bar_length - filled_blocks)
        
        # Получаем совет от LLM
        advice = get_advice(user_id, db)
        
        # Форматируем суммы
        day_formatted = f"{day_sum:.2f}"
        week_formatted = f"{week_sum:.2f}"
        month_formatted = f"{month_sum:.2f}"
        forecast_formatted = f"{monthly_forecast:.2f}" if monthly_forecast > 0 else "N/A"
        
        # Формируем сообщение
        await message.answer(
            f"<b>ФИНАНСОВАЯ СВОДКА</b>\n\n"
            f"<b>Сегодня:</b> {day_trend} <code>{day_formatted}</code> ₽\n"
            f"<b>Неделя:</b> {week_trend} <code>{week_formatted}</code> ₽\n"
            f"<b>Месяц:</b> <code>{month_formatted}</code> ₽\n\n"
            f"<b>Прогресс по бюджету:</b> {progress_percent}%\n"
            f"<code>{progress_bar}</code>\n\n"
            f"<b>Прогноз на месяц:</b> <code>{forecast_formatted}</code> ₽\n\n"
            f"<blockquote>{advice}</blockquote>\n\n"
            f"<i>Используйте /stats для подробной статистики</i>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /summary: {e}")
        await message.answer("Произошла ошибка при формировании отчета. Попробуйте позже.")
    finally:
        db.close()


def format_amount_markdown(amount: float, currency: str = "₽") -> str:
    """Форматирует сумму в стиле Cointry с кодовыми блоками Markdown"""
    return f"`{amount:.2f}`"


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """
    Обрабатывает команду /stats или /statistics:
    - Показывает расширенную статистику по расходам и доходам
    - Группировка по категориям с визуализацией
    - Сравнение с предыдущими периодами
    - Анализ трендов расходов
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
        month_start = datetime(now.year, now.month, 1)
        
        # Определяем начало предыдущего месяца
        if now.month == 1:
            prev_month_start = datetime(now.year - 1, 12, 1)
            prev_month_end = datetime(now.year, 1, 1)
        else:
            prev_month_start = datetime(now.year, now.month - 1, 1)
            prev_month_end = month_start
        
        # Запрашиваем расходы и доходы за текущий месяц
        current_transactions = db.query(
            Transaction, 
            Category.name.label('category_name'), 
            Category.emoji.label('category_emoji')
        ).join(
            Category, 
            Transaction.category_id == Category.id,
            isouter=True
        ).filter(
            Transaction.user_id == user.id,
            Transaction.transaction_date >= month_start
        ).order_by(desc(Transaction.transaction_date)).all()
        
        # Запрашиваем расходы и доходы за предыдущий месяц для сравнения
        prev_transactions = db.query(
            Transaction, 
            Category.name.label('category_name'), 
            Category.emoji.label('category_emoji')
        ).join(
            Category, 
            Transaction.category_id == Category.id,
            isouter=True
        ).filter(
            Transaction.user_id == user.id,
            Transaction.transaction_date >= prev_month_start,
            Transaction.transaction_date < prev_month_end
        ).all()
        
        # Группируем текущие расходы по категориям
        expenses_by_category = defaultdict(float)
        expenses_total = 0
        income_by_category = defaultdict(float)
        income_total = 0
        
        for tx, cat_name, cat_emoji in current_transactions:
            category_name = cat_name or "другое"
            category_emoji = cat_emoji or "💰"
            
            if tx.is_expense == 1:  # Расход
                expenses_by_category[(category_name, category_emoji)] += tx.amount
                expenses_total += tx.amount
            else:  # Доход
                income_by_category[(category_name, category_emoji)] += tx.amount
                income_total += tx.amount
        
        # Группируем предыдущие расходы по категориям для сравнения
        prev_expenses_by_category = defaultdict(float)
        prev_expenses_total = 0
        prev_income_total = 0
        
        for tx, cat_name, cat_emoji in prev_transactions:
            category_name = cat_name or "другое"
            category_emoji = cat_emoji or "💰"
            
            if tx.is_expense == 1:  # Расход
                prev_expenses_by_category[(category_name, category_emoji)] += tx.amount
                prev_expenses_total += tx.amount
            else:  # Доход
                prev_income_total += tx.amount
        
        # Создаем ответное сообщение
        month_name = calendar.month_name[now.month]
        prev_month_name = calendar.month_name[prev_month_start.month]
        
        response_parts = [f"<b>СТАТИСТИКА ЗА {month_name.upper()}</b>\n"]
        
        # Добавляем сводку по текущему месяцу
        response_parts.append("<b>ОБЩАЯ СВОДКА:</b>")
        
        # Сравниваем с предыдущим месяцем
        expense_change = 0
        expense_change_percent = 0
        if prev_expenses_total > 0:
            expense_change = expenses_total - prev_expenses_total
            expense_change_percent = (expense_change / prev_expenses_total) * 100
        
        expense_trend = "➡️"
        if expense_change_percent > 5:
            expense_trend = "📈"
        elif expense_change_percent < -5:
            expense_trend = "📉"
        
        income_change = 0
        income_change_percent = 0
        if prev_income_total > 0:
            income_change = income_total - prev_income_total
            income_change_percent = (income_change / prev_income_total) * 100
        
        income_trend = "➡️"
        if income_change_percent > 5:
            income_trend = "📈"
        elif income_change_percent < -5:
            income_trend = "📉"
        
        # Добавляем сравнение с прошлым месяцем
        response_parts.append(
            f"• Расходы: <code>{expenses_total:.2f}</code> ₽ {expense_trend}\n"
            f"• Доходы: <code>{income_total:.2f}</code> ₽ {income_trend}\n"
            f"• Баланс: <code>{income_total - expenses_total:.2f}</code> ₽\n"
        )
        
        if prev_expenses_total > 0 or prev_income_total > 0:
            response_parts.append(
                f"<i>По сравнению с {prev_month_name}:</i>\n"
                f"• Расходы: {'+' if expense_change >= 0 else ''}{expense_change:.2f} ₽ ({'+' if expense_change_percent >= 0 else ''}{expense_change_percent:.1f}%)\n"
                f"• Доходы: {'+' if income_change >= 0 else ''}{income_change:.2f} ₽ ({'+' if income_change_percent >= 0 else ''}{income_change_percent:.1f}%)\n"
            )
        
        # Добавляем расходы по категориям с визуализацией
        if expenses_total > 0:
            response_parts.append("\n<b>РАСХОДЫ ПО КАТЕГОРИЯМ:</b>")
            
            # Сортируем категории по убыванию сумм
            sorted_expenses = sorted(
                expenses_by_category.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            # Создаем визуализацию для топ-5 категорий
            top_categories = sorted_expenses[:5]
            max_amount = top_categories[0][1] if top_categories else 0
            
            for (category_name, category_emoji), amount in top_categories:
                percentage = (amount / expenses_total) * 100
                bar_length = int((amount / max_amount) * 10) if max_amount > 0 else 0
                bar = "█" * bar_length + "▒" * (10 - bar_length)
                
                # Получаем изменение по сравнению с прошлым месяцем
                prev_amount = prev_expenses_by_category.get((category_name, category_emoji), 0)
                change_str = ""
                if prev_amount > 0:
                    change = amount - prev_amount
                    change_percent = (change / prev_amount) * 100
                    change_symbol = "↗️" if change > 0 else "↘️" if change < 0 else "↔️"
                    change_str = f" {change_symbol} {change_percent:.1f}%"
                
                response_parts.append(
                    f"{category_emoji} {category_name.capitalize()}: <code>{amount:.2f}</code> ₽ ({percentage:.1f}%){change_str}\n"
                    f"<code>{bar}</code>"
                )
            
            # Если есть еще категории, добавляем их в сокращенном виде
            if len(sorted_expenses) > 5:
                other_sum = sum(amount for (_, _), amount in sorted_expenses[5:])
                other_percentage = (other_sum / expenses_total) * 100
                response_parts.append(f"\nДругие категории: <code>{other_sum:.2f}</code> ₽ ({other_percentage:.1f}%)")
        
        # Добавляем доходы
        if income_total > 0:
            response_parts.append("\n<b>ДОХОДЫ:</b>")
            
            sorted_income = sorted(
                income_by_category.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            for (category_name, category_emoji), amount in sorted_income:
                percentage = (amount / income_total) * 100
                response_parts.append(f"{category_emoji} {category_name.capitalize()}: <code>{amount:.2f}</code> ₽ ({percentage:.1f}%)")
        
        # Добавляем дневную статистику
        days_passed = now.day
        avg_daily_expense = expenses_total / days_passed if days_passed > 0 else 0
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        days_left = days_in_month - days_passed
        
        response_parts.append(
            f"\n<b>ДНЕВНАЯ СТАТИСТИКА:</b>\n"
            f"• В среднем за день: <code>{avg_daily_expense:.2f}</code> ₽\n"
            f"• Дней прошло: {days_passed} из {days_in_month}\n"
            f"• Прогноз на месяц: <code>{avg_daily_expense * days_in_month:.2f}</code> ₽"
        )
        
        # Добавляем советы по оптимизации расходов
        if expenses_total > 0:
            # Находим категорию с наибольшим ростом расходов
            biggest_increase = None
            biggest_increase_percent = 0
            
            for (category_name, category_emoji), amount in expenses_by_category.items():
                prev_amount = prev_expenses_by_category.get((category_name, category_emoji), 0)
                if prev_amount > 0:
                    change_percent = ((amount - prev_amount) / prev_amount) * 100
                    if change_percent > biggest_increase_percent:
                        biggest_increase = (category_name, category_emoji)
                        biggest_increase_percent = change_percent
            
            if biggest_increase and biggest_increase_percent > 20:
                category_name, category_emoji = biggest_increase
                response_parts.append(
                    f"\n💡 <i>Совет: Обратите внимание на категорию {category_emoji} {category_name.capitalize()} — "
                    f"расходы выросли на {biggest_increase_percent:.1f}% по сравнению с прошлым месяцем</i>"
                )
        
        await message.answer("\n".join(response_parts), parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /stats: {e}")
        await message.answer("Произошла ошибка при формировании статистики. Попробуйте позже.")
    finally:
        db.close()


@router.message(Command("list"))
async def cmd_list_transactions(message: Message):
    """
    Обрабатывает команду /list:
    - Показывает список последних транзакций
    - Группирует транзакции по дням
    - Отображает итоги за каждый день
    """
    user_id = message.from_user.id
    limit = 15  # Увеличиваем количество транзакций для отображения
    
    # Создаем сессию БД
    db = SessionLocal()
    try:
        # Получаем пользователя из БД
        user = db.query(User).filter(User.telegram_id == user_id).first()
        
        if not user:
            await message.answer("Для начала работы, пожалуйста, используйте команду /start")
            return
        
        # Запрашиваем последние транзакции
        transactions = db.query(
            Transaction, 
            Category.name.label('category_name'), 
            Category.emoji.label('category_emoji')
        ).join(
            Category, 
            Transaction.category_id == Category.id,
            isouter=True
        ).filter(
            Transaction.user_id == user.id
        ).order_by(desc(Transaction.transaction_date)).limit(limit).all()
        
        if not transactions:
            await message.answer("У вас пока нет записанных транзакций.")
            return
        
        # Группируем транзакции по дням
        transactions_by_day = {}
        for tx, cat_name, cat_emoji in transactions:
            date_key = tx.transaction_date.strftime("%Y-%m-%d")
            date_display = tx.transaction_date.strftime("%d.%m.%Y")
            
            if date_key not in transactions_by_day:
                transactions_by_day[date_key] = {
                    "display_date": date_display,
                    "transactions": [],
                    "expenses": 0,
                    "income": 0
                }
            
            category_name = cat_name or "другое"
            category_emoji = cat_emoji or "💰"
            
            # Определяем тип транзакции и добавляем к соответствующей сумме
            if tx.is_expense == 1:
                transactions_by_day[date_key]["expenses"] += tx.amount
            else:
                transactions_by_day[date_key]["income"] += tx.amount
            
            # Добавляем данные о транзакции
            transactions_by_day[date_key]["transactions"].append({
                "id": tx.id,
                "amount": tx.amount,
                "currency": tx.currency,
                "category_name": category_name,
                "category_emoji": category_emoji,
                "is_expense": tx.is_expense == 1,
                "description": tx.description
            })
        
        # Формируем сообщение
        response = ["<b>ИСТОРИЯ ТРАНЗАКЦИЙ</b>\n"]
        
        # Добавляем транзакции по дням
        for date_key, day_data in transactions_by_day.items():
            # Добавляем заголовок дня
            day_balance = day_data["income"] - day_data["expenses"]
            balance_sign = "+" if day_balance >= 0 else "-"
            balance_emoji = "📈" if day_balance >= 0 else "📉"
            
            response.append(
                f"\n<b>{day_data['display_date']} {balance_emoji}</b>\n\n"
                f"<i>Расходы: <code>{day_data['expenses']:.2f}</code> ₽ • "
                f"Доходы: <code>{day_data['income']:.2f}</code> ₽ • "
                f"Баланс: <code>{balance_sign}{abs(day_balance):.2f}</code> ₽</i>\n"
            )
            
            # Добавляем транзакции за день
            for tx in day_data["transactions"]:
                icon = "➖" if tx["is_expense"] else "➕"
                amount_str = f"{tx['amount']:.2f}"
                
                response.append(
                    f"{icon} {tx['category_emoji']} <b>{tx['category_name'].capitalize()}</b>: "
                    f"<code>{amount_str}</code> {tx['currency']}"
                )
        
        # Добавляем подсказку для фильтрации
        response.append(
            f"\n<i>Используйте /list [категория] для фильтрации по категории</i>\n"
            f"<i>Например: /list продукты или /list кафе</i>"
        )
        
        await message.answer("\n".join(response), parse_mode=ParseMode.HTML)
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /list: {e}")
        await message.answer("Произошла ошибка при получении списка транзакций. Попробуйте позже.")
    finally:
        db.close()


@router.message(Command("delete"))
async def cmd_delete_last(message: Message):
    """
    Обрабатывает команду /delete:
    - Показывает последние транзакции для выбора
    - Предлагает удалить последнюю или выбрать конкретную
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
        
        # Находим последние транзакции пользователя (до 5 штук)
        recent_transactions = db.query(
            Transaction, 
            Category.name.label('category_name'), 
            Category.emoji.label('category_emoji')
        ).join(
            Category, 
            Transaction.category_id == Category.id,
            isouter=True
        ).filter(
            Transaction.user_id == user.id
        ).order_by(desc(Transaction.created_at)).limit(5).all()
        
        if not recent_transactions:
            await message.answer("У вас нет транзакций для удаления.")
            return
        
        # Создаем клавиатуру с кнопками для выбора транзакции
        builder = InlineKeyboardBuilder()
        
        # Добавляем кнопку для удаления последней транзакции
        last_tx, last_cat_name, last_cat_emoji = recent_transactions[0]
        last_category_name = last_cat_name or "другое"
        last_category_emoji = last_cat_emoji or "💰"
        
        builder.button(
            text=f"Удалить последнюю: {last_category_emoji} {last_category_name} ({last_tx.amount} {last_tx.currency})",
            callback_data=f"delete_confirm:{last_tx.id}"
        )
        
        # Добавляем кнопки для других недавних транзакций
        for tx, cat_name, cat_emoji in recent_transactions:
            category_name = cat_name or "другое"
            category_emoji = cat_emoji or "💰"
            date_str = tx.transaction_date.strftime("%d.%m")
            
            # Пропускаем первую (последнюю) транзакцию, так как она уже добавлена выше
            if tx.id == last_tx.id:
                continue
                
            builder.button(
                text=f"{date_str}: {category_emoji} {category_name} ({tx.amount} {tx.currency})",
                callback_data=f"delete_tx:{tx.id}"
            )
        
        # Добавляем кнопку отмены
        builder.button(
            text="❌ Отмена",
            callback_data="delete_cancel"
        )
        
        # Располагаем кнопки в столбик
        builder.adjust(1)
        
        await message.answer(
            "🗑️ <b>УДАЛЕНИЕ ТРАНЗАКЦИЙ</b>\n\n"
            "Выберите транзакцию, которую хотите удалить:",
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Ошибка при подготовке к удалению транзакции: {e}")
        await message.answer("Произошла ошибка при подготовке к удалению. Попробуйте позже.")
    finally:
        db.close()


@router.callback_query(F.data.startswith("delete_tx:"))
async def process_delete_selection(callback: CallbackQuery):
    """Обрабатывает выбор транзакции для удаления"""
    # Извлекаем ID транзакции из callback_data
    tx_id = int(callback.data.split(":")[1])
    
    # Создаем клавиатуру для подтверждения
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Да, удалить",
        callback_data=f"delete_confirm:{tx_id}"
    )
    builder.button(
        text="❌ Отмена",
        callback_data="delete_cancel"
    )
    builder.adjust(2)
    
    await callback.message.edit_text(
        "❓ <b>Подтверждение удаления</b>\n\n"
        "Вы уверены, что хотите удалить эту транзакцию?",
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data.startswith("delete_confirm:"))
async def process_delete_confirm(callback: CallbackQuery):
    """Обрабатывает подтверждение удаления транзакции"""
    # Извлекаем ID транзакции из callback_data
    tx_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    # Создаем сессию БД
    db = SessionLocal()
    try:
        # Получаем пользователя из БД
        user = db.query(User).filter(User.telegram_id == user_id).first()
        
        if not user:
            await callback.message.edit_text("Для начала работы, пожалуйста, используйте команду /start")
            return
        
        # Находим транзакцию по ID
        transaction = db.query(Transaction).filter(
            Transaction.id == tx_id,
            Transaction.user_id == user.id
        ).first()
        
        if not transaction:
            await callback.message.edit_text("Транзакция не найдена или уже была удалена.")
            return
        
        # Получаем категорию, если она есть
        category = db.query(Category).filter(
            Category.id == transaction.category_id
        ).first() if transaction.category_id else None
        
        # Сохраняем данные для подтверждения
        amount = transaction.amount
        category_name = category.name if category else "другое"
        category_emoji = category.emoji if category else "💰"
        currency = transaction.currency
        is_expense = transaction.is_expense == 1
        
        # Удаляем запись из БД
        db.delete(transaction)
        
        # Если это был расход, также удаляем соответствующую запись из таблицы expenses
        # для обратной совместимости
        if is_expense:
            expense = db.query(Expense).filter(
                Expense.user_id == user.id,
                Expense.created_at == transaction.transaction_date
            ).first()
            
            if expense:
                db.delete(expense)
        
        db.commit()
        
        # Определяем тип транзакции для сообщения
        transaction_type = "расход" if is_expense else "доход"
        
        # Отправляем подтверждение об удалении
        await callback.message.edit_text(
            f"✅ <b>Транзакция удалена</b>\n\n"
            f"<b>{category_emoji} {category_name.capitalize()}</b>\n"
            f"{'➖' if is_expense else '➕'} <code>{amount:.2f}</code> {currency}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        db.rollback()
        logging.error(f"Ошибка при удалении транзакции: {e}")
        await callback.message.edit_text("Произошла ошибка при удалении записи. Попробуйте позже.")
    finally:
        db.close()


@router.callback_query(F.data == "delete_cancel")
async def process_delete_cancel(callback: CallbackQuery):
    """Обрабатывает отмену удаления транзакции"""
    await callback.message.edit_text(
        "❌ <b>Удаление отменено</b>\n\n"
        "Транзакция не была удалена.",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("categories"))
async def cmd_categories(message: Message):
    """
    Показывает список доступных категорий с эмодзи,
    сгруппированных по типам для удобства использования
    """
    from bot.expense import recognize_category, get_category_emoji
    
    # Группируем категории по типам
    category_groups = {
        "🍔 Питание": {
            "продукты": "🛒 Продукты (магазины, супермаркеты)",
            "кафе": "☕ Кафе (кофейни, пекарни)",
            "рестораны": "🍽️ Рестораны (бары, фастфуд)"
        },
        "🚌 Транспорт": {
            "транспорт": "🚗 Транспорт (общественный транспорт)",
            "такси": "🚕 Такси (поездки)"
        },
        "👚 Шоппинг": {
            "одежда": "👕 Одежда (магазины одежды)",
            "обувь": "👟 Обувь (магазины обуви)"
        },
        "🏠 Дом и быт": {
            "коммуналка": "🏠 Коммуналка (ЖКХ, аренда)",
            "связь": "📱 Связь (телефон, интернет)",
            "бытовая химия": "🧼 Бытовая химия (моющие средства)"
        },
        "🎮 Досуг": {
            "развлечения": "🎮 Развлечения (игры, кино, концерты)"
        },
        "🧠 Личное развитие": {
            "образование": "📚 Образование (курсы, книги)",
            "здоровье": "💊 Здоровье (аптека, врач)",
            "канцтовары": "✏️ Канцтовары (ручки, бумага)"
        }
    }
    
    # Формируем сообщение со списком категорий
    message_text = "📋 <b>ДОСТУПНЫЕ КАТЕГОРИИ</b>\n\n"
    
    # Добавляем категории по группам
    for group_name, categories in category_groups.items():
        message_text += f"<b>{group_name}</b>\n"
        
        for key, description in categories.items():
            message_text += f"  • {description}\n"
        
        message_text += "\n"
    
    # Добавляем инструкцию по использованию
    message_text += (
        "<b>КАК ИСПОЛЬЗОВАТЬ:</b>\n"
        "• Просто укажите категорию при добавлении расхода\n"
        "• Пример: <code>500 продукты</code> или <code>250 кафе</code>\n"
        "• Бот автоматически определит категорию по ключевым словам\n\n"
        "<i>Вы также можете создавать свои категории, просто используя их в транзакциях</i>"
    )
    
    await message.answer(message_text, parse_mode=ParseMode.HTML)


@router.message(Command("advice"))
async def cmd_advice(message: Message):
    """
    Обрабатывает команду /advice
    Отправляет финансовый совет на основе расходов пользователя
    """
    user_id = message.from_user.id
    
    # Создаем сессию БД
    db = SessionLocal()
    try:
        # Получаем совет
        advice = get_advice(user_id, db)
        
        # Отправляем совет
        await message.answer(
            f"💡 <b>Финансовый совет:</b>\n\n{advice}",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /advice: {e}")
        await message.answer("Произошла ошибка при получении совета. Попробуйте позже.")
    finally:
        db.close()


@router.message(Command("feedback"))
async def cmd_feedback(message: Message, state: FSMContext):
    """
    Обрабатывает команду /feedback
    Запускает процесс обратной связи по категоризации последней транзакции
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
        
        # Получаем последнюю транзакцию пользователя
        last_transaction = db.query(Transaction).filter(
            Transaction.user_id == user.id
        ).order_by(Transaction.created_at.desc()).first()
        
        if not last_transaction:
            await message.answer("У вас пока нет транзакций для обратной связи.")
            return
        
        # Получаем текущую категорию
        current_category = db.query(Category).filter(
            Category.id == last_transaction.category_id
        ).first()
        
        if not current_category:
            await message.answer("Не удалось найти категорию последней транзакции.")
            return
        
        # Получаем все категории пользователя
        user_categories = db.query(Category).filter(
            Category.user_id == user.id,
            Category.is_expense == last_transaction.is_expense
        ).all()
        
        # Создаем клавиатуру с категориями
        keyboard = InlineKeyboardMarkup(row_width=2)
        buttons = []
        
        for category in user_categories:
            # Помечаем текущую категорию звездочкой
            label = f"{category.emoji} {category.name.capitalize()}"
            if category.id == current_category.id:
                label += " ✓"
                
            buttons.append(InlineKeyboardButton(
                text=label, 
                callback_data=f"cat_{category.id}"
            ))
        
        keyboard.add(*buttons)
        
        # Сохраняем ID транзакции в состоянии
        await state.update_data(transaction_id=last_transaction.id)
        
        # Формируем сообщение
        message_text = (
            f"📝 <b>Обратная связь по категоризации</b>\n\n"
            f"Транзакция: <code>{last_transaction.description}</code>\n"
            f"Текущая категория: <b>{current_category.emoji} {current_category.name.capitalize()}</b>\n\n"
            f"Выберите правильную категорию:"
        )
        
        await message.answer(message_text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        
        # Устанавливаем состояние ожидания выбора категории
        await state.set_state(FeedbackStates.waiting_for_category)
        
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /feedback: {e}")
        await message.answer("Произошла ошибка при запуске обратной связи. Попробуйте позже.")
    finally:
        db.close()


@router.callback_query(F.data.startswith("cat_"), FeedbackStates.waiting_for_category)
async def process_category_feedback(callback_query: types.CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор категории в процессе обратной связи
    """
    # Получаем ID категории из callback_data
    category_id = int(callback_query.data.split("_")[1])
    
    # Получаем ID транзакции из состояния
    data = await state.get_data()
    transaction_id = data.get("transaction_id")
    
    if not transaction_id:
        await callback_query.answer("Ошибка: не найдена информация о транзакции")
        await state.clear()
        return
    
    # Создаем сессию БД
    db = SessionLocal()
    try:
        # Получаем транзакцию
        transaction = db.query(Transaction).filter(
            Transaction.id == transaction_id
        ).first()
        
        if not transaction:
            await callback_query.answer("Ошибка: транзакция не найдена")
            await state.clear()
            return
        
        # Получаем новую категорию
        new_category = db.query(Category).filter(
            Category.id == category_id
        ).first()
        
        if not new_category:
            await callback_query.answer("Ошибка: категория не найдена")
            await state.clear()
            return
        
        # Обновляем категорию транзакции
        old_category_id = transaction.category_id
        transaction.category_id = new_category.id
        
        # Обновляем также запись в таблице expenses для обратной совместимости
        if transaction.is_expense == 1:
            expense = db.query(Expense).filter(
                Expense.user_id == transaction.user_id,
                Expense.description == transaction.description,
                Expense.created_at == transaction.transaction_date
            ).first()
            
            if expense:
                expense.category = new_category.name
        
        # Обновляем кэш категоризации
        update_category_cache(db, transaction.description, new_category.name)
        
        db.commit()
        
        # Отправляем подтверждение
        await callback_query.message.edit_text(
            f"✅ Категория успешно обновлена на <b>{new_category.emoji} {new_category.name.capitalize()}</b>.\n\n"
            f"Спасибо за обратную связь! Это поможет улучшить категоризацию в будущем.",
            parse_mode=ParseMode.HTML
        )
        
        # Очищаем состояние
        await state.clear()
        
    except Exception as e:
        logging.error(f"Ошибка при обработке обратной связи: {e}")
        await callback_query.answer("Произошла ошибка при обновлении категории")
        await state.clear()
    finally:
        db.close()


@router.message(Command("clearcache"))
async def clear_category_cache(message: Message):
    """Очищает кэш категорий для текущего пользователя"""
    user_id = message.from_user.id
    
    try:
        db = SessionLocal()
        try:
            # Получаем пользователя из БД
            user = db.query(User).filter(User.telegram_id == user_id).first()
            
            if not user:
                await message.answer("Для начала работы, пожалуйста, используйте команду /start")
                return
            
            # Удаляем все записи кэша для данного пользователя
            cache_entries = db.query(CategoryCache).all()
            if cache_entries:
                for entry in cache_entries:
                    db.delete(entry)
                db.commit()
                await message.answer("✅ Кэш категорий успешно очищен")
            else:
                await message.answer("Кэш категорий уже пуст")
                
        except Exception as e:
            db.rollback()
            logging.error(f"Ошибка при очистке кэша категорий: {e}")
            await message.answer("Произошла ошибка при очистке кэша категорий")
        finally:
            db.close()
            
    except Exception as e:
        logging.error(f"Ошибка при обработке команды очистки кэша: {e}")
        await message.answer("Произошла ошибка при обработке команды")


@router.message(Command("learn"))
async def learn_category(message: Message):
    """Обучает бота правильной категоризации товара"""
    user_id = message.from_user.id
    
    try:
        # Парсим сообщение
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.answer(
                "Неверный формат команды. Используйте: /learn товар категория\n"
                "Например: /learn ручка канцтовары"
            )
            return
        
        # Извлекаем товар и категорию
        _, product, category = parts
        product = product.strip().lower()
        category = category.strip().lower()
        
        db = SessionLocal()
        try:
            # Получаем пользователя из БД
            user = db.query(User).filter(User.telegram_id == user_id).first()
            
            if not user:
                await message.answer("Для начала работы, пожалуйста, используйте команду /start")
                return
            
            # Проверяем, что категория существует
            categories = db.query(Category).filter(Category.user_id == user.id).all()
            categories_list = [cat.name for cat in categories]
            
            if category not in categories_list and category != "другое":
                categories_text = ", ".join(categories_list)
                await message.answer(
                    f"Категория '{category}' не найдена. Доступные категории:\n"
                    f"{categories_text}"
                )
                return
            
            # Обновляем кэш категорий
            success = update_category_cache(db, product, category)
            
            if success:
                await message.answer(
                    f"✅ Запомнил: товар '{product}' относится к категории '{category}'.\n"
                    f"Теперь я буду правильно категоризировать этот товар."
                )
            else:
                await message.answer("❌ Не удалось обновить информацию о категории.")
                
        finally:
            db.close()
            
    except Exception as e:
        logging.error(f"Ошибка при обучении категоризации: {e}")
        await message.answer("Произошла ошибка при обработке команды") 