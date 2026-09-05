# Bangkok Flight Watcher

Playwright worker for Railway. It watches one-way economy fares from Bangalore
(`BLR`) to Bangkok (`BKK`) for every Thursday, Friday, and Saturday in October
2026 and sends Telegram alerts for each ₹500-or-larger fall from the last
alerted price.

## How it behaves

- Runs every random 300–360 seconds.
- Rotates Google Flights, Kayak, and Skyscanner once per worker run.
- Scans 3 of the 15 target dates per run in round-robin order. This keeps each
  source/date request reasonably spaced; set `DATES_PER_RUN=15` only if you have
  permission and accept the higher block risk.
- Sends an initial baseline message for each date. Set
  `ALERT_ON_FIRST_SEEN=false` to make the first observation silent.
- Uses the cheapest plausible INR amount rendered on the results page. Always
  verify baggage, taxes, airport, and final checkout price before booking.
- Does not bypass CAPTCHAs or access controls. Selectors and page markup can
  change, so Railway logs should be checked if a provider stops returning data.

## Telegram setup

1. Message `@BotFather` in Telegram, run `/newbot`, and copy the bot token.
2. Send any message to the new bot.
3. Open `https://api.telegram.org/botYOUR_TOKEN/getUpdates` and copy
   `message.chat.id` as the chat ID.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
set -a; source .env; set +a
python app.py
```

## Deploy on Railway

1. Push this folder to a GitHub repository and create a Railway project from it.
2. Add a Railway **Volume**, mount it at `/data`, and keep
   `DATABASE_URL=sqlite:////data/prices.db`. Without the volume, price history
   can disappear on redeploy.
3. Add all variables from `.env.example`; replace the two Telegram values.
4. Deploy. The included Dockerfile installs Chromium and starts the worker.

Railway may charge for continuous execution and browser memory. The worker is
not affiliated with the flight sites; comply with their terms and robots rules.
