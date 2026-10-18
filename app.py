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
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__, static_folder="static", static_url_path="")
DB = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "data.db"))

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
