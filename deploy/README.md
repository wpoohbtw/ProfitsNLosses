# ProfitsNLosses deployment

ProfitsNLosses is intended to run behind SoftPortal at `/pnl/`.

The frontend is a static Vite build with `base: "/pnl/"`.
The backend listens privately on `127.0.0.1:8001`; do not expose it directly to the internet.

## Expected layout

```text
/srv/SoftPortal/
  backend/
  frontend/
    dist/
/srv/ProfitsNLosses/
  backend/
  dist/
```

## Backend

```bash
cd /srv/ProfitsNLosses/backend
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd /srv/ProfitsNLosses
cp deploy/pnl.env.production.example .env
nano .env
sudo cp /srv/ProfitsNLosses/deploy/pnl-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pnl-api
```

The first backend start needs access to the SoftPortal database from `PNL_PORTAL_DB_PATH`.
If you use `PNL_DEV_USERNAME=admin`, start SoftPortal once first so it creates the admin user.

## Frontend

```bash
cd /srv/ProfitsNLosses
npm ci
npm run build
```

SoftPortal must point to this build:

```text
PORTAL_PNL_DIST_PATH=/srv/ProfitsNLosses/dist
```

## Optional Google Sheets setup

If the Situations page is needed, copy the service account JSON to:

```text
/srv/ProfitsNLosses/backend/google-service-account.json
```

Then set `GOOGLE_SHEETS_SPREADSHEET_ID` in `/srv/ProfitsNLosses/.env`.

## Data migration

SQLite data is not committed to git. To keep local data, copy it separately:

```text
backend/data/profits_n_losses.sqlite3
```

Place it on the server at:

```text
/srv/ProfitsNLosses/backend/data/profits_n_losses.sqlite3
```
