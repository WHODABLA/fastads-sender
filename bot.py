"""
Zoro Ads — Multi Customer Bot System
Each customer gets their own bot token + log group
All bots run from this single script on the VPS
"""
import asyncio, os, json, logging
from datetime import datetime, timezone
from telethon import TelegramClient, events, functions
from telethon.tl.types import Channel
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO)

# ─── Config ────────────────────────────────────────────────────────────────────
API_ID   = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
SENDER_ACCOUNT = int(os.getenv("SENDER_ACCOUNT", "1"))  # which session file to use
INTERVAL = 30 * 60  # 30 minutes fixed

CATEGORIES = {
    "1":  "Instagram-OFM",
    "2":  "Instagram",
    "3":  "Telegram",
    "4":  "Whatsapp",
    "5":  "Others",
    "6":  "Exchanges",
    "7":  "TikTok",
    "8":  "Snapchat",
    "9":  "Twitter-X",
    "10": "Youtube",
    "11": "Discord"
}

# Groups per category — add your groups here
CATEGORY_GROUPS = {
    "Instagram-OFM": [
        "@ofmserviceswork",
        "@ofmboardj",
        "@ofmthehub",
    ],
    "Instagram": [
        "@chatgc1",
        "@chat8x",
        "@ichater",
    ],
    "Telegram": [
        "@marketdistrict",
        "@forumingly",
        "@rexygc",
    ],
    "Whatsapp": [
        "@chaterhub",
        "@textersgc",
        "@ogparks",
    ],
    "Others": [
        "@finanre",
        "@selll",
    ],
    "Exchanges": [],
    "TikTok": [],
    "Snapchat": [],
    "Twitter-X": [],
    "Youtube": [],
    "Discord": [],
}

# ─── Customer config ───────────────────────────────────────────────────────────
# customers.json format:
# [
#   {
#     "bot_token": "123456:ABC...",
#     "log_group_id": "-1001234567890",
#     "customer_name": "Customer A",
#     "expiry": "2026-09-01T00:00:00",
#     "sender_account": 1
#   }
# ]

def load_customers():
    path = "/opt/zoroadss/customers.json"
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)

def save_customers(customers):
    with open("/opt/zoroadss/customers.json", "w") as f:
        json.dump(customers, f, indent=2)

# ─── Per-customer state ────────────────────────────────────────────────────────
# state per user_id within a bot:
# { user_id: { "step": "waiting_link"|"waiting_category"|"waiting_confirm",
#              "msg_link": "", "from_chat": "", "msg_id": 0,
#              "category": "", "active": False, "last_sent": 0 } }

customer_states = {}  # bot_token -> { user_id -> state }

# ─── Sender client (Telethon userbot) ─────────────────────────────────────────
sender_clients = {}  # account_id -> TelegramClient

async def get_sender(account_id):
    if account_id in sender_clients:
        if sender_clients[account_id].is_connected():
            return sender_clients[account_id]
    session_path = f"/opt/zoroadss/sessions/account_{account_id}"
    c = TelegramClient(session_path, API_ID, API_HASH)
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
            pass

def parse_link(link):
    try:
        from urllib.parse import urlparse
        url = urlparse(link.strip())
        parts = [p for p in url.path.split("/") if p]
        if parts[0] == "c" and len(parts) >= 3:
            return f"-100{parts[1]}", int(parts[2])
        if len(parts) >= 2:
            return f"@{parts[0]}", int(parts[1])
    except:
        pass
    return None, None

