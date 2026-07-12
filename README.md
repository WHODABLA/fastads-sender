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
Install `requirements.txt`, run `login.py` once for each controlled Telegram account, then run `server.py`.

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
