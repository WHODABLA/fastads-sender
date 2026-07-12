import os, asyncio
from telethon import TelegramClient

API_ID = int(input("Telegram API ID: ").strip())
API_HASH = input("Telegram API Hash: ").strip()
SESSIONS = "./sessions"

async def main():
    os.makedirs(SESSIONS, exist_ok=True)
    account_id = int(input("Local account ID (1, 2, 3...): ").strip())
    c = TelegramClient(os.path.join(SESSIONS, f"account_{account_id}"), API_ID, API_HASH)
    await c.start()
    me = await c.get_me()
    print(f"✅ Authorized Telegram ID: {me.id}")
    print(f"Use local sender account ID: {account_id}")
    await c.disconnect()

asyncio.run(main())
