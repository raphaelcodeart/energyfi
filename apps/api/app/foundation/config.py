from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    log_level: str = "info"

    database_url: str = "postgresql+psycopg://sosnet:sosnet@localhost:5432/sosnet"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket_documents: str = "sosnet-documents"
    # Public-read bucket for photos; documents stay in the private bucket above.
    s3_bucket_media: str = "sosnet-media"
    s3_region: str = "eu-central-1"
    s3_use_ssl: bool = False

    cors_origins: list[str] = ["http://localhost:3000"]

    # Exposes /backend/docs, /backend/redoc and /backend/openapi.json publicly.
    # Useful in dev/demo; set ENABLE_API_DOCS=false in production to avoid
    # disclosing the full API surface (see docs/server-migration-guide.md).
    enable_api_docs: bool = True

    # Outbound mail. With smtp_host empty, emails are written to the audit log
    # instead of being sent (see docs/business-rules.md §Password reset).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = "no-reply@sosnet.demo"
    smtp_use_tls: bool = True

    # Account that receives invoice-redemption payments (served by
    # GET /payment-info). When empty, the wizard tells the customer to contact
    # administration rather than showing a fake IBAN.
    company_bank_iban: str = ""
    company_bank_holder: str = "SOSNET"

    # Public dashboard URL, used to build links in emails: the API sits behind
    # nginx and cannot infer its own public hostname.
    public_app_base_url: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
