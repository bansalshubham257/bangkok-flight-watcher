from dataclasses import dataclass
from datetime import date
import logging
import re
from urllib.parse import quote

from playwright.async_api import Browser, Page

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fare:
    amount: int
    source: str
    url: str


class Provider:
    name = "base"

    def url(self, origin: str, destination: str, departure: date) -> str:
        raise NotImplementedError

    async def search(self, browser: Browser, origin: str, destination: str, departure: date) -> Fare:
        page = await browser.new_page(
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            user_agent=("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
        )
        search_url = self.url(origin, destination, departure)
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(7_000)
            text = await page.locator("body").inner_text(timeout=15_000)
            amount = extract_lowest_inr(text)
            if amount is None:
                raise RuntimeError(f"No plausible INR fare found on {self.name}")
            return Fare(amount=amount, source=self.name, url=page.url)
        finally:
            await page.close()


class GoogleFlights(Provider):
    name = "Google Flights"

    def url(self, origin: str, destination: str, departure: date) -> str:
        query = f"Flights from {origin} to {destination} on {departure.isoformat()} one way"
        return f"https://www.google.com/travel/flights?hl=en&curr=INR&q={quote(query)}"


class Kayak(Provider):
    name = "Kayak"

    def url(self, origin: str, destination: str, departure: date) -> str:
        return f"https://www.kayak.co.in/flights/{origin}-{destination}/{departure.isoformat()}?sort=bestflight_a"


class Skyscanner(Provider):
    name = "Skyscanner"

    def url(self, origin: str, destination: str, departure: date) -> str:
        stamp = departure.strftime("%y%m%d")
        return (f"https://www.skyscanner.co.in/transport/flights/{origin.lower()}/"
                f"{destination.lower()}/{stamp}/?adultsv2=1&cabinclass=economy&currency=INR")


def extract_lowest_inr(text: str) -> int | None:
    # Flight pages usually render prices as ₹12,345 or INR 12,345. Ignore tiny
    # ancillary amounts and implausibly large values.
    patterns = (r"₹\s*([0-9][0-9,]{3,})", r"INR\s*([0-9][0-9,]{3,})")
    values: list[int] = []
    for pattern in patterns:
        for raw in re.findall(pattern, text, flags=re.IGNORECASE):
            value = int(raw.replace(",", ""))
            if 3_000 <= value <= 150_000:
                values.append(value)
    return min(values) if values else None


PROVIDERS = [GoogleFlights(), Kayak(), Skyscanner()]
