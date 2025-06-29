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

# Инициализация клиента OpenAI с настройками для Groq API
client = OpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

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
    "спар": "продукты",
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
    matches = difflib.get_close_matches(normalized_name, PRODUCTS_CATEGORIES.keys(), n=1, cutoff=0.7)
    if matches:
        return PRODUCTS_CATEGORIES[matches[0]], 0.8
    
    # Если не нашли совпадений, возвращаем None
    return None, 0.0

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
            max_tokens=300,
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
        str: краткий финансовый совет (не более 200 символов)
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
                "content": "Ты - финансовый помощник. Дай совет не больше 150 слов по экономии денег, основываясь на расходах пользователя за месяц. Не нужно лить воду, отвечай сухо и по делу и приводи примеры"
            },
            {
                "role": "user",
                "content": f"Мои траты за месяц: {total_spent} руб. Больше всего трачу на {largest_category[0]}: {largest_category[1]} руб."
            }
        ]
        
        # Получаем и возвращаем совет
        advice = ask_groq(messages)
        
        return advice
        
    except Exception as e:
        logging.error(f"Ошибка при получении совета: {e}")
        return "Не удалось сформировать финансовый совет."


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
        description_hash = hashlib.md5(normalized_description.encode()).hexdigest()
        
        # Определяем стандартные категории
        default_categories = [
            "продукты", "кафе", "рестораны", "транспорт", "такси", 
            "одежда", "развлечения", "здоровье", "связь", "коммуналка", 
            "образование", "спорт", "путешествия", "подарки", "техника",
            "зарплата", "доход", "другое", "канцтовары", "бытовая химия"
        ]
        
        # Получаем существующие категории пользователя
        user_categories = db.query(Category).filter(Category.user_id == user_id).all()
        
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
                logging.info(f"Категория '{cached_result.category_name}' для '{description}' взята из кэша")
                return cached_result.category_name
            else:
                # Если категория из кэша не в списке разрешенных, удаляем её из кэша
                logging.warning(f"Обнаружена некорректная категория '{cached_result.category_name}' в кэше. Удаляем запись.")
                db.delete(cached_result)
                db.commit()
        
        # Пытаемся определить категорию по словарю товаров
        matched_category, confidence = match_product_to_category(normalized_description)
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
                
                logging.info(f"Категория '{matched_category}' для '{description}' определена с помощью словаря товаров")
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
                    examples.append(f"Описание: {tx.description} -> Категория: {cat_name}")
        
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
            system_prompt += "\n\nПримеры категоризации:\n" + "\n".join(examples)
        
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
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=messages,
            temperature=0.2,
            max_tokens=50
        )
        
        # Получаем ответ LLM
        category = response.choices[0].message.content.strip().lower()
        
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
            logging.warning(f"LLM вернула недопустимую категорию: '{category}'. Используем 'другое'")
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
        
        logging.info(f"Категория '{category}' для '{description}' определена с помощью LLM и сохранена в кэш")
        return category
        
    except Exception as e:
        logging.error(f"Ошибка при категоризации транзакции: {e}")
        return "другое"  # В случае ошибки возвращаем "другое" вместо None


def update_category_cache(db: Session, description: str, new_category: str) -> bool:
    """
    Обновляет кэш категорий при ручной корректировке пользователем

    Args:
        db: сессия базы данных
        description: описание транзакции
        new_category: новая категория, указанная пользователем

    Returns:
        bool: True, если обновление успешно, иначе False
    """
    try:
        # Нормализуем описание и создаем хеш
        normalized_description = description.strip().lower()
        description_hash = hashlib.md5(normalized_description.encode()).hexdigest()
        
        # Ищем запись в кэше
        cache_entry = db.query(CategoryCache).filter(
            CategoryCache.description_hash == description_hash
        ).first()
        
        if cache_entry:
            # Обновляем существующую запись
            cache_entry.category_name = new_category
            cache_entry.confidence = 1.0  # Максимальная уверенность для ручной корректировки
            cache_entry.is_corrected = True
            cache_entry.last_used_at = datetime.now()
            db.commit()
            logging.info(f"Кэш категорий обновлен: '{description}' -> '{new_category}'")
            return True
        else:
            # Создаем новую запись
            new_entry = CategoryCache(
                description_hash=description_hash,
                description=normalized_description,
                category_name=new_category,
                confidence=1.0,
                is_corrected=True
            )
            db.add(new_entry)
            db.commit()
            logging.info(f"Создана новая запись в кэше категорий: '{description}' -> '{new_category}'")
            return True
            
    except Exception as e:
        logging.error(f"Ошибка при обновлении кэша категорий: {e}")
        return False


