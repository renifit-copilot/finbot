from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.db import Base
from datetime import datetime


class User(Base):
    """Модель пользователя"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=func.now())
    
    # Отношения
    expenses = relationship("Expense", back_populates="user")
    goals = relationship("Goal", back_populates="user")


class Expense(Base):
    """Модель расхода"""
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    amount = Column(Float, nullable=False)
    category = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    receipt_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())
    
    # Отношения
    user = relationship("User", back_populates="expenses")


class Goal(Base):
    """Модель финансовой цели"""
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(100), nullable=False)
    target_amount = Column(Float, nullable=False)
    current_amount = Column(Float, default=0.0)
    deadline = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    
    # Отношения
    user = relationship("User", back_populates="goals")


class Category(Base):
    """Модель категории расходов/доходов"""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    name = Column(String(100), nullable=False)
    emoji = Column(String(10), default="💰")
    is_expense = Column(Integer, default=1)  # 1 - расход, 0 - доход
    created_at = Column(DateTime, default=func.now())

    # Отношения
    user = relationship("User")


class Transaction(Base):
    """Расширенная модель транзакции (доход/расход)"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    amount = Column(Float, nullable=False)
    original_amount = Column(Float, nullable=True)
    currency = Column(String(3), default="RUB")
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    description = Column(Text, nullable=True)
    transaction_date = Column(DateTime, default=func.now())
    created_at = Column(DateTime, default=func.now())
    is_expense = Column(Integer, default=1)  # 1 - расход, 0 - доход
    receipt_path = Column(String(255), nullable=True)
    mentioned_user = Column(String(100), nullable=True)  # Упомянутый пользователь (@username)

    # Отношения
    user = relationship("User")
    category = relationship("Category") 