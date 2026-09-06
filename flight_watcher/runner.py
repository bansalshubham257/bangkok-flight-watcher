import logging

from playwright.async_api import async_playwright

from .config import Settings
from .dates import target_dates
from .providers import ALL_PROVIDERS, Cheapflights
from .store import Store
from .telegram import Telegram
from .weekends import RoundTrip, october_weekends, roundtrip_matrix

LOG = logging.getLogger(__name__)

BUFFER_LABELS = (
    ("fri-out", "Fri out"),
    ("thu-out", "Thu out"),
    ("mon-back", "Mon back"),
    ("tue-back", "Tue back"),
)


def build_roundtrip_message(known: dict[str, int]) -> str:
    """Single Telegram summary: every October weekend, both open-jaw
    directions, and one-side buffer alternatives with savings vs base."""
    lines = ["🔁 BLR ⇄ Phuket/Bangkok · RT per person (1 adult, direct both legs)"]
    for saturday, sunday in october_weekends():
        lines.append(f"\n📅 {saturday:%a %d %b} → {sunday:%a %d %b}")
        bases: dict[str, int] = {}
        for out_city, in_city, tag in (("HKT", "BKK", "A"), ("BKK", "HKT", "B")):
            base = known.get(
                RoundTrip(saturday, sunday, out_city, in_city, "base").key
            )
            if base is not None:
                bases[tag] = base
            buffers = []
            for label, short in BUFFER_LABELS:
                price = known.get(
                    RoundTrip(saturday, sunday, out_city, in_city, label).key
                )
                if price is None:
                    buffers.append(f"{short} …")
                elif base is None:
                    buffers.append(f"{short} ₹{price:,}")
                else:
                    diff = base - price
                    if diff > 0:
                        buffers.append(f"{short} ₹{price:,} (−₹{diff:,})")
                    elif diff < 0:
                        buffers.append(f"{short} ₹{price:,} (+₹{-diff:,})")
                    else:
                        buffers.append(f"{short} ₹{price:,} (=)")
            base_text = f"₹{base:,}" if base is not None else "checking…"
            lines.append(f"  {tag} Out {out_city} / Back {in_city}: {base_text}")
            lines.append(f"    buffers: {' · '.join(buffers)}")
        if len(bases) == 2:
            if bases["A"] < bases["B"]:
                lines.append(f"  ✅ Cheaper: A by ₹{bases['B'] - bases['A']:,}")
            elif bases["B"] < bases["A"]:
                lines.append(f"  ✅ Cheaper: B by ₹{bases['A'] - bases['B']:,}")
            else:
                lines.append("  ✅ A and B cost the same")
    lines.append("\nPrices refresh round-robin; verify final price before booking.")
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

        self.telegram.send(build_roundtrip_message(self.store.all_roundtrips()))

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
