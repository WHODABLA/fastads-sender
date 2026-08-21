import asyncio, os, json, logging
from datetime import datetime, timezone
from telethon import TelegramClient, events, functions
from telethon.tl.types import Channel
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

API_ID   = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
INTERVAL = 30 * 60

CATEGORIES = {
    "1": "Instagram-OFM", "2": "Instagram", "3": "Telegram",
    "4": "Whatsapp", "5": "Others", "6": "Exchanges",
    "7": "TikTok", "8": "Snapchat", "9": "Twitter-X",
    "10": "Youtube", "11": "Discord"
}

CATEGORY_GROUPS = {
    "Instagram-OFM": ["@ofmserviceswork", "@ofmboardj", "@ofmthehub"],
    "Instagram":     ["@chatgc1", "@chat8x", "@ichater"],
    "Telegram":      ["@marketdistrict", "@forumingly", "@rexygc"],
    "Whatsapp":      ["@chaterhub", "@textersgc", "@ogparks"],
    "Others":        ["@finanre", "@selll"],
    "Exchanges":     [], "TikTok": [], "Snapchat": [],
    "Twitter-X":     [], "Youtube": [], "Discord": [],
}

def load_customers():
    path = "/opt/zoroadss/customers.json"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)

def parse_link(link):
    try:
        from urllib.parse import urlparse
        parts = [p for p in urlparse(link.strip()).path.split("/") if p]
        if parts[0] == "c" and len(parts) >= 3:
            return f"-100{parts[1]}", int(parts[2])
        if len(parts) >= 2:
            return f"@{parts[0]}", int(parts[1])
    except:
        pass
    return None, None

def days_remaining(expiry_str):
    try:
        expiry = datetime.fromisoformat(expiry_str).replace(tzinfo=timezone.utc)
        delta  = expiry - datetime.now(timezone.utc)
        d = max(delta.days, 0)
        h = delta.seconds // 3600
        m = (delta.seconds % 3600) // 60
        return d, h, m, expiry
    except:
        return 0, 0, 0, None

sender_clients = {}

async def get_sender(account_id):
    if account_id in sender_clients and sender_clients[account_id].is_connected():
        return sender_clients[account_id]
    path = f"/opt/zoroadss/sessions/account_{account_id}"
    c = TelegramClient(path, API_ID, API_HASH)
    await c.connect()
    if not await c.is_user_authorized():
        raise RuntimeError(f"Account {account_id} not authorized")
    sender_clients[account_id] = c
    return c

async def try_join(client, peer):
    try:
        entity = await client.get_entity(peer)
        if isinstance(entity, Channel):
            await client(functions.channels.JoinChannelRequest(entity))
    except Exception as e:
        if "ALREADY" not in str(e) and "already" not in str(e):
            logging.warning(f"Join {peer}: {e}")

async def do_forward(bot, customer, state):
    account_id = customer.get("sender_account", 1)
    log_group  = customer.get("log_group_id")
    category   = state.get("category", "")
    from_chat  = state.get("from_chat")
    msg_id     = state.get("msg_id")
    owner_id   = state.get("owner_id")
    groups     = CATEGORY_GROUPS.get(category, [])

    if not groups:
        if owner_id:
            await bot.send_message(owner_id, "No groups for this category.")
        return

    try:
        sender = await get_sender(account_id)
    except Exception as e:
        if owner_id:
            await bot.send_message(owner_id, f"Sender error: {e}")
        return

    sent = failed = 0
    for peer in groups:
        try:
            await try_join(sender, peer)
            await sender.forward_messages(peer, msg_id, from_chat)
            sent += 1
            if log_group:
                peer_clean = peer.lstrip("@")
                try:
                    await bot.send_message(
                        int(log_group),
                        f"✅ Successfully forwarded to: [{peer_clean}](https://t.me/{peer_clean})",
                        parse_mode="md",
                        link_preview=False
                    )
                except Exception as le:
                    logging.warning(f"Log: {le}")
        except Exception as e:
            failed += 1
            if log_group:
                try:
                    await bot.send_message(int(log_group), f"❌ Failed: {peer}\n{str(e)[:80]}")
                except:
                    pass
        await asyncio.sleep(2)

    state["last_sent"] = asyncio.get_event_loop().time()
    if owner_id:
        await bot.send_message(owner_id,
            f"📊 Done\n✅ Sent: {sent}  ❌ Failed: {failed}  📬 Total: {sent+failed}")

