import logging
from datetime import date

from playwright.async_api import async_playwright

from .config import Settings
from .dates import target_dates
from .providers import ALL_PROVIDERS, PROVIDERS
from .store import Store
from .telegram import Telegram

LOG = logging.getLogger(__name__)


class FlightWatcher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = Store(settings.database_url)
        self.telegram = Telegram(settings.telegram_bot_token, settings.telegram_chat_id)
        self.playwright = None
        self.browser = None

    async def start(self) -> None:
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.settings.headless,
            args=["--disable-http2"],
        )

    async def close(self) -> None:
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.store.close()

    async def run_once(self) -> None:
        dates = target_dates(self.settings.year, self.settings.month)
        provider = PROVIDERS[self.store.next_index("provider", len(PROVIDERS))]
        start = self.store.next_index("date", len(dates), self.settings.dates_per_run)
        selected = [dates[(start + i) % len(dates)] for i in range(min(self.settings.dates_per_run, len(dates)))]
        LOG.info("Scanning %s with %s", ", ".join(map(str, selected)), provider.name)

        for departure in selected:
            try:
                fare = await provider.search(
                    self.browser, self.settings.origin, self.settings.destination, departure
                )
                self._process(departure.isoformat(), fare.amount, fare.source, fare.url)
            except Exception as exc:
                LOG.warning("%s failed for %s: %s", provider.name, departure, exc)
                error = str(exc)
                if "ERR_HTTP2_PROTOCOL_ERROR" in error or "Page.goto: Timeout" in error:
                    LOG.warning("%s is blocked at network level; skipping remaining dates", provider.name)
                    break

        self._send_top_three_summary()

    async def diagnose_all_providers(self) -> None:
        departure = (
            date.fromisoformat(self.settings.diagnostic_date)
            if self.settings.diagnostic_date
            else target_dates(self.settings.year, self.settings.month)[0]
        )
        requested = {
            name.strip().lower()
            for name in self.settings.diagnostic_provider.split(",")
            if name.strip()
        }
        providers = [
            provider for provider in ALL_PROVIDERS
            if not requested or provider.name.lower() in requested
        ]
        LOG.info("DIAGNOSTIC_START date=%s providers=%s", departure, len(providers))
        for provider in providers:
            try:
                fare = await provider.search(
                    self.browser, self.settings.origin, self.settings.destination, departure
                )
                LOG.info(
                    "DIAGNOSTIC_OK provider=%s price=%s url=%s",
                    provider.name, fare.amount, fare.url,
                )
            except Exception as exc:
                LOG.warning("DIAGNOSTIC_FAIL provider=%s reason=%s", provider.name, exc)
        LOG.info("DIAGNOSTIC_DONE")

    def _process(self, departure: str, price: int, source: str, url: str) -> None:
        parsed_date = date.fromisoformat(departure)
        display_date = f"{parsed_date:%A}, {parsed_date.day} {parsed_date:%B %Y}"
        previous = self.store.get_price(departure)
        if previous is None:
            self.store.save_price(departure, price, price, source)
            if price < self.settings.price_threshold:
                self.telegram.send(
                    f"🔥 Non-stop fare below ₹{self.settings.price_threshold:,}\n"
                    f"BLR → Bangkok on {display_date}\n"
                    f"Current price: ₹{price:,}\nSource: {source}\n{url}"
                    "\nChecked bag requested—verify allowance before booking."
                )
            elif self.settings.alert_on_first_seen:
                self.telegram.send(
                    f"✈️ Initial fare: BLR → Bangkok\n{display_date}: ₹{price:,}\nSource: {source}\n{url}"
                )
            return

        if price < self.settings.price_threshold <= previous.last_price:
            self.telegram.send(
                f"🔥 Non-stop fare crossed below ₹{self.settings.price_threshold:,}\n"
                f"BLR → Bangkok on {display_date}\n"
                f"Current price: ₹{price:,}\nSource: {source}\n{url}"
                "\nChecked bag requested—verify allowance before booking."
            )

        drop = previous.alert_anchor - price
        anchor = previous.alert_anchor
        if drop >= self.settings.drop_rupees:
            self.telegram.send(
                f"🔻 Flight price dropped ₹{drop:,}\nBLR → Bangkok on {display_date}\n"
                f"Was ₹{previous.alert_anchor:,}, now ₹{price:,}\nSource: {source}\n{url}"
                "\nNon-stop + checked bag requested; verify before booking."
            )
            anchor = price
        self.store.save_price(departure, price, anchor, source)

    def _send_top_three_summary(self) -> None:
        prices = self.store.all_prices()
        if not prices:
            return
        cheapest = sorted(prices, key=lambda row: row[1])[:3]
        signature = [(departure, price) for departure, price, _source in cheapest]
        if not self.store.summary_changed("top_three", signature):
            LOG.info("Top 3 dates and prices unchanged; Telegram summary skipped")
            return
        lines = ["🏆 Top 3 non-stop BLR → Bangkok fares (1 checked bag requested)"]
        for rank, (departure, price, source) in enumerate(cheapest, start=1):
            parsed = date.fromisoformat(departure)
            lines.append(
                f"{rank}. {parsed:%A}, {parsed.day} {parsed:%B %Y}: ₹{price:,} ({source})"
            )
        self.telegram.send("\n".join(lines))
