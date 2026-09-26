from datetime import datetime, timezone

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    member_a_port: int = 8101
    member_a_database_url: str = "sqlite:///./member_a.db"
    internal_api_token: str = "dev-internal-token-change-me"

    member_b_base: str = "http://localhost:8102"
    member_c_base: str = "http://localhost:8103"
    member_d_base: str = "http://localhost:8104"


settings = Settings()


def iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")
