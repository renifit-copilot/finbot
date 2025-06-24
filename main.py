import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from dotenv import load_dotenv
import os
from bot.commands import router as commands_router
from bot.expense import router as expense_router
from core.db import Base, engine
from core.models import User, Expense, Goal


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


async def main():
    """Основная функция запуска бота"""
    
    # Инициализируем бота и диспетчер
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    
    # Регистрируем роутеры
    dp.include_router(commands_router)
    dp.include_router(expense_router)
    
    # Создаем таблицы в БД, если их нет
    Base.metadata.create_all(engine)
    logger.info("База данных инициализирована")
    
    # Запускаем бота
    logger.info("Запуск бота...")
    await bot.delete_webhook(drop_pending_updates=True)
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