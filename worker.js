const PLANS = {
  Bronze: { price: 20, days: 30, adAccounts: 1, maxAds: 1, customGroups: 100, groups: "200+" },
  Silver: { price: 40, days: 30, adAccounts: 2, maxAds: 2, customGroups: 250, groups: "400+" },
  Gold: { price: 70, days: 30, adAccounts: 4, maxAds: 4, customGroups: 500, groups: "700+" }
};

const USER_MENU = {
  inline_keyboard: [
    [{ text: "📢 Create Ad", callback_data: "create_ad" }, { text: "📋 My Ads", callback_data: "my_ads" }],
    [{ text: "▶️ Start Ads", callback_data: "start_ads" }, { text: "⏹ Stop Ads", callback_data: "stop_ads" }],
    [{ text: "➕ Add Groups", callback_data: "add_groups" }, { text: "🤖 Auto Reply", callback_data: "auto_reply" }],
    [{ text: "📊 Delivery Logs", callback_data: "logs" }, { text: "💎 My Plan", callback_data: "plan" }],
    [{ text: "🛍 Services", callback_data: "services" }, { text: "💳 Buy Plan", callback_data: "buy_plan" }],
    [{ text: "🆘 Support", callback_data: "support" }]
  ]
};

const NO_PLAN_MENU = {
  inline_keyboard: [
    [{ text: "🛍 Services", callback_data: "services" }],
    [{ text: "💳 Buy Plan", callback_data: "buy_plan" }],
    [{ text: "🆘 Support", callback_data: "support" }]
  ]
};

const SERVICES_MENU = {
  inline_keyboard: [
    [{ text: "🥉 Bronze", callback_data: "service_bronze" }],
    [{ text: "🥈 Silver", callback_data: "service_silver" }],
    [{ text: "🥇 Gold", callback_data: "service_gold" }],
    [{ text: "⬅️ Back", callback_data: "home" }]
  ]
};

const ADMIN_MENU = {
  inline_keyboard: [
    [{ text: "💎 Give Plan", callback_data: "admin_give_plan" }],
    [{ text: "📡 Assign Sender", callback_data: "admin_assign_sender" }],
    [{ text: "🚫 Remove Plan", callback_data: "admin_remove_plan" }],
    [{ text: "👥 Users", callback_data: "admin_users" }, { text: "📊 Statistics", callback_data: "admin_stats" }]
  ]
};

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(runActiveCampaigns(env));
  },

  async fetch(request, env) {
    if (request.method === "GET") return new Response("Fast Ads Bot Running ⚡");
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    try {
      const update = await request.json();
      if (update.message) await handleMessage(update.message, env);
      if (update.callback_query) await handleCallback(update.callback_query, env);
      return new Response("OK");
    } catch (error) {
      console.error("BOT ERROR:", error);
      return new Response("OK");
    }
  }
};

async function telegram(method, data, env) {
  const response = await fetch(`https://api.telegram.org/bot${env.BOT_TOKEN}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  });
  return response.json();
}

async function sendMessage(chatId, text, env, replyMarkup = null) {
  const data = { chat_id: chatId, text, parse_mode: "HTML" };
  if (replyMarkup) data.reply_markup = replyMarkup;
  return telegram("sendMessage", data, env);
}

async function getUser(userId, username, env) {
  let user = await env.DB.prepare("SELECT * FROM users WHERE telegram_id = ?").bind(userId).first();

  if (!user) {
    await env.DB.prepare("INSERT INTO users (telegram_id, username) VALUES (?, ?)")
      .bind(userId, username || null).run();
    user = await env.DB.prepare("SELECT * FROM users WHERE telegram_id = ?").bind(userId).first();
  }

  if (username && username !== user.username) {
    await env.DB.prepare("UPDATE users SET username = ? WHERE telegram_id = ?")
      .bind(username, userId).run();
    user.username = username;
  }

  return checkPlanExpiry(user, env);
}

async function setState(userId, state, env) {
  await env.DB.prepare("UPDATE users SET state = ? WHERE telegram_id = ?").bind(state, userId).run();
}

async function checkPlanExpiry(user, env) {
  if (!user.plan || !user.plan_expires_at) return user;

  const expiry = new Date(user.plan_expires_at);
  if (Date.now() >= expiry.getTime()) {
    await env.DB.prepare(`
      UPDATE users SET plan = NULL, ad_accounts = 0, max_ads = 0,
      custom_group_limit = 0, plan_started_at = NULL, plan_expires_at = NULL, state = NULL
      WHERE telegram_id = ?
    `).bind(user.telegram_id).run();

    return {
      ...user, plan: null, ad_accounts: 0, max_ads: 0,
      custom_group_limit: 0, plan_started_at: null, plan_expires_at: null, state: null
    };
  }
  return user;
}


async function senderRequest(path, body, env) {
  if (!env.SENDER_URL || !env.SENDER_SECRET) throw new Error("SENDER_NOT_CONFIGURED");
  const response = await fetch(`${env.SENDER_URL}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "authorization": `Bearer ${env.SENDER_SECRET}`
    },
    body: JSON.stringify(body)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.detail || data.error || `SENDER_HTTP_${response.status}`);
  return data;
}

