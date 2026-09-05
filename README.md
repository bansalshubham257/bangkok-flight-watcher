# Bangkok Flight Watcher

Playwright worker for Railway. It watches one-way economy fares from Bangalore
(`BLR`) to Bangkok (`BKK`) for every Thursday, Friday, and Saturday in October
2026 and sends Telegram alerts when a fare falls below ₹15,000 or drops by
₹500 or more from the last alerted price.
Every 15 minutes, the bot sends the three cheapest latest non-stop fares with
one checked bag requested, including their weekday and date. Fare-site baggage
data can change at checkout, so alerts instruct the user to verify allowance.
An unchanged top-three list is not resent; a message is sent when any displayed
date or price changes.

For safety, a price is accepted only when one flight-result card explicitly
shows both non-stop/direct travel and included checked baggage. Page-wide prices
and unconfirmed baggage fares are ignored.
Paytm is the user-selected exception: when a Paytm card explicitly says
non-stop but omits baggage text, checked baggage is assumed to be included.
Paytm cards labelled "No Check-in Baggage" are always rejected.
Paytm uses the supplied direct-search route for 4 adults and 1 child so the
returned availability reflects the full travelling party.

## How it behaves

- Starts a full scan every 15 minutes.
- Rotates Paytm, MakeMyTrip, Skyscanner, Goibibo, Agoda, Booking.com, Yatra,
  Amazon Flights, and Flipkart Flights. Login-only or unverifiable sources are
  skipped safely.
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
