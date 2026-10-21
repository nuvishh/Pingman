"""Pingman — self-hostable API testing tool.

Backend: Flask + SQLite. The server executes HTTP requests itself, so
CORS-blocked APIs work with no browser proxy needed. Saved requests,
tags and history persist in data.db.

Run locally:  pip install -r requirements.txt && python app.py
"""
import json
import os
import sqlite3
import time
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, redirect, request, send_from_directory, session

app = Flask(__name__, static_folder="static", static_url_path="")
DB = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "data.db"))

# --- Password protection ---------------------------------------------------
# Active only when the APP_PASSWORD environment variable is set (e.g. on
# Render). Without it the app runs open, as before (local use). The password
# itself never lives in the code or the repo — only in the server's env.
import hashlib
import hmac
from datetime import timedelta

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
app.secret_key = os.environ.get("SECRET_KEY") or (
    hashlib.sha256(("pingman:" + APP_PASSWORD).encode()).hexdigest()
    if APP_PASSWORD
    else "pingman-local-dev"
)
app.permanent_session_lifetime = timedelta(days=30)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),
)

_LOGIN_CSS = """
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:flex;align-items:center;
justify-content:center;color:#f2f2f0;padding:16px;
background:radial-gradient(900px 480px at 85% -10%,rgba(245,158,11,.13),transparent 60%),#0a0a0c;
font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.card{background:#141419;border:1px solid #33333f;border-radius:18px;padding:38px 32px;width:min(92vw,360px);
box-shadow:0 24px 60px rgba(0,0,0,.55);text-align:center}
.badge-img{width:54px;height:54px;border-radius:15px;margin:0 auto 14px;display:block;
box-shadow:0 6px 22px rgba(245,158,11,.35)}
.logo{font-size:26px;font-weight:800;letter-spacing:-.02em;margin-bottom:6px}
.logo span{background:linear-gradient(90deg,#fbbf24,#fb923c);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.sub{color:#9a9aa5;font-size:14px;margin-bottom:22px;line-height:1.5}
input{width:100%;padding:12px 14px;border-radius:10px;border:1px solid #33333f;background:#0a0a0c;color:#f2f2f0;
font-size:15px;outline:none}input:focus{border-color:#f59e0b;box-shadow:0 0 0 3px rgba(245,158,11,.15)}
button{width:100%;margin-top:14px;padding:12px;border:0;border-radius:10px;cursor:pointer;
background:linear-gradient(135deg,#f59e0b,#ea580c);color:#1a1005;font-size:15px;font-weight:700}
button:hover{filter:brightness(1.08)}
.err{background:rgba(248,113,113,.1);color:#fca5a5;border:1px solid rgba(248,113,113,.45);
padding:9px 12px;border-radius:10px;font-size:13px;margin-bottom:14px}
"""


def _login_page(error=""):
    err = f'<div class="err">{error}</div>' if error else ""
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Pingman — Login</title>"
        "<link rel='icon' type='image/svg+xml' href='/logo.svg'>"
        f"<style>{_LOGIN_CSS}</style></head><body>"
        "<form class='card' method='post' action='/login'>"
        "<img class='badge-img' src='/logo.svg' alt='Pingman logo'>"
        "<div class='logo'>Ping<span>man</span></div>"
        "<div class='sub'>This Pingman is private.<br>Enter the password to continue.</div>"
        f"{err}"
        "<input type='password' name='password' placeholder='Password' autofocus required>"
        "<button type='submit'>Unlock</button>"
        "</form></body></html>"
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD:
        return redirect("/")
    if session.get("authed"):
        return redirect("/")
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), APP_PASSWORD):
            session["authed"] = True
            session.permanent = True
            return redirect("/")
        return _login_page("Wrong password — try again."), 401
    return _login_page()


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login" if APP_PASSWORD else "/")


@app.before_request
def _auth_guard():
    if not APP_PASSWORD:
        return
    if request.endpoint in ("login", "logout"):
        return
    if request.path == "/logo.svg":
        return  # public: the login page itself shows the logo + favicon
    if session.get("authed"):
        return
    if request.path.startswith("/api/"):
        return jsonify({"error": "login required"}), 401
    return redirect("/login")


# --- end password protection ------------------------------------------------

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade", "content-length",
}
PRIVATE_RE = __import__("re").compile(
    r"^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|\[::1\])",
    __import__("re").I,
)


