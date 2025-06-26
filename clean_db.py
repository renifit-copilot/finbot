import sqlite3
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Подключение к базе данных
conn = sqlite3.connect('finbot.db')
cursor = conn.cursor()

try:
    # 1. Удаляем неправильные категории
    bad_categories = [
        'магнит', 'спар', 'ld', 'e2', 't2', 'кб', 'хуй', 'чипсы', 'салат',
        'ресторан "плакучая ива"'
    ]
    
    # Формируем строку для SQL запроса
    placeholders = ', '.join(['?' for _ in bad_categories])
    delete_query = f"DELETE FROM categories WHERE name IN ({placeholders})"
    
    # Выполняем запрос
    cursor.execute(delete_query, bad_categories)
    logging.info(f"Удалено {cursor.rowcount} неправильных категорий")
    
    # 2. Очищаем таблицу кэша категорий
    cursor.execute("DELETE FROM category_cache")
    logging.info(f"Очищено {cursor.rowcount} записей из кэша категорий")
    
    # Сохраняем изменения
    conn.commit()
    logging.info("Изменения сохранены в базе данных")

except Exception as e:
    # Откатываем изменения в случае ошибки
    conn.rollback()
    logging.error(f"Произошла ошибка: {e}")

finally:
    # Закрываем соединение
    conn.close()
    logging.info("Соединение с базой данных закрыто") 