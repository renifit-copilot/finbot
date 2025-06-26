from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings
import logging
from pathlib import Path

# Создаем базовый класс для моделей
Base = declarative_base()

# Создаем движок SQLAlchemy
engine = create_engine(settings.DB_PATH)

# Создаем фабрику сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """
    Инициализирует базу данных и создает таблицы, если их нет
    """
    try:
        # Импортируем модели, чтобы они были доступны при создании таблиц
        from core.models import User, Expense, Goal, Category, Transaction, CategoryCache
        
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