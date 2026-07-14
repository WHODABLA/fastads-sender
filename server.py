import os, asyncio, httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel
from telethon import TelegramClient, errors, functions
from telethon.tl.types import Channel
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
        print(f"Join failed for {peer}: {err}")
        return False

async def do_send(account_id, message, peers, callback_url, callback_secret, user_id, ad_id):
    """Runs in background — sends to all groups then calls Worker back with results."""
    try:
        c = await client_for(account_id)
        results = []
        async with locks[account_id]:
            for raw in peers:
                peer = str(raw).strip()
                # Auto join
                await try_join(c, peer)
                # Send
                try:
                    await c.send_message(peer, message)
                    results.append({"peer": peer, "ok": True})
                except errors.FloodWaitError as e:
                    print(f"FloodWait {e.seconds}s for {peer}")
                    await asyncio.sleep(e.seconds)
                    try:
                        await c.send_message(peer, message)
                        results.append({"peer": peer, "ok": True})
                    except Exception as e2:
                        results.append({"peer": peer, "ok": False, "error": str(e2)})
                except Exception as e:
                    results.append({"peer": peer, "ok": False, "error": str(e)})
                await asyncio.sleep(2)

        # Call Worker back with results
        async with httpx.AsyncClient(timeout=30) as http:
            await http.post(
                callback_url,
                json={
                    "secret": callback_secret,
                    "user_id": user_id,
                    "ad_id": ad_id,
                    "results": results
                }
            )
    except Exception as e:
        print(f"do_send error: {e}")
        # Still try to callback with error
        try:
            async with httpx.AsyncClient(timeout=10) as http:
                await http.post(callback_url, json={
                    "secret": callback_secret,
                    "user_id": user_id,
                    "ad_id": ad_id,
                    "results": [],
                    "error": str(e)
                })
        except:
            pass

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
    callbackUrl: str
    callbackSecret: str
    userId: str
    adId: int

@app.get("/health")
async def health():
    return {"ok": True, "service": "fastads-telethon-sender"}

@app.post("/send")
async def send(req: SendRequest, background_tasks: BackgroundTasks, authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {SECRET}":
        raise HTTPException(401, "Unauthorized")
    # Return immediately — send happens in background
    background_tasks.add_task(
        do_send,
        req.accountId,
        req.message,
        req.peers,
        req.callbackUrl,
        req.callbackSecret,
        req.userId,
        req.adId
    )
    return {"ok": True, "status": "sending_in_background"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "3000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
