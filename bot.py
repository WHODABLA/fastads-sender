import asyncio, os, json, logging, random, re
from datetime import datetime, timezone
from urllib.parse import urlparse
from telethon import TelegramClient, events, functions
from telethon.tl.types import Channel
from telethon.sessions import StringSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("zoroads")

# ---------------- CONFIG ----------------
API_ID   = int(os.getenv("TG_API_ID", "0"))
API_HASH = os.getenv("TG_API_HASH", "")

INTERVAL        = 30 * 60      # 30 min break between full campaigns
GROUP_DELAY_MIN = 75           # min seconds between each group send
GROUP_DELAY_MAX = 150          # max seconds between each group send (jitter)
JOIN_DELAY_MIN  = 4            # delay after joining before sending
JOIN_DELAY_MAX  = 9

CUSTOMERS_PATH = "/opt/zoroadss/customers.json"
SESSIONS_DIR   = "/opt/zoroadss/sessions"

# ---------------- CATEGORIES (5 only, all share ONE master list) ----------------
CATEGORIES = {
    "1": "Instagram-OFM",
    "2": "YouTube",
    "3": "TikTok",
    "4": "Discord",
    "5": "Telegram",
}

# ============ MASTER LIST (used by ALL categories) ============
_instagram_ofm_groups = [
    "@ofmserviceswork", "@ofmboardj",
    "@vitorez", "@SELLERS_Z0NE", "@NFTdiscussion",
    "@d_onifriomartz", "@pinkmarkettt", "@top0promo",
    "@nitrouhq", "@avatradercompany", "@jezzy_market",
    "@GOTMARKET", "@onlyfans_mart",
    "@buyerndseller",
    "@dubai_rr", "@promoperfrection", "@board_onlyfans",
    "@chat_arabb", "@blackfridayym",
    "@adult_desk", "@cryptoworldgemsgroup", "@HDSMM_SELLERS",
    "@chezrass", "@barbie_agency111", "@TheGangMP",
    "@fivetutormarket", "@gakuenbabies",
    "@acaagawgfwa", "@yawamarket", "@Advertising_BF",
    "@networkingmodels",
    "@cardingkicks", "@italianspam",
    "@Marshall_SMM", "@emblemmarket", "@collectordesk",
    "@financialtrademarket", "@ZsMarketplace", "@Mariosells",
    "@sbbarebearsmarket", "@ofmmonopoly", "@lucawtbwts",
    "@market_fn", "@Cc4Btc", "@zazazamkx",
    "@OFMManiacs", "@market_fn", "@Mariosells",
    "@PromotionsOFM", "@otcmarket3",
    "@ofmjoino", "@yeshinzuX2", "@rumorsii",
    "@PiratedPromo", "@ethio93", "@webcamadultdesk",
    "@linopubchat", "@NT4_CHAT", "@slumdrunk",
    "@supersfs", "@celestialmart", "@shippedd",
    "@webcam_token", "@GenieSwaps", "@moonteamart",
    "@DeskSpark", "@AUSNZFCHAT", "@pluggerz",
    "@chezwilliams", "@ICE_adult", "@Google_Ads3",
    "@InstagramTrade", "@ACHACHA_NIG_LTD", "@page_marketplace_IG",
    "@swgrouplinks", "@TRAS_adult",
    "@onlymiumiu", "@VRStudios", "@NsmIGGroup",
    "@igbst", "@takeoffmarket", "@of_room",
    "@asclepiusmarket", "@PromotionsOFM", "@areumart",
    "@lucawtbwts", "@OFMManiacs", "@shdwmarket",
    "@sikeyyop", "@spamcapace2", "@ThePeachyMart",
    "@paradisehiring", "@nytoux", "@theofmcareers",
    "@orbisgroup2", "@swifplys", "@goblinmarkett",
    "@ofmcircleofficial", "@hunterakemonnetwork",
    "@ewhoree", "@citybadgechat",
    "@chatgc1", "@chat8x", "@ichater",
    "@marketdistrict", "@forumingly", "@rexygc",
    "@chaterhub", "@textersgc", "@ogparks",
    "@finanre", "@selll",
    # -------- newly added groups --------
    "@Victorii71chat",
    "@azoqchat",
    "@glopertchat",
    "@czechsell",
    "@Elite_Likes",
    "@execmarket",
    "@CryptoZackLounge",
    "@Arewacrypto1",
    "@ChargeMarketPlace",
    "@czechsell",
    "@RitePremMarket",
    "@PSYCHOMARKETT",
    "@luminousmarket",
    "@akatsukimart",
    "@alienxmarket",
    "@alphamartxx",
    "@ariesmarket",
    "@aquariusmart",
    "@ashemarket",
    "@asmanomart",
    "@atelepalengke",
    "@bratz_lfmarket",
    "@buysellhubs",
    "@byeolmarket",
    "@capricornmart",
    "@charslamarket",
    "@chillluxmarket",
    "@chrrymrt",
    "@clubbanana",
    "@digimate_premium",
    "@disneymart",
    "@eagleselling",
    "@etherealmart",
    "@flaneurmerkada",
    "@iintmarket",
    "@incognitomarkett",
    "@jabamimarket",
    "@jiminmart",
    "@kab3tmarket",
    "@kiritomarket",
    "@kkkmarket",
    "@laspaganmarket",
    "@lfbuyerandseller",
    "@midnightmarket",
    "@socialmediasgames",
    "@infernomarket",
    "@moneytree89",
    "@souruteikamarketx",
    "@shikshumarket",
    "@adsplaza",
    "@alienmarkett",
    "@ministxp",
    "@laspaganmarket",
    "@seveneleben",
    "@soleilmarket",
    "@the24m",
    "@whitewookies",
    "@palengke",
    "@skyymarket",
    "@chrrymrt",
    "@mediaamarkett",
    "@sfsgroup4u",
]

