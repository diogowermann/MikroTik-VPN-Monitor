from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VPN_MONITOR_",
        env_file=".env",
        extra="ignore",
    )

    database_url: str = "sqlite:///./vpn-monitor.db"
    query_api_key: str | None = None
    log_level: str = "INFO"
    bind_host: str = "127.0.0.1"
    bind_port: int = Field(default=8092, ge=1, le=65535)


@lru_cache
def get_settings() -> Settings:
    return Settings()
