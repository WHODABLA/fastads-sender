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

# ⚠️⚠️⚠️ PUT YOUR ADMIN BOT TOKEN HERE ⚠️⚠️⚠️
ADMIN_BOT_TOKEN = "8694738520:AAGJ44_L0MwdEQUbpPfy4-GJK1oLFy_oltw"
# ⚠️⚠️⚠️ PUT YOUR PERSONAL TELEGRAM USER ID HERE ⚠️⚠️⚠️
SUPER_ADMIN_IDS = [6742599309,7643126976]

INTERVAL        = 30 * 60      # 30 min break between full campaigns
GROUP_DELAY_MIN = 75           # min seconds between each group send
GROUP_DELAY_MAX = 150          # max seconds between each group send (jitter)
JOIN_DELAY_MIN  = 4            # delay after joining before sending
JOIN_DELAY_MAX  = 9

CUSTOMERS_PATH = "/opt/zoroadss/customers.json"
SESSIONS_DIR   = "/opt/zoroadss/sessions"
SESSION_META   = "/opt/zoroadss/session_meta.json"

# ---------------- CATEGORIES ----------------
CATEGORIES = {
    "1": "Instagram-OFM",
    "2": "YouTube",
    "3": "TikTok",
    "4": "Discord",
    "5": "Telegram",
}

# ============ MASTER LIST (shared by all categories) ============
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
    "@Victorii71chat", "@azoqchat", "@glopertchat",
    "@czechsell", "@Elite_Likes", "@execmarket",
    "@CryptoZackLounge", "@Arewacrypto1", "@ChargeMarketPlace",
    "@RitePremMarket", "@PSYCHOMARKETT", "@luminousmarket",
    "@akatsukimart", "@alienxmarket", "@alphamartxx",
    "@ariesmarket", "@aquariusmart", "@ashemarket",
    "@asmanomart", "@atelepalengke", "@bratz_lfmarket",
    "@buysellhubs", "@byeolmarket", "@capricornmart",
    "@charslamarket", "@chillluxmarket", "@chrrymrt",
    "@clubbanana", "@digimate_premium", "@disneymart",
    "@eagleselling", "@etherealmart", "@flaneurmerkada",
    "@iintmarket", "@incognitomarkett", "@jabamimarket",
    "@jiminmart", "@kab3tmarket", "@kiritomarket",
    "@kkkmarket", "@laspaganmarket", "@lfbuyerandseller",
    "@midnightmarket", "@socialmediasgames", "@infernomarket",
    "@moneytree89", "@souruteikamarketx", "@shikshumarket",
    "@adsplaza", "@alienmarkett", "@ministxp",
    "@seveneleben", "@soleilmarket", "@the24m",
    "@whitewookies", "@palengke", "@skyymarket",
    "@mediaamarkett", "@sfsgroup4u",
]

MASTER_GROUPS = list(dict.fromkeys(_instagram_ofm_groups))
CATEGORY_GROUPS = {name: MASTER_GROUPS for name in CATEGORIES.values()}

# ---------------- helpers ----------------
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        log.error(f"Error loading {path}: {e}")
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

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

# ---------------- sender client pool (.session file format) ----------------
sender_clients = {}
sender_locks   = {}

def get_sender_lock(account_id):
    if account_id not in sender_locks:
        sender_locks[account_id] = asyncio.Lock()
    return sender_locks[account_id]

async def get_sender(account_id, api_id=None, api_hash=None):
    if account_id in sender_clients and sender_clients[account_id].is_connected():
        return sender_clients[account_id]
    if account_id in sender_clients:
        try:
            await sender_clients[account_id].disconnect()
        except Exception:
            pass

    os.makedirs(SESSIONS_DIR, exist_ok=True)
    path = os.path.join(SESSIONS_DIR, f"account_{account_id}")
    aid   = api_id   or API_ID
    ahash = api_hash or API_HASH

    c = TelegramClient(
        path, aid, ahash,
        connection_retries=5, retry_delay=2, auto_reconnect=True,
        request_retries=3,
    )
    await c.connect()
    if not await c.is_user_authorized():
        raise RuntimeError(f"Account {account_id} not authorized")
    sender_clients[account_id] = c
    log.info(f"Sender account {account_id} connected (session file)")
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