# ─── Forward to groups ─────────────────────────────────────────────────────────
async def forward_to_groups(bot_client, customer, state, user_id):
    account_id = customer.get("sender_account", 1)
    log_group  = customer.get("log_group_id")
    category   = state.get("category", "")
    from_chat  = state.get("from_chat")
    msg_id     = state.get("msg_id")
    groups     = CATEGORY_GROUPS.get(category, [])

    if not groups:
        await bot_client.send_message(user_id, "❌ No groups found for this category.")
        return

    try:
        sender = await get_sender(account_id)
    except Exception as e:
        await bot_client.send_message(user_id, f"❌ Sender error: {e}")
        return

    sent = 0
    failed = 0

    for peer in groups:
        try:
            await try_join(sender, peer)
            await sender.forward_messages(peer, msg_id, from_chat)
            sent += 1

            # Real-time log to log group
            if log_group:
                peer_clean = peer.replace("@", "")
                try:
                    await bot_client.send_message(
                        int(log_group),
                        f"✅ Successfully forwarded to: [{peer_clean}](https://t.me/{peer_clean})",
                        parse_mode="markdown",
                        link_preview=False
                    )
                except:
                    pass

        except Exception as e:
            failed += 1
            if log_group:
                try:
                    await bot_client.send_message(
                        int(log_group),
                        f"❌ Failed to send to {peer}\nError: {str(e)[:100]}",
                    )
                except:
                    pass

        await asyncio.sleep(2)

    # Update last sent time
    state["last_sent"] = asyncio.get_event_loop().time()

    # Summary to user
    await bot_client.send_message(
        user_id,
        f"📊 **Campaign Complete**\n\n✅ Sent: {sent}\n❌ Failed: {failed}\n📬 Total: {sent + failed}"
    )

# ─── Schedule loop ─────────────────────────────────────────────────────────────
async def schedule_loop(bot_client, customer):
    while True:
        await asyncio.sleep(60)  # check every minute
        now = asyncio.get_event_loop().time()
        states = customer_states.get(customer["bot_token"], {})
        for user_id, state in list(states.items()):
            if not state.get("active"):
                continue
            last = state.get("last_sent", 0)
            if now - last >= INTERVAL:
                try:
                    await forward_to_groups(bot_client, customer, state, user_id)
                except Exception as e:
                    logging.error(f"Schedule error for {user_id}: {e}")

