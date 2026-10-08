from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://mercado:mercado@localhost:5432/mercado"
    SECRET_KEY: str = "dev-secret-change-me"
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "deepseek/deepseek-chat"
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OBS_WINDOW_DAYS: int = 90
    EMA_HALF_LIFE_DAYS: float = 30.0
    APP_TZ: str = "America/Sao_Paulo"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    DATASET_DIR: str = "/datasets"
    ML_MODEL_PATH: str = "/app/ml_data/model.txt"
    DEFAULT_MARKET_CUSTOMERS: int = 100
    FRONTEND_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    SIMULATOR_ENABLED: bool = True

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()