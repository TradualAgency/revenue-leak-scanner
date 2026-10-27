from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://revleak:revleak@localhost:5432/revleak"
    PAGESPEED_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    SERANKING_API_KEY: str = ""
    DATAFORSEO_LOGIN: str = ""
    DATAFORSEO_PASSWORD: str = ""
    # Gates the operator side of the app: starting audits, the full audit working file
    # (`GET /full-audit/{id}`), the scans list and the Sanity export. Prospects read the
    # public `/full-audit/{id}/report` projection instead.
    OPERATOR_API_KEY: str = ""
    # Fixed conversion for the USD app-store list prices in data/known_plugins.json.
    # Shown as an indication ("±€X/mnd"); review occasionally, not a live rate.
    USD_TO_EUR_RATE: float = 0.92
    # Where every client-facing CTA points (the Sanity report's button included).
    CONTACT_URL: str = "https://tradual.com/book-a-call"
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

    # Fix agents (operator-only): turn audit findings into implementation packages.
    # Cost knobs: model, effort ("low" | "medium" | "high") and turn budget per agent.
    FIX_AGENT_MODEL: str = "claude-sonnet-5"
    FIX_AGENT_EFFORT: str = "medium"
    FIX_AGENT_MAX_TURNS: int = 10
    # Finding-verifier (app/agents/verifier): checks every priced finding on the live
    # store before the euros are final. Off in the audit pipeline by default (cost);
    # the operator starts it per audit. Model falls back to FIX_AGENT_MODEL.
    VERIFIER_ENABLED: bool = False
    VERIFIER_MODEL: str | None = "claude-sonnet-5"
    VERIFIER_EFFORT: str = "medium"
    VERIFIER_MAX_TURNS: int = 8
    # Funnel agent (app/agents/funnel): walks home -> search -> PDP -> cart -> checkout in a
    # mobile browser. Off in the audit pipeline by default (cost); the operator starts it
    # per audit. Needs Chromium (`playwright install chromium`).
    FUNNEL_AGENT_ENABLED: bool = False
    FUNNEL_AGENT_MODEL: str = "claude-sonnet-5"
    FUNNEL_AGENT_EFFORT: str = "low"
    FUNNEL_AGENT_MAX_TURNS: int = 20
    FUNNEL_AGENT_TIMEOUT_S: int = 300
    # Fernet key (`Fernet.generate_key()`) for the per-audit Shopify Admin token. Empty
    # means tokens can't be stored — the agents then work outside-only.
    TOKEN_ENCRYPTION_KEY: str = ""
    SHOPIFY_ADMIN_API_VERSION: str = "2026-10"


settings = Settings()
