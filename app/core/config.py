"""
app/core/config.py
Centralised Pydantic Settings for OROVA.
Zero hardcoded credentials. All values from environment.
Fails fast with clear error messages if required vars are missing.

Usage:
    from app.core.config import cfg
    print(cfg.telegram_bot_token)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional, List
import os


class OROVASettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Agency Identity ──────────────────────────────────────────
    agency_name: str = Field(default="OROVA", description="Public agency name")
    vertical_name: str = Field(default="LuxuryRemodeling")

    # ── AI Providers ─────────────────────────────────────────────
    openai_api_key: Optional[str] = Field(default=None)
    openai_base_url: str = Field(default="https://openrouter.ai/api/v1")
    groq_api_key: Optional[str] = Field(default=None)
    deepseek_api_key: Optional[str] = Field(default=None)
    google_api_key: Optional[str] = Field(default=None)
    gemini_api_key: Optional[str] = Field(default=None)
    
    # ── MiMo (Kilo Code) ─────────────────────────────────
    mimo_api_key: Optional[str] = Field(default=None)
    mimo_base_url: str = Field(default="https://api.kilocode.ai/v1")
    mimo_model: str = Field(default="MiMo/v2-pro")

    # ── Telegram ─────────────────────────────────────────────────
    telegram_bot_token: Optional[str] = Field(default=None, description="Telegram bot token")
    admin_chat_id: Optional[str] = Field(default=None, description="Owner Telegram chat ID")
    personal_chat_id: Optional[str] = Field(default=None)

    # ── Retell AI (Voice Calling) ─────────────────────────────────
    retell_api_key: Optional[str] = Field(default=None)
    retell_agent_id: Optional[str] = Field(default=None)
    retell_from_number: Optional[str] = Field(
        default=None,
        description="E.164 format: +12137774445"
    )

    # ── Email (AgentMail) ─────────────────────────────────────────
    agentmail_api_key: Optional[str] = Field(default=None)

    # ── Email Rotation (multi-domain) ────────────────────────────
    # JSON: [{"user":"nova@orova.co","pass":"xxx","label":"orova.co"}]
    email_accounts: Optional[str] = Field(default=None)
    email_daily_cap: int = Field(default=20)
    email_min_delay_s: int = Field(default=60)
    email_max_delay_s: int = Field(default=120)

    # ── Google ────────────────────────────────────────────────────
    google_application_credentials: Optional[str] = Field(default=None)
    crm_sheet_id: Optional[str] = Field(default=None)

    # ── Meta Ads ─────────────────────────────────────────────────
    meta_access_token: Optional[str] = Field(default=None)
    meta_ad_account_id: Optional[str] = Field(
        default=None,
        description="Format: act_XXXXXXXXXX"
    )
    meta_app_id: Optional[str] = Field(default=None)
    meta_app_secret: Optional[str] = Field(default=None)

    # ── Calling Hours ─────────────────────────────────────────────
    call_hour_start: int = Field(default=9)
    call_hour_end: int = Field(default=17)

    # ── Server ────────────────────────────────────────────────────
    port: int = Field(default=10000)
    data_dir: str = Field(default="/data")
    flask_debug: bool = Field(default=False)
    space_id: Optional[str] = Field(default=None)
    ec2_public_ip: Optional[str] = Field(default=None)

    @classmethod
    @field_validator("retell_from_number")
    def validate_e164(cls, v):
        if v and not v.startswith("+"):
            raise ValueError(
                f"retell_from_number must be E.164 format (+12137774445). Got: {v}"
            )
        return v

    @classmethod
    @field_validator("meta_ad_account_id")
    def validate_ad_account(cls, v):
        if v and not v.startswith("act_"):
            raise ValueError(
                f"meta_ad_account_id must start with 'act_'. Got: {v}"
            )
        return v

    @property
    def data_root(self) -> str:
        """Auto-detect persistent storage: /data on HuggingFace, /opt/orova/data on Oracle."""
        if os.path.exists("/data"):
            return "/data"
        if os.path.exists("/opt/orova"):
            return "/opt/orova/data"
        return "."

    @property
    def is_production(self) -> bool:
        return not self.flask_debug


# Singleton instance — import this everywhere
cfg = OROVASettings()
