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
            f"📝 <b>Как добавить трату:</b>\n"
            f"• Напиши сумму и категорию, например: <i>-500 кофе</i>\n"
            f"• Отправь фото чека, и я распознаю сумму\n\n"
            f"📊 <b>Команды:</b>\n"
            f"• /help — справка по боту\n"
            f"• /summary — сводка по тратам\n"
            f"• /stats — подробная статистика\n"
            f"• /list — история транзакций\n"
            f"• /delete — удалить последнюю запись\n"
            f"• /categories — список категорий\n"
            f"• /open — полная справка\n\n"
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
        "🧮 <b>Добавление расходов и доходов:</b>\n"
        "• <i>СУММА КАТЕГОРИЯ</i> — добавить трату\n"
        "   Например: <i>500 кофе</i> или <i>2500 продукты</i>\n"
        "• <i>+СУММА КАТЕГОРИЯ</i> — добавить доход\n"
        "   Например: <i>+50000 зарплата</i>\n"
        "• <i>СУММА ВАЛЮТА КАТЕГОРИЯ</i> — указать валюту\n"
        "   Например: <i>100 USD книги</i>\n"
        "• Можно указать дату: <i>500 обед вчера</i>\n"
        "• Можно упомянуть человека: <i>1500 подарок @username</i>\n"
        "• Отправьте фото чека для автоматического распознавания\n\n"
        "📊 <b>Команды:</b>\n"
        "• /summary — краткая сводка по расходам\n"
        "• /stats — подробная статистика по категориям\n"
        "• /list — список последних транзакций\n"
        "• /delete — удалить последнюю запись\n"
        "• /categories — список доступных категорий\n"
        "• /open — полная справка в стиле Cointry\n"
        "• /start — перезапустить бота\n\n"
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
        
        # Форматируем суммы в стиле Cointry
        day_formatted = f"`{day_sum:.2f}`"
        week_formatted = f"`{week_sum:.2f}`"
        month_formatted = f"`{month_sum:.2f}`"
        
        # Формируем сообщение в стиле Cointry
        await message.answer(
            f"📊 <b>Сводка по расходам:</b>\n\n"
            f"Сегодня: {day_formatted} ₽\n"
            f"Неделя: {week_formatted} ₽\n"
            f"Месяц: {month_formatted} ₽\n\n"
            f"💡 <i>{advice}</i>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logging.error(f"Ошибка при обработке команды /summary: {e}")
        await message.answer("Произошла ошибка при формировании отчета. Попробуйте позже.")
    finally:
        db.close()

# === NEW CODE ===
from sqlalchemy import func, desc, and_, extract
import calendar
from collections import defaultdict
from aiogram.utils.markdown import code
from core.models import Transaction, Category


def format_amount_markdown(amount: float, currency: str = "₽") -> str:
    """Форматирует сумму в стиле Cointry с кодовыми блоками Markdown"""
    return f"`{amount:.2f}`"


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """
    Обрабатывает команду /stats или /statistics:
    - Показывает расширенную статистику по расходам и доходам
    - Группировка по категориям
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
        
        # Запрашиваем расходы и доходы за текущий месяц
        transactions = db.query(
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
        
        # Группируем расходы по категориям
        expenses_by_category = defaultdict(float)
        expenses_total = 0
        income_by_category = defaultdict(float)
        income_total = 0
        
        for tx, cat_name, cat_emoji in transactions:
            category_name = cat_name or "другое"
            category_emoji = cat_emoji or "💰"
            
            if tx.is_expense == 1:  # Расход
                expenses_by_category[(category_name, category_emoji)] += tx.amount
                expenses_total += tx.amount
            else:  # Доход
                income_by_category[(category_name, category_emoji)] += tx.amount
                income_total += tx.amount
        
        # Создаем ответное сообщение
        response_parts = [f"📊 <b>Статистика за {calendar.month_name[now.month]}</b>\n"]
        
        # Добавляем расходы
        if expenses_total > 0:
            response_parts.append("\n<b>Расходы по категориям:</b>")
            
            # Сортируем категории по убыванию сумм
            sorted_expenses = sorted(
                expenses_by_category.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            for (category_name, category_emoji), amount in sorted_expenses:
                percentage = (amount / expenses_total) * 100 if expenses_total > 0 else 0
                response_parts.append(
                    f"{category_emoji} {category_name.capitalize()}: {format_amount_markdown(amount)} ({percentage:.1f}%)"
                )
            
            response_parts.append(f"\n<b>Всего расходов:</b> {format_amount_markdown(expenses_total)} ₽")
        
        # Добавляем доходы
        if income_total > 0:
            response_parts.append("\n<b>Доходы:</b>")
            
            sorted_income = sorted(
                income_by_category.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            for (category_name, category_emoji), amount in sorted_income:
                response_parts.append(f"{category_emoji} {category_name.capitalize()}: {format_amount_markdown(amount)}")
            
            response_parts.append(f"\n<b>Всего доходов:</b> {format_amount_markdown(income_total)} ₽")
        
        # Добавляем баланс
        balance = income_total - expenses_total
        balance_emoji = "📈" if balance >= 0 else "📉"
        response_parts.append(f"\n{balance_emoji} <b>Баланс:</b> {format_amount_markdown(balance)} ₽")
        
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
    """
    user_id = message.from_user.id
    limit = 10  # Количество транзакций для отображения
    
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
        
        # Формируем сообщение
        response = ["📋 <b>Последние транзакции:</b>\n"]
        
        for i, (tx, cat_name, cat_emoji) in enumerate(transactions, start=1):
            category_name = cat_name or "другое"
            category_emoji = cat_emoji or "💰"
            
            # Определяем тип транзакции
            icon = "➖" if tx.is_expense == 1 else "➕"
            
            # Форматируем дату
            date_str = tx.transaction_date.strftime("%d.%m.%Y")
            
            # Форматируем сумму
            amount_str = format_amount_markdown(tx.amount)
            
            # Формируем строку для транзакции
            response.append(
                f"{i}. {icon} {date_str} {category_emoji} {category_name.capitalize()}: {amount_str} {tx.currency}"
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
    - Удаляет последнюю добавленную транзакцию
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
        
        # Находим последнюю транзакцию пользователя
        last_transaction = db.query(Transaction).filter(
            Transaction.user_id == user.id
        ).order_by(desc(Transaction.created_at)).first()
        
        if not last_transaction:
            await message.answer("У вас нет транзакций для удаления.")
            return
        
        # Получаем категорию, если она есть
        category = db.query(Category).filter(
            Category.id == last_transaction.category_id
        ).first() if last_transaction.category_id else None
        
        # Сохраняем данные для подтверждения
        amount = last_transaction.amount
        category_name = category.name if category else "другое"
        category_emoji = category.emoji if category else "💰"
        currency = last_transaction.currency
        is_expense = last_transaction.is_expense == 1
        
        # Удаляем запись из БД
        db.delete(last_transaction)
        
        # Если это был расход, также удаляем соответствующую запись из таблицы expenses
        # для обратной совместимости
        if is_expense:
            last_expense = db.query(Expense).filter(
                Expense.user_id == user.id
            ).order_by(desc(Expense.created_at)).first()
            
            if last_expense:
                db.delete(last_expense)
        
        db.commit()
        
        # Определяем тип транзакции для сообщения
        transaction_type = "расход" if is_expense else "доход"
        
        # Отправляем подтверждение об удалении в стиле Cointry
        await message.answer(
            f"🗑️ Удалена запись:\n"
            f"<b>{category_emoji} {category_name.capitalize()}</b>\n"
            f"{'➖' if is_expense else '➕'} {format_amount_markdown(amount)} {currency}",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        db.rollback()
        logging.error(f"Ошибка при удалении транзакции: {e}")
        await message.answer("Произошла ошибка при удалении записи. Попробуйте позже.")
    finally:
        db.close()


@router.message(Command("categories"))
async def cmd_categories(message: Message):
    """Показывает список доступных категорий с эмодзи"""
    from bot.expense import recognize_category, get_category_emoji
    
    # Получаем список категорий из функции распознавания
    categories = {
        "продукты": "🛒 Продукты (магнит, пятерочка, перекресток, ашан и т.д.)",
        "кафе": "☕ Кафе (кофе, чай, кондитерская, пекарня)",
        "ресторан": "🍽️ Рестораны (бары, фастфуд, доставка еды)",
        "транспорт": "🚗 Транспорт (метро, автобус, проезд)",
        "такси": "🚕 Такси (яндекс такси, uber, поездки)",
        "одежда": "👕 Одежда (магазины одежды, онлайн-шопинг)",
        "обувь": "👟 Обувь (магазины обуви)",
        "развлечения": "🎮 Развлечения (игры, кино, театр, концерты)",
        "здоровье": "💊 Здоровье (аптека, врач, клиника)",
        "связь": "📱 Связь (телефон, интернет, операторы)",
        "коммуналка": "🏠 Коммуналка (ЖКХ, аренда, квартплата)",
        "образование": "📚 Образование (учеба, курсы, книги)"
    }
    
    # Формируем сообщение со списком категорий
    message_text = "📋 <b>Доступные категории:</b>\n\n"
    
    for category, description in categories.items():
        message_text += f"{description}\n"
    
    message_text += "\n<i>При добавлении расхода бот автоматически определит категорию по ключевым словам</i>"
    
    await message.answer(message_text, parse_mode=ParseMode.HTML)


@router.message(Command("open"))
async def cmd_open(message: Message):
    """
    Обрабатывает команду /open:
    - Показывает справку по командам в стиле Cointry
    """
    await message.answer(
        "<b>Команды:</b>\n\n"
        "- <b>[сумма] [необязательный комментарий]</b>, чтобы записать расходы:\n"
        "  `12000 куртка замшевая`\n\n"
        "Если перед суммой добавить знак +, она запишется как доход:\n"
        "  `+100000 нажито непосильным трудом`\n\n"
        "⭐ Можно указать валюту в трёхбуквенном формате. В статистике сумма будет корректно сконвертирована в Вашу основную валюту по курсу на дату транзакции.\n"
        "  `1600 USD три кинокамеры заграничных`\n\n"
        "⭐ В конец команды можно добавить дату транзакции в форматах `1.12.20` или `2020-12-01`, а также можно просто написать `вчера` или `позавчера`:\n"
        "  `4000 ресторан \"Плакучая ива\" 26.12.2024`\n\n"
        "⭐ Если Ваш партнёр часто забывает делать записи, Вы можете делать это за него. Просто упомяните его по имени в Телеграме через @:\n"
        "  `@durov 3600 три портсигара отечественных`\n\n"
        "- `/open` - запустить приложение;\n"
        "- Статистика или `/stats` - узнать статистику своих расходов;\n"
        "- Удалить или `/delete` - удалить свою последнюю запись;\n"
        "- История или `/list` - получить список всех записей;\n"
        "- Категории или `/categories` - добавить или изменить категории;",
        parse_mode=ParseMode.HTML
    ) 