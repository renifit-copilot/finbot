import pytesseract
import re
from PIL import Image
import logging
from pathlib import Path
import os


def parse_receipt(image_path: str) -> tuple[float, str]:
    """
    Обрабатывает изображение чека с помощью OCR и извлекает сумму и категорию
    
    Args:
        image_path: путь к файлу изображения
        
    Returns:
        tuple: (сумма расхода, категория расхода)
    """
    try:
        # Открываем изображение
        image = Image.open(image_path)
        
        # Извлекаем текст из изображения
        text = pytesseract.image_to_string(image, lang='rus')
        logging.debug(f"OCR извлек текст: {text}")
        
        # Ищем сумму в тексте (ищем число с запятой/точкой и рублевым знаком или словом руб)
        amount_patterns = [
            r'(?:ИТОГО|ИТОГ|ВСЕГО|СУММА)(?:\s*[:]?\s*)(\d+[\.,]\d{2})',  # ИТОГО: 123.45
            r'(?:ИТОГО|ИТОГ|ВСЕГО|СУММА)(?:\s*[:]?\s*)(\d+)',            # ИТОГО: 123
            r'(\d+[\.,]\d{2})(?:\s*р|\s*руб|\s*₽)',                      # 123.45 руб
            r'(\d+)(?:\s*р|\s*руб|\s*₽)',                                # 123 руб
        ]
        
        amount = 0.0
        for pattern in amount_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Берем первое совпадение и конвертируем его в число
                amount_str = matches[0].replace(',', '.')
                amount = float(amount_str)
                break
        
        # Пытаемся определить категорию по ключевым словам
        categories = {
            "продукты": ["магазин", "продукт", "супермаркет", "пятерочка", "магнит", "перекресток", "ашан", "лента"],
            "кафе": ["кафе", "ресторан", "бар", "кофе", "чай", "кофейня", "макдоналдс", "бургер", "пицца"],
            "транспорт": ["такси", "метро", "автобус", "проезд", "билет", "uber", "яндекс такси"],
            "развлечения": ["кино", "театр", "концерт", "выставка", "музей", "парк"],
            "связь": ["связь", "интернет", "телефон", "мобильный"],
        }
        
        category = "другое"
        for cat, keywords in categories.items():
            for keyword in keywords:
                if keyword.lower() in text.lower():
                    category = cat
                    break
            if category != "другое":
                break
        
        logging.info(f"Найдены сумма {amount} руб. и категория '{category}'")
        return amount, category
        
    except Exception as e:
        logging.error(f"Ошибка при обработке чека: {e}")
        return 0.0, "ошибка" 