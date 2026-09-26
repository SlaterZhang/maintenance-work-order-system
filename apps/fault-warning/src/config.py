from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    member_b_port: int = 8102
    member_b_database_url: str = "sqlite:///./member_b.db"
    internal_api_token: str = "dev-internal-token-change-me"

    member_a_base: str = "http://localhost:8101"
    member_c_base: str = "http://localhost:8103"
    member_d_base: str = "http://localhost:8104"

    model_version: str = "rule-engine-1.0.0"
    low_score_threshold: float = 85.0
    medium_score_threshold: float = 60.0
    high_score_threshold: float = 30.0


settings = Settings()