async function sendUserAds(userId, env) {
  const user = await env.DB.prepare("SELECT * FROM users WHERE telegram_id = ?").bind(userId).first();
  if (!user?.plan || !user.plan_expires_at || new Date(user.plan_expires_at).getTime() <= Date.now()) {
    throw new Error("NO_ACTIVE_PLAN");
  }

  const assignment = await env.DB.prepare(`
    SELECT sa.local_account_id
    FROM user_sender_assignments usa
    JOIN sender_accounts sa ON sa.id = usa.sender_account_id
    WHERE usa.user_id = ? AND sa.status = 'active'
    LIMIT 1
  `).bind(userId).first();
  if (!assignment) throw new Error("NO_SENDER_ASSIGNED");

  const ads = await env.DB.prepare(`
    SELECT id, ad_text FROM ads
    WHERE user_id = ? AND status = 'active'
    ORDER BY id ASC LIMIT ?
  `).bind(userId, Number(user.max_ads)).all();

  const groups = await env.DB.prepare(`
    SELECT id, chat_id FROM groups WHERE user_id = ? ORDER BY id ASC
  `).bind(userId).all();

  if (!ads.results.length) throw new Error("NO_ACTIVE_ADS");
  if (!groups.results.length) throw new Error("NO_GROUPS");

  for (const ad of ads.results) {
    const result = await senderRequest("/send", {
      accountId: Number(assignment.local_account_id),
      message: ad.ad_text,
      peers: groups.results.map(g => String(g.chat_id))
    }, env);

    for (const item of result.results || []) {
      const group = groups.results.find(g => String(g.chat_id) === String(item.peer));
      if (!group) continue;
      await env.DB.prepare(`
        INSERT INTO delivery_logs (user_id, ad_id, group_id, status)
        VALUES (?, ?, ?, ?)
      `).bind(userId, ad.id, group.id, item.ok ? "sent" : "failed").run();
    }
  }
}

async function runActiveCampaigns(env) {
  const users = await env.DB.prepare(`
    SELECT telegram_id FROM users
    WHERE plan IS NOT NULL AND plan_expires_at > ?
  `).bind(new Date().toISOString()).all();

  for (const row of users.results) {
    const active = await env.DB.prepare(`
      SELECT 1 AS ok FROM ads WHERE user_id = ? AND status = 'active' LIMIT 1
    `).bind(row.telegram_id).first();
    if (!active) continue;
    try { await sendUserAds(row.telegram_id, env); }
    catch (error) { console.error("CAMPAIGN ERROR", row.telegram_id, error.message); }
  }
}

