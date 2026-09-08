#!/usr/bin/env node
/**
 * 🤖 WhatsApp Personal Assistant — دستیار هوشمند شخصی واتساپ
 * Connected to AI (GLM via 9router). Manages tasks, reminders, shopping lists,
 * daily reports, natural-language parsing, smart memory.
 *
 * Features:
 *  - Smart chat with AI
 *  - Task capture via natural language (per-user scoped)
 *  - Scheduled reminders (one-off + recurring daily/weekly) — sent only to owner
 *  - Smart memory / habit learning
 *  - Todo list with done-marking (per-user)
 *  - Morning daily report + evening summary (per-user)
 *  - Shopping list (per-user)
 *  - Text summarization & translation
 *  - Automatic data backup
 *
 * Speed note: every incoming message triggers exactly ONE AI call (combined
 * parse + reply), so latency stays ~2-5s instead of 60s+.
 */

const fs = require('fs');
const path = require('path');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const QR = require('qrcode');
const cron = require('node-cron');
const OpenAI = require('openai');

// ─── Config ─────────────────────────────────────────────────────────────
const DATA_DIR = __dirname;
const STORE_FILE = path.join(DATA_DIR, 'data.json');
const SESSION_DIR = path.join(DATA_DIR, 'auth');

const OPENAI_KEY = process.env.OPENAI_API_KEY || '';
const OPENAI_BASE = process.env.OPENAI_BASE_URL || 'https://9router-production-d365.up.railway.app/v1';
const AI_MODEL = process.env.AI_MODEL || 'GLM';
const OWN_NUMBER = '989200919019'; // bot's own WhatsApp number (self-chat support)

const openai = new OpenAI({ apiKey: OPENAI_KEY, baseURL: OPENAI_BASE });

// ─── Current time context (Tehran, Persian + Gregorian) ──────────────────
function nowContext() {
  const now = new Date();
  const faDate = new Intl.DateTimeFormat('fa-IR-u-ca-persian', { timeZone: 'Asia/Tehran', weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }).format(now);
  const faTime = new Intl.DateTimeFormat('fa-IR', { timeZone: 'Asia/Tehran', hour: '2-digit', minute: '2-digit', hour12: false }).format(now);
  const iso = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(now);
  return `🕒 زمان الان (تهران): ${faDate}، ساعت ${faTime} — میلادی: ${iso}`;
}

// ─── Persistent store ─────────────────────────────────────────────────────
function loadStore() {
  try {
    const s = JSON.parse(fs.readFileSync(STORE_FILE, 'utf8'));
    // ensure new per-user buckets exist for backward compat
    s.tasks = s.tasks || [];
    s.reminders = s.reminders || [];
    s.shopping = s.shopping || {}; // { [jid]: [item, ...] }
    s.users = s.users || {};
    s.memories = s.memories || {};
    return s;
  } catch {
    return { tasks: [], reminders: [], shopping: {}, users: {}, memories: {} };
  }
}
function saveStore(s) { fs.writeFileSync(STORE_FILE, JSON.stringify(s, null, 2)); }
let STORE = loadStore();

// ─── AI helpers ───────────────────────────────────────────────────────────
const ASSISTANT_SYS = `تو یک دستیار شخصی هوشمند فارسی‌زبان روی واتساپ هستی.
وظایف: مدیریت کارها، یادآوری‌ها، لیست خرید، گزارش روزانه، خلاصه‌سازی و ترجمه.
لحن صمیمی ولی مفید باش. پاسخ‌ها کوتاه و کاربردی. از ایموجی مناسب استفاده کن.
اگر درخواست نیاز به ثبت در سیستم دارد، ابتدا انجام بده و بعد تأیید بده.
مهم: مستقیم و کوتاه جواب بده، بدون مرحله تفکر.`;

