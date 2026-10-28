from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    bot_token: str = ''
    database_url: str = 'sqlite+aiosqlite:///./swissotel.db'
    web_host: str = '0.0.0.0'
    web_port: int = 8000
    admin_telegram_ids: str = ''
    secret_key: str = 'development-only-change-me'
    bot_username: str = ''
    port: int = 8000

    @property
    def admin_ids(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_telegram_ids.split(',') if x.strip().isdigit()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
