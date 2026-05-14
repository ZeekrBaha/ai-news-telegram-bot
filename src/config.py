from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    telegram_bot_token: str
    telegram_channel_id: str
    telegram_api_id: int
    telegram_api_hash: str
    telethon_session_name: str = "reader"
    supabase_url: str
    supabase_service_key: str
    schedule_hour: int = 9
    schedule_minute: int = 0
    timezone: str = "Europe/Moscow"
    digest_top_n: int = 5
    min_digest_items: int = 3
    max_age_hours: int = 36
    log_level: str = "INFO"
    enable_hero_media: bool = True
    default_hero_path: str = "assets/default_hero.png"

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, KeyError):
            raise ValueError(f"Invalid timezone: {value!r}")
        return value

    @field_validator("digest_top_n")
    @classmethod
    def validate_digest_top_n(cls, value: int) -> int:
        if value < 1:
            raise ValueError("digest_top_n must be >= 1")
        return value

    @field_validator("min_digest_items")
    @classmethod
    def validate_min_digest_items(cls, value: int) -> int:
        if value < 1:
            raise ValueError("min_digest_items must be >= 1")
        return value

    @field_validator("max_age_hours")
    @classmethod
    def validate_max_age_hours(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_age_hours must be > 0")
        return value

    @model_validator(mode="after")
    def validate_min_vs_top(self) -> "Settings":
        if self.min_digest_items > self.digest_top_n:
            raise ValueError("min_digest_items must be <= digest_top_n")
        return self


class RssSource(BaseModel):
    name: str
    url: str


class SourcesConfig(BaseModel):
    rss: list[RssSource]
    telegram_channels: list[str]
    filters: dict  # keep flexible for now


def load_sources(path: str = "config/sources.yaml") -> SourcesConfig:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError as e:
        raise FileNotFoundError(
            f"Sources config not found at '{path}'. Copy config/sources.yaml from the example."
        ) from e
    return SourcesConfig(**data)


def get_settings() -> Settings:
    return Settings()
