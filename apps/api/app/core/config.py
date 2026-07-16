import os
from typing import List, Union, Optional
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class OracleSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    telegram_bot_token: str = Field(
        validation_alias=AliasChoices("TELEGRAM_ORACLE_BOT_TOKEN", "TELEGRAM_BOT_TOKEN")
    )
    gemini_api_key: Optional[str] = Field(default=None, validation_alias="GEMINI_ORACLE_API_KEY")
    gemini_model: str = Field(default="gemini-flash-latest", validation_alias="GEMINI_ORACLE_MODEL")
    gemini_enrichment: bool = Field(default=True, validation_alias="ORACLE_GEMINI_ENRICHMENT")
    gemini_discovery: bool = Field(default=True, validation_alias="ORACLE_GEMINI_DISCOVERY")
    groq_api_key: Optional[str] = Field(default=None, validation_alias="GROQ_ORACLE_API_KEY")
    groq_model: str = Field(default="openai/gpt-oss-20b", validation_alias="GROQ_ORACLE_MODEL")
    font_metadata_model: str = Field(default="openai/gpt-oss-20b", validation_alias="GROQ_FONT_MODEL")
    scrape_start_hour_utc: int = Field(default=21, validation_alias="ORACLE_SCRAPE_START_HOUR_UTC")
    briefing_hour_utc: int = Field(default=10, validation_alias="ORACLE_BRIEFING_HOUR_UTC")
    pinterest_access_token: Optional[str] = Field(default=None, validation_alias="PINTEREST_ACCESS_TOKEN")
    pinterest_enabled: bool = Field(default=False, validation_alias="ORACLE_PINTEREST_ENABLED")
    pinterest_regions: str = Field(default="US,GB+IE,CA", validation_alias="PINTEREST_REGIONS")
    bing_webmaster_api_key: Optional[str] = Field(default=None, validation_alias="BING_WEBMASTER_API_KEY")
    yandex_wordstat_token: Optional[str] = Field(default=None, validation_alias="YANDEX_WORDSTAT_TOKEN")
    yandex_enabled: bool = Field(default=False, validation_alias="ORACLE_YANDEX_ENABLED")

class WriterSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    telegram_bot_token: Optional[str] = Field(default=None, validation_alias="TELEGRAM_WRITER_BOT_TOKEN")
    telegram_review_channel_id: Optional[str] = Field(default=None, validation_alias="TELEGRAM_WRITER_REVIEW_CHANNEL_ID")
    gemini_api_key: Optional[str] = Field(default=None, validation_alias="GEMINI_WRITER_API_KEY")
    groq_api_key: Optional[str] = Field(default=None, validation_alias="GROQ_WRITER_API_KEY")
    groq_model: str = Field(default="openai/gpt-oss-120b", validation_alias="GROQ_WRITER_MODEL")

class SeoSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    telegram_bot_token: Optional[str] = Field(default=None, validation_alias="TELEGRAM_SEO_BOT_TOKEN")
    telegram_admin_chat_id: Optional[str] = Field(default=None, validation_alias="TELEGRAM_SEO_ADMIN_CHAT_ID")
    groq_api_key: Optional[str] = Field(default=None, validation_alias="GROQ_SEO_API_KEY")
    groq_model: str = Field(default="openai/gpt-oss-20b", validation_alias="GROQ_SEO_MODEL")
    enabled: bool = Field(default=False, validation_alias="SEO_BOT_ENABLED")
    report_weekday_utc: int = Field(default=0, ge=0, le=6, validation_alias="SEO_REPORT_WEEKDAY_UTC")
    report_hour_utc: int = Field(default=9, ge=0, le=23, validation_alias="SEO_REPORT_HOUR_UTC")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    # --- TELEGRAM (Top Level) ---
    TELEGRAM_API_ID: int = Field(validation_alias="TELEGRAM_API_ID")
    TELEGRAM_API_HASH: str = Field(validation_alias="TELEGRAM_API_HASH")
    TELEGRAM_MAIN_CHANNEL_ID: int = Field(
        validation_alias=AliasChoices("TELEGRAM_MAIN_CHANNEL_ID", "TARGET_CHANNEL_ID")
    )
    
    # --- NESTED AI SETTINGS ---
    oracle: OracleSettings = Field(default_factory=OracleSettings)
    writer: WriterSettings = Field(default_factory=WriterSettings)
    seo: SeoSettings = Field(default_factory=SeoSettings)

    # --- CLOUDFLARE R2 ---
    R2_ACCOUNT_ID: str = Field(validation_alias="R2_ACCOUNT_ID")
    R2_ACCESS_KEY_ID: str = Field(validation_alias="R2_ACCESS_KEY_ID")
    R2_SECRET_ACCESS_KEY: str = Field(validation_alias="R2_SECRET_ACCESS_KEY")
    R2_BUCKET_NAME: str = Field(validation_alias="R2_BUCKET_NAME")
    R2_PUBLIC_BASE_URL: str = Field(validation_alias="R2_PUBLIC_BASE_URL")

    # --- CLOUDFLARE PAGES ---
    CF_PAGES_DEPLOY_HOOK_URL: str = Field(validation_alias="CF_PAGES_DEPLOY_HOOK_URL")
    DEPLOY_MONTHLY_LIMIT: int = Field(default=80, validation_alias="DEPLOY_MONTHLY_LIMIT")
    DEPLOY_MANUAL_COOLDOWN_SECONDS: int = Field(default=900, validation_alias="DEPLOY_MANUAL_COOLDOWN_SECONDS")
    DEPLOY_STALE_LOCK_SECONDS: int = Field(default=21600, validation_alias="DEPLOY_STALE_LOCK_SECONDS")

    # --- SECURITY & INFRA ---
    BUILD_SECRET: str = Field(validation_alias="BUILD_SECRET")
    SITE_URL: str = Field(default="https://sinpes.com", validation_alias="SITE_URL")
    DATABASE_PATH: str = Field(default="/opt/sinpes/data/sinpes.db", validation_alias="DATABASE_PATH")
    APP_ENV: str = Field(default="production")  # Default to production for safety

    # --- EXTERNAL APIs ---
    POLLINATIONS_API_KEY: Optional[str] = Field(default=None, validation_alias="POLLINATIONS_API_KEY")
    IMAGE_GEN_WORKER_URL: Optional[str] = Field(default=None, validation_alias="IMAGE_GEN_WORKER_URL")
    IMAGE_GEN_WORKER_SECRET: Optional[str] = Field(default=None, validation_alias="IMAGE_GEN_WORKER_SECRET")
    
    # --- PIPELINE CADENCE ---
    QUEUE_INTERVAL_MINUTES: int = Field(default=30, validation_alias="QUEUE_INTERVAL_MINUTES")
    QUEUE_POLL_SECONDS: int = Field(default=5, validation_alias="QUEUE_POLL_SECONDS")
    ARTICLE_QUEUE_INTERVAL_MINUTES: int = Field(default=720, validation_alias="ARTICLE_QUEUE_INTERVAL_MINUTES")
    MAX_RETRIES: int = Field(default=3)

    # --- WEBHOOK IPs (Stored as a LIST, not a string) ---
    # Allow both string (from .env) and list (for testing) formats
    WEBHOOK_ALLOWED_IPS: Union[str, List[str]] = Field(default="149.154.160.0/20,91.108.4.0/22", validation_alias="WEBHOOK_ALLOWED_IPS")

    # --- CORS (Will be computed after .env is loaded) ---
    CORS_ORIGINS: List[str] = []  # Placeholder, will be set by validator

    @field_validator("WEBHOOK_ALLOWED_IPS", mode="before")
    @classmethod
    def parse_webhook_ips(cls, v):
        """Ensures WEBHOOK_ALLOWED_IPS is always a List[str] internally."""
        if isinstance(v, str):
            return [ip.strip() for ip in v.split(",") if ip.strip()]
        return v

    @model_validator(mode="after")
    def set_cors_origins(self):
        """Dynamically sets CORS_ORIGINS AFTER environment variables are loaded."""
        if self.APP_ENV == "production":
            self.CORS_ORIGINS = ["https://sinpes.com", "https://www.sinpes.com"]
        else:
            self.CORS_ORIGINS = [
                "http://localhost:4321",
                "http://127.0.0.1:4321",
                "https://sinpes.com"
            ]
        return self

config = Settings()
