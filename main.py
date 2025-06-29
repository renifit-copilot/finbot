import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import BotCommand, BotCommandScopeDefault, Message
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from bot.commands import router as commands_router
from bot.expense import router as expense_router
from core.db import init_db
from core.models import User, Expense, Goal, Category, Transaction

# Загружаем переменные окружения из .env файла
load_dotenv()

# Получаем токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Настройка логирования
logging.basicConfig(level=logging.INFO, filename='finbot.log', filemode='a',
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Добавляем вывод логов в консоль
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logging.getLogger().addHandler(console_handler)

# Получаем логгер для текущего модуля
logger = logging.getLogger(__name__)

# Словарь соответствия текстовых команд и их слеш-аналогов
TEXT_COMMANDS = {
    "помощь": "help",
    "статистика": "stats",
    "список": "list",
    "отчет": "summary",
    "категории": "categories",
    "удалить": "delete",
    "совет": "advice",
    "обратная связь": "feedback",
    "меню": "menu"
}

async def set_commands(bot: Bot):
    """Устанавливает команды бота в меню"""
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="stats", description="Статистика"),
        BotCommand(command="list", description="Список транзакций"),
        BotCommand(command="summary", description="Отчет за месяц"),
        BotCommand(command="categories", description="Категории"),
        BotCommand(command="delete", description="Удалить транзакцию"),
        BotCommand(command="advice", description="Финансовый совет"),
        BotCommand(command="feedback", description="Обратная связь"),
        BotCommand(command="menu", description="Показать меню бота")
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    
    logging.info("Команды бота установлены")

async def main():
    """Основная функция запуска бота"""
    
    # Инициализируем бота и диспетчер с хранилищем состояний
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрируем роутеры
    dp.include_router(commands_router)
    dp.include_router(expense_router)
    
    # Обработчик для текстовых команд
    @dp.message(lambda message: message.text and message.text.lower() in TEXT_COMMANDS)
    async def process_text_command(message: Message):
        """Обрабатывает текстовые команды и перенаправляет на соответствующие слеш-команды"""
        command = TEXT_COMMANDS[message.text.lower()]
        
        # Вместо изменения объекта message, вызываем соответствующий обработчик напрямую
        if command == "help":
            from bot.commands import cmd_help
            await cmd_help(message)
        elif command == "stats":
            from bot.commands import cmd_stats
            await cmd_stats(message)
        elif command == "list":
            from bot.commands import cmd_list_transactions
            await cmd_list_transactions(message)
        elif command == "summary":
            from bot.commands import cmd_summary
            await cmd_summary(message)
        elif command == "categories":
            from bot.commands import cmd_categories
            await cmd_categories(message)
        elif command == "delete":
            from bot.commands import cmd_delete_last
            await cmd_delete_last(message)
        elif command == "advice":
            from bot.commands import cmd_advice
            await cmd_advice(message)
        elif command == "feedback":
            from bot.commands import cmd_feedback
            await cmd_feedback(message)
        elif command == "menu":
            from bot.commands import cmd_menu
            await cmd_menu(message)
    
    # Создаем таблицы в БД, если их нет
    init_db()
    
    # Создаем директорию для хранения чеков, если её нет
    receipts_dir = "receipts"
    if not os.path.exists(receipts_dir):
        os.makedirs(receipts_dir)
        logger.info(f"Создана директория для хранения чеков: {receipts_dir}")
    
    # Настраиваем команды бота
    await set_commands(bot)
    
    # Запускаем бота
    logger.info("Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main()) 