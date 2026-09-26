from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    member_d_port: int = 8104
    member_d_database_url: str = "sqlite:///./member_d.db"
    internal_api_token: str = "dev-internal-token-change-me"

    login_default_password: str = "demo123456"
    jwt_secret: str = "dev-jwt-secret-change-me"
    jwt_expires_seconds: int = 7200

    member_a_base: str = "http://localhost:8101"
    member_b_base: str = "http://localhost:8102"
    member_c_base: str = "http://localhost:8103"


settings = Settings()
