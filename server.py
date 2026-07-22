import os, asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SECRET = os.getenv("SENDER_SECRET", "fastads_test_secret_123456")
clients, locks = {}, {}

async def client_for(account_id):
    if account_id not in clients:
        session_str = os.getenv(f"TG_SESSION_{account_id}")
        if not session_str:
            raise RuntimeError(f"NO_SESSION_ENV_FOR_ACCOUNT_{account_id}")
        c = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await c.connect()
        if not await c.is_user_authorized():
            await c.disconnect()
            raise RuntimeError("ACCOUNT_NOT_AUTHORIZED")
        clients[account_id] = c
        locks[account_id] = asyncio.Lock()
    if not clients[account_id].is_connected():
        await clients[account_id].connect()
    return clients[account_id]

@asynccontextmanager
async def lifespan(app):
    yield
    for c in clients.values():
        await c.disconnect()

app = FastAPI(title="FastAds Authorized Sender", lifespan=lifespan)

class SendRequest(BaseModel):
    accountId: int
    message: str
    peers: list[str]
    encryptedSession: str | None = None

# Fix HEAD method for UptimeRobot
@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"ok": True, "service": "fastads-telethon-sender"}

@app.post("/send")
async def send(req: SendRequest, authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {SECRET}":
        raise HTTPException(401, "Unauthorized")
    if not req.message.strip():
        raise HTTPException(400, "EMPTY_MESSAGE")
    if len(req.peers) > 50:
        raise HTTPException(400, "MAX_50_PEERS_PER_REQUEST")

    c = await client_for(req.accountId)
    results = []

    async with locks[req.accountId]:
        for raw in req.peers:
            peer = str(raw).strip()
            try:
                await c.send_message(peer, req.message)
                results.append({"peer": peer, "ok": True})
            except errors.FloodWaitError as e:
                results.append({"peer": peer, "ok": False, "error": "FLOOD_WAIT", "retryAfter": int(e.seconds)})
                break
            except errors.ChatWriteForbiddenError:
                results.append({"peer": peer, "ok": False, "error": "CHAT_WRITE_FORBIDDEN"})
            except Exception as e:
                results.append({"peer": peer, "ok": False, "error": type(e).__name__})
    return {"ok": True, "results": results}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "3000"))
    print("⚡ FASTADS TELETHON SENDER")
    print("==========================")
    print(f"Server: http://0.0.0.0:{port}")
    print(f"Health: http://0.0.0.0:{port}/health")
    print("==========================")
    uvicorn.run(app, host="0.0.0.0", port=port)