def get_transaction_suggestions(description: str, db: Session, user_id: int) -> Dict[str, Any]:
    """
    Получает предложения по категоризации и дополнительной информации о транзакции

    Args:
        description: описание транзакции
        db: сессия базы данных
        user_id: ID пользователя в базе данных

    Returns:
        Dict[str, Any]: словарь с предложениями по категории и другим параметрам
    """
    try:
        # Проверяем, есть ли результат в кэше
        normalized_description = description.strip().lower()
        description_hash = hashlib.md5(normalized_description.encode()).hexdigest()
        
        cached_result = db.query(CategoryCache).filter(
            CategoryCache.description_hash == description_hash
        ).first()
        
        if cached_result and cached_result.is_corrected:
            # Для вручную скорректированных записей возвращаем только основную категорию
            return {
                "category": cached_result.category_name,
                "top_categories": [cached_result.category_name],
                "is_expense": True,  # По умолчанию считаем расходом
                "suggested_tags": [],
                "from_cache": True
            }
        
        # Пытаемся определить категорию по словарю товаров
        matched_category, confidence = match_product_to_category(normalized_description)
        if matched_category and confidence >= 0.7:
            return {
                "category": matched_category,
                "top_categories": [matched_category],
                "is_expense": True,  # По умолчанию считаем расходом
                "suggested_tags": [],
                "from_dictionary": True
            }
        
        # Получаем существующие категории пользователя
        categories = db.query(Category).filter(Category.user_id == user_id).all()
        categories_list = [category.name for category in categories]
        
        # Формируем запрос к LLM
        system_prompt = """Ты - система анализа финансовых транзакций. 
        Твоя задача - проанализировать описание транзакции и предоставить информацию в JSON формате.
        """
        
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
                "content": f"""Проанализируй эту транзакцию: "{description}"
                
                Доступные категории: {", ".join(categories_list)}
                
                Верни результат в формате JSON:
                {{
                    "category": "наиболее подходящая категория",
                    "top_categories": ["список из 3 наиболее вероятных категорий"],
                    "is_expense": true/false (вероятность того, что это расход, а не доход),
                    "suggested_tags": ["список из 1-3 тегов, которые можно добавить к транзакции"]
                }}
                """
            }
        ]
        
        # Отправляем запрос
        response = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=messages,
            temperature=0.5,
            max_tokens=150,
            response_format={"type": "json_object"}
        )
        
        # Парсим ответ
        try:
            import json
            result = json.loads(response.choices[0].message.content)
            
            # Добавляем флаг, что результат не из кэша
            result["from_cache"] = False
            
            # Если основная категория определена, сохраняем в кэш
            if "category" in result and result["category"]:
                if not cached_result:
                    # Создаем новую запись в кэше
                    cache_entry = CategoryCache(
                        description_hash=description_hash,
                        description=normalized_description,
                        category_name=result["category"],
                        confidence=0.9  # Высокая уверенность для результатов из JSON
                    )
                    db.add(cache_entry)
                    db.commit()
                    logging.info(f"Категория '{result['category']}' для '{description}' сохранена в кэш")
            
            return result
            
        except json.JSONDecodeError:
            logging.error("Не удалось распарсить JSON ответ от LLM")
            return {
                "category": "другое",
                "top_categories": ["другое"],
                "is_expense": True,
                "suggested_tags": [],
                "from_cache": False
            }
        
    except Exception as e:
        logging.error(f"Ошибка при получении предложений по транзакции: {e}")
        return {
            "category": "другое",
            "top_categories": ["другое"],
            "is_expense": True,
            "suggested_tags": [],
            "from_cache": False
        } 

