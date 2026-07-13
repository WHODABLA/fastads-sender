import os, asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient, errors, functions
from telethon.tl.types import Channel, Chat
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

app = FastAPI(title="FastAds Sender", lifespan=lifespan)

class SendRequest(BaseModel):
    accountId: int
    message: str
    peers: list[str]

class JoinRequest(BaseModel):
    accountId: int
    peers: list[str]

@app.get("/health")
async def health():
    return {"ok": True, "service": "fastads-telethon-sender"}

@app.post("/join")
async def join_groups(req: JoinRequest, authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {SECRET}":
        raise HTTPException(401, "Unauthorized")
    c = await client_for(req.accountId)
    results = []
    # No lock here — join is a separate pre-send step, runs independently
    for raw in req.peers:
        peer = str(raw).strip()
        try:
            entity = await c.get_entity(peer)
            if isinstance(entity, Channel):
                # Public channel or supergroup — can self-join
                await c(functions.channels.JoinChannelRequest(entity))
                results.append({"peer": peer, "ok": True})
            else:
                # Regular group — needs invite link, can't self-join
                # Just check if we can get dialogs for it (already member)
                results.append({"peer": peer, "ok": True, "note": "regular_group"})
        except Exception as e:
            err = str(e)
            if any(x in err for x in ["ALREADY", "already", "USER_ALREADY_PARTICIPANT", "user_already"]):
                results.append({"peer": peer, "ok": True})
            else:
                results.append({"peer": peer, "ok": False, "error": err})
        await asyncio.sleep(2)
    return {"ok": True, "results": results}

@app.post("/send")
async def send(req: SendRequest, authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {SECRET}":
        raise HTTPException(401, "Unauthorized")
    c = await client_for(req.accountId)
    results = []
    async with locks[req.accountId]:
        for raw in req.peers:
            peer = str(raw).strip()
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
