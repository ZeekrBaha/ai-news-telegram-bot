from supabase import Client, create_client

from src.config import Settings

_client: Client | None = None


def get_client(settings: Settings) -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client
