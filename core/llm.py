# Импортируем OpenAI
from openai import OpenAI
import os
import logging
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from config import settings
from sqlalchemy.orm import Session
from core.models import User, Expense, Category, Transaction, CategoryCache
from sqlalchemy import func
import difflib
import re

# Инициализация клиента OpenAI с OpenRouter
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.OPENROUTER_API_KEY
)

# Флаг доступности LLM
LLM_AVAILABLE = True

# Расширенный словарь товаров с их категориями
# Структура: {"товар": "категория"}
PRODUCTS_CATEGORIES = {
    # Продукты и магазины продуктов
    "хлеб": "продукты",
    "молоко": "продукты",
    "сыр": "продукты",
    "яйца": "продукты",
    "масло": "продукты",
    "йогурт": "продукты",
    "творог": "продукты",
    "кефир": "продукты",
    "сметана": "продукты",
    "колбаса": "продукты",
    "сосиски": "продукты",
    "мясо": "продукты",
    "курица": "продукты",
    "рыба": "продукты",
    "овощи": "продукты",
    "фрукты": "продукты",
    "яблоки": "продукты",
    "бананы": "продукты",
    "апельсины": "продукты",
    "картошка": "продукты",
    "картофель": "продукты",
    "морковь": "продукты",
    "лук": "продукты",
    "чеснок": "продукты",
    "помидоры": "продукты",
    "огурцы": "продукты",
    "капуста": "продукты",
    "макароны": "продукты",
    "крупа": "продукты",
    "рис": "продукты",
    "гречка": "продукты",
    "сахар": "продукты",
    "соль": "продукты",
    "мука": "продукты",
    "печенье": "продукты",
    "конфеты": "продукты",
    "шоколад": "продукты",
    "чай": "продукты",
    "кофе": "продукты",
    "вода": "продукты",
    "сок": "продукты",
    "газировка": "продукты",
    "пиво": "продукты",
    "вино": "продукты",
    "водка": "продукты",

    # Магазины продуктов
    "магнит": "продукты",
    "пятерочка": "продукты",
    "перекресток": "продукты",
    "ашан": "продукты",
    "лента": "продукты",
    "дикси": "продукты",
    "окей": "продукты",
    "метро": "продукты",
    "азбука вкуса": "продукты",
    "вкусвилл": "продукты",
    "sпар": "продукты",
    "spar": "продукты",
    "auchan": "продукты",
    "магнолия": "продукты",
    "мираторг": "продукты",
    "карусель": "продукты",
    "глобус": "продукты",
    "billa": "продукты",
    "билла": "продукты",
    "верный": "продукты",
    "перекрёсток": "продукты",
    "лавка": "продукты",
    "продуктовый": "продукты",
    "супермаркет": "продукты",
    "гипермаркет": "продукты",
    "продукты": "продукты",

    # Канцтовары
    "ручка": "канцтовары",
    "карандаш": "канцтовары",
    "тетрадь": "канцтовары",
    "блокнот": "канцтовары",
    "бумага": "канцтовары",
    "степлер": "канцтовары",
    "скрепки": "канцтовары",
    "папка": "канцтовары",
    "файлы": "канцтовары",
    "маркер": "канцтовары",
    "ластик": "канцтовары",
    "линейка": "канцтовары",
    "калькулятор": "канцтовары",

    # Бытовая химия
    "мыло": "бытовая химия",
    "шампунь": "бытовая химия",
    "гель для душа": "бытовая химия",
    "зубная паста": "бытовая химия",
    "зубная щетка": "бытовая химия",
    "стиральный порошок": "бытовая химия",
    "кондиционер для белья": "бытовая химия",
    "средство для мытья посуды": "бытовая химия",
    "чистящее средство": "бытовая химия",
    "туалетная бумага": "бытовая химия",
    "салфетки": "бытовая химия",
    "бумажные полотенца": "бытовая химия",

    # Одежда
    "футболка": "одежда",
    "рубашка": "одежда",
    "брюки": "одежда",
    "джинсы": "одежда",
    "куртка": "одежда",
    "пальто": "одежда",
    "платье": "одежда",
    "юбка": "одежда",
    "носки": "одежда",
    "нижнее белье": "одежда",
    "шапка": "одежда",
    "шарф": "одежда",
    "перчатки": "одежда",

    # Обувь
    "туфли": "обувь",
    "кроссовки": "обувь",
    "ботинки": "обувь",
    "сапоги": "обувь",
    "сандалии": "обувь",
    "тапочки": "обувь",

    # Транспорт
    "проезд": "транспорт",
    "метро": "транспорт",
    "автобус": "транспорт",
    "маршрутка": "транспорт",
    "трамвай": "транспорт",
    "троллейбус": "транспорт",
    "электричка": "транспорт",
    "такси": "такси",
    "бензин": "транспорт",
    "парковка": "транспорт",

    # Кафе и рестораны
    "кофе": "кафе",
    "чай": "кафе",
    "завтрак": "кафе",
    "обед": "кафе",
    "ужин": "кафе",
    "ресторан": "рестораны",
    "кафе": "кафе",
    "бар": "рестораны",
    "пицца": "кафе",
    "суши": "рестораны",
    "фастфуд": "кафе",
    "бургер": "кафе",
    "шаурма": "кафе",
    "макдоналдс": "кафе",
    "kfc": "кафе",
    "бургер кинг": "кафе",
    "старбакс": "кафе",
    "starbucks": "кафе",
    "шоколадница": "кафе",
    "кофеин": "кафе",
    "costa coffee": "кафе",
    "subway": "кафе",
    "сабвей": "кафе",

    # Здоровье
    "лекарства": "здоровье",
    "аптека": "здоровье",
    "врач": "здоровье",
    "анализы": "здоровье",
    "витамины": "здоровье",
    "стоматолог": "здоровье",
    "массаж": "здоровье",

    # Связь
    "телефон": "связь",
    "интернет": "связь",
    "мобильная связь": "связь",
    "роутер": "связь",
    "модем": "связь",

    # Развлечения
    "кино": "развлечения",
    "театр": "развлечения",
    "концерт": "развлечения",
    "выставка": "развлечения",
    "музей": "развлечения",
    "боулинг": "развлечения",
    "бильярд": "развлечения",
    "караоке": "развлечения",
    "клуб": "развлечения",
    "игры": "развлечения",
    "подписка": "развлечения",

    # Коммунальные услуги
    "квартплата": "коммуналка",
    "электричество": "коммуналка",
    "вода": "коммуналка",
    "газ": "коммуналка",
    "отопление": "коммуналка",
    "интернет": "связь",
    "телевидение": "связь",
}