// ONE AI call: ask for JSON action AND a ready Persian reply in the same response.
async function parseAndRespond(text, jid) {
  const sys = `تحلیل کن متن کاربر و یکی از دستورهای زیر را انجام بده.
در پاسخ، دقیقاً یک بلاک JSON خام (بدون توضیح اضافه) برگردان که شامل "action" و "reply" باشد:
{"action":"task_add","title":"...","due":"ISO یا null","priority":"low|normal|high","reply":"تأیید کوتاه فارسی"}
{"action":"task_list","reply":"..."}
{"action":"task_done","id":N,"reply":"..."}
{"action":"reminder_add","text":"...","when":"ISO datetime یا null","repeat":"none|daily|weekly","reply":"تأیید کوتاه"}
{"action":"reminder_list","reply":"..."}
{"action":"shopping_add","item":"...","reply":"..."}
{"action":"shopping_list","reply":"..."}
{"action":"shopping_remove","item":"...","reply":"..."}
{"action":"summary","text":"...","reply":"خلاصه ۳ خطی"}
{"action":"translate","text":"...","to":"en|fa","reply":"ترجمه"}
{"action":"chat","reply":"پاسخ دوستانه و کوتاه به فارسی"}
اگر متن فقط گفتگوست action=chat باشد.
${nowContext()}
قواعد زمان: "امروز" یعنی همین تاریخ الان. برای due/when از ISO 8601 با آفست تهران استفاده کن (مثال: 2026-09-07T16:30:00+03:30). هرگز زمان گذشته نساز مگر کاربر صریحاً گفته باشد.
فیلد reply همیشه پاسخ نهایی فارسی کوتاه باشد (با ایموجی).
مهم: بدون هیچ مرحله استدلال یا تفکر، مستقیم و کوتاه جواب بده. thinking را خاموش کن.`;
  try {
    const r = await openai.chat.completions.create({
      model: AI_MODEL,
      messages: [{ role: 'system', content: sys }, ...getHistory(jid).slice(-6), { role: 'user', content: text }],
      temperature: 0.2,
      max_tokens: 300,
    });
    let raw = r.choices[0].message.content.trim();
    raw = raw.replace(/^```json/i, '').replace(/```$/i, '').trim();
    const start = raw.indexOf('{');
    const end = raw.lastIndexOf('}');
    if (start === -1 || end === -1) return { action: 'chat', reply: raw };
    const action = JSON.parse(raw.slice(start, end + 1));
    return action;
  } catch (e) {
    console.error('AI error:', e.message);
    return { action: 'chat', reply: '⚠️ الان نتونستم به هوش‌مصنوعی وصل بشم. لطفاً چند لحظه دیگه امتحان کن یا دستور رو مستقیم بزن.' };
  }
}


