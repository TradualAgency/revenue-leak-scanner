from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://revleak:revleak@localhost:5432/revleak"
    PAGESPEED_API_KEY: str = ""
    SCRAPER_MAX_PAGES: int = 15
    SCRAPER_TIMEOUT_SECONDS: int = 15
    SCRAPER_CONCURRENCY: int = 5
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    APP_ENV: str = "development"


settings = Settings()
