import pytesseract
import re
from PIL import Image
import logging
from pathlib import Path
import os


# Настройка пути к tesseract.exe если он не в PATH
if os.name == 'nt':  # Для Windows
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


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
        
        # Используем 'eng' вместо 'rus', который может отсутствовать
        # Большинство цифр и многие названия магазинов распознаются и с английской моделью
        text = pytesseract.image_to_string(image, lang='eng')
        logging.debug(f"OCR извлек текст: {text}")
        
        # Ищем сумму в тексте (ищем число с запятой/точкой и рублевым знаком или словом руб)
        amount_patterns = [
            r'(?:ИТОГО|ИТОГ|ВСЕГО|СУММА|TOTAL|SUM|AMOUNT)(?:\s*[:]?\s*)(\d+[\.,]\d{2})',  # ИТОГО: 123.45
            r'(?:ИТОГО|ИТОГ|ВСЕГО|СУММА|TOTAL|SUM|AMOUNT)(?:\s*[:]?\s*)(\d+)',            # ИТОГО: 123
            r'(\d+[\.,]\d{2})(?:\s*р|\s*руб|\s*₽|\s*RUB)',                      # 123.45 руб
            r'(\d+)(?:\s*р|\s*руб|\s*₽|\s*RUB)',                                # 123 руб
            r'TOTAL[:\s]+(\d+[\.,]\d{2})',                                     # TOTAL: 123.45
            r'TOTAL[:\s]+(\d+)',                                               # TOTAL: 123
            r'(\d+[\.,]\d{2})',                                                # просто число с десятичной точкой/запятой
        ]
        
        amount = 0.0
        for pattern in amount_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Берем первое совпадение и конвертируем его в число
                amount_str = str(matches[0]).replace(',', '.')
                try:
                    amount = float(amount_str)
                    break
                except (ValueError, TypeError):
                    continue
        
        # Пытаемся определить категорию по ключевым словам
        categories = {
            "продукты": ["магазин", "продукт", "супермаркет", "пятерочка", "магнит", "перекресток", 
                         "ашан", "лента", "shop", "market", "store", "supermarket", "grocery"],
            "кафе": ["кафе", "ресторан", "бар", "кофе", "чай", "кофейня", "макдоналдс", "бургер", 
                     "пицца", "cafe", "restaurant", "coffee", "tea", "burger", "pizza"],
            "транспорт": ["такси", "метро", "автобус", "проезд", "билет", "uber", "яндекс такси",
                          "taxi", "metro", "bus", "ticket", "fare", "transport"],
            "развлечения": ["кино", "театр", "концерт", "выставка", "музей", "парк",
                           "cinema", "movie", "theatre", "concert", "museum", "entertainment"],
            "связь": ["связь", "интернет", "телефон", "мобильный",
                     "internet", "phone", "mobile", "communication"],
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