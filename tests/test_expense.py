import unittest
import re
import sys
import os
from pathlib import Path
from datetime import datetime

# Добавляем корневую директорию проекта в sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.models import User, Expense
from core.db import Base, engine, SessionLocal
from core.ocr import parse_receipt


class TestExpenseParser(unittest.TestCase):
    """Тесты для парсера сообщений о расходах"""

    def test_expense_regex(self):
        """Тест регулярного выражения для парсинга сообщений о расходах"""
        # Паттерн для парсинга расходов
        pattern = r'^-(\d+(?:[.,]\d+)?)\s+(.+)$'
        
        # Тестовые кейсы (сообщение, ожидаемая сумма, ожидаемая категория)
        test_cases = [
            ("-100 кофе", "100", "кофе"),
            ("-750.50 обед", "750.50", "обед"),
            ("-1234,56 продукты", "1234,56", "продукты"),
            ("-500 такси до дома", "500", "такси до дома"),
            ("-1000 подарок маме", "1000", "подарок маме"),
        ]
        
        for message, expected_amount, expected_category in test_cases:
            match = re.match(pattern, message)
            self.assertIsNotNone(match, f"Сообщение '{message}' не распознано")
            self.assertEqual(match.group(1), expected_amount)
            self.assertEqual(match.group(2), expected_category)


class TestDatabaseModels(unittest.TestCase):
    """Тесты для моделей базы данных"""
    
    @classmethod
    def setUpClass(cls):
        """Создаем временную базу данных для тестов"""
        # Используем SQLite в памяти
        from sqlalchemy import create_engine
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = SessionLocal
        
    def setUp(self):
        """Создаем сессию для каждого теста"""
        self.session = SessionLocal(bind=self.engine)
        
    def tearDown(self):
        """Закрываем сессию после каждого теста"""
        self.session.close()
        
    def test_user_model(self):
        """Тест модели пользователя"""
        user = User(
            telegram_id=123456789, 
            username="testuser", 
            first_name="Тест", 
            last_name="Юзеров"
        )
        self.session.add(user)
        self.session.commit()
        
        # Проверяем сохранение
        saved_user = self.session.query(User).filter_by(telegram_id=123456789).first()
        self.assertIsNotNone(saved_user)
        self.assertEqual(saved_user.username, "testuser")
        self.assertEqual(saved_user.first_name, "Тест")
        
    def test_expense_model(self):
        """Тест модели расхода"""
        # Создаем пользователя
        user = User(telegram_id=987654321, username="expenseuser")
        self.session.add(user)
        self.session.commit()
        
        # Создаем расход
        expense = Expense(
            user_id=user.id,
            amount=150.75,
            category="кофе",
            description="Утренний кофе"
        )
        self.session.add(expense)
        self.session.commit()
        
        # Проверяем сохранение
        saved_expense = self.session.query(Expense).filter_by(user_id=user.id).first()
        self.assertIsNotNone(saved_expense)
        self.assertEqual(saved_expense.amount, 150.75)
        self.assertEqual(saved_expense.category, "кофе")
        
        # Проверяем связь с пользователем
        self.assertEqual(saved_expense.user.telegram_id, 987654321)


if __name__ == "__main__":
    unittest.main() 