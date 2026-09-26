from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    member_c_port: int = 8103
    database_url: str = "sqlite:///./member_c.db"
    internal_api_token: str = "dev-internal-token-change-me"

    member_a_base: str = "http://localhost:8101"
    member_b_base: str = "http://localhost:8102"
    member_d_base: str = "http://localhost:8104"

    # 事件重试
    event_max_retries: int = 3
    event_retry_delay_seconds: float = 1.0


settings = Settings()