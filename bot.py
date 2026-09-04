import asyncio, os, json, logging, re
from datetime import datetime, timezone
from telethon import TelegramClient, events, functions
from telethon.tl.types import Channel
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

API_ID   = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")
INTERVAL = 30 * 60  # 30 minutes break between full campaigns
GROUP_DELAY = 60    # 1 minute between each group send

CATEGORIES = {
    "1": "Instagram-OFM", "2": "Instagram",  "3": "Telegram",
    "4": "Whatsapp",      "5": "Others",     "6": "Exchanges",
    "7": "TikTok",        "8": "Snapchat",   "9": "Twitter-X",
    "10": "Youtube",      "11": "Discord"
}

# Build the Instagram‑OFM group list with all existing + new groups, deduplicated.
_instagram_ofm_groups = [
    "@ofmserviceswork", "@ofmboardj", "@ofmthehub",
    "@vitorez", "@SELLERS_Z0NE", "@NFTdiscussion",
    "@d_onifriomartz", "@pinkmarkettt", "@top0promo",
    "@nitrouhq", "@avatradercompany", "@jezzy_market",
    "@GOTMARKET", "@datingworkplace", "@onlyfans_mart",
    "@marketplace_forums", "@backupped", "@buyerndseller",
    "@dubai_rr", "@promoperfrection", "@board_onlyfans",
    "@chat_arabb", "@blackfridayym", "@SocialCove",
    "@adult_desk", "@cryptoworldgemsgroup", "@HDSMM_SELLERS",
    "@chezrass", "@barbie_agency111", "@TheGangMP",
    "@fivetutormarket", "@instaempiremarket", "@gakuenbabies",
    "@acaagawgfwa", "@yawamarket", "@Advertising_BF",
    "@BUYINGANDSELLING2", "@networkingmodels", "@NiggaMarketplace",
    "@flipside", "@cardingkicks", "@italianspam",
    "@Marshall_SMM", "@emblemmarket", "@collectordesk",
    "@financialtrademarket", "@ZsMarketplace", "@Mariosells",
    "@sbbarebearsmarket", "@ofmmonopoly", "@lucawtbwts",
    "@market_fn", "@Cc4Btc", "@zazazamkx",
    "@OFMManiacs", "@market_fn", "@Mariosells",
    "@PromotionsOFM", "@otcmarket3", "@stockless",
    # -------- new groups added below --------
    "@ofmjoino",
    "@dablixkystore",
    "@yeshinzuX2",
    "@rumorsii",
    "@PiratedPromo",
    "@ethio93",
    "@webcamadultdesk",
    "@linopubchat",
    "@NT4_CHAT",
    "@slumdrunk",
    "@supersfs",
    "@celestialmart",
    "@shippedd",
    "@webcam_token",
    "@GenieSwaps",
    "@FLAIR_MARKET",
    "@moonteamart",
    "@DeskSpark",
    "@AUSNZFCHAT",
    "@pluggerz",
    "@chezwilliams",
    "@ICE_adult",
    "@texted",
    "@Google_Ads3",
    "@InstagramTrade",
    "@ACHACHA_NIG_LTD",
    "@page_marketplace_IG",
    "@swgrouplinks",
    "@TRAS_adult"
]
# Remove duplicates while preserving order
CATEGORY_GROUPS = {
    "Instagram-OFM": list(dict.fromkeys(_instagram_ofm_groups)),
    "Instagram":     ["@chatgc1", "@chat8x", "@ichater"],
    "Telegram":      ["@marketdistrict", "@forumingly", "@rexygc"],
    "Whatsapp":      ["@chaterhub", "@textersgc", "@ogparks"],
    "Others":        ["@finanre", "@selll"],
    "Exchanges":     [],
    "TikTok":        [],
    "Snapchat":      [],
    "Twitter-X":     [],
    "Youtube":       [],
    "Discord":       [],
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
            await asyncio.sleep(3)
    except Exception as e:
        err = str(e)
        if "flood" in err.lower() or "wait" in err.lower():
            secs = re.findall(r'\d+', err)
            wait = int(secs[0]) if secs else 10
            await asyncio.sleep(wait)
        elif "ALREADY" in err or "already" in err or "USER_ALREADY" in err:
            pass
        else:
            logging.warning(f"Join {peer}: {err}")

def get_message_link(peer, msg_id):
    """Generate a clickable link to a specific message in a group/channel."""
    peer = peer.lstrip("@")
    if peer.startswith("-100"):
        channel_id = peer[4:]
        return f"https://t.me/c/{channel_id}/{msg_id}"
    else:
        return f"https://t.me/{peer}/{msg_id}"

async def send_log(bot, log_group, peer, ok, error=None, msg_link=None):
    """Send clickable log to log group, including a 'View Message' link if available."""
    if not log_group:
        return
    try:
        peer_clean = peer.lstrip("@")
        if ok:
            group_link = f'<a href="https://t.me/{peer_clean}">{peer_clean}</a>'
            text = f'✅ Forwarded to: {group_link}'
            if msg_link:
                text += f'\n🔗 <a href="{msg_link}">View Message</a>'
        else:
            text = f'❌ Failed to send to: <a href="https://t.me/{peer_clean}">{peer_clean}</a>'
            if error:
                text += f'\nError: {str(error)[:80]}'
        await bot.send_message(
            int(log_group),
            text,
            parse_mode="html",
            link_preview=False
        )
    except Exception as le:
        logging.warning(f"Log failed: {le}")

async def do_forward(bot, customer, state):
    """Send to all groups — 1 group per minute — then set last_sent for 30 min break"""
    account_id = customer.get("sender_account", 1)
    log_group  = customer.get("log_group_id")
    category   = state.get("category", "")
    from_chat  = state.get("from_chat")
    msg_id     = state.get("msg_id")
    owner_id   = state.get("owner_id")
    groups     = CATEGORY_GROUPS.get(category, [])

    if not groups:
        if owner_id:
            await bot.send_message(owner_id, "❌ No groups configured for this category.")
        return

    try:
        sender = await get_sender(account_id)
    except Exception as e:
        if owner_id:
            await bot.send_message(owner_id, f"❌ Sender error: {e}")
        return

    sent = failed = 0

    for i, peer in enumerate(groups):
        if not state.get("active"):
            logging.info(f"Campaign stopped mid-way for {owner_id}")
            break

        await try_join(sender, peer)

        try:
            forwarded = await sender.forward_messages(peer, msg_id, from_chat)
            if isinstance(forwarded, list):
                new_msg = forwarded[0] if forwarded else None
            else:
                new_msg = forwarded
            if new_msg:
                new_msg_id = new_msg.id
                msg_link = get_message_link(peer, new_msg_id)
            else:
                msg_link = None
            sent += 1
            await send_log(bot, log_group, peer, True, msg_link=msg_link)
        except Exception as e:
            failed += 1
            logging.warning(f"Forward failed {peer}: {e}")
            await send_log(bot, log_group, peer, False, error=e)

        if i < len(groups) - 1 and state.get("active"):
            await asyncio.sleep(GROUP_DELAY)

    state["last_sent"] = asyncio.get_event_loop().time()
    state["running"]   = False

    if owner_id and state.get("active"):
        await bot.send_message(
            owner_id,
            f"📊 **Campaign Complete**\n\n"
            f"✅ Sent: {sent}\n"
            f"❌ Failed: {failed}\n"
            f"📬 Total: {sent + failed}\n\n"
            f"⏳ Next campaign in 30 minutes."
        )

async def run_customer_bot(customer):
    token  = customer["bot_token"]
    name   = customer.get("customer_name", "Customer")
    expiry = customer.get("expiry", "")
    states = {}

    def get_state(uid):
        if uid not in states:
            states[uid] = {
                "step":      "idle",
                "from_chat": None,
                "msg_id":    None,
                "category":  None,
                "active":    False,
                "running":   False,
                "last_sent": 0,
                "owner_id":  uid
            }
        return states[uid]

    bot = TelegramClient(StringSession(), API_ID, API_HASH)
    await bot.start(bot_token=token)
    logging.info(f"✅ Started: {name}")

    @bot.on(events.NewMessage(pattern="/start"))
    async def on_start(event):
        s = get_state(event.sender_id)
        s["step"] = "waiting_link"
        d, h, m, _ = days_remaining(expiry)
        await event.respond(
            f"👋 Welcome to **{name}**!\n\n"
            f"⏳ Validity: **{d} Days {h} Hours {m} Minutes**\n\n"
            f"📨 Send your **message link** to start forwarding:\n"
            f"`https://t.me/yourchannel/123`"
        )

    @bot.on(events.NewMessage(pattern="/validity"))
    async def on_validity(event):
        d, h, m, exp = days_remaining(expiry)
        exp_str = exp.strftime("%d %b %Y %H:%M UTC") if exp else "N/A"
        await event.respond(
            f"⏳ **Validity Remaining:**\n"
            f"{d} Days {h} Hours {m} Minutes\n\n"
            f"📅 Expiry Date: {exp_str}"
        )

    @bot.on(events.NewMessage(pattern="/stop"))
    async def on_stop(event):
        s = get_state(event.sender_id)
        s["active"]  = False
        s["running"] = False
        s["step"]    = "idle"
        await event.respond(
            "⏹ **Forwarding Stopped.**\n\n"
            "Send /start to begin again."
        )

    @bot.on(events.NewMessage(pattern="/change"))
    async def on_change(event):
        s = get_state(event.sender_id)
        s["active"]  = False
        s["running"] = False
        s["step"]    = "waiting_link"
        await event.respond(
            "🔄 **Change Process Initiated**\n\n"
            "1. Send new message link\n"
            "2. Select category\n\n"
            "Changes take effect from next loop.\n\n"
            "Send the new message link now:"
        )

    @bot.on(events.NewMessage(pattern="/Yes"))
    async def on_yes(event):
        s = get_state(event.sender_id)
        if s.get("step") != "waiting_confirm":
            await event.respond("❌ Nothing to confirm. Send /start first.")
            return
        s["active"]    = True
        s["step"]      = "active"
        s["last_sent"] = 0
        s["running"]   = False
        await event.respond(
            f"✅ **Forwarding Activated!**\n"
            f"• Channel: {s['from_chat']}\n"
            f"• Message ID: {s['msg_id']}\n"
            f"• Category: {s['category']}\n\n"
            f"🔄 Sends to 1 group per minute.\n"
            f"⏳ After all groups done — 30 min break.\n"
            f"Send /stop to stop anytime."
        )
        asyncio.ensure_future(do_forward(bot, customer, s))
        s["running"] = True

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
                    "❌ **Invalid Link**\n\n"
                    "Send a valid Telegram message link:\n"
                    "`https://t.me/yourchannel/123`"
                )
                return
            s["from_chat"] = fc
            s["msg_id"]    = mid
            s["step"]      = "waiting_category"
            cats = "\n".join(f"{k}. {v}" for k, v in CATEGORIES.items())
            await event.respond(
                f"📁 **Available Categories:**\n{cats}\n\n"
                f"Reply with the category number:"
            )

        elif s["step"] == "waiting_category":
            if text not in CATEGORIES:
                await event.respond("❌ Invalid. Choose 1 to 11.")
                return
            s["category"] = CATEGORIES[text]
            s["step"]     = "waiting_confirm"
            await event.respond(
                f"📋 **Message Details**\n"
                f"• Channel: {s['from_chat']}\n"
                f"• Message ID: {s['msg_id']}\n"
                f"• Category: {s['category']}\n\n"
                f"Give Confirmation By /Yes or /No"
            )

    async def schedule_loop():
        while True:
            await asyncio.sleep(60)
            now = asyncio.get_event_loop().time()
            for uid, s in list(states.items()):
                if (s.get("active") and
                    not s.get("running") and
                    now - s.get("last_sent", 0) >= INTERVAL):
                    logging.info(f"Auto-forwarding for {uid} ({name})")
                    s["running"] = True
                    asyncio.ensure_future(do_forward(bot, customer, s))

    asyncio.ensure_future(schedule_loop())
    await bot.run_until_disconnected()

async def main():
    customers = load_customers()
    if not customers:
        logging.warning("No customers in /opt/zoroadss/customers.json")
        await asyncio.sleep(999999)
        return
    logging.info(f"Starting {len(customers)} customer bot(s)...")
    await asyncio.gather(*[run_customer_bot(c) for c in customers])

if __name__ == "__main__":
    asyncio.run(main())