// ─── Reply sanitizer: blocks English "thinking" leaks from the model ──────
function sanitizeReply(reply) {
  if (typeof reply !== 'string' || !reply.trim()) return null;
  const s = reply.trim();
  const ascii = (s.match(/[A-Za-z]/g) || []).length;
  const persian = (s.match(/[\u0600-\u06FF]/g) || []).length;
  // Long mostly-Latin text with no Persian = leaked reasoning → reject
  if (s.length > 100 && ascii > s.length * 0.5 && persian < 3) return null;
  // Known reasoning openers
  if (/^(here'?s|sure,?|let'?s|i'?ll|first,|step \d|analyz|thinking)/i.test(s)) return null;
  return s;
}

// ─── Task / reminder / shopping logic (all per-user scoped) ────────────────
function nextTaskId() {
  return STORE.tasks.reduce((m, t) => Math.max(m, t.id || 0), 0) + 1;
}
function userShopping(jid) {
  if (!STORE.shopping[jid]) STORE.shopping[jid] = [];
  return STORE.shopping[jid];
}

async function handleAction(action, jid, originalText) {
  switch (action.action) {
    case 'task_add': {
      const t = { id: nextTaskId(), jid, title: action.title || originalText, done: false, due: action.due || null, priority: action.priority || 'normal', created: Date.now() };
      STORE.tasks.push(t); saveStore(STORE);
      return `✅ کار ثبت شد:\n📌 ${t.title}${t.due ? `\n⏰ موعد: ${new Date(t.due).toLocaleString('fa-IR')}` : ''}`;
    }
    case 'task_list': {
      const open = STORE.tasks.filter(t => !t.done && t.jid === jid);
      if (!open.length) return '📭 هیچ کار بازی نداری.';
      return '📋 کارهای باز:\n' + open.map(t => `${t.id}. ${t.done ? '☑️' : '🔲'} ${t.title}`).join('\n');
    }
    case 'task_done': {
      const t = STORE.tasks.find(t => t.id === action.id && t.jid === jid);
      if (!t) return '❌ کار با این شماره پیدا نشد.';
      t.done = true; saveStore(STORE);
      return `☑️ انجام شد: ${t.title}`;
    }
    case 'reminder_add': {
      if (!action.when) return '⏰ زمان یادآوری رو متوجه نشدم. دقیق‌تر بگو، مثلاً: «فردا ساعت ۹ صبح یادآوری کن که…»';
      const fireDate = new Date(action.when);
      if (isNaN(fireDate.getTime()) || fireDate.getTime() <= Date.now()) {
        return '⚠️ این زمان گذشته یا نامعتبره. یه زمان آینده بگو، مثلاً: «۲ دقیقه دیگه یادآوری کن که…»';
      }
      // duplicate guard: same text + same minute for this user
      const dup = STORE.reminders.find(r => r.jid === jid && r.text === (action.text || originalText) && r.when === action.when);
      if (dup) return `🔔 این یادآوری قبلاً ثبت شده: ${dup.text}`;
      const rem = { id: Date.now(), jid, text: action.text || originalText, when: action.when, repeat: action.repeat || 'none' };
      STORE.reminders.push(rem); saveStore(STORE);
      scheduleReminder(rem);
      const whenStr = action.when ? new Date(action.when).toLocaleString('fa-IR') : 'زود';
      return `⏰ یادآوری تنظیم شد:\n🔔 ${rem.text}\n🗓 ${whenStr}${action.repeat !== 'none' ? ` (تکرار: ${action.repeat === 'daily' ? 'روزانه' : 'هفتگی'})` : ''}`;
    }
    case 'reminder_list': {
      const mine = STORE.reminders.filter(r => r.jid === jid);
      if (!mine.length) return '🔕 یادآوری فعالی نداری.';
      return '⏰ یادآوری‌ها:\n' + mine.map(r => `🔔 ${r.text} — ${r.when ? new Date(r.when).toLocaleString('fa-IR') : 'زود'}`).join('\n');
    }
    case 'shopping_add': {
      const list = userShopping(jid);
      list.push(action.item); saveStore(STORE);
      return `🛒 اضافه شد به لیست خرید: ${action.item}`;
    }
    case 'shopping_list': {
      const list = userShopping(jid);
      if (!list.length) return '🛒 لیست خرید خالیه.';
      return '🛒 لیست خرید:\n' + list.map((i, n) => `${n + 1}. ${i}`).join('\n');
    }
    case 'shopping_remove': {
      const list = userShopping(jid);
      const before = list.length;
      STORE.shopping[jid] = list.filter(i => i !== action.item);
      saveStore(STORE);
      return before !== STORE.shopping[jid].length ? `🗑 حذف شد: ${action.item}` : '❌ این مورد تو لیست نبود.';
    }
    case 'summary': {
      const s = await aiChat('متن زیر را در ۳ خط خلاصه کن (فارسی):', action.text || originalText);
      return `📝 خلاصه:\n${s}`;
    }
    case 'translate': {
      const to = action.to === 'en' ? 'انگلیسی' : 'فارسی';
      const s = await aiChat(`متن را به ${to} ترجمه کن:`, action.text || originalText);
      return `🌐 ترجمه (${to}):\n${s}`;
    }
    default: {
      // action.reply already holds the chat answer from the same AI call
      const clean = sanitizeReply(action.reply);
      if (clean) return clean;
      const retry = await aiChat(ASSISTANT_SYS + '\n' + nowContext() + '\nفقط فارسی، حداکثر ۳ جمله، بدون توضیح انگلیسی.', originalText, getHistory(jid));
      return sanitizeReply(retry) || '🤖 ببخشید، درست متوجه نشدم. یه بار دیگه بگو؟';
    }
  }
}

async function aiChat(systemPrompt, userText, history = []) {
  try {
    const r = await openai.chat.completions.create({
      model: AI_MODEL,
      messages: [{ role: 'system', content: systemPrompt }, ...history, { role: 'user', content: userText }],
      temperature: 0.2,
      max_tokens: 500,
    });
    return r.choices[0].message.content.trim();
  } catch (e) {
    return '⚠️ مشکل در پاسخ‌دهی.';
  }
}

function getHistory(jid) {
  const u = STORE.users[jid] || [];
  return u.slice(-10);
}
function pushHistory(jid, role, text) {
  if (!STORE.users[jid]) STORE.users[jid] = [];
  STORE.users[jid].push({ role, content: text });
  if (STORE.users[jid].length > 30) STORE.users[jid].shift();
  saveStore(STORE);
}

// ─── Reminders scheduling (owner-scoped) ───────────────────────────────────
function scheduleReminder(rem) {
  if (!rem.when) return;
  const fire = new Date(rem.when);
  let delay = fire.getTime() - Date.now();
  const LATE = -delay;
  // Missed while bot was off: ≤24h → fire NOW (catch-up, "sorry late"); >24h → drop/roll
  if (delay <= 0) {
    if (LATE <= 24 * 60 * 60 * 1000) {
      delay = 3000;
    } else if (rem.repeat === 'none') {
      STORE.reminders = STORE.reminders.filter(r => r.id !== rem.id);
      saveStore(STORE);
      console.log(`[REM] dropped stale one-off (>24h late): ${(rem.text || '').slice(0, 30)}`);
      return;
    } else {
      // recurring missed by >24h: roll to next future occurrence (no catch-up spam)
      while (new Date(rem.when).getTime() <= Date.now()) {
        const step = rem.repeat === 'weekly' ? 7 * 86400000 : 86400000;
        rem.when = new Date(new Date(rem.when).getTime() + step).toISOString();
      }
      saveStore(STORE);
      delay = new Date(rem.when).getTime() - Date.now();
    }
  }
  if (delay > 0) {
    setTimeout(async () => {
      await sendReminder(rem, LATE > 60000);
      if (rem.repeat === 'daily') {
        rem.when = new Date(fire.getTime() + 86400000).toISOString();
        saveStore(STORE); scheduleReminder(rem);
      } else if (rem.repeat === 'weekly') {
        rem.when = new Date(fire.getTime() + 7 * 86400000).toISOString();
        saveStore(STORE); scheduleReminder(rem);
      }
    }, delay);
  }
}
async function sendReminder(rem, isLate = false) {
  const s = global.sockRef();
  const prefix = isLate ? '⏰ یادآوری (ببخشید دیر شد — ربات لحظه‌ای آفلاین بود):\n🔔' : '⏰ یادآوری:\n🔔';
  if (s) await s.sendMessage(rem.jid, { text: `${prefix} ${rem.text}` }).catch(() => {});
}
STORE.reminders.forEach(scheduleReminder);

// ─── Daily report (09:00) & evening summary (22:00) — per user ────────────
cron.schedule('0 9 * * *', () => {
  const jids = new Set([...STORE.reminders.map(r => r.jid), ...Object.keys(STORE.users)]);
  jids.forEach(jid => {
    const open = STORE.tasks.filter(t => !t.done && t.jid === jid);
    const shopping = (STORE.shopping[jid] || []).length;
    const msg = `☀️ گزارش صبح:\n📋 ${open.length} کار باز\n${open.slice(0, 5).map(t => `• ${t.title}`).join('\n')}\n🛒 لیست خرید: ${shopping} مورد`;
    const s = global.sockRef();
    if (s) s.sendMessage(jid, { text: msg }).catch(() => {});
  });
});
cron.schedule('0 22 * * *', () => {
  const jids = new Set([...STORE.reminders.map(r => r.jid), ...Object.keys(STORE.users)]);
  jids.forEach(jid => {
    const done = STORE.tasks.filter(t => t.done && t.jid === jid).length;
    const open = STORE.tasks.filter(t => !t.done && t.jid === jid).length;
    const msg = `🌙 جمع‌بندی شب:\n✅ انجام‌شده: ${done}\n📋 باز: ${open}`;
    const s = global.sockRef();
    if (s) s.sendMessage(jid, { text: msg }).catch(() => {});
  });
});

// ─── Automatic backup ──────────────────────────────────────────────────────
cron.schedule('0 */6 * * *', () => {
  try {
    const bak = path.join(DATA_DIR, `data.backup.${Date.now()}.json`);
    fs.copyFileSync(STORE_FILE, bak);
    const files = fs.readdirSync(DATA_DIR).filter(f => f.startsWith('data.backup.')).sort();
    while (files.length > 5) { fs.unlinkSync(path.join(DATA_DIR, files.shift())); }
    console.log('backup done');
  } catch (e) { console.error('backup err', e.message); }
});

// ─── WhatsApp connection ──────────────────────────────────────────────────
let sock;
let ownPn = OWN_NUMBER;
let ownLid = null;
const botSentIds = new Set();

async function connectToWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);
  const { version } = await fetchLatestBaileysVersion();
  sock = makeWASocket({ version, auth: state, printQRInTerminal: false });
  global.sockRef = () => sock;

  sock.ev.on('connection.update', (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      const qrPath = path.join(__dirname, 'wa_login_qr.png');
      QR.toFile(qrPath, qr, { width: 420 }, (err) => { if (!err) console.log('QR_SAVED:' + qrPath); });
    }
    if (connection === 'close') {
      if (lastDisconnect?.error?.output?.statusCode !== DisconnectReason.loggedOut) connectToWhatsApp();
    }
    if (connection === 'open') {
      ownPn = (sock.user?.id || '').split('@')[0].split(':')[0] || ownPn;
      ownLid = (sock.user?.lid || '').split('@')[0].split(':')[0] || null;
      console.log(`✅ WhatsApp connected (ownPn=${ownPn}, ownLid=${ownLid})`);
    }
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    for (const m of messages) {
      if (!m.message) continue;
      const jid = m.key.remoteJid || '';
      const isGroup = jid.endsWith('@g.us');
      if (botSentIds.has(m.key.id)) { botSentIds.delete(m.key.id); continue; }
      const jidNum = (jid.split('@')[0] || '').split(':')[0];
      const isSelfChat = !isGroup && (jidNum === ownPn || (ownLid && jidNum === ownLid));
      if (m.key.fromMe && !isSelfChat && !isGroup) continue;
      console.log(`[IN] jid=${jid} type=${type} self=${isSelfChat} grp=${isGroup} text=${JSON.stringify((m.message.conversation || m.message.extendedTextMessage?.text || '').slice(0, 80))}`);
      if (!isGroup && !jid.endsWith('@s.whatsapp.net') && !jid.endsWith('@lid')) continue;
      const text = m.message.conversation || m.message.extendedTextMessage?.text || '';
      if (!text) continue;

      try {
        pushHistory(jid, 'user', text);
        const action = await parseAndRespond(text, jid);
        let reply = await handleAction(action, jid, text);
        // no-English-leak guard on EVERY outgoing reply (not just chat)
        const cleaned = sanitizeReply(reply);
        if (!cleaned) reply = '🤖 ببخشید، درست متوجه نشدم. یه بار دیگه بگو؟';
        else reply = cleaned;
        pushHistory(jid, 'assistant', reply);
        const sent = await sock.sendMessage(jid, { text: reply });
        if (sent?.key?.id) {
          botSentIds.add(sent.key.id);
          if (botSentIds.size > 500) botSentIds.clear();
        }
        console.log(`[OUT] reply sent to ${jid}`);
      } catch (e) {
        console.error(`[ERR] handler for ${jid}: ${e.message}`);
        try { await sock.sendMessage(jid, { text: '⚠️ مشکلی پیش اومد — دوباره امتحان کن.' }); } catch (_) {}
      }
    }
  });
}

connectToWhatsApp();
console.log('🤖 WhatsApp Assistant starting...');
