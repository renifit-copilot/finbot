#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import logging
import os
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("purge_db.log"),
        logging.StreamHandler()
    ]
)

def purge_database(db_path="finbot.db"):
    """
    Полностью очищает все таблицы в базе данных, сохраняя структуру.
    
    Args:
        db_path: путь к файлу базы данных (по умолчанию "finbot.db")
    """
    try:
        # Проверяем существование файла БД
        if not os.path.exists(db_path):
            logging.error(f"База данных {db_path} не найдена")
            return False
            
        # Создаем резервную копию перед очисткой
        backup_path = f"{db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with open(db_path, 'rb') as src, open(backup_path, 'wb') as dst:
            dst.write(src.read())
        logging.info(f"Создана резервная копия базы данных: {backup_path}")
        
        # Подключаемся к базе данных
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Получаем список всех таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        # Отключаем проверку внешних ключей для упрощения очистки
        cursor.execute("PRAGMA foreign_keys = OFF;")
        
        # Очищаем каждую таблицу
        for table in tables:
            table_name = table[0]
            # Пропускаем системные таблицы SQLite
            if table_name.startswith('sqlite_'):
                continue
                
            try:
                cursor.execute(f"DELETE FROM {table_name};")
                logging.info(f"Таблица {table_name} очищена")
            except Exception as e:
                logging.error(f"Ошибка при очистке таблицы {table_name}: {e}")
        
        # Включаем проверку внешних ключей обратно
        cursor.execute("PRAGMA foreign_keys = ON;")
        
        # Сбрасываем счетчики автоинкремента
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            if table_name.startswith('sqlite_'):
                continue
                
            try:
                cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table_name}';")
                logging.info(f"Сброшен счетчик автоинкремента для таблицы {table_name}")
            except Exception as e:
                logging.warning(f"Не удалось сбросить счетчик для таблицы {table_name}: {e}")
        
        # Сохраняем изменения и закрываем соединение
        conn.commit()
        conn.close()
        
        logging.info("База данных успешно очищена")
        return True
        
    except Exception as e:
        logging.error(f"Произошла ошибка при очистке базы данных: {e}")
        return False

if __name__ == "__main__":
    # Запрашиваем подтверждение у пользователя
    print("ВНИМАНИЕ! Эта операция удалит ВСЕ данные из базы данных!")
    print("Будет создана резервная копия, но восстановление потребует ручного вмешательства.")
    confirmation = input("Введите 'да' для подтверждения: ")
    
    if confirmation.lower() == 'да':
        success = purge_database()
        if success:
            print("База данных успешно очищена.")
        else:
            print("Произошла ошибка при очистке базы данных. Проверьте лог-файл purge_db.log")
    else:
        print("Операция отменена.") 