MASTER_GROUPS = list(dict.fromkeys(_instagram_ofm_groups))  # dedup preserving order
CATEGORY_GROUPS = {name: MASTER_GROUPS for name in CATEGORIES.values()}

# ---------------- helpers ----------------
def load_customers():
    if not os.path.exists(CUSTOMERS_PATH):
        return []
    with open(CUSTOMERS_PATH) as f:
        return json.load(f)

def parse_link(link):
    try:
        parts = [p for p in urlparse(link.strip()).path.split("/") if p]
        if parts and parts[0] == "c" and len(parts) >= 3:
            return f"-100{parts[1]}", int(parts[2])
        if len(parts) >= 2:
            return f"@{parts[0]}", int(parts[1])
    except Exception:
        pass
    return None, None

def _parse_expiry(expiry_str):
    if not expiry_str:
        return None
    try:
        dt = datetime.fromisoformat(expiry_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        log.warning(f"Bad expiry format '{expiry_str}': {e}")
        return "invalid"

def is_expired(expiry_str):
    exp = _parse_expiry(expiry_str)
    if exp is None:
        return False
    if exp == "invalid":
        return True
    return datetime.now(timezone.utc) >= exp

def days_remaining(expiry_str):
    exp = _parse_expiry(expiry_str)
    if not isinstance(exp, datetime):
        return 0, 0, 0, None
    delta = exp - datetime.now(timezone.utc)
    if delta.total_seconds() <= 0:
        return 0, 0, 0, exp
    d = delta.days
    h = delta.seconds // 3600
    m = (delta.seconds % 3600) // 60
    return d, h, m, exp

def get_message_link(peer, msg_id):
    peer = peer.lstrip("@")
    if peer.startswith("-100"):
        return f"https://t.me/c/{peer[4:]}/{msg_id}"
    return f"https://t.me/{peer}/{msg_id}"

# ---------------- sender client pool ----------------
sender_clients = {}
sender_locks   = {}

def get_sender_lock(account_id):
    if account_id not in sender_locks:
        sender_locks[account_id] = asyncio.Lock()
    return sender_locks[account_id]

async def get_sender(account_id):
    cached = sender_clients.get(account_id)
    if cached and cached.is_connected():
        return cached
    if cached:
        try:
            await cached.disconnect()
        except Exception:
            pass

    os.makedirs(SESSIONS_DIR, exist_ok=True)
    path = os.path.join(SESSIONS_DIR, f"account_{account_id}")
    c = TelegramClient(
        path, API_ID, API_HASH,
        connection_retries=5, retry_delay=2, auto_reconnect=True,
        request_retries=3,
    )
    await c.connect()
    if not await c.is_user_authorized():
        raise RuntimeError(f"Account {account_id} not authorized")
    sender_clients[account_id] = c
    log.info(f"Sender account {account_id} connected")
    return c

async def try_join(client, peer):
    try:
        entity = await client.get_entity(peer)
        if isinstance(entity, Channel):
            try:
                await client(functions.channels.JoinChannelRequest(entity))
                await asyncio.sleep(random.uniform(2, 5))
            except Exception as e:
                err = str(e)
                if "ALREADY" in err or "already" in err or "USER_ALREADY" in err:
                    return
                raise
    except Exception as e:
        err = str(e)
        if "flood" in err.lower() or "wait" in err.lower():
            secs = re.findall(r"\d+", err)
            wait = int(secs[0]) if secs else 30
            log.warning(f"Flood wait {wait}s on join {peer}")
            await asyncio.sleep(wait)
        elif "ALREADY" in err or "already" in err or "USER_ALREADY" in err:
            return
        else:
            log.warning(f"Join {peer}: {err}")

# ---------------- logging to customer log group ----------------
async def send_log(bot, log_group, peer, ok, error=None, msg_link=None):
    if not log_group:
        return
    try:
        peer_clean = peer.lstrip("@")
        if ok:
            text = f'✅ Forwarded to: <a href="https://t.me/{peer_clean}">{peer_clean}</a>'
            if msg_link:
                text += f'\n🔗 <a href="{msg_link}">View Message</a>'
        else:
            text = f'❌ Failed to send to: <a href="https://t.me/{peer_clean}">{peer_clean}</a>'
            if error:
                text += f'\nError: {str(error)[:80]}'
        await bot.send_message(int(log_group), text, parse_mode="html", link_preview=False)
    except Exception as le:
        log.warning(f"Log failed: {le}")

# ---------------- forwarding worker ----------------
async def do_forward(bot, customer, state):
    account_id = customer.get("sender_account", 1)
    log_group  = customer.get("log_group_id")
    category   = state.get("category", "")
    from_chat  = state.get("from_chat")
    msg_id     = state.get("msg_id")
    owner_id   = state.get("owner_id")

    groups = CATEGORY_GROUPS.get(category, [])
    if not groups:
        if owner_id:
            await bot.send_message(owner_id, "❌ No groups configured.")
        state["running"] = False
        return

    try:
        sender = await get_sender(account_id)
    except Exception as e:
        log.exception("Sender error")
        if owner_id:
            await bot.send_message(owner_id, f"❌ Sender error: {e}")
        state["running"] = False
        return

    sent = failed = 0
    lock = get_sender_lock(account_id)

    try:
        for i, peer in enumerate(groups):
            if not state.get("active"):
                log.info(f"Campaign stopped mid-way for {owner_id}")
                break

            await asyncio.sleep(random.uniform(0.8, 2.5))
            await try_join(sender, peer)
            await asyncio.sleep(random.uniform(JOIN_DELAY_MIN, JOIN_DELAY_MAX))

            try:
                async with lock:
                    forwarded = await sender.forward_messages(peer, msg_id, from_chat)
                new_msg = forwarded[0] if isinstance(forwarded, list) and forwarded else forwarded
                msg_link = get_message_link(peer, new_msg.id) if new_msg else None
                sent += 1
                await send_log(bot, log_group, peer, True, msg_link=msg_link)
            except Exception as e:
                failed += 1
                log.warning(f"Forward failed {peer}: {e}")
                await send_log(bot, log_group, peer, False, error=e)
                err = str(e).lower()
                if "flood" in err or "wait" in err or "ban" in err or "spam" in err:
                    await asyncio.sleep(random.uniform(30, 60))

            if i < len(groups) - 1 and state.get("active"):
                wait = random.uniform(GROUP_DELAY_MIN, GROUP_DELAY_MAX)
                log.info(f"[{owner_id}] sleeping {wait:.0f}s before next group")
                await asyncio.sleep(wait)
    finally:
        state["last_sent"] = asyncio.get_event_loop().time()
        state["running"]   = False

    if owner_id and state.get("active"):
        try:
            await bot.send_message(
                owner_id,
                f"📊 **Campaign Complete**\n\n"
                f"✅ Sent: {sent}\n"
                f"❌ Failed: {failed}\n"
                f"📬 Total: {sent + failed}\n\n"
                f"⏳ Next campaign in 30 minutes."
            )
        except Exception:
            pass

# ---------------- per-customer bot ----------------
async def run_customer_bot(customer):
    token  = customer["bot_token"]
    name   = customer.get("customer_name", "Customer")
    expiry = customer.get("expiry", "")
    admins = set(customer.get("admins") or [])

    if is_expired(expiry):
        log.warning(f"⚠️  {name}: EXPIRED (expiry={expiry}). Bot will reject users.")
    if not admins:
        log.warning(f"⚠️  {name}: no admins configured — nobody will be able to use it.")

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
                "owner_id":  uid,
            }
        return states[uid]

    bot = TelegramClient(
        StringSession(), API_ID, API_HASH,
        connection_retries=5, retry_delay=3, auto_reconnect=True,
    )
    await bot.start(bot_token=token)
    log.info(f"✅ Started bot: {name}")

    # ---- guards ----
    async def gate(event, need_admin=True):
        """Return True if the event may proceed."""
        if need_admin and event.sender_id not in admins:
            try:
                await event.respond("This is an ad bot contact @ihatedesk for more information.")
            except Exception:
                pass
            log.warning(f"[{name}] blocked uid={event.sender_id}")
            return False
        if is_expired(expiry):
            exp = _parse_expiry(expiry)
            exp_str = exp.strftime("%d %b %Y %H:%M UTC") if isinstance(exp, datetime) else str(expiry)
            try:
                await event.respond(
                    f"❌ **Subscription Expired**\n\n"
                    f"Bot: {name}\n"
                    f"Expired on: {exp_str}\n\n"
                    f"Please contact the admin to renew."
                )
            except Exception:
                pass
            return False
        return True

    # ---- commands ----
    @bot.on(events.NewMessage(pattern="/start"))
    async def on_start(event):
        if not await gate(event):
            return
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
        if not await gate(event):
            return
        d, h, m, exp = days_remaining(expiry)
        exp_str = exp.strftime("%d %b %Y %H:%M UTC") if exp else "N/A"
        await event.respond(
            f"⏳ **Validity Remaining:**\n"
            f"{d} Days {h} Hours {m} Minutes\n\n"
            f"📅 Expiry Date: {exp_str}"
        )

    @bot.on(events.NewMessage(pattern="/stop"))
    async def on_stop(event):
        if not await gate(event):
            return
        s = get_state(event.sender_id)
        s["active"] = False
        s["running"] = False
        s["step"] = "idle"
        await event.respond("⏹ **Forwarding Stopped.**\n\nSend /start to begin again.")

    @bot.on(events.NewMessage(pattern="/change"))
    async def on_change(event):
        if not await gate(event):
            return
        s = get_state(event.sender_id)
        s["active"]  = False
        s["running"] = False
        s["step"]    = "waiting_link"
        await event.respond(
            "🔄 **Change Process Initiated**\n\n"
            "Send the new message link now:"
        )

    @bot.on(events.NewMessage(pattern=r"/Yes"))
    async def on_yes(event):
        if not await gate(event):
            return
        s = get_state(event.sender_id)
        if s.get("step") != "waiting_confirm":
            await event.respond("❌ Nothing to confirm. Send /start first.")
            return
        s["active"]    = True
        s["step"]      = "active"
        s["last_sent"] = 0
        s["running"]   = True  # set BEFORE task spawn
        await event.respond(
            f"✅ **Forwarding Activated!**\n"
            f"• Channel: {s['from_chat']}\n"
            f"• Message ID: {s['msg_id']}\n"
            f"• Category: {s['category']}"
        )
        asyncio.ensure_future(do_forward(bot, customer, s))

    @bot.on(events.NewMessage(pattern=r"/No"))
    async def on_no(event):
        if not await gate(event):
            return
        s = get_state(event.sender_id)
        s["step"] = "waiting_link"
        await event.respond("❌ Cancelled.\n\nSend a new message link to try again.")

    @bot.on(events.NewMessage())
    async def on_msg(event):
        if event.text and event.text.startswith("/"):
            return
        if not await gate(event):
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
                await event.respond("❌ Invalid. Choose 1 to 5.")
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

    # ---- per-bot scheduler ----
    async def schedule_loop():
        while True:
            try:
                await asyncio.sleep(60)
                now = asyncio.get_event_loop().time()
                for uid, s in list(states.items()):
                    if (s.get("active")
                            and not s.get("running")
                            and now - s.get("last_sent", 0) >= INTERVAL):
                        log.info(f"Auto-forwarding for {uid} ({name})")
                        s["running"] = True
                        asyncio.ensure_future(do_forward(bot, customer, s))
            except Exception:
                log.exception("schedule_loop error")

    asyncio.ensure_future(schedule_loop())
    await bot.run_until_disconnected()


# ---------------- supervisor ----------------
async def bot_supervisor(customer, delay):
    await asyncio.sleep(delay)
    name = customer.get("customer_name", "Customer")
    backoff = 15
    while True:
        try:
            await run_customer_bot(customer)
            log.warning(f"Bot {name} disconnected normally. Restarting in 10s...")
            backoff = 15
        except Exception as e:
            log.exception(f"Bot {name} crashed: {e}")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 300)

async def main():
    customers = load_customers()
    if not customers:
        log.warning(f"No customers in {CUSTOMERS_PATH}")
        await asyncio.sleep(999999)
        return

    log.info(f"Starting {len(customers)} customer bot(s) with 3s stagger...")
    tasks = []
    for i, c in enumerate(customers):
        tasks.append(asyncio.create_task(bot_supervisor(c, delay=i * 3)))
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())