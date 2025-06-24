import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from loguru import logger

from config import settings
from core.db import init_db
from bot.commands import router as commands_router
from bot.expense import router as expense_router


# Настройка логирования
def setup_logging():
    """Настраивает логирование для приложения"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Настройка логгера loguru
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "finbot.log",
        rotation="1 MB",
        retention="10 days",
        compression="zip",
        level="DEBUG"
    )
    
    # Перехватываем логи библиотек
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            logger_opt = logger.opt(depth=6, exception=record.exc_info)
            logger_opt.log(record.levelname, record.getMessage())
    
    # Устанавливаем обработчик для стандартного логгера
    logging.getLogger().addHandler(InterceptHandler())
    
    return logger


async def main():
    """Запускает телеграм-бота"""
    # Настраиваем логирование
    logger = setup_logging()
    logger.info("Запуск FinBot...")
    
    # Инициализируем базу данных
    try:
        init_db()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        return
    
    # Инициализируем бота и диспетчер
    bot = Bot(token=settings.BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()
    
    # Регистрируем роутеры
    dp.include_router(commands_router)
    dp.include_router(expense_router)
    
    logger.info("Запускаем long polling...")
    
    # Запускаем поллинг
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()
        logger.info("Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен вручную")
    except Exception as e:
        logging.error(f"Необработанная ошибка: {e}")
        logging.exception(e) 