async function handleMessage(message, env) {
  const chatId = message.chat.id;
  const userId = message.from.id;
  const username = message.from.username || null;
  const text = message.text || "";
  const user = await getUser(userId, username, env);

  if (text === "/start" || text.startsWith("/start@")) {
    await setState(userId, null, env);
    if (isAdmin(userId, env)) {
      return sendMessage(chatId, `👑 <b>Fast Ads Admin Panel</b>

Welcome Admin.

Manage users and subscriptions below 👇`, env, ADMIN_MENU);
    }
    return showHome(chatId, user, env);
  }

  if (isAdmin(userId, env)) {
    const handled = await handleAdminMessage(chatId, userId, text, env);
    if (handled) return;
  }

  if (!user.plan) {
    return sendMessage(chatId, `🔒 <b>No Active Subscription</b>

You need an active paid plan to use Fast Ads.`, env, NO_PLAN_MENU);
  }

  if (user.state === "waiting_ad") {
    if (!text.trim()) return sendMessage(chatId, "❌ Please send a text advertisement.", env);

    const count = await env.DB.prepare(`
      SELECT COUNT(*) AS total FROM ads
      WHERE user_id = ? AND status IN ('ready', 'active')
    `).bind(userId).first();

    if (Number(count.total) >= Number(user.max_ads)) {
      await setState(userId, null, env);
      return sendMessage(chatId, `❌ <b>Ad Limit Reached</b>

Your ${escapeHtml(user.plan)} plan allows ${user.max_ads} active ad(s).`, env, USER_MENU);
    }

    await env.DB.prepare("INSERT INTO ads (user_id, ad_text, status) VALUES (?, ?, 'ready')")
      .bind(userId, text).run();
    await setState(userId, null, env);

    return sendMessage(chatId, `✅ <b>Ad Created Successfully</b>

📢 Advertisement saved.

Status: <b>Ready</b>`, env, USER_MENU);
  }

  if (user.state === "waiting_groups") {
    const inputGroups = text.split("\n").map(group => group.trim()).filter(Boolean);
    const groupCount = await env.DB.prepare("SELECT COUNT(*) AS total FROM groups WHERE user_id = ?")
      .bind(userId).first();
    const available = Number(user.custom_group_limit) - Number(groupCount.total);

    if (available <= 0) {
      await setState(userId, null, env);
      return sendMessage(chatId, "❌ Custom group limit reached.", env, USER_MENU);
    }

    const groupsToAdd = [...new Set(inputGroups)].slice(0, available);
    let added = 0;

    for (const group of groupsToAdd) {
      const result = await env.DB.prepare(`
        INSERT OR IGNORE INTO groups (user_id, chat_id) VALUES (?, ?)
      `).bind(userId, group).run();
      if (Number(result.meta?.changes || 0) > 0) added++;
    }

    await setState(userId, null, env);
    const newCount = await env.DB.prepare("SELECT COUNT(*) AS total FROM groups WHERE user_id = ?")
      .bind(userId).first();

    return sendMessage(chatId, `✅ <b>Groups Added</b>

Added: <b>${added}</b>

Total Groups:
<b>${newCount.total}/${user.custom_group_limit}</b>

Only use groups where you are authorized to post.`, env, USER_MENU);
  }

  return sendMessage(chatId, "⚡ Select an option below.", env, USER_MENU);
}