# ─── Build and run a single customer bot ──────────────────────────────────────
async def run_customer_bot(customer):
    token = customer["bot_token"]
    name  = customer.get("customer_name", "Customer")
    expiry_str = customer.get("expiry", "")

    bot = TelegramClient(
        StringSession(), API_ID, API_HASH
    ).start(bot_token=token)

    # Init state for this bot
    if token not in customer_states:
        customer_states[token] = {}

    def get_state(user_id):
        if user_id not in customer_states[token]:
            customer_states[token][user_id] = {
                "step": "idle",
                "msg_link": "",
                "from_chat": "",
                "msg_id": 0,
                "category": "",
                "active": False,
                "last_sent": 0
            }
        return customer_states[token][user_id]

    def days_remaining():
        if not expiry_str:
            return 0, None
        try:
            expiry = datetime.fromisoformat(expiry_str).replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            delta = expiry - now
            days = delta.days
            hours = delta.seconds // 3600
            mins = (delta.seconds % 3600) // 60
            return max(days, 0), expiry, hours, mins
        except:
            return 0, None, 0, 0

    async with bot:
        logging.info(f"✅ Bot started: {name}")

        @bot.on(events.NewMessage(pattern="/start"))
        async def start(event):
            state = get_state(event.sender_id)
            state["step"] = "waiting_link"
            days, expiry, hours, mins = days_remaining()
            await event.respond(
                f"👋 Welcome to **{name} Ads Bot**!\n\n"
                f"⏳ Validity: **{days} Days {hours} Hours {mins} Minutes**\n\n"
                f"📨 Send your **message link** to start forwarding:\n"
                f"Example: `https://t.me/yourchannel/123`"
            )

        @bot.on(events.NewMessage(pattern="/validity"))
        async def validity(event):
            days, expiry, hours, mins = days_remaining()
            await event.respond(
                f"⏳ **Validity Remaining:**\n"
                f"{days} Days {hours} Hours {mins} Minutes\n\n"
                f"📅 Expiry Date: {expiry.strftime('%d %b %Y %H:%M UTC') if expiry else 'N/A'}"
            )

        @bot.on(events.NewMessage(pattern="/stop"))
        async def stop(event):
            state = get_state(event.sender_id)
            state["active"] = False
            state["step"] = "idle"
            await event.respond("⏹ **Forwarding Stopped.**\n\nSend /start to begin again.")

        @bot.on(events.NewMessage(pattern="/change"))
        async def change(event):
            state = get_state(event.sender_id)
            state["step"] = "waiting_link"
            state["active"] = False
            await event.respond(
                "🔄 **Change Process Initiated**\n\n"
                "1. Send new message link\n"
                "2. Select categories\n"
                "Changes will take effect from the next loop.\n\n"
                "First, send the new message link:"
            )

        @bot.on(events.NewMessage(pattern="/Yes"))
        async def confirm_yes(event):
            state = get_state(event.sender_id)
            if state.get("step") != "waiting_confirm":
                return
            state["active"] = True
            state["step"] = "active"
            state["last_sent"] = 0  # send immediately
            cat = state.get("category", "")
            from_chat = state.get("from_chat", "")
            msg_id = state.get("msg_id", 0)
            await event.respond(
                f"✅ **Forwarding Activated!**\n"
                f"• Channel: {from_chat}\n"
                f"• Message ID: {msg_id}\n"
                f"• Category: {cat}\n\n"
                f"🔄 Forwarding every 30 minutes automatically."
            )
            # Start immediately
            await forward_to_groups(bot, customer, state, event.sender_id)

        @bot.on(events.NewMessage(pattern="/No"))
        async def confirm_no(event):
            state = get_state(event.sender_id)
            state["step"] = "waiting_link"
            await event.respond("❌ Cancelled.\n\nSend a new message link to try again.")

        @bot.on(events.NewMessage())
        async def handle_message(event):
            if event.text and event.text.startswith("/"):
                return
            state = get_state(event.sender_id)
            text = event.text or ""

            # Step 1: Waiting for message link
            if state["step"] == "waiting_link":
                from_chat, msg_id = parse_link(text)
                if not from_chat or not msg_id:
                    await event.respond(
                        "❌ **Invalid Link**\n\n"
                        "Please send a valid Telegram message link.\n"
                        "Example: `https://t.me/yourchannel/123`"
                    )
                    return
                state["msg_link"] = text.strip()
                state["from_chat"] = from_chat
                state["msg_id"] = msg_id
                state["step"] = "waiting_category"

                cat_list = "\n".join([f"{k}. {v}" for k, v in CATEGORIES.items()])
                await event.respond(
                    f"📁 **Available Categories:**\n{cat_list}\n\n"
                    f"Reply with the category number:"
                )
                return

            # Step 2: Waiting for category
            if state["step"] == "waiting_category":
                cat_num = text.strip()
                if cat_num not in CATEGORIES:
                    await event.respond("❌ Invalid number. Please choose 1-11.")
                    return
                state["category"] = CATEGORIES[cat_num]
                state["step"] = "waiting_confirm"

                from_chat = state["from_chat"]
                msg_id = state["msg_id"]
                category = state["category"]

                await event.respond(
                    f"📋 **Message Details**\n"
                    f"• Channel: {from_chat}\n"
                    f"• Message ID: {msg_id}\n"
                    f"• Category: {category}\n\n"
                    f"Give Confirmation By /Yes or /No"
                )
                return

        # Run schedule loop alongside bot
        asyncio.ensure_future(schedule_loop(bot, customer))
        await bot.run_until_disconnected()

# ─── Main — run all customer bots ─────────────────────────────────────────────
async def main():
    customers = load_customers()
    if not customers:
        logging.warning("No customers found in /opt/zoroadss/customers.json")
        logging.warning("Add customers and restart.")
        # Keep running so PM2 doesn't restart loop
        await asyncio.sleep(999999)
        return

    logging.info(f"Starting {len(customers)} customer bot(s)...")
    tasks = [run_customer_bot(c) for c in customers]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