def match_product_to_category(product_name: str) -> Tuple[str, float]:
    """
    Сопоставляет название товара с категорией, используя нечеткое сопоставление

    Args:
        product_name: название товара

    Returns:
        Tuple[str, float]: категория и уверенность в сопоставлении (0-1)
    """
    # Нормализуем название товара
    normalized_name = product_name.lower().strip()

    # Точное совпадение
    if normalized_name in PRODUCTS_CATEGORIES:
        return PRODUCTS_CATEGORIES[normalized_name], 1.0

    # Проверяем, содержит ли название товара ключевое слово из словаря
    for product, category in PRODUCTS_CATEGORIES.items():
        if product in normalized_name or normalized_name in product:
            return category, 0.9

    # Нечеткое сопоставление
    matches = difflib.get_close_matches(
        normalized_name, PRODUCTS_CATEGORIES.keys(), n=1, cutoff=0.7)
    if matches:
        return PRODUCTS_CATEGORIES[matches[0]], 0.8

    # Если не нашли совпадений, возвращаем None
    return None, 0.0


def ask_cerebras(messages: List[Dict[str, str]]) -> str:
    """
    Отправляет запрос к LLM API и возвращает ответ

    Args:
        messages: список сообщений в формате [{role: "user", content: "текст"}]

    Returns:
        str: ответ от модели
    """
    if not LLM_AVAILABLE:
        logging.error("LLM не установлен")
        return "Не удалось получить совет, LLM не установлен."

    try:
        response = client.chat.completions.create(
            model="mistralai/mistral-7b-instruct:free",
            messages=messages,
            temperature=0.2,
            max_tokens=300,
            top_p=1,
            extra_headers={
                # Optional. Site URL for rankings on openrouter.ai
                "HTTP-Referer": "https://finbot.app",
                "X-Title": "FinBot",  # Optional. Site title for rankings on openrouter.ai
            },
            extra_body={}
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Ошибка при запросе к LLM API: {e}")
        return "Не удалось получить совет, попробуйте позже."


def categorize_transaction(description: str, db: Session, user_id: int) -> Optional[str]:
    """
    Определяет категорию транзакции с помощью LLM на основе описания с использованием кэша.
    Использует только предопределенные категории и не создает новые.

    Args:
        description: описание транзакции
        db: сессия базы данных
        user_id: ID пользователя в базе данных

    Returns:
        Optional[str]: название категории или None в случае ошибки
    """
    try:
        # Нормализуем описание (удаляем лишние пробелы)
        normalized_description = description.strip().lower()

        # Создаем хеш описания для поиска в кэше
        description_hash = hashlib.md5(
            normalized_description.encode()).hexdigest()

        # Определяем стандартные категории
        default_categories = [
            "продукты", "кафе", "рестораны", "транспорт", "такси",
            "одежда", "развлечения", "здоровье", "связь", "коммуналка",
            "образование", "спорт", "путешествия", "подарки", "техника",
            "зарплата", "доход", "другое", "канцтовары", "бытовая химия"
        ]

        # Получаем существующие категории пользователя
        user_categories = db.query(Category).filter(
            Category.user_id == user_id).all()

        # Если у пользователя есть категории, используем их, иначе используем стандартные
        if user_categories:
            categories_list = [category.name for category in user_categories]
        else:
            categories_list = default_categories

        # Проверяем, есть ли результат в кэше
        cached_result = db.query(CategoryCache).filter(
            CategoryCache.description_hash == description_hash
        ).first()

        if cached_result:
            # Проверяем, что категория из кэша находится в списке разрешенных категорий
            if cached_result.category_name in categories_list or cached_result.category_name == "другое":
                # Обновляем счетчик использований и время последнего использования
                cached_result.use_count += 1
                cached_result.last_used_at = datetime.now()
                db.commit()

                # Возвращаем категорию из кэша
                logging.info(
                    f"Категория '{cached_result.category_name}' для '{description}' взята из кэша")
                return cached_result.category_name
            else:
                # Если категория из кэша не в списке разрешенных, удаляем её из кэша
                logging.warning(
                    f"Обнаружена некорректная категория '{cached_result.category_name}' в кэше. Удаляем запись.")
                db.delete(cached_result)
                db.commit()

        # Пытаемся определить категорию по словарю товаров
        matched_category, confidence = match_product_to_category(
            normalized_description)
        if matched_category and confidence >= 0.7:
            # Проверяем, что категория из словаря находится в списке разрешенных
            if matched_category in categories_list:
                # Сохраняем результат в кэш
                cache_entry = CategoryCache(
                    description_hash=description_hash,
                    description=normalized_description,
                    category_name=matched_category,
                    confidence=confidence
                )
                db.add(cache_entry)
                db.commit()

                logging.info(
                    f"Категория '{matched_category}' для '{description}' определена с помощью словаря товаров")
                return matched_category

        # Если не удалось определить категорию по словарю, используем историю транзакций и LLM
        # Получаем историю транзакций пользователя для обучения модели
        recent_transactions = db.query(
            Transaction, Category.name.label('category_name')
        ).join(
            Category, Transaction.category_id == Category.id
        ).filter(
            Transaction.user_id == user_id
        ).order_by(Transaction.transaction_date.desc()).limit(10).all()

        # Формируем примеры для обучения
        examples = []

        if recent_transactions:
            for tx, cat_name in recent_transactions:
                if tx.description and cat_name:
                    examples.append(
                        f"Описание: {tx.description} -> Категория: {cat_name}")

        # Формируем запрос к LLM
        system_prompt = """Ты - система категоризации финансовых транзакций. 
        Твоя задача - определить наиболее подходящую категорию для описания транзакции.
        
        ВАЖНО: Ты ДОЛЖЕН выбрать категорию ТОЛЬКО из предоставленного списка категорий.
        НЕ СОЗДАВАЙ новые категории. Если не можешь точно определить категорию, выбери "другое".
        
        НИКОГДА не используй нецензурную лексику или оскорбительные слова в категориях.
        
        Отвечай ТОЛЬКО названием категории из предложенного списка, без дополнительных пояснений или знаков препинания.
        """

        # Добавляем примеры в системный промпт, если они есть
        if examples:
            system_prompt += "\n\nПримеры категоризации:\n" + \
                "\n".join(examples)

        # Добавляем информацию о словаре товаров
        system_prompt += "\n\nСправочная информация о категориях товаров:\n"
        system_prompt += "- Продукты: хлеб, молоко, сыр, яйца, мясо, овощи, фрукты, крупы\n"
        system_prompt += "- Магазины продуктов: магнит, пятерочка, перекресток, ашан, лента, дикси, спар, вкусвилл\n"
        system_prompt += "- Канцтовары: ручка, карандаш, тетрадь, блокнот, бумага, степлер\n"
        system_prompt += "- Бытовая химия: мыло, шампунь, зубная паста, стиральный порошок\n"
        system_prompt += "- Одежда: футболка, рубашка, брюки, джинсы, куртка, платье\n"
        system_prompt += "- Обувь: туфли, кроссовки, ботинки, сапоги\n"
        system_prompt += "- Кафе: кофе, чай, завтрак, обед, ужин, пицца, фастфуд, макдоналдс, kfc\n"

        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"""Определи категорию для: "{description}"
                
                Доступные категории: {", ".join(categories_list)}
                """
            }
        ]

        # Отправляем запрос к LLM
        if LLM_AVAILABLE:
            try:
                response = client.chat.completions.create(
                    model="mistralai/mistral-7b-instruct:free",
                    messages=messages,
                    temperature=0.2,
                    max_tokens=50,
                    top_p=1,
                    extra_headers={
                        # Optional. Site URL for rankings on openrouter.ai
                        "HTTP-Referer": "https://finbot.app",
                        "X-Title": "FinBot",  # Optional. Site title for rankings on openrouter.ai
                    },
                    extra_body={}
                )
                category = response.choices[0].message.content.strip().lower()
            except Exception as e:
                logging.error(f"Ошибка при запросе к LLM API: {e}")
                # В случае ошибки используем словарный подход и вероятности
                category = "другое"
                confidence = 0.1
                # Выходим из блока try-except раньше
                return category
        else:
            logging.warning(
                "LLM не установлен, используем словарный метод")
            category = "другое"  # Значение по умолчанию, если LLM недоступна
            confidence = 0.1

        # Проверяем, что категория есть в списке доступных
        if category in categories_list:
            confidence = 1.0  # Высокая уверенность, если категория точно совпадает
        else:
            # Если точного совпадения нет, проверяем частичное совпадение
            matched = False
            for available_category in categories_list:
                if available_category in category or category in available_category:
                    category = available_category
                    confidence = 0.8  # Средняя уверенность при частичном совпадении
                    matched = True
                    break

            # Если нет даже частичного совпадения, используем "другое"
            if not matched:
                category = "другое"
                confidence = 0.5  # Низкая уверенность

        # Дополнительная проверка на недопустимые категории
        if category not in categories_list and category != "другое":
            logging.warning(
                f"LLM вернула недопустимую категорию: '{category}'. Используем 'другое'")
            category = "другое"
            confidence = 0.1  # Очень низкая уверенность

        # Сохраняем результат в кэш
        cache_entry = CategoryCache(
            description_hash=description_hash,
            description=normalized_description,
            category_name=category,
            confidence=confidence
        )
        db.add(cache_entry)
        db.commit()

        logging.info(
            f"Категория '{category}' для '{description}' определена с помощью LLM и сохранена в кэш")
        return category

    except Exception as e:
        logging.error(f"Ошибка при категоризации транзакции: {e}")
        return "другое"  # В случае ошибки возвращаем "другое" вместо None