async function handleCallback(query, env) {
  const chatId = query.message.chat.id;
  const userId = query.from.id;
  const username = query.from.username || null;
  const action = query.data;
  let user = await getUser(userId, username, env);

  await telegram("answerCallbackQuery", { callback_query_id: query.id }, env);

  if (action === "home") {
    if (isAdmin(userId, env)) return sendMessage(chatId, "👑 <b>Admin Panel</b>", env, ADMIN_MENU);
    return showHome(chatId, user, env);
  }

  if (action === "services") {
    return sendMessage(chatId, `🛍 <b>Fast Ads Services</b>

Select a subscription plan to view full details 👇`, env, SERVICES_MENU);
  }

  if (action === "buy_plan") {
    return sendMessage(chatId, `💳 <b>Buy a Fast Ads Plan</b>

To purchase Bronze, Silver, or Gold, contact @icztv.

Send your preferred plan name and your Telegram User ID:
<code>${userId}</code>`, env, {
      inline_keyboard: [
        [{ text: "💬 Contact @icztv", url: "https://t.me/icztv" }],
        [{ text: "🛍 View Plans", callback_data: "services" }],
        [{ text: "⬅️ Home", callback_data: "home" }]
      ]
    });
  }

  if (action.startsWith("service_")) {
    const planName = capitalize(action.replace("service_", ""));
    if (!PLANS[planName]) return;
    return showService(chatId, planName, env);
  }

  if (action.startsWith("buy_")) {
    const planName = capitalize(action.replace("buy_", ""));
    if (!PLANS[planName]) return;

    return sendMessage(chatId, `💳 <b>Purchase ${escapeHtml(planName)} Plan</b>

Please contact support to purchase the subscription.

After payment confirmation, the administrator will activate your plan.

👤 Your User ID:
<code>${userId}</code>`, env, {
      inline_keyboard: [
        [{ text: "🆘 Contact Support", url: `https://t.me/${env.SUPPORT_USERNAME}` }],
        [{ text: "⬅️ Services", callback_data: "services" }]
      ]
    });
  }

  if (isAdmin(userId, env)) {
    const handled = await handleAdminCallback(chatId, userId, action, env);
    if (handled) return;
  }

  user = await getUser(userId, username, env);

  if (!user.plan) {
    return sendMessage(chatId, `🔒 <b>No Active Subscription</b>

Purchase a plan to access this feature.`, env, NO_PLAN_MENU);
  }

  if (action === "start_ads") {
    const ready = await env.DB.prepare(`
      SELECT COUNT(*) AS total FROM ads WHERE user_id = ? AND status IN ('ready','active')
    `).bind(userId).first();
    if (!Number(ready.total)) return sendMessage(chatId, "❌ Create an ad first.", env, USER_MENU);

    const assignment = await env.DB.prepare(`
      SELECT 1 AS ok FROM user_sender_assignments usa
      JOIN sender_accounts sa ON sa.id = usa.sender_account_id
      WHERE usa.user_id = ? AND sa.status = 'active' LIMIT 1
    `).bind(userId).first();
    if (!assignment) return sendMessage(chatId, "❌ No sender account is assigned. Contact support.", env, USER_MENU);

    await env.DB.prepare(`
      UPDATE ads SET status = 'active'
      WHERE id IN (
        SELECT id FROM ads WHERE user_id = ? AND status IN ('ready','active')
        ORDER BY id ASC LIMIT ?
      )
    `).bind(userId, Number(user.max_ads)).run();

    try {
      await sendUserAds(userId, env);
      return sendMessage(chatId, "▶️ <b>Ads Started</b>\\n\\nInitial authorized-group delivery completed. Scheduled runs will continue while ads remain active.", env, USER_MENU);
    } catch (error) {
      return sendMessage(chatId, `❌ Sender error: <code>${escapeHtml(error.message)}</code>`, env, USER_MENU);
    }
  }

  if (action === "stop_ads") {
    await env.DB.prepare("UPDATE ads SET status = 'ready' WHERE user_id = ? AND status = 'active'")
      .bind(userId).run();
    return sendMessage(chatId, "⏹ <b>Ads Stopped</b>", env, USER_MENU);
  }

  if (action === "create_ad") {
    await setState(userId, "waiting_ad", env);
    return sendMessage(chatId, `📢 <b>Create New Ad</b>

Send your advertisement text.

Your next message will be saved as your ad.`, env);
  }

  if (action === "my_ads") {
    const result = await env.DB.prepare(`
      SELECT * FROM ads WHERE user_id = ? ORDER BY id DESC LIMIT 10
    `).bind(userId).all();

    if (!result.results.length) return sendMessage(chatId, "📋 You don't have any ads yet.", env, USER_MENU);

    const ads = result.results.map((ad, index) => `<b>Ad ${index + 1}</b>

Status: <b>${escapeHtml(ad.status)}</b>

${escapeHtml(ad.ad_text)}`).join("\n\n────────────\n\n");

    return sendMessage(chatId, `📋 <b>My Ads</b>

${ads}`, env, USER_MENU);
  }

  if (action === "add_groups") {
    await setState(userId, "waiting_groups", env);
    return sendMessage(chatId, `➕ <b>Add Custom Groups</b>

Send authorized group usernames or chat IDs.

One group per line.

Example:

@my_marketplace
-1001234567890

Limit:
<b>${user.custom_group_limit}</b>`, env);
  }

  if (action === "auto_reply") {
    const newStatus = Number(user.auto_reply) ? 0 : 1;
    await env.DB.prepare("UPDATE users SET auto_reply = ? WHERE telegram_id = ?")
      .bind(newStatus, userId).run();

    return sendMessage(chatId, `🤖 <b>Auto Reply</b>

Status: <b>${newStatus ? "ON ✅" : "OFF ❌"}</b>`, env, USER_MENU);
  }

  if (action === "logs") {
    const result = await env.DB.prepare(`
      SELECT delivery_logs.*, groups.chat_id
      FROM delivery_logs
      LEFT JOIN groups ON groups.id = delivery_logs.group_id
      WHERE delivery_logs.user_id = ?
      ORDER BY delivery_logs.id DESC
      LIMIT 15
    `).bind(userId).all();

    if (!result.results.length) {
      return sendMessage(chatId, `📊 <b>Delivery Logs</b>

No delivery logs yet.`, env, USER_MENU);
    }

    const logs = result.results.map(log => {
      const icon = log.status === "sent" ? "✅" : "❌";
      return `${icon} ${escapeHtml(log.chat_id || "Unknown Group")}`;
    }).join("\n");

    return sendMessage(chatId, `📊 <b>Delivery Logs</b>

${logs}`, env, USER_MENU);
  }

  if (action === "plan") {
    return sendMessage(chatId, `💎 <b>Your Plan</b>

Plan:
<b>${escapeHtml(user.plan)}</b>

🤖 Ad Accounts:
<b>${user.ad_accounts}</b>

📢 Concurrent Ads:
<b>${user.max_ads}</b>

➕ Custom Group Limit:
<b>${user.custom_group_limit}</b>

🤖 Auto Reply:
<b>${Number(user.auto_reply) ? "Enabled ✅" : "Disabled ❌"}</b>

📅 Started:
<b>${formatDate(user.plan_started_at)}</b>

⏳ Expires:
<b>${formatDate(user.plan_expires_at)}</b>`, env, USER_MENU);
  }

  if (action === "support") {
    return sendMessage(chatId, `🆘 <b>Fast Ads Support</b>

Contact support for assistance.`, env, {
      inline_keyboard: [
        [{ text: "💬 Contact Support", url: `https://t.me/${env.SUPPORT_USERNAME}` }],
        [{ text: "⬅️ Home", callback_data: "home" }]
      ]
    });
  }
}

