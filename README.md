# FastAds integrated build

This build connects the Cloudflare Worker/D1 bot to the Telethon sender for accounts you control and chats where posting is authorized.

## D1
Run `migration.sql` once in the D1 console.

## Worker variables
- BOT_TOKEN
- ADMIN_ID
- SUPPORT_USERNAME
- SENDER_URL = public HTTPS sender origin
- SENDER_SECRET = same value as sender server

Keep the existing D1 binding named `DB`.

## Sender

### Local login (do this on your own machine, not on Render)
Install `requirements.txt`, then run `login.py` once per controlled Telegram account:
```
pip install -r requirements.txt
python3 login.py
```
It prints a `TG_SESSION_<n>` string session at the end — copy it, you'll paste it into Render as an env var. Treat it like a password.

### Deploy on Render (free, no card required)
1. Push this folder to a GitHub repo.
2. Render dashboard → New → Web Service → connect the repo. `render.yaml` will auto-configure the build/start commands.
3. Set env vars: `TG_API_ID`, `TG_API_HASH`, `SENDER_SECRET`, and one `TG_SESSION_1`, `TG_SESSION_2`, ... per account (from the login.py output above).
4. Deploy. Render gives you a free HTTPS URL — put it in the Worker's `SENDER_URL`.

Note: free Render web services sleep after 15 minutes idle (~30-60s cold start on the next request). Fine for cron/user-triggered sends, not for instant-response use cases.

Add every authorized destination chat to `allowlist.txt`, one exact username or numeric ID per line.

## Admin flow
Open the bot as admin:
1. Assign Sender
2. Send customer Telegram user ID
3. Send local account ID from `login.py`

The Worker stores the mapping in D1. A user's Start Ads button reads their active ads, groups, and assigned sender, then calls the sender API.

## Scheduling
Add a Cloudflare Worker Cron Trigger for the interval you intentionally want. The scheduled handler processes active campaigns. Telegram FloodWait is respected by the sender.

The package intentionally does not implement unsolicited mass messaging, account rotation to evade restrictions, or ban evasion.
