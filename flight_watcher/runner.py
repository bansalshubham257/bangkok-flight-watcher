import logging
from datetime import timedelta

from playwright.async_api import async_playwright

from .config import Settings
from .dates import target_dates
from .providers import ALL_PROVIDERS, Cheapflights
from .store import Store
from .telegram import Telegram
from .weekends import RoundTrip, october_weekends, roundtrip_matrix

LOG = logging.getLogger(__name__)

BUFFER_DELTAS = (
    ("fri-out", -1, "out"),
    ("thu-out", -2, "out"),
    ("mon-back", +1, "back"),
    ("tue-back", +2, "back"),
)


def build_direction_message(
    known: dict[str, int], out_city: str, in_city: str, title: str,
) -> str:
    """One message per direction: every weekend base price plus buffer
    alternatives with the buffered day in brackets and savings vs base."""
    out_name = "Phuket" if out_city == "HKT" else "Bangkok"
    back_name = "Bangkok" if in_city == "BKK" else "Phuket"
    lines = [f"{title} BLR → {out_name}, back via {back_name} · RT per person (1 adult, direct)"]
    for saturday, sunday in october_weekends():
        base = known.get(
            RoundTrip(saturday, sunday, out_city, in_city, "base").key
        )
        base_text = f"₹{base:,}" if base is not None else "checking…"
        lines.append(f"\n📅 {saturday:%a %d %b} → {sunday:%a %d %b}: {base_text}")
        for label, delta, leg in BUFFER_DELTAS:
            if leg == "out":
                combo = RoundTrip(
                    saturday + timedelta(days=delta), sunday,
                    out_city, in_city, label,
                )
                day = combo.out_date
            else:
                combo = RoundTrip(
                    saturday, sunday + timedelta(days=delta),
                    out_city, in_city, label,
                )
                day = combo.back_date
            price = known.get(combo.key)
            if price is None:
                continue
            if base is None:
                lines.append(f"  ↳ ₹{price:,} ({day:%a %d %b} {leg})")
            else:
                diff = base - price
                if diff > 0:
                    lines.append(f"  ↳ ₹{price:,} ({day:%a %d %b} {leg}, −₹{diff:,})")
                elif diff < 0:
                    lines.append(f"  ↳ ₹{price:,} ({day:%a %d %b} {leg}, +₹{-diff:,})")
                else:
                    lines.append(f"  ↳ ₹{price:,} ({day:%a %d %b} {leg}, =)")
    return "\n".join(lines)


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
        combos = roundtrip_matrix()
        provider = Cheapflights()
        batch = max(1, self.settings.roundtrips_per_run)
        start = self.store.next_index("rt", len(combos), batch)
        selected = [combos[(start + i) % len(combos)] for i in range(min(batch, len(combos)))]
        LOG.info("Scanning %d round trips from %s", len(selected), selected[0].key)

        for combo in selected:
            try:
                fare = await provider.search_roundtrip(
                    self.browser, combo.out_city, combo.in_city,
                    combo.out_date, combo.back_date,
                )
                self.store.save_roundtrip(combo.key, fare.amount)
            except Exception as exc:
                LOG.warning("RT failed for %s: %s", combo.key, exc)

        known = self.store.all_roundtrips()
        self.telegram.send(build_direction_message(known, "HKT", "BKK", "1️⃣"))
        self.telegram.send(
            build_direction_message(known, "BKK", "HKT", "2️⃣")
            + "\n\nPrices refresh round-robin; verify final price before booking."
        )

    async def diagnose_all_providers(self) -> None:
        from datetime import date

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
