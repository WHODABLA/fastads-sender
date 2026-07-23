import os, asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient, errors, functions
from telethon.tl.types import Channel
from telethon.sessions import StringSession

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SECRET = os.getenv("SENDER_SECRET", "changeme")
clients, locks = {}, {}

def load_session(account_id):
    # 1. Try session file in repo root (most reliable — no paste truncation)
    for path in [f"session_{account_id}.txt", f"./session_{account_id}.txt"]:
        if os.path.exists(path):
            with open(path) as f:
                s = f.read().strip()
            if len(s) >= 350:
                print(f"✅ Account {account_id}: loaded from file {path} (length: {len(s)})")
                return s
            else:
                print(f"⚠️ Account {account_id}: file {path} too short ({len(s)} chars)")

    # 2. Try env var
    s = os.getenv(f"TG_SESSION_{account_id}", "").strip()
    if len(s) >= 350:
        print(f"✅ Account {account_id}: loaded from env var (length: {len(s)})")
        return s
    elif s:
        print(f"⚠️ Account {account_id}: env var too short ({len(s)} chars) — likely truncated")

    print(f"❌ Account {account_id}: no valid session found")
    return None

async def client_for(account_id):
    if account_id not in clients:
        session_str = load_session(account_id)
        if not session_str:
            raise RuntimeError(f"NO_VALID_SESSION_FOR_ACCOUNT_{account_id}")
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

async def try_join(client, peer):
    try:
        entity = await client.get_entity(peer)
        if isinstance(entity, Channel):
            await client(functions.channels.JoinChannelRequest(entity))
        return True
    except Exception as e:
        err = str(e)
        if any(x in err for x in ["ALREADY", "already", "USER_ALREADY_PARTICIPANT"]):
            return True
        return False

@asynccontextmanager
async def lifespan(app):
    yield
    for c in clients.values():
        try:
            await c.disconnect()
        except:
            pass

app = FastAPI(title="FastAds Sender", lifespan=lifespan)

class SendRequest(BaseModel):
    accountId: int
    message: str
    peers: list[str]

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"ok": True, "service": "fastads-sender"}

@app.post("/send")
async def send(req: SendRequest, authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {SECRET}":
        raise HTTPException(401, "Unauthorized")
    if not req.message.strip():
        raise HTTPException(400, "EMPTY_MESSAGE")

    c = await client_for(req.accountId)
    results = []

    async with locks[req.accountId]:
        for raw in req.peers:
            peer = str(raw).strip()
            await try_join(c, peer)
            try:
                await c.send_message(peer, req.message)
                results.append({"peer": peer, "ok": True})
            except errors.FloodWaitError as e:
                await asyncio.sleep(e.seconds)
                try:
                    await c.send_message(peer, req.message)
                    results.append({"peer": peer, "ok": True})
                except Exception as e2:
                    results.append({"peer": peer, "ok": False, "error": str(e2)})
            except Exception as e:
                results.append({"peer": peer, "ok": False, "error": str(e)})
            await asyncio.sleep(2)

    return {"ok": True, "results": results}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "3000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
