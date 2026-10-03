import uuid
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "ProofPay"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]
    SESSION_CSRF_KEY: SecretStr = SecretStr("")
    SESSION_COOKIE_SECURE: bool = True
    SESSION_TTL_SECONDS: int = Field(default=28800, ge=300, le=86400)
    DEMO_JUDGE_ACCESS_CODE: SecretStr = SecretStr("")
    DEMO_OWNER_ACCESS_CODE: SecretStr = SecretStr("")
    DEMO_MAYA_ACCESS_CODE: SecretStr = SecretStr("")
    DEMO_LEO_ACCESS_CODE: SecretStr = SecretStr("")
    WORKER_LEASE_SECONDS: int = Field(default=120, ge=5, le=600)
    WORKER_HEARTBEAT_SECONDS: int = Field(default=20, ge=1, le=60)
    WORKER_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=10)

    DEFAULT_AGENCY_ID: uuid.UUID = uuid.UUID("10000000-0000-4000-8000-000000000001")
    DEFAULT_AGENCY_NAME: str = "Apex Software Studio (Demo)"
    DEFAULT_ADVISORY_LOCK_KEY: int = 847291038472
    WORKSPACE_PRINCIPAL_LIMIT_CENTS: int = Field(default=1000000, gt=0)

    DATABASE_URL: str = "postgresql+asyncpg://proofpay_api:local_api_only@localhost:5432/proofpay"
    FIXTURE_URL: str = "http://localhost:8080"
    LLM_PROVIDER: str = "unconfigured"
    GEMINI_API_KEY: SecretStr = SecretStr("")
    OPENAI_API_KEY: SecretStr = SecretStr("")
    COMPILER_PROMPT_VERSION: str = "compiler-v0.1"
    REVIEWER_PROMPT_VERSION: str = "reviewer-v0.1"
    SCHEMA_VERSION: str = "proofpay-tools-v0.1"


class PayPalSettings(BaseSettings):
    """Load financial credentials only when the executor is instantiated."""

    model_config = SettingsConfigDict(
        env_file=".env.executor", env_file_encoding="utf-8", extra="ignore",
        validate_assignment=True,
    )

    PAYPAL_MODE: Literal["sandbox"] = "sandbox"
    PAYPAL_BASE_URL: Literal["https://api-m.sandbox.paypal.com"] = (
        "https://api-m.sandbox.paypal.com"
    )
    PAYPAL_CLIENT_ID: SecretStr = SecretStr("")
    PAYPAL_CLIENT_SECRET: SecretStr = SecretStr("")
    PAYPAL_WEBHOOK_ID: str = ""


settings = Settings()