def rebuild_category_cache(db: Session, user_id: int) -> bool:
    """
    Перестраивает кэш категорий для стандартных товаров

    Args:
        db: сессия базы данных
        user_id: ID пользователя 

    Returns:
        bool: True в случае успеха, False в случае ошибки
    """
    try:
        # 1. Очищаем существующий кэш категорий
        db.query(CategoryCache).delete()
        
        # 2. Получаем пользователя и его категории
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logging.error(f"Пользователь с ID {user_id} не найден")
            return False
            
        # 3. Создаем словарь стандартных товаров и их категорий
        standard_items = {
            # Продукты и магазины
            "магнит": "продукты",
            "пятерочка": "продукты",
            "перекресток": "продукты",
            "ашан": "продукты",
            "лента": "продукты",
            "дикси": "продукты",
            "окей": "продукты",
            "магазин": "продукты",
            "молоко": "продукты",
            "хлеб": "продукты",
            
            # Кафе
            "кафе": "еда вне дома",
            "кофейня": "еда вне дома",
            "кофе": "еда вне дома",
            "чай": "еда вне дома",
            "завтрак": "еда вне дома",
            "обед": "еда вне дома",
            "ужин": "еда вне дома",
            "ресторан": "еда вне дома",
            "макдоналдс": "еда вне дома",
            "бургер": "еда вне дома",
            
            # Быт
            "магазин": "быт",
            "бытовая химия": "быт",
            "мыло": "быт",
            "шампунь": "быт",
            "посуда": "быт",
            "губки": "быт",
            "порошок": "быт",
            
            # Одежда и обувь
            "одежда": "одежда и обувь",
            "брюки": "одежда и обувь",
            "рубашка": "одежда и обувь",
            "футболка": "одежда и обувь",
            "платье": "одежда и обувь",
            "туфли": "одежда и обувь",
            "кроссовки": "одежда и обувь",
            
            # Здоровье и красота
            "аптека": "здоровье и красота",
            "лекарства": "здоровье и красота",
            "витамины": "здоровье и красота",
            "косметика": "здоровье и красота",
            "крем": "здоровье и красота",
            
            # Транспорт
            "метро": "транспорт",
            "автобус": "транспорт",
            "такси": "транспорт",
            "бензин": "транспорт",
            "парковка": "транспорт",
            
            # Связь и интернет
            "телефон": "связь и интернет",
            "связь": "связь и интернет",
            "мтс": "связь и интернет",
            "мегафон": "связь и интернет",
            "билайн": "связь и интернет",
            "теле2": "связь и интернет",
            "интернет": "связь и интернет",
            
            # Жильё и коммунальные услуги
            "аренда": "жильё и коммунальные услуги",
            "жкх": "жильё и коммунальные услуги",
            "квартплата": "жильё и коммунальные услуги",
            "счет": "жильё и коммунальные услуги",
            "коммуналка": "жильё и коммунальные услуги",
            
            # Развлечения
            "кино": "развлечения",
            "театр": "развлечения",
            "концерт": "развлечения",
            "музей": "развлечения",
            "игры": "развлечения",
            "подписка": "развлечения"
        }
        
        # 4. Добавляем стандартные товары в кэш
        for description, category_name in standard_items.items():
            description_hash = hashlib.md5(description.encode()).hexdigest()
            
            cache_entry = CategoryCache(
                description_hash=description_hash,
                description=description,
                category_name=category_name.lower(),
                confidence=1.0,
                is_corrected=True
            )
            db.add(cache_entry)
        
        # 5. Добавляем также часто используемые транзакции на основе истории пользователя
        recent_transactions = db.query(
            Transaction, Category.name.label('category_name')
        ).join(
            Category, Transaction.category_id == Category.id
        ).filter(
            Transaction.user_id == user_id
        ).order_by(Transaction.transaction_date.desc()).limit(30).all()
        
        # Добавляем популярные транзакции пользователя в кэш
        for tx, cat_name in recent_transactions:
            if tx.description:
                normalized_description = tx.description.strip().lower()
                description_hash = hashlib.md5(normalized_description.encode()).hexdigest()
                
                # Проверяем, нет ли уже такой записи в кэше
                existing = db.query(CategoryCache).filter(
                    CategoryCache.description_hash == description_hash
                ).first()
                
                if not existing:
                    cache_entry = CategoryCache(
                        description_hash=description_hash,
                        description=normalized_description,
                        category_name=cat_name,
                        confidence=1.0,
                        is_corrected=True
                    )
                    db.add(cache_entry)
        
        db.commit()
        logging.info(f"Кэш категорий успешно перестроен")
        return True
        
    except Exception as e:
        db.rollback()
        logging.error(f"Ошибка при перестройке кэша категорий: {e}")
        return False 