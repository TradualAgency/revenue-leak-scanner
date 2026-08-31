from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://revleak:revleak@localhost:5432/revleak"
    PAGESPEED_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    SERANKING_API_KEY: str = ""
    # Gates operator-only data (the Sanity CMS export, which embeds a page password) on
    # the full-audit endpoints. The rest of a full audit is reachable by anyone holding
    # the (unguessable) audit UUID, matching the shareable-report-link model used
    # elsewhere in the app — this key exists only to keep the Sanity password itself
    # from leaking through that same link.
    OPERATOR_API_KEY: str = ""
    SCRAPER_MAX_PAGES: int = 15
    SCRAPER_TIMEOUT_SECONDS: int = 15
    SCRAPER_CONCURRENCY: int = 5
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    APP_ENV: str = "development"


settings = Settings()