async function handleAdminMessage(chatId, adminId, text, env) {
  const state = await env.DB.prepare("SELECT * FROM admin_states WHERE admin_id = ?").bind(adminId).first();
  if (!state) return false;

  if (state.action === "waiting_sender_user") {
    const targetId = Number(text.trim());
    if (!Number.isSafeInteger(targetId)) { await sendMessage(chatId, "❌ Invalid Telegram User ID.", env); return true; }
    const target = await env.DB.prepare("SELECT telegram_id FROM users WHERE telegram_id = ?").bind(targetId).first();
    if (!target) { await sendMessage(chatId, "❌ User not found. Ask them to /start first.", env); return true; }
    await setAdminState(adminId, "waiting_sender_id", targetId, env);
    await sendMessage(chatId, "📡 Send the local sender account ID created by login.py. Example: <code>1</code>", env);
    return true;
  }

  if (state.action === "waiting_sender_id") {
    const localId = Number(text.trim());
    if (!Number.isSafeInteger(localId) || localId < 1) { await sendMessage(chatId, "❌ Invalid local sender ID.", env); return true; }

    await env.DB.prepare(`
      INSERT INTO sender_accounts (local_account_id, status)
      VALUES (?, 'active')
      ON CONFLICT(local_account_id) DO UPDATE SET status = 'active'
    `).bind(localId).run();

    const sender = await env.DB.prepare("SELECT id FROM sender_accounts WHERE local_account_id = ?").bind(localId).first();
    await env.DB.prepare("DELETE FROM user_sender_assignments WHERE user_id = ?").bind(state.target_user_id).run();
    await env.DB.prepare(`
      INSERT INTO user_sender_assignments (user_id, sender_account_id) VALUES (?, ?)
    `).bind(state.target_user_id, sender.id).run();
    await env.DB.prepare("DELETE FROM admin_states WHERE admin_id = ?").bind(adminId).run();

    await sendMessage(chatId, `✅ Sender <b>${localId}</b> assigned to <code>${state.target_user_id}</code>.`, env, ADMIN_MENU);
    return true;
  }

  if (state.action === "waiting_plan_user") {
    const targetId = Number(text.trim());

    if (!Number.isSafeInteger(targetId)) {
      await sendMessage(chatId, "❌ Invalid Telegram User ID.", env);
      return true;
    }

    const target = await env.DB.prepare("SELECT * FROM users WHERE telegram_id = ?").bind(targetId).first();

    if (!target) {
      await sendMessage(chatId, `❌ User not found.

Ask the customer to /start the bot first.`, env);
      return true;
    }

    await env.DB.prepare(`
      UPDATE admin_states SET action = 'select_plan', target_user_id = ? WHERE admin_id = ?
    `).bind(targetId, adminId).run();

    await sendMessage(chatId, `👤 User:
<code>${targetId}</code>

Select a plan 👇`, env, {
      inline_keyboard: [
        [{ text: "🥉 Bronze", callback_data: "admin_plan_Bronze" }],
        [{ text: "🥈 Silver", callback_data: "admin_plan_Silver" }],
        [{ text: "🥇 Gold", callback_data: "admin_plan_Gold" }]
      ]
    });
    return true;
  }

  if (state.action === "waiting_remove_user") {
    const targetId = Number(text.trim());

    if (!Number.isSafeInteger(targetId)) {
      await sendMessage(chatId, "❌ Invalid User ID.", env);
      return true;
    }

    const target = await env.DB.prepare("SELECT telegram_id FROM users WHERE telegram_id = ?").bind(targetId).first();

    if (!target) {
      await sendMessage(chatId, "❌ User not found.", env);
      return true;
    }

    await env.DB.prepare(`
      UPDATE users SET plan = NULL, ad_accounts = 0, max_ads = 0,
      custom_group_limit = 0, plan_started_at = NULL, plan_expires_at = NULL, state = NULL
      WHERE telegram_id = ?
    `).bind(targetId).run();

    await env.DB.prepare("DELETE FROM admin_states WHERE admin_id = ?").bind(adminId).run();

    await sendMessage(targetId, `⚠️ <b>Subscription Removed</b>

Your Fast Ads subscription is no longer active.`, env, NO_PLAN_MENU);

    await sendMessage(chatId, `✅ Plan removed from:

<code>${targetId}</code>`, env, ADMIN_MENU);
    return true;
  }

  return false;
}

