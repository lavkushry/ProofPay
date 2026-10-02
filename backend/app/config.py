from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import uuid

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application & Environment
    APP_NAME: str = "ProofPay"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Seeded Agency Identity (I8 scope fence)
    DEFAULT_AGENCY_ID: uuid.UUID = Field(default_factory=lambda: uuid.UUID("10000000-0000-4000-8000-000000000001"))
    DEFAULT_AGENCY_NAME: str = "Apex Software Studio (Demo)"
    DEFAULT_ADVISORY_LOCK_KEY: int = 847291038472

    # Database
    # Defaults to SQLite async for zero-friction local testing, overridden by postgresql+asyncpg in docker
    DATABASE_URL: str = "sqlite+aiosqlite:///./proofpay.db"

    # PayPal Sandbox Constraints (Invariant I7: Reject live mode)
    PAYPAL_MODE: str = "sandbox"
    PAYPAL_BASE_URL: str = "https://api-m.sandbox.paypal.com"
    PAYPAL_CLIENT_ID: str = "demo_client_id"
    PAYPAL_CLIENT_SECRET: str = "demo_client_secret"
    PAYPAL_WEBHOOK_ID: str = "demo_webhook_id"
    PAYER_ACCOUNT_REF: str = "payer_sandbox_us"

    # Security & Custody (Invariant I1: secrets held only by executor)
    ENCRYPTION_KEY: str = "proofpay-secret-32-byte-key-12345" # Used for receiver ciphertext
    INTERNAL_SERVICE_TOKEN: str = "runner-internal-service-secret-token"

    # Runner & Fixture URLs
    FIXTURE_URL: str = "http://localhost:8080"
    RUNNER_URL: str = "http://localhost:8081"

    # LLM Settings
    LLM_PROVIDER: str = "gemini" # or mock for deterministic testing
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    COMPILER_PROMPT_VERSION: str = "compiler-v0.1"
    REVIEWER_PROMPT_VERSION: str = "reviewer-v0.1"
    SCHEMA_VERSION: str = "proofpay-tools-v0.1"

settings = Settings()