# ---------------- logging ----------------
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
    cust_api_id   = customer.get("api_id")
    cust_api_hash = customer.get("api_hash")

    groups = CATEGORY_GROUPS.get(category, [])
    if not groups:
        if owner_id:
            await bot.send_message(owner_id, "❌ No groups configured.")
        state["running"] = False
        return

    try:
        sender = await get_sender(account_id, cust_api_id, cust_api_hash)
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
        log.warning(f"⚠️  {name}: EXPIRED. Bot will reject users.")
    if not admins:
        log.warning(f"⚠️  {name}: no admins configured.")

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

    async def gate(event, need_admin=True):
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
        s["running"]   = True
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


# ================================================================
#                    ADMIN BOT
# ================================================================
login_states = {}

async def run_admin_bot():
    bot = TelegramClient(StringSession(), API_ID, API_HASH)
    await bot.start(bot_token=ADMIN_BOT_TOKEN)
    log.info("✅ Admin Bot started")

    @bot.on(events.NewMessage(pattern="/start"))
    async def start(event):
        if event.sender_id not in SUPER_ADMIN_IDS:
            await event.respond("⛔ Unauthorized.")
            return
        await event.respond(
            "🛠 **Admin Panel**\n\n"
            "`/add_session` - Login a new Telegram account (creates a .session file)\n"
            "`/add_customer` - Add a new customer bot\n"
            "`/edit_customer` - Edit an existing customer\n"
            "`/del_customer` - Delete a customer\n"
            "`/list_sessions` - Show all .session files\n"
            "`/list_customers` - Show all customers\n"
            "`/cancel` - Cancel current flow"
        )

    @bot.on(events.NewMessage(pattern="/add_session"))
    async def add_session(event):
        if event.sender_id not in SUPER_ADMIN_IDS: return
        login_states[event.sender_id] = {"step": "api_id", "flow": "session"}
        await event.respond("🔑 **Step 1/6**\n\nSend your **API ID** (numbers only):")

    @bot.on(events.NewMessage(pattern="/add_customer"))
    async def add_customer(event):
        if event.sender_id not in SUPER_ADMIN_IDS: return
        login_states[event.sender_id] = {"step": "cust_token", "flow": "customer"}
        await event.respond("🤖 **Step 1/7**\n\nSend the **Bot Token** from @BotFather:")

    @bot.on(events.NewMessage(pattern="/edit_customer"))
    async def edit_customer_cmd(event):
        if event.sender_id not in SUPER_ADMIN_IDS: return
        customers = load_json(CUSTOMERS_PATH, [])
        if not customers:
            await event.respond("No customers to edit.")
            return
        login_states[event.sender_id] = {"step": "edit_pick_customer", "flow": "edit"}
        msg = "✏️ **Which customer do you want to edit?**\n\n"
        for i, c in enumerate(customers, 1):
            msg += f"`{i}`. {c.get('customer_name')} | Acc: {c.get('sender_account')} | Exp: {c.get('expiry','N/A')[:10]}\n"
        msg += "\nReply with the **number** (or /cancel):"
        await event.respond(msg)

    @bot.on(events.NewMessage(pattern="/del_customer"))
    async def del_customer_cmd(event):
        if event.sender_id not in SUPER_ADMIN_IDS: return
        customers = load_json(CUSTOMERS_PATH, [])
        if not customers:
            await event.respond("No customers.")
            return
        login_states[event.sender_id] = {"step": "del_pick", "flow": "delete"}
        msg = "🗑 **Which customer do you want to DELETE?**\n\n"
        for i, c in enumerate(customers, 1):
            msg += f"`{i}`. {c.get('customer_name')} | Acc: {c.get('sender_account')}\n"
        msg += "\n⚠️ This cannot be undone. Reply with the **number** (or /cancel):"
        await event.respond(msg)

    @bot.on(events.NewMessage(pattern="/cancel"))
    async def cancel_cmd(event):
        if event.sender_id not in SUPER_ADMIN_IDS: return
        if event.sender_id in login_states:
            del login_states[event.sender_id]
            await event.respond("❌ Cancelled.")
        else:
            await event.respond("Nothing to cancel.")

    @bot.on(events.NewMessage(pattern="/list_sessions"))
    async def list_sessions(event):
        if event.sender_id not in SUPER_ADMIN_IDS: return
        if not os.path.exists(SESSIONS_DIR):
            await event.respond("No sessions folder yet.")
            return
        files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".session")]
        if not files:
            await event.respond("No .session files found.")
            return
        meta = load_json(SESSION_META, {})
        msg = "📱 **Saved Sessions:**\n\n"
        for f in sorted(files):
            acc_id = f.replace("account_", "").replace(".session", "")
            m = meta.get(acc_id, {})
            msg += f"• ID: `{acc_id}` | Phone: `{m.get('phone','?')}` | API: `{m.get('api_id','env')}`\n"
        await event.respond(msg)

    @bot.on(events.NewMessage(pattern="/list_customers"))
    async def list_customers(event):
        if event.sender_id not in SUPER_ADMIN_IDS: return
        customers = load_json(CUSTOMERS_PATH, [])
        if not customers:
            await event.respond("No customers.")
            return
        msg = "📋 **Customers:**\n\n"
        for c in customers:
            exp = c.get("expiry", "N/A")
            msg += f"• {c.get('customer_name')} | Exp: {exp[:10]} | Acc: `{c.get('sender_account')}`\n"
        await event.respond(msg)

    @bot.on(events.NewMessage())
    async def handle_message(event):
        if event.sender_id not in SUPER_ADMIN_IDS: return
        if event.text.startswith("/"): return
        uid = event.sender_id
        if uid not in login_states: return
        state = login_states[uid]
        step = state["step"]
        flow = state.get("flow", "session")

        # ============ SESSION LOGIN ============
        if flow == "session":
            if step == "api_id":
                try:
                    state["api_id"] = int(event.text.strip())
                except:
                    await event.respond("❌ Invalid API ID. Send a number.")
                    return
                state["step"] = "api_hash"
                await event.respond("🔑 **Step 2/6**\n\nSend your **API Hash**:")

            elif step == "api_hash":
                state["api_hash"] = event.text.strip()
                state["step"] = "account_id"
                await event.respond("🔑 **Step 3/6**\n\nSend a **Sender Account ID** (e.g., `1`, `2`, `3`...):")

            elif step == "account_id":
                try:
                    acc_id = int(event.text.strip())
                except:
                    await event.respond("❌ Send a number.")
                    return

                sess_file = os.path.join(SESSIONS_DIR, f"account_{acc_id}.session")
                if os.path.exists(sess_file):
                    await event.respond(
                        f"❌ **Sender Account ID `{acc_id}` already exists!**\n\n"
                        f"A session file for this ID is already present.\n"
                        f"Please use a different ID, or delete the existing session first."
                    )
                    del login_states[uid]
                    return

                state["sender_account"] = acc_id
                state["step"] = "phone"
                await event.respond("📱 **Step 4/6**\n\nSend the **Phone Number** (e.g., `+1234567890`):")

            elif step == "phone":
                phone = event.text.strip()
                os.makedirs(SESSIONS_DIR, exist_ok=True)
                session_path = os.path.join(SESSIONS_DIR, f"account_{state['sender_account']}")
                client = TelegramClient(session_path, state["api_id"], state["api_hash"])
                await client.connect()
                try:
                    sent = await client.send_code_request(phone)
                    state.update({"step": "code", "phone": phone, "client": client, "phone_code_hash": sent.phone_code_hash})
                    await event.respond("✅ OTP sent! **Step 5/6**\n\nSend the **OTP code**:")
                except Exception as e:
                    await event.respond(f"❌ Error: {e}\nTry /add_session again.")
                    try: await client.disconnect()
                    except: pass
                    del login_states[uid]

            elif step == "code":
                code = event.text.strip()
                client = state["client"]
                try:
                    await client.sign_in(state["phone"], code, phone_code_hash=state["phone_code_hash"])
                    meta = load_json(SESSION_META, {})
                    meta[str(state["sender_account"])] = {
                        "api_id": state["api_id"],
                        "api_hash": state["api_hash"],
                        "phone": state["phone"]
                    }
                    save_json(SESSION_META, meta)
                    await client.disconnect()

                    await event.respond(
                        f"✅ **Session Saved!**\n\n"
                        f"File: `account_{state['sender_account']}.session`\n"
                        f"Sender ID: `{state['sender_account']}`\n"
                        f"Phone: `{state['phone']}`\n\n"
                        f"Use `/add_customer` to attach this session."
                    )
                    del login_states[uid]
                except Exception as e:
                    if "password" in str(e).lower() or "2FA" in str(e):
                        state["step"] = "password"
                        await event.respond("🔐 2FA enabled. **Step 6/6**\n\nSend your **2FA Password**:")
                    else:
                        await event.respond(f"❌ Login failed: {e}\nTry /add_session again.")
                        try: await client.disconnect()
                        except: pass
                        del login_states[uid]

            elif step == "password":
                password = event.text.strip()
                client = state["client"]
                try:
                    await client.sign_in(password=password)
                    meta = load_json(SESSION_META, {})
                    meta[str(state["sender_account"])] = {
                        "api_id": state["api_id"],
                        "api_hash": state["api_hash"],
                        "phone": state["phone"]
                    }
                    save_json(SESSION_META, meta)
                    await client.disconnect()

                    await event.respond(
                        f"✅ **Session Saved!**\n\n"
                        f"File: `account_{state['sender_account']}.session`\n"
                        f"Sender ID: `{state['sender_account']}`\n"
                        f"Phone: `{state['phone']}`\n\n"
                        f"Use `/add_customer` to attach this session."
                    )
                    del login_states[uid]
                except Exception as e:
                    await event.respond(f"❌ 2FA failed: {e}")
                    try: await client.disconnect()
                    except: pass
                    del login_states[uid]

        # ============ ADD CUSTOMER ============
        elif flow == "customer":
            if step == "cust_token":
                state["bot_token"] = event.text.strip()
                state["step"] = "cust_name"
                await event.respond("📝 **Step 2/7**\n\nSend the **Customer Name**:")

            elif step == "cust_name":
                state["customer_name"] = event.text.strip()
                state["step"] = "cust_expiry"
                await event.respond("📅 **Step 3/7**\n\nSend the **Expiry Date** (e.g., `2026-12-31T23:59:59+00:00`):")

            elif step == "cust_expiry":
                state["expiry"] = event.text.strip()
                state["step"] = "cust_sender_account"
                existing = []
                if os.path.exists(SESSIONS_DIR):
                    existing = [f.replace("account_","").replace(".session","")
                                for f in os.listdir(SESSIONS_DIR) if f.endswith(".session")]
                meta = load_json(SESSION_META, {})
                sess_list = "\n".join([f"• ID: `{i}` (Phone: {meta.get(i,{}).get('phone','?')})" for i in existing]) or "No sessions found!"
                await event.respond(f"📱 **Step 4/7**\n\nSend the **Sender Account ID**:\n\n{sess_list}")

            elif step == "cust_sender_account":
                try:
                    state["sender_account"] = int(event.text.strip())
                except:
                    await event.respond("❌ Send a number.")
                    return
                state["step"] = "cust_log_group"
                await event.respond("📋 **Step 5/7**\n\nSend the **Log Group ID** (e.g., `-1001234567890`):")

            elif step == "cust_log_group":
                try:
                    state["log_group_id"] = int(event.text.strip())
                except:
                    await event.respond("❌ Send a number.")
                    return
                state["step"] = "cust_admins"
                await event.respond("👑 **Step 6/7**\n\nSend the **Admin User IDs** (e.g., `111111,222222`):")

            elif step == "cust_admins":
                try:
                    admins = [int(x.strip()) for x in event.text.split(",")]
                except:
                    await event.respond("❌ Invalid format.")
                    return
                state["admins"] = admins

                sess_file = os.path.join(SESSIONS_DIR, f"account_{state['sender_account']}.session")
                if not os.path.exists(sess_file):
                    await event.respond(f"❌ No .session file found for ID `{state['sender_account']}`. Use /add_session first.")
                    del login_states[uid]
                    return

                meta = load_json(SESSION_META, {})
                m = meta.get(str(state["sender_account"]), {})

                new_customer = {
                    "bot_token": state["bot_token"],
                    "customer_name": state["customer_name"],
                    "expiry": state["expiry"],
                    "sender_account": state["sender_account"],
                    "log_group_id": state["log_group_id"],
                    "admins": state["admins"],
                }
                if "api_id" in m and "api_hash" in m:
                    new_customer["api_id"]   = m["api_id"]
                    new_customer["api_hash"] = m["api_hash"]

                customers = load_json(CUSTOMERS_PATH, [])
                if any(c.get("bot_token") == new_customer["bot_token"] for c in customers):
                    await event.respond("❌ This bot token already exists.")
                    del login_states[uid]
                    return

                customers.append(new_customer)
                save_json(CUSTOMERS_PATH, customers)

                await event.respond(
                    f"✅ **Step 7/7 Success!**\n\n"
                    f"Customer `{new_customer['customer_name']}` added.\n"
                    f"Using session file: `account_{new_customer['sender_account']}.session`\n\n"
                    f"The main bot will start it within 10 seconds."
                )
                del login_states[uid]

        # ============ EDIT CUSTOMER ============
        elif flow == "edit":
            customers = load_json(CUSTOMERS_PATH, [])

            if step == "edit_pick_customer":
                try:
                    idx = int(event.text.strip()) - 1
                    if idx < 0 or idx >= len(customers):
                        raise ValueError
                except:
                    await event.respond("❌ Send a valid number from the list.")
                    return
                state["edit_index"] = idx
                state["step"] = "edit_pick_field"
                cust = customers[idx]
                await event.respond(
                    f"✏️ **Editing:** `{cust.get('customer_name')}`\n\n"
                    f"**Which field do you want to change?**\n\n"
                    f"`1`. Bot Token\n"
                    f"`2`. Customer Name\n"
                    f"`3`. Expiry Date\n"
                    f"`4`. Sender Account ID\n"
                    f"`5`. Log Group ID\n"
                    f"`6`. Admin User IDs\n\n"
                    f"Reply with a **number** (or /cancel):"
                )

            elif step == "edit_pick_field":
                field_map = {
                    "1": "bot_token",
                    "2": "customer_name",
                    "3": "expiry",
                    "4": "sender_account",
                    "5": "log_group_id",
                    "6": "admins",
                }
                key = event.text.strip()
                if key not in field_map:
                    await event.respond("❌ Send a number between 1 and 6.")
                    return
                state["edit_field"] = field_map[key]
                state["step"] = "edit_new_value"
                cust = customers[state["edit_index"]]
                current = cust.get(state["edit_field"], "N/A")
                await event.respond(
                    f"Current value: `{current}`\n\n"
                    f"Send the **new value** for `{state['edit_field']}`:"
                )

            elif step == "edit_new_value":
                field = state["edit_field"]
                raw   = event.text.strip()
                cust  = customers[state["edit_index"]]

                try:
                    if field in ("sender_account", "log_group_id"):
                        new_val = int(raw)
                        if field == "sender_account":
                            sess_file = os.path.join(SESSIONS_DIR, f"account_{new_val}.session")
                            if not os.path.exists(sess_file):
                                await event.respond(
                                    f"❌ No .session file found for ID `{new_val}`.\n"
                                    f"Use /add_session first or pick a different ID."
                                )
                                del login_states[uid]
                                return
                    elif field == "admins":
                        new_val = [int(x.strip()) for x in raw.split(",")]
                    else:
                        new_val = raw
                except:
                    await event.respond("❌ Invalid format. Try again or /cancel.")
                    return

                old_token = cust.get("bot_token")
                cust[field] = new_val
                save_json(CUSTOMERS_PATH, customers)

                restart_customer_bot(old_token)

                await event.respond(
                    f"✅ **Updated!**\n\n"
                    f"Customer: `{cust.get('customer_name')}`\n"
                    f"Field: `{field}`\n"
                    f"New value: `{new_val}`\n\n"
                    f"🔄 Bot is restarting with the new config..."
                )
                del login_states[uid]

        # ============ DELETE CUSTOMER ============
        elif flow == "delete":
            customers = load_json(CUSTOMERS_PATH, [])
            if step == "del_pick":
                try:
                    idx = int(event.text.strip()) - 1
                    if idx < 0 or idx >= len(customers):
                        raise ValueError
                except:
                    await event.respond("❌ Invalid number.")
                    return
                cust = customers.pop(idx)
                save_json(CUSTOMERS_PATH, customers)
                restart_customer_bot(cust.get("bot_token"))
                await event.respond(
                    f"✅ **Deleted!**\n\n"
                    f"Customer `{cust.get('customer_name')}` has been removed.\n"
                    f"Its bot has been stopped."
                )
                del login_states[uid]

    await bot.run_until_disconnected()


