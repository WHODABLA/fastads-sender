import os, asyncio, httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel
from telethon import TelegramClient, errors, functions
from telethon.tl.types import Channel
from telethon.sessions import StringSession

API_ID = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SECRET = os.getenv("SENDER_SECRET", "changeme")
WORKER_URL = os.getenv("WORKER_URL", "")
clients, locks, stop_flags = {}, {}, {}

def load_session(account_id):
    for path in [
        f"/opt/zoroadss/sessions/account_{account_id}.session",
        f"/opt/zoroadss/sessions/session_{account_id}.txt"
    ]:
        if os.path.exists(path):
            if path.endswith(".txt"):
                with open(path) as f:
                    s = f.read().strip()
                if len(s) >= 350:
                    print(f"✅ Account {account_id}: string session")
                    return ("string", s)
            else:
                print(f"✅ Account {account_id}: file session")
                return ("file", path.replace(".session", ""))
    s = os.getenv(f"TG_SESSION_{account_id}", "").strip()
    if len(s) >= 350:
        return ("string", s)
    return None

async def client_for(account_id):
    if account_id not in clients:
        data = load_session(account_id)
        if not data:
            raise RuntimeError(f"NO_SESSION_FOR_ACCOUNT_{account_id}")
        t, v = data
        session = StringSession(v) if t == "string" else v
        c = TelegramClient(session, API_ID, API_HASH)
        await c.connect()
        if not await c.is_user_authorized():
            await c.disconnect()
            raise RuntimeError("ACCOUNT_NOT_AUTHORIZED")
        clients[account_id] = c
        locks[account_id] = asyncio.Lock()
        stop_flags[account_id] = False
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
        if any(x in str(e) for x in ["ALREADY", "already", "USER_ALREADY_PARTICIPANT"]):
            return True
        return False

async def send_log(user_id, peer, ok):
    if not WORKER_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            await http.post(f"{WORKER_URL}/log", json={
                "secret": SECRET,
                "user_id": user_id,
                "peer": peer,
                "ok": ok
            })
    except:
        pass

async def do_forward(account_id, from_chat_id, msg_id, message, peers, user_id, ad_id):
    try:
        c = await client_for(account_id)
        stop_flags[account_id] = False
        results = []

        async with locks[account_id]:
            for raw in peers:
                if stop_flags.get(account_id, False):
                    break
                peer = str(raw).strip()

                # Auto join first
                await try_join(c, peer)

                try:
                    if from_chat_id and msg_id:
                        # Forward the message
                        await c.forward_messages(peer, msg_id, from_chat_id)
                    else:
                        # Fallback to sending text
                        await c.send_message(peer, message)
                    results.append({"peer": peer, "ok": True})
                    await send_log(user_id, peer, True)
                except errors.FloodWaitError as e:
                    await asyncio.sleep(min(e.seconds, 30))
                    try:
                        if from_chat_id and msg_id:
                            await c.forward_messages(peer, msg_id, from_chat_id)
                        else:
                            await c.send_message(peer, message)
                        results.append({"peer": peer, "ok": True})
                        await send_log(user_id, peer, True)
                    except Exception as e2:
                        results.append({"peer": peer, "ok": False, "error": str(e2)})
                        await send_log(user_id, peer, False)
                except Exception as e:
                    results.append({"peer": peer, "ok": False, "error": str(e)})
                    await send_log(user_id, peer, False)

                await asyncio.sleep(2)

        # Send final summary back to worker
        if WORKER_URL:
            async with httpx.AsyncClient(timeout=30) as http:
                await http.post(f"{WORKER_URL}/delivery", json={
                    "secret": SECRET,
                    "user_id": user_id,
                    "ad_id": ad_id,
                    "results": results
                })
    except Exception as e:
        print(f"do_forward error: {e}")
        if WORKER_URL:
            try:
                async with httpx.AsyncClient(timeout=10) as http:
                    await http.post(f"{WORKER_URL}/delivery", json={
                        "secret": SECRET,
                        "user_id": user_id,
                        "ad_id": ad_id,
                        "results": [],
                        "error": str(e)
                    })
            except:
                pass

@asynccontextmanager
async def lifespan(app):
    os.makedirs("/opt/zoroadss/sessions", exist_ok=True)
    yield
    for c in clients.values():
        try:
            await c.disconnect()
        except:
            pass

app = FastAPI(title="Zoro Ads Sender", lifespan=lifespan)

class ForwardRequest(BaseModel):
    accountId: int
    fromChatId: str | None = None
    msgId: int | None = None
    message: str = ""
    peers: list[str]
    userId: str
    adId: int

class StopRequest(BaseModel):
    accountId: int

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"ok": True, "service": "zoro-ads-sender", "accounts": len(clients)}

@app.post("/stop")
async def stop(req: StopRequest, authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {SECRET}":
        raise HTTPException(401, "Unauthorized")
    stop_flags[req.accountId] = True
    return {"ok": True}

@app.post("/forward")
async def forward(req: ForwardRequest, background_tasks: BackgroundTasks, authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {SECRET}":
        raise HTTPException(401, "Unauthorized")
    # Validate session before returning
    await client_for(req.accountId)
    background_tasks.add_task(
        do_forward,
        req.accountId,
        req.fromChatId,
        req.msgId,
        req.message,
        req.peers,
        req.userId,
        req.adId
    )
    return {"ok": True, "status": "forwarding"}

# Keep /send for backward compatibility
@app.post("/send")
async def send(req: ForwardRequest, background_tasks: BackgroundTasks, authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {SECRET}":
        raise HTTPException(401, "Unauthorized")
    await client_for(req.accountId)
    background_tasks.add_task(
        do_forward,
        req.accountId,
        req.fromChatId,
        req.msgId,
        req.message,
        req.peers,
        req.userId,
        req.adId
    )
    return {"ok": True, "status": "sending"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "3000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
