from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    LLM_API_KEY: str = ""
    LLM_PROVIDER: str = "mock"
    DATABASE_URL: str = "sqlite:///./smarty_vibz.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # WhatsApp Business Cloud API
    WHATSAPP_APP_ID: str = ""
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_WEBHOOK_SECRET: str = ""

    # PMIS Push (Primavera P6 / MS Project)
    PMIS_PUSH_ENDPOINT_URL: str = ""
    PMIS_PUSH_API_KEY: str = ""
    PMIS_PUSH_TIMEOUT_SECONDS: int = 30
    PMIS_PUSH_MAX_RETRIES: int = 3
    PMIS_PUSH_RETRY_BACKOFF_SECONDS: int = 2

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()