async function handleAdminCallback(chatId, adminId, action, env) {
  if (action === "admin_assign_sender") {
    await setAdminState(adminId, "waiting_sender_user", null, env);
    await sendMessage(chatId, "📡 <b>Assign Sender</b>\\n\\nSend the customer's Telegram User ID.", env);
    return true;
  }

  if (action === "admin_give_plan") {
    await setAdminState(adminId, "waiting_plan_user", null, env);
    await sendMessage(chatId, `💎 <b>Give Plan</b>

Send the customer's Telegram User ID.`, env);
    return true;
  }

  if (action === "admin_remove_plan") {
    await setAdminState(adminId, "waiting_remove_user", null, env);
    await sendMessage(chatId, `🚫 <b>Remove Plan</b>

Send the customer's Telegram User ID.`, env);
    return true;
  }

  if (action.startsWith("admin_plan_")) {
    const planName = action.replace("admin_plan_", "");
    const plan = PLANS[planName];
    if (!plan) return true;

    const state = await env.DB.prepare("SELECT * FROM admin_states WHERE admin_id = ?").bind(adminId).first();

    if (!state?.target_user_id) {
      await sendMessage(chatId, "❌ No user selected.", env, ADMIN_MENU);
      return true;
    }

    const startedAt = new Date();
    const expiresAt = new Date(startedAt.getTime() + plan.days * 24 * 60 * 60 * 1000);

    await env.DB.prepare(`
      UPDATE users SET plan = ?, ad_accounts = ?, max_ads = ?, custom_group_limit = ?,
      plan_started_at = ?, plan_expires_at = ?, state = NULL
      WHERE telegram_id = ?
    `).bind(
      planName, plan.adAccounts, plan.maxAds, plan.customGroups,
      startedAt.toISOString(), expiresAt.toISOString(), state.target_user_id
    ).run();

    await env.DB.prepare("DELETE FROM admin_states WHERE admin_id = ?").bind(adminId).run();

    await sendMessage(state.target_user_id, `🎉 <b>Plan Activated!</b>

💎 Plan:
<b>${planName}</b>

📅 Activated:
<b>${formatDate(startedAt)}</b>

⏳ Expires:
<b>${formatDate(expiresAt)}</b>

Your dashboard is now active ⚡`, env, USER_MENU);

    await sendMessage(chatId, `✅ <b>Plan Activated</b>

👤 User:
<code>${state.target_user_id}</code>

💎 Plan:
<b>${planName}</b>

⏳ Expires:
<b>${formatDate(expiresAt)}</b>`, env, ADMIN_MENU);
    return true;
  }

  if (action === "admin_users") {
    const result = await env.DB.prepare(`
      SELECT telegram_id, username, plan FROM users ORDER BY created_at DESC LIMIT 20
    `).all();

    const users = result.results.map(user => `👤 <code>${user.telegram_id}</code>
@${escapeHtml(user.username || "NoUsername")}
💎 ${escapeHtml(user.plan || "No Plan")}`).join("\n\n");

    await sendMessage(chatId, `👥 <b>Latest Users</b>

${users || "No users."}`, env, ADMIN_MENU);
    return true;
  }

  if (action === "admin_stats") {
    const total = await env.DB.prepare("SELECT COUNT(*) AS total FROM users").first();
    const active = await env.DB.prepare(`
      SELECT COUNT(*) AS total FROM users WHERE plan IS NOT NULL AND plan_expires_at > ?
    `).bind(new Date().toISOString()).first();
    const ads = await env.DB.prepare("SELECT COUNT(*) AS total FROM ads").first();

    await sendMessage(chatId, `📊 <b>Bot Statistics</b>

👥 Total Users:
<b>${total.total}</b>

💎 Active Subscribers:
<b>${active.total}</b>

📢 Total Ads:
<b>${ads.total}</b>`, env, ADMIN_MENU);
    return true;
  }

  return false;
}

