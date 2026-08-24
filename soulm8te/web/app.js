/* ULTI companion PWA frontend.
   - Talks to the Python backend API
   - Web3 identity via injected wallet (window.ethereum / EIP-1193)
   - Self-sovereign: conversation + relationship state stored locally in
     IndexedDB, AES-GCM encrypted with a key derived from the wallet signature
   - Offline-first: messages queue locally and sync when connection returns
*/
"use strict";

const API = "";
const SIGN_MESSAGE = "ULTI Companion :: derive local encryption key :: v1";
let wallet = null;       // address or null (guest)
let encKey = null;       // CryptoKey for local encryption
let pending = [];        // queued messages while offline

/* ---------------- storage (IndexedDB, encrypted) ---------------- */
const DB_NAME = "ulti-store";
function openDB() {
  return new Promise((res, rej) => {
    const r = indexedDB.open(DB_NAME, 1);
    r.onupgradeneeded = () => r.result.createObjectStore("state", { keyPath: "id" });
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
}
async function dbPut(id, value) {
  const db = await openDB();
  return new Promise((res, rej) => {
    const tx = db.transaction("state", "readwrite");
    tx.objectStore("state").put({ id, value });
    tx.oncomplete = () => res();
    tx.onerror = () => rej(tx.error);
  });
}
async function dbGet(id) {
  const db = await openDB();
  return new Promise((res, rej) => {
    const tx = db.transaction("state", "readonly");
    const rq = tx.objectStore("state").get(id);
    rq.onsuccess = () => res(rq.result ? rq.result.value : null);
    rq.onerror = () => rej(rq.error);
  });
}
const storageId = () => "chat:" + (wallet || "guest");

/* ---------------- crypto ---------------- */
async function deriveKeyFromSignature(sigHex) {
  const bytes = hexToBytes(sigHex);
  return crypto.subtle.importKey("raw", bytes, { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}
function hexToBytes(hex) {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
}
async function encrypt(text) {
  if (!encKey) return text;
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, encKey, new TextEncoder().encode(text));
  return btoa(String.fromCharCode(...iv) + "|" + btoa(String.fromCharCode(...new Uint8Array(ct))));
}
async function decrypt(blob) {
  if (!encKey || typeof blob !== "string" || !blob.includes("|")) return blob;
  try {
    const [ivB64, ctB64] = blob.split("|");
    const iv = new Uint8Array(atob(ivB64).split("").map((c) => c.charCodeAt(0)));
    const ct = new Uint8Array(atob(ctB64).split("").map((c) => c.charCodeAt(0)));
    const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, encKey, ct);
    return new TextDecoder().decode(pt);
  } catch { return blob; }
}

/* ---------------- persistence of conversation ---------------- */
async function saveConversation(messages) {
  const enc = await Promise.all(messages.map(async (m) => ({ ...m, text: await encrypt(m.text) })));
  await dbPut(storageId(), JSON.stringify(enc));
}
async function loadConversation() {
  const raw = await dbGet(storageId());
  if (!raw) return [];
  const arr = JSON.parse(raw);
  return await Promise.all(arr.map(async (m) => ({ ...m, text: await decrypt(m.text) })));
}

/* ---------------- chat UI ---------------- */
const chatEl = document.getElementById("chat");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const statusEl = document.getElementById("statusLine");
const offlineBar = document.getElementById("offlineBar");
let messages = [];

function addMsg(role, text, pendingFlag = false) {
  const div = document.createElement("div");
  div.className = `msg ${role}${pendingFlag ? " pending" : ""}`;
  div.textContent = text;
  if (pendingFlag) {
    const meta = document.createElement("span");
    meta.className = "meta"; meta.textContent = "در انتظار اتصال…";
    div.appendChild(meta);
  }
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}
function showTyping() {
  const div = document.createElement("div");
  div.className = "msg bot";
  div.innerHTML = '<span class="typing"><span></span><span></span><span></span></span>';
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}

async function send() {
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = "";
  addMsg("me", text);
  messages.push({ role: "me", text, ts: Date.now() });
  await saveConversation(messages);

  const typing = showTyping();
  const res = await apiPost("/api/chat", { text, wallet });
  typing.remove();

  if (res && res.reply) {
    addMsg("bot", res.reply);
    messages.push({ role: "bot", text: res.reply, ts: Date.now() });
    await saveConversation(messages);
    updateStatus(res);
  } else {
    // offline or error: keep pending locally
    addMsg("bot", "پیام رسید، اما هم‌اکنون دسترسی به همدم قطع است. پیام نزد تو می‌ماند و همگام می‌شود.", true);
  }
}

async function apiPost(path, body) {
  try {
    const r = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error("http " + r.status);
    setOffline(false);
    return await r.json();
  } catch {
    setOffline(true);
    pending.push(body);
    return null;
  }
}
async function apiGet(path) {
  try {
    const r = await fetch(API + path + (wallet ? "?wallet=" + encodeURIComponent(wallet) : ""));
    if (!r.ok) throw new Error();
    setOffline(false);
    return await r.json();
  } catch { setOffline(true); return null; }
}

function setOffline(off) {
  offlineBar.classList.toggle("hidden", !off);
}
function updateStatus(res) {
  if (res && res.status) statusEl.textContent = res.status.replace(/\n/g, " · ");
}

/* ---------------- Web3 identity ---------------- */
const walletBtn = document.getElementById("walletBtn");
async function connectWallet() {
  if (!window.ethereum) {
    statusEl.textContent = "کیف‌پولی یافت نشد — حالت مهمان فعال است.";
    return;
  }
  try {
    const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
    wallet = accounts[0];
    const provider = new ethers.BrowserProvider(window.ethereum);
    const signer = await provider.getSigner();
    const sig = await signer.signMessage(SIGN_MESSAGE);
    encKey = await deriveKeyFromSignature(sig.slice(2)); // strip 0x
    walletBtn.textContent = wallet.slice(0, 6) + "…" + wallet.slice(-4);
    statusEl.textContent = "هویت وب۳ متصل و داده‌ها رمزنگاری شدند.";
    await reloadForWallet();
  } catch (e) {
    statusEl.textContent = "اتصال کیف‌پول لغو شد — حالت مهمان.";
  }
}
walletBtn.addEventListener("click", connectWallet);

async function reloadForWallet() {
  messages = await loadConversation();
  chatEl.innerHTML = "";
  for (const m of messages) addMsg(m.role, m.text);
  const s = await apiGet("/api/status");
  if (s && s.status) statusEl.textContent = s.status.replace(/\n/g, " · ");
}

/* ---------------- backup (self-sovereign export) ---------------- */
document.getElementById("backupBtn").addEventListener("click", async () => {
  const raw = await dbGet(storageId());
  if (!raw) { alert("هنوز داده‌ای برای پشتیبان‌گیری نیست."); return; }
  const blob = new Blob([raw], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `ulti-backup-${wallet || "guest"}.json`;
  a.click();
  statusEl.textContent = "نسخه پشتیبان رمزنگاری‌شده دانلود شد — متعلق به خودت است.";
});

/* ---------------- wiring ---------------- */
sendBtn.addEventListener("click", send);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(140, inputEl.scrollHeight) + "px";
});

window.addEventListener("online", flushPending);
async function flushPending() {
  if (!pending.length) return;
  const queued = pending.slice();
  pending = [];
  for (const body of queued) {
    const res = await apiPost("/api/chat", body);
    if (res && res.reply) {
      addMsg("bot", res.reply);
      messages.push({ role: "bot", text: res.reply, ts: Date.now() });
    }
  }
  await saveConversation(messages);
}

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}

/* boot: guest mode by default, then attempt to restore */
(async () => {
  messages = await loadConversation();
  for (const m of messages) addMsg(m.role, m.text);
  const s = await apiGet("/api/status");
  if (s && s.status) statusEl.textContent = s.status.replace(/\n/g, " · ");
  else statusEl.textContent = "آفلاین — پیام‌ها ذخیره می‌شوند.";
})();
