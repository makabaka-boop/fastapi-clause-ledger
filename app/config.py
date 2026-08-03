from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLAUSE_LEDGER_")

    app_name: str = "clause-ledger"
    database_url: str = "sqlite:///./clause_ledger.db"
    port: int = 18103


settings = Settings()
