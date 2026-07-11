import "dotenv/config";
import input from "input";
import {TelegramClient} from "telegram";
import {StringSession} from "telegram/sessions/index.js";
const c=new TelegramClient(new StringSession(""),Number(process.env.TG_API_ID),process.env.TG_API_HASH,{connectionRetries:5});
await c.start({phoneNumber:()=>input.text("Phone number: "),phoneCode:()=>input.text("Telegram login code: "),password:()=>input.text("2FA password: "),onError:console.error});
console.log("\nSTRING SESSION:\n"+c.session.save());await c.disconnect();
