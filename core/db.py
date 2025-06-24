from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings
import logging
from pathlib import Path

# Создаем базовый класс для моделей
Base = declarative_base()

# Создаем движок SQLAlchemy с указанным URI
engine = create_engine(settings.DB_PATH)

# Создаем фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """
    Инициализация базы данных: создание таблиц, если их нет.
    """
    try:
        # Импортируем модели здесь, чтобы избежать циклического импорта
        from core.models import User, Expense, Goal
        
        # Создаем таблицы
        Base.metadata.create_all(bind=engine)
        logging.info("БД инициализирована успешно")
    except Exception as e:
        logging.error(f"Ошибка при инициализации БД: {e}")
        raise


def get_db():
    """
    Создает новую сессию БД для каждого запроса и закрывает ее после выполнения
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 