const $ = id => document.getElementById(id);
let activeTag = null, editingId = null, searchQ = "";

const api = {
  get: p => fetch(p).then(r => r.json()),
  post: (p, b) => fetch(p, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(b)}).then(r => r.json()),
  put: (p, b) => fetch(p, {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(b)}).then(r => r.json()),
  del: p => fetch(p, {method: "DELETE"}).then(r => r.json()),
};

function toast(msg) {
  const t = $("toast"); t.textContent = msg; t.classList.remove("hidden");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), 2200);
}

// ---------- key-value rows ----------
function kvRow(container, k = "", v = "", on = true) {
  const d = document.createElement("div"); d.className = "kv";
  d.innerHTML = `<input type="checkbox" ${on ? "checked" : ""} title="enabled">
    <input placeholder="key" value="${esc(k)}"><input placeholder="value" value="${esc(v)}">
    <button class="x" title="remove">×</button>`;
  d.querySelector(".x").onclick = () => { d.remove(); syncFromRows(); };
  d.querySelectorAll("input").forEach(i => i.oninput = syncFromRows);
  $(container).appendChild(d);
  return d;
}
const esc = s => String(s ?? "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
function rows(container) {
  return [...document.querySelectorAll("#" + container + " .kv")].map(d => {
    const [c, k, v] = d.querySelectorAll("input");
    return {on: c.checked, key: k.value.trim(), value: v.value};
  }).filter(r => r.key);
}
function syncFromRows() {
  const params = rows("paramRows").filter(r => r.on);
  const u = $("url").value.trim();
  const base = u.split("?")[0];
  const qs = new URLSearchParams();
  params.forEach(p => qs.append(p.key, p.value));
  // preserve hash
  const hash = u.includes("#") ? u.slice(u.indexOf("#")) : "";
  $("url").value = qs.toString() ? base + "?" + qs + hash : base + hash;
  updateCounts();
}
function syncToRows() {
  try {
    const u = new URL($("url").value.trim(), location.origin);
    $("paramRows").innerHTML = "";
    let n = 0;
    u.searchParams.forEach((v, k) => { kvRow("paramRows", k, v); n++; });
    if (!n) kvRow("paramRows");
  } catch (e) { /* invalid url — leave rows */ }
  updateCounts();
}
function updateCounts() {
  const p = rows("paramRows").length, h = rows("headerRows").length;
  $("paramCount").textContent = p || ""; $("headerCount").textContent = h || "";
}
let urlTimer;
$("url").addEventListener("input", () => { clearTimeout(urlTimer); urlTimer = setTimeout(syncToRows, 600); });
$("addParam").onclick = () => kvRow("paramRows");
$("addHeader").onclick = () => kvRow("headerRows");

// ---------- tabs ----------
document.querySelectorAll(".req-tab").forEach(b => b.onclick = () => {
  document.querySelectorAll(".req-tab").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  ["params", "headers", "body"].forEach(t => $("tab-" + t).classList.toggle("hidden", t !== b.dataset.tab));
});
document.querySelectorAll(".resp-tab").forEach(b => b.onclick = () => {
  document.querySelectorAll(".resp-tab").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  $("respBody").classList.toggle("hidden", b.dataset.rtab !== "rbody");
  $("respHeaders").classList.toggle("hidden", b.dataset.rtab !== "rheaders");
});
document.querySelectorAll(".side-tab").forEach(b => b.onclick = () => {
  document.querySelectorAll(".side-tab").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  const saved = b.id === "tabSaved";
  $("savedPane").classList.toggle("hidden", !saved);
  $("historyPane").classList.toggle("hidden", saved);
});
$("bodyType").onchange = e => {
  const t = e.target.value;
  $("bodyHint").textContent = {json: "Sent as application/json", form: "Sent as application/x-www-form-urlencoded",
    raw: "Sent as text/plain", none: "No body sent"}[t];
  if (t === "form" && !$("body").value) $("body").value = "key=value&foo=bar";
};

// ---------- send ----------
function collect() {
  const params = rows("paramRows").filter(r => r.on);
  const headers = {};
  rows("headerRows").filter(r => r.on).forEach(r => headers[r.key] = r.value);
  const bt = $("bodyType").value, bv = $("body").value;
  let body = "";
  if (bt !== "none" && ["POST", "PUT", "PATCH", "DELETE"].includes($("method").value)) {
    body = bv;
    if (bt === "json" && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    if (bt === "form" && !headers["Content-Type"]) headers["Content-Type"] = "application/x-www-form-urlencoded";
    if (bt === "raw" && !headers["Content-Type"]) headers["Content-Type"] = "text/plain";
  }
  return {method: $("method").value, url: $("url").value.trim(), headers, params, body};
}
$("sendBtn").onclick = async () => {
  const c = collect();
  if (!c.url) return toast("Enter a URL first");
  if (c.bodyType !== "none" && $("bodyType").value === "json" && c.body) {
    try { JSON.parse(c.body); } catch (e) { return toast("Body is not valid JSON"); }
  }
  $("sendBtn").disabled = true; $("sendBtn").textContent = "Sending…";
  $("error").classList.add("hidden"); $("response").classList.add("hidden");
  try {
    const r = await api.post("/api/send", {...c, request_id: editingId});
    renderResponse(r, c.url);
    loadHistory();
  } catch (e) {
    $("error").textContent = "Could not reach the Pingman server: " + e.message;
    $("error").classList.remove("hidden");
  }
  $("sendBtn").disabled = false; $("sendBtn").textContent = "Send ➤";
};
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") $("sendBtn").click();
});

