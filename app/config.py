import os


class Settings:
    APP_NAME: str = "fastapi-clause-ledger"
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("APP_PORT", "18103"))
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite:///./clause_ledger.db"
    )


settings = Settings()
