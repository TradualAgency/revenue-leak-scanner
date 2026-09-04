from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://revleak:revleak@localhost:5432/revleak"
    PAGESPEED_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    SERANKING_API_KEY: str = ""
    DATAFORSEO_LOGIN: str = ""
    DATAFORSEO_PASSWORD: str = ""
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

    # Competitor benchmark — kept low relative to SCRAPER_CONCURRENCY because
    # BackgroundTasks runs in the same event loop/process as the API server. Measuring
    # N domains concurrently multiplies scraper connections, PSI calls, and DNS probes
    # against that same process; too high a value trades wall-clock for measurement
    # failures under load (which each cost a data point in the market median).
    COMPETITOR_CONCURRENCY: int = 2
    COMPETITOR_MEASURE_LIMIT: int = 8
    COMPETITOR_SCRAPER_MAX_PAGES: int = 6
    COMPETITOR_DOMAIN_TIMEOUT_S: int = 180
    COMPETITOR_SNAPSHOT_TTL_DAYS: int = 14
    COMPETITOR_SNAPSHOT_NEGATIVE_TTL_DAYS: int = 2


settings = Settings()