function hl(json) {
  return esc(json).replace(/(&quot;(\\u[a-f0-9]{4}|\\[^u]|[^\\&])*?&quot;(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g,
    m => {
      let cls = "j-n";
      if (/^&quot;/.test(m)) cls = /:$/.test(m) ? "j-k" : "j-s";
      else if (/true|false|null/.test(m)) cls = "j-b";
      return `<span class="${cls}">${m}</span>`;
    });
}
function renderResponse(r, url) {
  $("response").classList.remove("hidden");
  const st = $("respStatus");
  if (r.error) {
    st.textContent = "ERROR"; st.className = "status s0";
    $("respBody").innerHTML = esc(r.error);
  } else {
    const code = r.status;
    st.textContent = code; st.className = "status " + (code < 300 ? "s2" : code < 500 ? "s4" : "s5");
    let pretty = r.body;
    try { pretty = JSON.stringify(JSON.parse(r.body), null, 2); $("respBody").innerHTML = hl(pretty); }
    catch (e) { $("respBody").textContent = r.body; }
    $("respHeaders").textContent = Object.entries(r.headers || {}).map(([k, v]) => k + ": " + v).join("\n");
  }
  $("respTime").textContent = (r.time_ms ?? 0) + " ms";
  $("respSize").textContent = r.size != null ? fmtSize(r.size) : "";
  $("respUrl").textContent = r.final_url && r.final_url !== url ? "→ " + r.final_url : "";
  $("respBody").dataset.raw = r.body || r.error || "";
}
const fmtSize = b => b < 1024 ? b + " B" : (b / 1024).toFixed(1) + " KB";
$("copyResp").onclick = () => { navigator.clipboard.writeText($("respBody").dataset.raw || ""); toast("Copied"); };

// ---------- save ----------
$("saveBtn").onclick = () => { $("saveModal").classList.remove("hidden"); $("saveName").focus(); };
$("saveCancel").onclick = () => $("saveModal").classList.add("hidden");
$("saveConfirm").onclick = async () => {
  const c = collect();
  const name = $("saveName").value.trim() || c.method + " " + c.url.slice(0, 40);
  const tags = $("saveTags").value.split(",").map(t => t.trim().toLowerCase()).filter(Boolean);
  const payload = {...c, name, tags};
  if (editingId) { await api.put("/api/requests/" + editingId, payload); toast("Updated"); }
  else { const r = await api.post("/api/requests", payload); editingId = r.id; toast("Saved" + (tags.length ? " under " + tags.join(", ") : "")); }
  $("saveModal").classList.add("hidden");
  loadSaved(); loadTags();
};

// ---------- sidebar ----------
async function loadTags() {
  const tags = await api.get("/api/tags");
  const el = $("tagList"); el.innerHTML = "";
  const all = document.createElement("span");
  all.className = "tag" + (!activeTag ? " active" : ""); all.textContent = "All";
  all.onclick = () => { activeTag = null; loadTags(); loadSaved(); };
  el.appendChild(all);
  tags.forEach(t => {
    const s = document.createElement("span");
    s.className = "tag" + (activeTag === t.name ? " active" : "");
    s.innerHTML = `${esc(t.name)}<span class="n">${t.count}</span>`;
    s.onclick = () => { activeTag = activeTag === t.name ? null : t.name; loadTags(); loadSaved(); };
    el.appendChild(s);
  });
}
async function loadSaved() {
  const p = new URLSearchParams();
  if (activeTag) p.set("tag", activeTag);
  if (searchQ) p.set("q", searchQ);
  const list = await api.get("/api/requests?" + p);
  const el = $("savedPane"); el.innerHTML = list.length ? "" : `<div class="hint" style="padding:8px">No saved requests yet.</div>`;
  list.forEach(r => {
    const d = document.createElement("div"); d.className = "item";
    d.innerHTML = `<span class="del" title="delete">×</span>
      <span class="m m-${r.method}">${r.method}</span><span class="u">${esc(r.url.slice(0, 60))}</span>
      <div class="t">${esc(r.name)}</div>
      <div class="tags">${(r.tags || []).map(t => `<span>${esc(t)}</span>`).join("")}</div>`;
    d.onclick = e => { if (e.target.classList.contains("del")) return; loadIntoComposer(r); };
    d.querySelector(".del").onclick = async () => { await api.del("/api/requests/" + r.id); loadSaved(); loadTags(); toast("Deleted"); };
    el.appendChild(d);
  });
}
async function loadHistory() {
  const list = await api.get("/api/history");
  const el = $("historyList"); el.innerHTML = list.length ? "" : `<div class="hint" style="padding:8px">No history yet.</div>`;
  list.forEach(h => {
    const d = document.createElement("div"); d.className = "item";
    const when = new Date(h.created_at * 1000);
    d.innerHTML = `<span class="m m-${h.method}">${h.method}</span><span class="u">${esc(h.url.slice(0, 52))}</span>
      <div class="t">${h.status ?? "ERR"} · ${h.time_ms ?? 0} ms · ${when.toLocaleString()}</div>`;
    d.onclick = () => {
      $("method").value = h.method; $("url").value = h.url; syncToRows();
      editingId = h.request_id; toast("Loaded from history");
    };
    el.appendChild(d);
  });
}
function loadIntoComposer(r) {
  editingId = r.id;
  $("method").value = r.method; $("url").value = r.url;
  $("paramRows").innerHTML = "";
  (r.params || []).forEach(p => kvRow("paramRows", p.key, p.value, p.on !== false));
  if (!(r.params || []).length) kvRow("paramRows");
  $("headerRows").innerHTML = "";
  Object.entries(r.headers || {}).forEach(([k, v]) => kvRow("headerRows", k, v));
  if (!Object.keys(r.headers || {}).length) kvRow("headerRows");
  $("body").value = r.body || "";
  syncFromRows(); updateCounts();
  toast("Loaded: " + r.name);
}
$("clearHistory").onclick = async () => { await api.del("/api/history"); loadHistory(); toast("History cleared"); };
let searchTimer;
$("search").addEventListener("input", e => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { searchQ = e.target.value.trim(); loadSaved(); }, 400); });

// ---------- init ----------
kvRow("paramRows"); kvRow("headerRows");
$("bodyType").onchange({target: $("bodyType")});
loadTags(); loadSaved(); loadHistory();
