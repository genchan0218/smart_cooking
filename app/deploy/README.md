# Deploying the pantry dashboard to the VPS

What goes up: the `app/` folder (without `grocery.db`, `uploads/`, `__pycache__`) and the two seed files
`data/inventory.json` and `data/recipes.json`. Do NOT upload `photos/`, `scripts/`, or anything from `C:\Users\genki\Documents\PK\`.

Layout on the server (suggested): `/opt/pantry/app/`, `/opt/pantry/data/` (seed JSON), `/var/lib/pantry/` (SQLite + uploads).
`db.py` finds the seed files at `../data` relative to `app/`, so keep that structure.

## Steps
1. `python3 -m venv /opt/pantry/venv && /opt/pantry/venv/bin/pip install -r /opt/pantry/app/requirements.txt`
2. Create `/etc/pantry.env` (mode 600, root-owned) from `pantry.env.example`; set a real `APP_PASSWORD`.
3. Install `pantry.service` to `/etc/systemd/system/`, then `systemctl enable --now pantry`.
4. Put Caddy in front (`Caddyfile.example`) for HTTPS, or bind to localhost and use an SSH tunnel until a domain exists.
5. Nightly backup: copy `/var/lib/pantry/grocery.db` somewhere else (`sqlite3 grocery.db ".backup ..."`).
6. Check `GET /health`, then log in as user `home` with `APP_PASSWORD`.

## Notes
- First start creates the database and imports the seed JSON. Later edits live in the database only.
- `VISION_BACKEND=off` on the VPS: the vision model runs on the owner's PC (Ollama), not the server. The manual Add form works.
  To enable photo intake from the server later, point `OLLAMA_URL` at a reachable Ollama (e.g. over a private tunnel).
- Run `python smoke_test.py` from `app/` after install; it uses a throwaway database.
