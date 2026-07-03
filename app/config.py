"""
app/config.py — HermesClaw Central Configuration
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ───────────────────────────────────────────────────────────────────
    app_env: str = "development"
    debug: bool = False
    port: int = 18790
    secret_key: str  # No default — must be set via .env or environment

    # ── Dashboard ─────────────────────────────────────────────────────────────
    dashboard_api_key: str  # No default — must be set via .env or environment

    # ── LLM ───────────────────────────────────────────────────────────────────
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    google_ai_studio_key: str = ""
    openai_api_key: str = ""

    primary_llm_base_url: str = "https://api.groq.com/openai/v1"
    primary_llm_model: str = "llama-3.3-70b-versatile"
    primary_llm_api_key: str = ""

    scheduler_llm_base_url: str = "https://api.cerebras.ai/v1"
    scheduler_llm_model: str = "llama3.1-70b"
    scheduler_llm_api_key: str = ""

    research_llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    research_llm_model: str = "gemini-2.5-flash"
    research_llm_api_key: str = ""

    fallback_llm_base_url: str = "https://openrouter.ai/api/v1"
    fallback_llm_model: str = "openrouter/free"
    fallback_llm_api_key: str = ""

    # ── Telegram ─────────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_allowed_ids: str = ""

    @property
    def allowed_telegram_ids(self) -> set[int]:
        return {
            int(x.strip())
            for x in self.telegram_allowed_ids.split(",")
            if x.strip().isdigit()
        }

    # ── AgentMail ─────────────────────────────────────────────────────────────
    agentmail_api_key: str = ""
    agentmail_inbox_id: str = ""
    agentmail_from_name: str = "Nova"

    # ── Google Sheets ─────────────────────────────────────────────────────────
    google_credentials_path: str = "credentials.json"
    google_spreadsheet_id: str = ""
    google_worksheet_name: str = "Leads"

    # ── Database ─────────────────────────────────────────────────────────────
    # Note: DatabaseManager uses raw sqlite3 with DB_PATH from database.py.
    # This URL is kept for future sqlmodel/aiosqlite migration.
    database_url: str = "sqlite+aiosqlite:///./data/orova.db"

    # ── Webhooks ─────────────────────────────────────────────────────────────
    discord_webhook_url: str = ""
    slack_webhook_url: str = ""

    # ── Scraper ───────────────────────────────────────────────────────────────
    scraper_headless: bool = True
    scraper_max_results: int = 40
    scraper_concurrency: int = 6

    # ── Business Hours (PST) ─────────────────────────────────────────────────
    biz_hours_start: int = 9
    biz_hours_end: int = 17
    biz_timezone: str = "America/Los_Angeles"

    # ── Hunt Targets ─────────────────────────────────────────────────────────
    hunt_targets: str = "home remodeling:California,automotive:West Coast,aviation:West Coast,real estate:West Coast"

    @property
    def parsed_hunt_targets(self) -> list[tuple[str, str]]:
        pairs = []
        for item in self.hunt_targets.split(","):
            if ":" in item:
                q, loc = item.split(":", 1)
                pairs.append((q.strip(), loc.strip()))
        return pairs or [("dentists", "Dallas TX")]

    @model_validator(mode="after")
    def validate_production_settings(self):
        """Ensure critical secrets are set in production."""
        if self.app_env == "production":
            if not self.secret_key or self.secret_key == "change-me-in-production":
                raise ValueError("secret_key must be set in production (remove default 'change-me-in-production')")
            if not self.dashboard_api_key:
                raise ValueError("DASHBOARD_API_KEY must be set in production")
        # Ensure at least one AI provider is configured
        has_provider = any([
            self.groq_api_key, self.openrouter_api_key,
            self.google_ai_studio_key, self.openai_api_key,
            self.primary_llm_api_key,
        ])
        if not has_provider:
            import logging
            logging.getLogger(__name__).warning(
                "⚠️  No LLM API key configured — all AI calls will fail. "
                "Set at least one of: GROQ_API_KEY, OPENROUTER_API_KEY, "
                "GOOGLE_AI_STUDIO_KEY, OPENAI_API_KEY, or PRIMARY_LLM_API_KEY"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()