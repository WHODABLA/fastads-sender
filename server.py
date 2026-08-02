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
    for path in [f"session_{account_id}.txt", f"./session_{account_id}.txt"]:
        if os.path.exists(path):
            with open(path) as f:
                s = f.read().strip()
            if len(s) >= 350:
                print(f"✅ Account {account_id}: loaded from file (length: {len(s)})")
                return s
    s = os.getenv(f"TG_SESSION_{account_id}", "").strip()
    if len(s) >= 350:
        print(f"✅ Account {account_id}: loaded from env var (length: {len(s)})")
        return s
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

async def send_log_to_worker(log_data):
    """Send real-time log entry back to Worker for forwarding to log group."""
    if not WORKER_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as http:
            await http.post(f"{WORKER_URL}/log", json={**log_data, "secret": SECRET})
    except:
        pass

async def do_send_background(account_id, message, peers, user_id, ad_id):
    try:
        c = await client_for(account_id)
        stop_flags[account_id] = False
        results = []
        sent_count = 0
        failed_count = 0

        async with locks[account_id]:
            for raw in peers:
                if stop_flags.get(account_id, False):
                    print(f"🛑 Aborted for account {account_id}")
                    break

                peer = str(raw).strip()
                await try_join(c, peer)

                try:
                    await c.send_message(peer, message)
                    results.append({"peer": peer, "ok": True})
                    sent_count += 1
                    # Real-time log — send immediately after each group
                    await send_log_to_worker({
                        "user_id": user_id,
                        "ad_id": ad_id,
                        "peer": peer,
                        "ok": True,
                        "sent": sent_count,
                        "failed": failed_count
                    })
                except errors.FloodWaitError as e:
                    await asyncio.sleep(min(e.seconds, 30))
                    try:
                        await c.send_message(peer, message)
                        results.append({"peer": peer, "ok": True})
                        sent_count += 1
                        await send_log_to_worker({
                            "user_id": user_id, "ad_id": ad_id,
                            "peer": peer, "ok": True,
                            "sent": sent_count, "failed": failed_count
                        })
                    except Exception as e2:
                        results.append({"peer": peer, "ok": False, "error": str(e2)})
                        failed_count += 1
                        await send_log_to_worker({
                            "user_id": user_id, "ad_id": ad_id,
                            "peer": peer, "ok": False,
                            "sent": sent_count, "failed": failed_count
                        })
                except Exception as e:
                    results.append({"peer": peer, "ok": False, "error": str(e)})
                    failed_count += 1
                    await send_log_to_worker({
                        "user_id": user_id, "ad_id": ad_id,
                        "peer": peer, "ok": False,
                        "sent": sent_count, "failed": failed_count
                    })

                await asyncio.sleep(2)

        # Final summary callback
        if WORKER_URL:
            async with httpx.AsyncClient(timeout=30) as http:
                await http.post(f"{WORKER_URL}/delivery", json={
                    "secret": SECRET,
                    "user_id": user_id,
                    "ad_id": ad_id,
                    "results": results
                })

    except Exception as e:
        print(f"do_send_background error: {e}")
        if WORKER_URL:
            try:
                async with httpx.AsyncClient(timeout=10) as http:
                    await http.post(f"{WORKER_URL}/delivery", json={
                        "secret": SECRET, "user_id": user_id,
                        "ad_id": ad_id, "results": [], "error": str(e)
                    })
            except:
                pass

@asynccontextmanager
async def lifespan(app):
    yield
    for c in clients.values():
        try:
            await c.disconnect()
        except:
            pass

app = FastAPI(title="Zoro Ads Sender", lifespan=lifespan)

class SendRequest(BaseModel):
    accountId: int
    message: str
    peers: list[str]
    userId: str
    adId: int

class StopRequest(BaseModel):
    accountId: int

@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    return {"ok": True, "service": "zoro-ads-sender"}

@app.post("/stop")
async def stop(req: StopRequest, authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {SECRET}":
        raise HTTPException(401, "Unauthorized")
    stop_flags[req.accountId] = True
    return {"ok": True}

@app.post("/send")
async def send(req: SendRequest, background_tasks: BackgroundTasks, authorization: str | None = Header(default=None)):
    if authorization != f"Bearer {SECRET}":
        raise HTTPException(401, "Unauthorized")
    if not req.message.strip():
        raise HTTPException(400, "EMPTY_MESSAGE")
    await client_for(req.accountId)  # validate session before returning
    background_tasks.add_task(
        do_send_background,
        req.accountId, req.message, req.peers,
        req.userId, req.adId
    )
    return {"ok": True, "status": "sending"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "3000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
