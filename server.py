import os, asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient, errors

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SECRET = os.getenv("SENDER_SECRET", "fastads_test_secret_123456")
SESSIONS = os.getenv("SESSIONS_DIR", "./sessions")
ALLOWLIST = os.getenv("ALLOWLIST_FILE", "./allowlist.txt")
clients, locks = {}, {}

def allowed():
    try:
        with open(ALLOWLIST, encoding="utf-8") as f:
            return {x.strip() for x in f if x.strip() and not x.lstrip().startswith("#")}
    except FileNotFoundError:
        return set()

async def client_for(account_id):
    if account_id not in clients:
        c = TelegramClient(os.path.join(SESSIONS, f"account_{account_id}"), API_ID, API_HASH)
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
    os.makedirs(SESSIONS, exist_ok=True)
    yield
    for c in clients.values():
        await c.disconnect()

app = FastAPI(title="FastAds Authorized Sender", lifespan=lifespan)

class SendRequest(BaseModel):
    accountId: int
    message: str
    peers: list[str]
    encryptedSession: str | None = None

@app.get("/health")
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
    allow = allowed()
    results = []

    async with locks[req.accountId]:
        for raw in req.peers:
            peer = str(raw).strip()
            if peer not in allow:
                results.append({"peer": peer, "ok": False, "error": "PEER_NOT_ALLOWLISTED"})
                continue
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
    print("⚡ FASTADS TELETHON SENDER")
    print("==========================")
    print("Server: http://127.0.0.1:3000")
    print("Health: http://127.0.0.1:3000/health")
    print("==========================")
    uvicorn.run(app, host="0.0.0.0", port=3000)
