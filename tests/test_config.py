import pytest
from pydantic import ValidationError

from src.config import Settings, SourcesConfig, load_sources


@pytest.fixture
def minimal_settings_env(monkeypatch):
    """Set all required environment variables for Settings instantiation."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "@testchannel")
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abc123hash")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key-123")


def test_load_sources_returns_sources_config():
    sources = load_sources("config/sources.yaml")
    assert isinstance(sources, SourcesConfig)
    assert len(sources.rss) == 9
    names = [s.name for s in sources.rss]
    assert "openai_blog" in names
    assert "venturebeat_ai" in names


def test_load_sources_telegram_channels_empty():
    sources = load_sources("config/sources.yaml")
    assert sources.telegram_channels == []


def test_load_sources_filters_present():
    sources = load_sources("config/sources.yaml")
    assert "keywords_include" in sources.filters
    assert "min_content_chars" in sources.filters


def test_load_sources_file_not_found():
    with pytest.raises(FileNotFoundError, match="Sources config not found at"):
        load_sources("/nonexistent/sources.yaml")


def test_settings_missing_required_fields_raises(monkeypatch):
    # Remove all required env vars so pydantic-settings has nothing to pull from
    for key in [
        "OPENAI_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHANNEL_ID",
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)

    # pydantic-settings also tries to read .env; point it somewhere that doesn't exist
    monkeypatch.setenv("ENV_FILE", "/nonexistent/.env")

    with pytest.raises(ValidationError):
        # Override env_file so pydantic-settings won't accidentally load a real .env
        Settings(_env_file="/nonexistent/.env")


def test_settings_valid_env_vars(minimal_settings_env):
    s = Settings(_env_file="/nonexistent/.env")
    assert s.openai_api_key == "sk-test-key"
    assert s.openai_model == "gpt-4o-mini"
    assert s.digest_top_n == 5
    assert s.min_digest_items == 3
    assert s.max_age_hours == 36
    assert s.timezone == "Europe/Moscow"


def test_settings_invalid_timezone(minimal_settings_env, monkeypatch):
    monkeypatch.setenv("TIMEZONE", "Not/ATimezone")

    with pytest.raises(ValidationError):
        Settings(_env_file="/nonexistent/.env")


def test_settings_digest_top_n_zero(minimal_settings_env, monkeypatch):
    monkeypatch.setenv("DIGEST_TOP_N", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file="/nonexistent/.env")


def test_settings_min_digest_items_exceeds_top_n(minimal_settings_env, monkeypatch):
    monkeypatch.setenv("DIGEST_TOP_N", "3")
    monkeypatch.setenv("MIN_DIGEST_ITEMS", "5")

    with pytest.raises(ValidationError):
        Settings(_env_file="/nonexistent/.env")


def test_settings_max_age_hours_zero(minimal_settings_env, monkeypatch):
    monkeypatch.setenv("MAX_AGE_HOURS", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file="/nonexistent/.env")
