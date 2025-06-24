from openai import OpenAI
import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from config import settings
from sqlalchemy.orm import Session
from core.models import User, Expense


# Инициализация клиента OpenAI с настройками для Groq API
client = OpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)


def ask_groq(messages: List[Dict[str, str]]) -> str:
    """
    Отправляет запрос к Groq API и возвращает ответ

    Args:
        messages: список сообщений в формате [{role: "user", content: "текст"}]

    Returns:
        str: ответ от модели
    """
    try:
        response = client.chat.completions.create(
            model="llama3-70b-8192",  # Используем Llama 3 70B
            messages=messages,
            temperature=0.7,
            max_tokens=150,
            top_p=0.9
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка при запросе к Groq API: {e}")
        return "Не удалось получить совет, попробуйте позже."


def get_advice(user_id: int, db: Session) -> str:
    """
    Получает финансовый совет на основе расходов пользователя

    Args:
        user_id: Telegram ID пользователя
        db: сессия базы данных

    Returns:
        str: краткий финансовый совет (не более 60 символов)
    """
    try:
        # Получаем пользователя из БД
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            return "Для получения советов добавьте хотя бы одну трату."
            
        # Получаем расходы пользователя за последние 30 дней
        thirty_days_ago = datetime.now() - timedelta(days=30)
        expenses = db.query(Expense).filter(
            Expense.user_id == user.id,
            Expense.created_at >= thirty_days_ago
        ).all()
        
        if not expenses:
            return "Добавьте больше трат для получения персонализированного совета."
        
        # Формируем данные о расходах
        total_spent = sum(expense.amount for expense in expenses)
        categories = {}
        for expense in expenses:
            cat = expense.category or "другое"
            if cat not in categories:
                categories[cat] = 0
            categories[cat] += expense.amount
            
        # Находим самую большую категорию расходов
        largest_category = max(categories.items(), key=lambda x: x[1])
        
        # Формируем запрос к LLM
        messages = [
            {
                "role": "system", 
                "content": "Ты - финансовый помощник. Дай очень краткий совет (не более 60 символов) по экономии денег, основываясь на расходах пользователя за месяц."
            },
            {
                "role": "user",
                "content": f"Мои траты за месяц: {total_spent} руб. Больше всего трачу на {largest_category[0]}: {largest_category[1]} руб."
            }
        ]
        
        # Получаем и возвращаем совет
        advice = ask_groq(messages)
        
        # Обрезаем совет до 60 символов, если он длиннее
        if len(advice) > 60:
            advice = advice[:57] + "..."
            
        return advice
        
    except Exception as e:
        logging.error(f"Ошибка при получении совета: {e}")
        return "Не удалось сформировать финансовый совет." 