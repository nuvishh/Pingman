# Pingman 🏓

A self-hostable, Postman-lite API testing tool. The **server executes HTTP
requests itself**, so CORS-blocked APIs (servers without
`Access-Control-Allow-Origin`) work with no browser proxy needed. Saved
requests, tags and history persist in SQLite.

## Features
- Request composer: method, URL, query-params table (syncs both ways with the URL), headers, JSON/form/raw body
- Response viewer: status, time, size, syntax-highlighted JSON, headers view, copy
- Save requests with **tags** (e.g. `campusman`), filter by tag, search
- **History** of every send (click to reload), clearable
- `Ctrl+Enter` to send

## Run locally
```bash
pip install -r requirements.txt
python app.py
# open http://localhost:5000
```

## Deploy — PythonAnywhere
1. Upload this folder (or `git clone` the repo) to PythonAnywhere
2. Web tab → new **Flask** web app → point the WSGI file at `app.py`:
   ```python
   import sys
   sys.path.insert(0, '/home/YOURNAME/pingman')
   from app import app as application
   ```
3. `pip install -r requirements.txt --user` (or a virtualenv)
4. Reload. Data lives in `data.db` next to `app.py` (set `DB_PATH` env var to move it).

## Deploy — Render / Railway / any VPS
```bash
pip install -r requirements.txt
gunicorn app:app   # or: python app.py
```
Set `PORT` env var as needed (defaults to 5000).

## API
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/send` | Execute a request server-side `{method, url, headers, body, request_id?}` |
| GET/POST | `/api/requests` | List (filter `?tag=` / `?q=`) / save a request |
| PUT/DELETE | `/api/requests/<id>` | Update / delete a saved request |
| GET/DELETE | `/api/history` | List (latest 100) / clear history |
| GET | `/api/tags` | Tag names with counts |

## Notes
- Private/LAN targets (`localhost`, `10.x`, `192.168.x`…) are blocked from `/api/send` (SSRF guard).
- History keeps the latest 200 entries.
