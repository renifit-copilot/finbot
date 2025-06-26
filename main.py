import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from bot.commands import router as commands_router
from bot.expense import router as expense_router
from core.db import init_db
from core.models import User, Expense, Goal, Category, Transaction


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("finbot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Загружаем переменные окружения из .env файла
load_dotenv()


# Получаем токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("Токен бота не найден. Укажите BOT_TOKEN в файле .env")
    sys.exit(1)

# Проверяем наличие API ключа для Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    logger.warning("API ключ Groq не найден. Функции LLM будут недоступны.")


async def main():
    """Основная функция запуска бота"""
    
    # Инициализируем бота и диспетчер с хранилищем состояний
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрируем роутеры
    dp.include_router(commands_router)
    dp.include_router(expense_router)
    
    # Создаем таблицы в БД, если их нет
    init_db()
    logger.info("База данных инициализирована")
    
    # Проверяем наличие директории для хранения чеков
    receipts_dir = "receipts"
    if not os.path.exists(receipts_dir):
        os.makedirs(receipts_dir)
        logger.info(f"Создана директория для хранения чеков: {receipts_dir}")
    
    # Запускаем бота
    logger.info("Запуск бота...")
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Выводим информацию о боте
    bot_info = await bot.get_me()
    logger.info(f"Бот @{bot_info.username} ({bot_info.id}) запущен")
    
    # Запускаем поллинг
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        # Создаем цикл событий и запускаем основную функцию
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}", exc_info=True)
        sys.exit(1) 