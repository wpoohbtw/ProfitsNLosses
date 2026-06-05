# ProfitsNLosses

Локальная панель для имитации крипто-сделок: биржевые балансы, позиции, закрытые сделки, календарь PnL и страница ситуаций через Google Sheets.

## Стек

- Frontend: React + TypeScript + Vite
- Backend: Python + FastAPI
- Database: SQLite
- Icons: lucide-react
- Market data: public futures/perpetual endpoints бирж

## Требования

- Node.js + npm
- Python 3.11+
- Windows для `run-local.bat`

## Первичная настройка

1. Скопируй `.env.example` в `.env`.
2. Заполни `GOOGLE_SHEETS_SPREADSHEET_ID` в `.env`.
3. Положи Google service account файл сюда:

```text
backend/google-service-account.json
```

4. Убедись, что Google Sheet расшарен на email service account.

## Запуск

```bat
run-local.bat
```

Скрипт сам:

- создаст `backend/.venv`, если его нет;
- установит Python зависимости;
- установит frontend зависимости, если нет `node_modules`;
- поднимет backend на `http://127.0.0.1:8001`;
- поднимет frontend на `http://127.0.0.1:5173`;
- при закрытии остановит локальные процессы.

## Локальные данные

SQLite база создаётся автоматически в:

```text
backend/data/profits_n_losses.sqlite3
```

Эта база не коммитится. У каждого пользователя будет своя локальная история балансов и сделок.

## Что не коммитить

- `.env`
- `backend/google-service-account.json`
- `backend/data/*.sqlite3`
- `backend/.venv/`
- `node_modules/`
- `dist/`
- `vault/`
- `.lazyweb/`

## Иконки бирж

Иконки лежат в:

```text
public/exchange-icons/
```

Файл должен называться по slug биржи, например `binance.svg`, `mexc.svg`, `kucoin.svg`.
