import "dotenv/config";
import express from "express";
import crypto from "node:crypto";
import { TelegramClient } from "telegram";
import { StringSession } from "telegram/sessions/index.js";

const app = express();
app.use(express.json({limit:"1mb"}));
const apiId=Number(process.env.TG_API_ID), apiHash=process.env.TG_API_HASH;
const secret=process.env.CONTROL_SECRET, key=Buffer.from(process.env.SESSION_KEY||"","base64");
if(!apiId||!apiHash||!secret||key.length!==32) throw new Error("Missing/invalid environment variables");
const clients=new Map();
const auth=(req,res,next)=>(req.get("authorization")===`Bearer ${secret}`?next():res.status(401).json({ok:false,error:"unauthorized"}));
const encrypt=s=>{const iv=crypto.randomBytes(12),c=crypto.createCipheriv("aes-256-gcm",key,iv),d=Buffer.concat([c.update(s,"utf8"),c.final()]);return [iv,c.getAuthTag(),d].map(x=>x.toString("base64")).join(".")};
const decrypt=s=>{const [iv,t,d]=s.split(".").map(x=>Buffer.from(x,"base64")),c=crypto.createDecipheriv("aes-256-gcm",key,iv);c.setAuthTag(t);return Buffer.concat([c.update(d),c.final()]).toString("utf8")};
async function getClient(id,session){if(clients.has(String(id)))return clients.get(String(id));const c=new TelegramClient(new StringSession(decrypt(session)),apiId,apiHash,{connectionRetries:5});await c.connect();if(!(await c.isUserAuthorized()))throw new Error("SESSION_NOT_AUTHORIZED");clients.set(String(id),c);return c}
app.get("/health",(_,res)=>res.json({ok:true,service:"fastads-sender"}));
app.post("/accounts/import",auth,async(req,res)=>{try{const {accountId,stringSession}=req.body;if(!accountId||!stringSession)throw new Error("accountId and stringSession required");const c=new TelegramClient(new StringSession(String(stringSession)),apiId,apiHash,{connectionRetries:5});await c.connect();if(!(await c.isUserAuthorized()))throw new Error("SESSION_NOT_AUTHORIZED");const me=await c.getMe(),encryptedSession=encrypt(c.session.save());await c.disconnect();res.json({ok:true,accountId:String(accountId),telegramUserId:String(me.id),username:me.username||null,encryptedSession})}catch(e){res.status(400).json({ok:false,error:String(e.message||e)})}});
app.post("/send",auth,async(req,res)=>{try{const {accountId,encryptedSession,message,peers}=req.body;if(!accountId||!encryptedSession||!message||!Array.isArray(peers))throw new Error("invalid payload");if(peers.length>50)throw new Error("MAX_50_PEERS_PER_JOB");const c=await getClient(accountId,encryptedSession),results=[];for(const raw of peers){const peer=String(raw||"").trim();if(!/^(@[A-Za-z0-9_]{5,}|-?\d+)$/.test(peer)){results.push({peer,ok:false,error:"INVALID_PEER"});continue}try{const entity=await c.getEntity(peer);await c.sendMessage(entity,{message:String(message)});results.push({peer,ok:true});await new Promise(r=>setTimeout(r,1500))}catch(e){const seconds=Number(e?.seconds||0);results.push({peer,ok:false,error:String(e?.errorMessage||e?.message||e),retryAfter:seconds||null});if(seconds>0)break}}res.json({ok:true,results})}catch(e){res.status(400).json({ok:false,error:String(e.message||e)})}});
app.post("/accounts/disconnect",auth,async(req,res)=>{const id=String(req.body.accountId||""),c=clients.get(id);if(c)await c.disconnect().catch(()=>{});clients.delete(id);res.json({ok:true})});
app.listen(Number(process.env.PORT||3000),()=>console.log("FastAds sender started"));