# ================================================================
#                    SUPERVISOR & MAIN
# ================================================================
async def bot_supervisor(customer, delay):
    await asyncio.sleep(delay)
    name = customer.get("customer_name", "Customer")
    backoff = 15
    while True:
        try:
            await run_customer_bot(customer)
            log.warning(f"Bot {name} disconnected. Restarting in 10s...")
            backoff = 15
        except asyncio.CancelledError:
            log.info(f"Bot {name} was stopped.")
            break
        except Exception as e:
            log.exception(f"Bot {name} crashed: {e}")
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 300)

running_tasks = {}

def restart_customer_bot(token):
    """Cancel a running customer bot so the watcher restarts it fresh."""
    if token in running_tasks:
        try:
            running_tasks[token].cancel()
        except Exception:
            pass
        del running_tasks[token]
        log.info(f"🔄 Restarting bot for token {token[:15]}...")

async def watch_customers():
    last_mtime = 0
    while True:
        try:
            if os.path.exists(CUSTOMERS_PATH):
                mtime = os.path.getmtime(CUSTOMERS_PATH)
                if mtime > last_mtime:
                    last_mtime = mtime
                    customers = load_json(CUSTOMERS_PATH, [])
                    current_tokens = {c["bot_token"]: c for c in customers if "bot_token" in c}

                    for token, customer in current_tokens.items():
                        if token not in running_tasks:
                            name = customer.get("customer_name", "Customer")
                            log.info(f"🚀 New customer detected: {name}. Starting bot...")
                            running_tasks[token] = asyncio.create_task(bot_supervisor(customer, delay=0))

                    for token in list(running_tasks.keys()):
                        if token not in current_tokens:
                            log.info(f"🛑 Customer removed. Stopping bot...")
                            running_tasks[token].cancel()
                            del running_tasks[token]
        except Exception as e:
            log.exception("watch_customers error")
        await asyncio.sleep(10)

async def admin_supervisor():
    while True:
        try:
            await run_admin_bot()
        except Exception as e:
            log.exception(f"Admin Bot crashed: {e}")
        log.warning("Admin Bot disconnected. Restarting in 10s...")
        await asyncio.sleep(10)

async def main():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    asyncio.ensure_future(admin_supervisor())

    customers = load_json(CUSTOMERS_PATH, [])
    if not customers:
        log.warning(f"No customers in {CUSTOMERS_PATH}. Waiting for admin bot...")
    else:
        log.info(f"Starting {len(customers)} customer bot(s)...")
        for i, c in enumerate(customers):
            token = c.get("bot_token")
            if token:
                running_tasks[token] = asyncio.create_task(bot_supervisor(c, delay=i * 3))

    asyncio.ensure_future(watch_customers())

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())