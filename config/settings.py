from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "SmarTraderAI"
    APP_VERSION: str = "2.0.0"

    # Data source
    YAHOO_CHART_URL: str = "https://query1.finance.yahoo.com/v8/finance/chart"
    MARKET_REFRESH_SECONDS: int = 15
    REQUEST_TIMEOUT_SECONDS: float = 10.0
    CACHE_TTL_SECONDS: int = 15
    CANDLE_CACHE_TTL_SECONDS: int = 60
    WATCHLIST: str = (
        "RELIANCE.NS,TCS.NS,HDFCBANK.NS,ICICIBANK.NS,INFY.NS,SBIN.NS,"
        "BHARTIARTL.NS,TMPV.NS,WIPRO.NS,KOTAKBANK.NS,ASIANPAINT.NS,"
        "MARUTI.NS,AXISBANK.NS,LT.NS,DMART.NS"
    )
    INDICES: str = "^NSEI,^NSEBANK,^BSESN"

    # SQL (PostgreSQL / MySQL / SQLite via SQLAlchemy, optional)
    DATABASE_URL: str = ""
    SQL_ECHO: bool = False

    # Cache and event streaming (Redis / Kafka, optional)
    REDIS_URL: str = ""
    EVENT_BUS: str = "memory"  # memory | redis | kafka
    KAFKA_BOOTSTRAP_SERVERS: str = ""
    KAFKA_TOPIC: str = "smartraderai.market"
    REDIS_STREAM: str = "smartraderai.market"

    # OAuth 2.0 client-credentials clients (comma-separated id:secret pairs)
    OAUTH_CLIENT_ID: str = "smartraderai"
    OAUTH_CLIENT_SECRET: str = ""
    OAUTH_CLIENTS: str = ""  # extra "id:secret,id2:secret2" pairs

    # Cloud object storage (local | s3 | azure)
    CLOUD_STORAGE: str = "local"
    AWS_REGION: str = "ap-south-1"
    AWS_S3_BUCKET: str = ""
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_CONTAINER: str = "smartraderai"

    # Optional sidecar services (Node/Express, Java/Spring Boot, Django)
    NODE_GATEWAY_URL: str = ""
    SPRING_STREAM_URL: str = ""
    DJANGO_ADMIN_URL: str = ""

    # Optional broker / AI credentials
    MONGO_URI: str = ""
    DATABASE_NAME: str = "smartraderai"
    KITE_API_KEY: str = ""
    KITE_API_SECRET: str = ""
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_BRIEF_TTL_SECONDS: int = 600

    # Risk guard: real order placement must be explicitly enabled by the operator
    TRADING_ENABLED: bool = False
    SIGNAL_MIN_CONFIDENCE: int = 55

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def watchlist(self) -> list[str]:
        return [s.strip() for s in self.WATCHLIST.split(",") if s.strip()]

    @property
    def indices(self) -> list[str]:
        return [s.strip() for s in self.INDICES.split(",") if s.strip()]

    @property
    def oauth_clients(self) -> dict[str, str]:
        clients: dict[str, str] = {}
        if self.OAUTH_CLIENT_ID and self.OAUTH_CLIENT_SECRET:
            clients[self.OAUTH_CLIENT_ID] = self.OAUTH_CLIENT_SECRET
        for pair in self.OAUTH_CLIENTS.split(","):
            if ":" in pair:
                client_id, secret = pair.split(":", 1)
                if client_id.strip() and secret.strip():
                    clients[client_id.strip()] = secret.strip()
        return clients

    @property
    def broker_configured(self) -> bool:
        return bool(self.KITE_API_KEY and self.KITE_API_SECRET)

    @property
    def openai_configured(self) -> bool:
        return bool(self.OPENAI_API_KEY and self.OPENAI_API_KEY.strip())


settings = Settings()
