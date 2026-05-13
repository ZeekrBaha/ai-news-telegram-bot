"""One-time interactive script to create a Telethon session file."""
import asyncio
import os
import sys


async def main():
    try:
        from telethon import TelegramClient
    except ImportError:
        print("Error: telethon not installed. Run: uv sync")
        sys.exit(1)

    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    session_name = os.environ.get("TELETHON_SESSION_NAME", "reader")

    if not api_id or not api_hash:
        print("Error: TELEGRAM_API_ID and TELEGRAM_API_HASH must be set in environment")
        sys.exit(1)

    os.makedirs("sessions", exist_ok=True)
    session_path = f"sessions/{session_name}"

    client = TelegramClient(session_path, int(api_id), api_hash)

    await client.start()
    me = await client.get_me()
    print(f"Logged in as: {me.first_name} {me.last_name or ''} (@{me.username})")
    print(f"Session saved to: {session_path}.session")
    print("Keep this file secure — it grants access to your Telegram account.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
