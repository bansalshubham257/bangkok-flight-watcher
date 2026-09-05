import asyncio
import logging

from playwright.async_api import async_playwright

from .config import Settings
from .dates import target_dates
from .providers import PROVIDERS
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
        self.browser = await self.playwright.chromium.launch(headless=self.settings.headless)

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
                await asyncio.to_thread(self._process, departure.isoformat(), fare.amount, fare.source, fare.url)
            except Exception as exc:
                LOG.warning("%s failed for %s: %s", provider.name, departure, exc)

    def _process(self, departure: str, price: int, source: str, url: str) -> None:
        previous = self.store.get_price(departure)
        if previous is None:
            self.store.save_price(departure, price, price, source)
            if self.settings.alert_on_first_seen:
                self.telegram.send(
                    f"✈️ Initial fare: BLR → Bangkok\n{departure}: ₹{price:,}\nSource: {source}\n{url}"
                )
            return

        drop = previous.alert_anchor - price
        anchor = previous.alert_anchor
        if drop >= self.settings.drop_rupees:
            self.telegram.send(
                f"🔻 Flight price dropped ₹{drop:,}\nBLR → Bangkok on {departure}\n"
                f"Was ₹{previous.alert_anchor:,}, now ₹{price:,}\nSource: {source}\n{url}"
            )
            anchor = price
        self.store.save_price(departure, price, anchor, source)
