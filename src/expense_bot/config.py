from __future__ import annotations

from functools import cached_property
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    database_path: str = Field(default="data/expenses.db", alias="DATABASE_PATH")
    default_currency: str = Field(default="SGD", alias="DEFAULT_CURRENCY")
    bot_timezone: str = Field(default="Asia/Singapore", alias="BOT_TIMEZONE")
    polling_timeout: int = Field(default=30, alias="POLLING_TIMEOUT")
    restart_delay_seconds: int = Field(default=5, alias="RESTART_DELAY_SECONDS")
    max_restart_delay_seconds: int = Field(default=60, alias="MAX_RESTART_DELAY_SECONDS")
    sqlite_busy_timeout_ms: int = Field(default=5000, alias="SQLITE_BUSY_TIMEOUT_MS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @cached_property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.bot_timezone)

    @cached_property
    def database_file(self) -> Path:
        return Path(self.database_path)