async def run_customer_bot(customer):
    token  = customer["bot_token"]
    name   = customer.get("customer_name", "Customer")
    expiry = customer.get("expiry", "")
    states = {}

    def get_state(uid):
        if uid not in states:
            states[uid] = {
                "step": "idle", "from_chat": None, "msg_id": None,
                "category": None, "active": False, "last_sent": 0, "owner_id": uid
            }
        return states[uid]

    bot = TelegramClient(StringSession(), API_ID, API_HASH)
    await bot.start(bot_token=token)
    logging.info(f"Started: {name}")

    @bot.on(events.NewMessage(pattern="/start"))
    async def on_start(event):
        s = get_state(event.sender_id)
        s["step"] = "waiting_link"
        d, h, m, _ = days_remaining(expiry)
        await event.respond(
            f"👋 Welcome to **{name}**!\n\n"
            f"⏳ Validity: **{d} Days {h} Hours {m} Minutes**\n\n"
            f"📨 Send your message link to start:\n"
            f"`https://t.me/yourchannel/123`"
        )

    @bot.on(events.NewMessage(pattern="/validity"))
    async def on_validity(event):
        d, h, m, exp = days_remaining(expiry)
        await event.respond(
            f"⏳ **Validity Remaining:**\n{d} Days {h} Hours {m} Minutes\n\n"
            f"📅 Expiry: {exp.strftime('%d %b %Y %H:%M UTC') if exp else 'N/A'}"
        )

    @bot.on(events.NewMessage(pattern="/stop"))
    async def on_stop(event):
        s = get_state(event.sender_id)
        s["active"] = False
        s["step"] = "idle"
        await event.respond("⏹ Forwarding Stopped.\n\nSend /start to begin again.")

    @bot.on(events.NewMessage(pattern="/change"))
    async def on_change(event):
        s = get_state(event.sender_id)
        s["active"] = False
        s["step"] = "waiting_link"
        await event.respond(
            "🔄 Change Process Initiated\n\n"
            "1. Send new message link\n"
            "2. Select category\n"
            "Changes take effect from next loop.\n\n"
            "Send the new message link:"
        )

    @bot.on(events.NewMessage(pattern="/Yes"))
    async def on_yes(event):
        s = get_state(event.sender_id)
        if s.get("step") != "waiting_confirm":
            return
        s["active"] = True
        s["step"] = "active"
        s["last_sent"] = 0
        await event.respond(
            f"✅ Forwarding Activated!\n"
            f"• Channel: {s['from_chat']}\n"
            f"• Message ID: {s['msg_id']}\n"
            f"• Category: {s['category']}\n\n"
            f"🔄 Repeats every 30 minutes."
        )
        await do_forward(bot, customer, s)

    @bot.on(events.NewMessage(pattern="/No"))
    async def on_no(event):
        s = get_state(event.sender_id)
        s["step"] = "waiting_link"
        await event.respond("❌ Cancelled.\n\nSend a new message link to try again.")

    @bot.on(events.NewMessage())
    async def on_msg(event):
        if event.text and event.text.startswith("/"):
            return
        uid  = event.sender_id
        s    = get_state(uid)
        text = (event.text or "").strip()

        if s["step"] == "waiting_link":
            fc, mid = parse_link(text)
            if not fc or not mid:
                await event.respond(
                    "❌ Invalid link.\nSend: `https://t.me/yourchannel/123`"
                )
                return
            s["from_chat"] = fc
            s["msg_id"]    = mid
            s["step"]      = "waiting_category"
            cats = "\n".join(f"{k}. {v}" for k, v in CATEGORIES.items())
            await event.respond(f"📁 Available Categories:\n{cats}\n\nReply with the category number:")

        elif s["step"] == "waiting_category":
            if text not in CATEGORIES:
                await event.respond("❌ Invalid. Send a number from 1 to 11.")
                return
            s["category"] = CATEGORIES[text]
            s["step"]     = "waiting_confirm"
            await event.respond(
                f"📋 Message Details\n"
                f"• Channel: {s['from_chat']}\n"
                f"• Message ID: {s['msg_id']}\n"
                f"• Category: {s['category']}\n\n"
                f"Give Confirmation By /Yes or /No"
            )

    async def loop():
        while True:
            await asyncio.sleep(60)
            now = asyncio.get_event_loop().time()
            for uid, s in list(states.items()):
                if s.get("active") and now - s.get("last_sent", 0) >= INTERVAL:
                    try:
                        await do_forward(bot, customer, s)
                    except Exception as e:
                        logging.error(f"Loop {uid}: {e}")

    asyncio.ensure_future(loop())
    await bot.run_until_disconnected()

async def main():
    customers = load_customers()
    if not customers:
        logging.warning("No customers found. Add to /opt/zoroadss/customers.json and restart.")
        await asyncio.sleep(999999)
        return
    logging.info(f"Starting {len(customers)} bot(s)...")
    await asyncio.gather(*[run_customer_bot(c) for c in customers])

if __name__ == "__main__":
    asyncio.run(main())
