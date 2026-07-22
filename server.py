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

def load_session(account_id):
    """
    Load session string for account_id.
    Priority:
    1. Env var TG_SESSION_<id> (if long enough — not truncated)
    2. Render Secret File at /etc/secrets/session_<id>
    3. Render Secret File at /etc/secrets/session_<id>.txt
    """
    # 1. Env var
    session_str = os.getenv(f"TG_SESSION_{account_id}", "").strip()
    if len(session_str) >= 350:
        print(f"Account {account_id}: loaded from env var (length: {len(session_str)})")
        return session_str

    # 2. Secret file (no extension) — recommended for multi-account
    for path in [
        f"/etc/secrets/session_{account_id}",
        f"/etc/secrets/session_{account_id}.txt",
    ]:
        if os.path.exists(path):
            with open(path) as f:
                data = f.read().strip()
            if len(data) >= 350:
                print(f"Account {account_id}: loaded from {path} (length: {len(data)})")
                return data
            else:
                print(f"Account {account_id}: file {path} too short ({len(data)} chars) — possibly truncated")

    print(f"Account {account_id}: no valid session found")
    import glob
    print(f"Available secret files: {glob.glob('/etc/secrets/*')}")
    return None

async def client_for(account_id):
    if account_id not in clients:
        session_str = load_session(account_id)
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
                # Check if user stopped ads before each group send
                try:
                    status_url = f"{callback_url.replace('/delivery', '/status')}?user_id={user_id}&secret={callback_secret}"
                    async with httpx.AsyncClient(timeout=5) as check:
                        r = await check.get(status_url)
                        data = r.json()
                        if not data.get("active", True):
                            print(f"User {user_id} stopped ads — aborting send")
                            results.append({"peer": peer, "ok": False, "error": "STOPPED_BY_USER"})
                            continue
                except Exception:
                    pass  # if status check fails, keep sending

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

@app.api_route("/health", methods=["GET", "HEAD"])
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