def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            method TEXT NOT NULL DEFAULT 'GET',
            url TEXT NOT NULL,
            headers TEXT NOT NULL DEFAULT '{}',
            params TEXT NOT NULL DEFAULT '[]',
            body TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER,
            method TEXT NOT NULL,
            url TEXT NOT NULL,
            status INTEGER,
            time_ms INTEGER,
            created_at INTEGER NOT NULL
        );
        """
    )
    con.commit()
    con.close()


def row_to_dict(r):
    d = dict(r)
    for k in ("headers", "params", "tags"):
        if k in d:
            try:
                d[k] = json.loads(d[k] or ("{}" if k == "headers" else "[]"))
            except Exception:
                d[k] = {} if k == "headers" else []
    return d


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/send", methods=["POST"])
def api_send():
    data = request.get_json(force=True) or {}
    method = (data.get("method") or "GET").upper()
    url = (data.get("url") or "").strip()
    headers = data.get("headers") or {}
    body = data.get("body") or ""
    req_id = data.get("request_id")

    if method not in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
        return jsonify({"error": "unsupported method"}), 400
    if not urlparse(url).scheme in ("http", "https"):
        return jsonify({"error": "url must start with http:// or https://"}), 400
    host = urlparse(url).hostname or ""
    if PRIVATE_RE.match(host):
        return jsonify({"error": "private/LAN targets are blocked"}), 403

    fwd = {k: v for k, v in headers.items()
           if k.lower() not in HOP_BY_HOP and k.lower() != "host"}
    started = time.time()
    try:
        r = requests.request(method, url, headers=fwd,
                             data=body.encode() if body else None,
                             timeout=30, allow_redirects=True)
        elapsed = int((time.time() - started) * 1000)
        try:
            body_text = r.text
        except Exception:
            body_text = ""
        result = {
            "status": r.status_code,
            "headers": dict(r.headers),
            "body": body_text,
            "time_ms": elapsed,
            "size": len(r.content),
            "final_url": r.url,
        }
        ok_status = r.status_code
    except Exception as e:
        elapsed = int((time.time() - started) * 1000)
        result = {"error": f"request failed: {e}", "time_ms": elapsed}
        ok_status = None

    con = db()
    con.execute(
        "INSERT INTO history (request_id, method, url, status, time_ms, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (req_id, method, url, ok_status, elapsed, int(time.time())),
    )
    con.execute("DELETE FROM history WHERE id NOT IN "
                "(SELECT id FROM history ORDER BY id DESC LIMIT 200)")
    con.commit()
    con.close()
    return jsonify(result)


@app.route("/api/requests", methods=["GET"])
def list_requests():
    tag = request.args.get("tag")
    q = request.args.get("q", "").lower()
    con = db()
    rows = con.execute("SELECT * FROM requests ORDER BY id DESC").fetchall()
    con.close()
    out = []
    for r in rows:
        d = row_to_dict(r)
        if tag and tag not in d["tags"]:
            continue
        if q and q not in (d["name"] + " " + d["url"]).lower():
            continue
        out.append(d)
    return jsonify(out)


@app.route("/api/requests", methods=["POST"])
def save_request():
    data = request.get_json(force=True) or {}
    con = db()
    cur = con.execute(
        "INSERT INTO requests (name, method, url, headers, params, body, tags, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (data.get("name", "Untitled"),
         (data.get("method") or "GET").upper(),
         data.get("url", ""),
         json.dumps(data.get("headers") or {}),
         json.dumps(data.get("params") or []),
         data.get("body") or "",
         json.dumps(data.get("tags") or []),
         int(time.time())),
    )
    con.commit()
    rid = cur.lastrowid
    con.close()
    return jsonify({"id": rid}), 201


@app.route("/api/requests/<int:rid>", methods=["PUT"])
def update_request(rid):
    data = request.get_json(force=True) or {}
    con = db()
    con.execute(
        "UPDATE requests SET name=?, method=?, url=?, headers=?, params=?, body=?, tags=?"
        " WHERE id=?",
        (data.get("name", "Untitled"),
         (data.get("method") or "GET").upper(),
         data.get("url", ""),
         json.dumps(data.get("headers") or {}),
         json.dumps(data.get("params") or []),
         data.get("body") or "",
         json.dumps(data.get("tags") or []),
         rid),
    )
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.route("/api/requests/<int:rid>", methods=["DELETE"])
def delete_request(rid):
    con = db()
    con.execute("DELETE FROM requests WHERE id=?", (rid,))
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.route("/api/history", methods=["GET"])
def list_history():
    con = db()
    rows = con.execute(
        "SELECT * FROM history ORDER BY id DESC LIMIT 100").fetchall()
    con.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/history", methods=["DELETE"])
def clear_history():
    con = db()
    con.execute("DELETE FROM history")
    con.commit()
    con.close()
    return jsonify({"ok": True})


@app.route("/api/tags", methods=["GET"])
def list_tags():
    con = db()
    rows = con.execute("SELECT tags FROM requests").fetchall()
    con.close()
    tags = {}
    for r in rows:
        try:
            for t in json.loads(r["tags"] or "[]"):
                tags[t] = tags.get(t, 0) + 1
        except Exception:
            pass
    return jsonify([{"name": n, "count": c} for n, c in sorted(tags.items())])


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
else:
    init_db()
