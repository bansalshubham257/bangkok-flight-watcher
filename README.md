# Bangkok Flight Watcher

Playwright worker for Railway. It watches open-jaw round-trip fares from
Bangalore (`BLR`) to Phuket (`HKT`) and Bangkok (`BKK`) for every October 2026
weekend (Saturday out, Sunday back, 1 adult, direct flights only) and sends a
single Telegram summary every 5 minutes with per-person prices.
Two directions are compared: out via Phuket back via Bangkok, and out via
Bangkok back via Phuket. One-side buffer alternatives (outbound Friday or
Thursday, return Monday or Tuesday) show how much cheaper each option is
versus the Saturday/Sunday base.

For safety, a price is accepted only from an individual flight-result card that
shows non-stop/direct travel. Missing baggage text is treated as included; a
card explicitly labelled "No Check-in Baggage", "No Checked Baggage", or an
equivalent warning is always rejected. Page-wide prices are ignored.
Paytm uses the supplied direct-search route for 4 adults and 1 child so the
returned availability reflects the full travelling party.
The other source URLs request the same party (child age 3 where supported).
Yatra uses its international PWA search route; advertising and user-tracking
parameters are intentionally excluded.
MakeMyTrip uses its international search mode with client-side rendering.
Goibibo uses the equivalent international `/flight/search` route; advertising
campaign and device-memory parameters are excluded.

## How it behaves

- Starts a full scan every 5 minutes (8 round trips per run, round-robin).
- Production alerts use Cheapflights open-jaw search with the direct-only
  filter (`fs=stops=0`). A card counts only when leg 1 is BLR → outbound city
  direct and leg 2 is inbound city → BLR direct. Paytm and Yatra remain
  available for diagnostics.
  Other configured sources remain
  available for diagnostics. Amazon and Flipkart are not used.
  safely.
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
