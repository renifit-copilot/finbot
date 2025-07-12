from pydantic_settings import BaseSettings
from pydantic import Field
import os
from pathlib import Path


class Settings(BaseSettings):
    """Настройки приложения"""
    # Токен Telegram бота
    BOT_TOKEN: str = Field(..., description="Токен Telegram бота")

    # API ключ для OpenRouter
    OPENROUTER_API_KEY: str = Field(..., description="API ключ для OpenRouter")

    # Путь к базе данных
    DB_PATH: str = Field(default="sqlite:///finbot.db",
                         description="Путь к базе данных SQLite")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Создаем экземпляр настроек
settings = Settings()
