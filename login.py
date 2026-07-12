import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = int(input("Telegram API ID: ").strip())
API_HASH = input("Telegram API Hash: ").strip()

async def main():
    account_id = int(input("Local account ID (1, 2, 3...): ").strip())
    c = TelegramClient(StringSession(), API_ID, API_HASH)
    await c.start()
    me = await c.get_me()
    session_string = c.session.save()

    print(f"\n✅ Authorized Telegram ID: {me.id}")
    print(f"Local sender account ID: {account_id}")
    print(f"\nAdd this to Render as env var TG_SESSION_{account_id}:")
    print(session_string)
    print("\nTreat this string like a password — anyone with it controls this Telegram account.")

    await c.disconnect()

asyncio.run(main())