async function setAdminState(adminId, action, targetUserId, env) {
  await env.DB.prepare(`
    INSERT INTO admin_states (admin_id, action, target_user_id)
    VALUES (?, ?, ?)
    ON CONFLICT(admin_id) DO UPDATE SET
      action = excluded.action,
      target_user_id = excluded.target_user_id
  `).bind(adminId, action, targetUserId).run();
}

async function showService(chatId, planName, env) {
  const plan = PLANS[planName];
  const icons = { Bronze: "🥉", Silver: "🥈", Gold: "🥇" };

  return sendMessage(chatId, `${icons[planName]} <b>${planName}</b>

💰 Monthly: <b>$${plan.price}</b>
🤖 Bots Included: <b>${plan.adAccounts}</b>

📢 <b>Features</b>

• ${plan.adAccounts} Ad Account(s)
• Auto Reply
• ${plan.groups} Groups
• Add up to ${plan.customGroups}+ Custom Groups
• Free Replacement
• Run up to ${plan.maxAds} ad(s) at the same time

⏳ Duration:
<b>${plan.days} Days</b>`, env, {
    inline_keyboard: [
      [{ text: "💳 Buy Plan", callback_data: `buy_${planName.toLowerCase()}` }],
      [{ text: "⬅️ Back to Services", callback_data: "services" }]
    ]
  });
}

async function showHome(chatId, user, env) {
  if (!user.plan) {
    return sendMessage(chatId, `⚡ <b>Welcome to Fast Ads</b>

🔒 <b>No Active Subscription</b>

You need an active paid subscription to access the advertising dashboard.

View our services below 👇`, env, NO_PLAN_MENU);
  }

  return sendMessage(chatId, `⚡ <b>Fast Ads Panel</b>

💎 Plan:
<b>${escapeHtml(user.plan)}</b>

🤖 Ad Accounts:
<b>${user.ad_accounts}</b>

📢 Active Ad Limit:
<b>${user.max_ads}</b>

⏳ Expires:
<b>${formatDate(user.plan_expires_at)}</b>

Choose an option below 👇`, env, USER_MENU);
}

function isAdmin(userId, env) {
  return String(userId) === String(env.ADMIN_ID);
}

function formatDate(date) {
  if (!date) return "N/A";
  return new Date(date).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric"
  });
}

function capitalize(text = "") {
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

function escapeHtml(text = "") {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
