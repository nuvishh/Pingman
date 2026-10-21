<p align="center">
  <img src="static/logo.svg" width="96" alt="Pingman logo">
</p>

# Pingman 🏓

A self-hostable, Postman-lite API testing tool. The **server executes HTTP
requests itself**, so CORS-blocked APIs (servers without
`Access-Control-Allow-Origin`) work with no browser proxy needed. Saved
requests, tags and history persist in SQLite.

🔗 **Live (password-protected instance):** https://pingman-uisd.onrender.com
*(Render free tier — sleeps after ~15 min idle, first load takes ~30–60s;
saved data lives on an ephemeral disk and may reset on redeploys.)*

## Features
- Request composer: method, URL, query-params table (syncs both ways with the URL), headers, JSON/form/raw body
- Response viewer: status pill, time, size, syntax-highlighted JSON, headers view, copy
- Save requests with **tags** (e.g. `campusman`), filter by tag, search
- **History** of every send (click to reload), clearable
- `Ctrl+Enter` to send
- **Amber console UI** — command-bar composer, card sidebar, works on mobile
- Optional **password protection** (see below)

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
Set `PORT` env var as needed (defaults to 5000). A `render.yaml` blueprint
is included — on Render, "New → Blueprint" deploys it in one go.
**Custom domain:** point a subdomain at the service (e.g.
`pingman.yourdomain.dev` via CNAME) under Settings → Custom Domains —
Render issues the HTTPS certificate automatically.

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

## Password protection

Set the `APP_PASSWORD` environment variable to lock the app behind a login
page (recommended for any public deployment — e.g. on Render: service →
Environment → Add `APP_PASSWORD`). Without the variable the app runs open,
which is fine for local use. Sessions last 30 days; use the Logout button
in the header to sign out. Optionally also set `SECRET_KEY` to keep
sessions valid across password changes.

## License

MIT

---

Made with ♥ by **nuvish**
