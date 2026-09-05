from dataclasses import dataclass
from datetime import date
import logging
import re

from playwright.async_api import Browser, Page

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class Fare:
    amount: int
    source: str
    url: str


class Provider:
    name = "base"
    card_selectors: tuple[str, ...] = ()
    require_checked_bag = True

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
            amount = await self.extract_verified_card_price(page)
            if amount is None:
                raise RuntimeError(
                    f"No flight card explicitly confirmed both non-stop and checked baggage on {self.name}"
                )
            return Fare(amount=amount, source=self.name, url=page.url)
        finally:
            await page.close()

    async def extract_verified_card_price(self, page: Page) -> int | None:
        prices: list[int] = []
        for selector in self.card_selectors:
            cards = page.locator(selector)
            for index in range(await cards.count()):
                text = await cards.nth(index).inner_text(timeout=5_000)
                amount = extract_verified_inr(text, require_checked_bag=self.require_checked_bag)
                if amount is not None:
                    prices.append(amount)
        return min(prices) if prices else None


class Paytm(Provider):
    name = "Paytm"
    card_selectors = ("[class*='FlightCard']", "[class*='flightCard']", "[class*='flight_list']")
    require_checked_bag = False

    def url(self, origin: str, destination: str, departure: date) -> str:
        return (f"https://tickets.paytm.com/flights/flightSearch/{origin}-{destination}/"
                f"1/0/0/E/{departure.isoformat()}")


class MakeMyTrip(Provider):
    name = "MakeMyTrip"
    card_selectors = (".listingCard", ".clusterContent", "[class*='listingCard']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        stamp = departure.strftime("%d/%m/%Y")
        return ("https://www.makemytrip.com/flight/search?tripType=O&cabinClass=E&"
                f"itinerary={origin}-{destination}-{stamp}&paxType=A-1_C-0_I-0")


class Goibibo(Provider):
    name = "Goibibo"
    card_selectors = ("[data-testid='flight-card']", "[class*='FlightCard']", "[class*='CardWrap']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        return (f"https://www.goibibo.com/flights/air-{origin}-{destination}-"
                f"{departure.strftime('%Y%m%d')}--1-0-0-E-D/")


class Skyscanner(Provider):
    name = "Skyscanner"
    card_selectors = ("[data-testid='itinerary-card']", "[class*='FlightsTicket']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        stamp = departure.strftime("%y%m%d")
        return (f"https://www.skyscanner.co.in/transport/flights/{origin.lower()}/"
                f"{destination.lower()}/{stamp}/?adultsv2=1&cabinclass=economy&currency=INR&stops=direct")


class Agoda(Provider):
    name = "Agoda"
    card_selectors = ("[data-component='flight-card']", "[data-testid='flight-card']", "[class*='FlightCard']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        return ("https://www.agoda.com/flights/results?tripType=one-way&adults=1&children=0&"
                f"departureFrom={origin}&arrivalTo={destination}&departDate={departure.isoformat()}")


class BookingCom(Provider):
    name = "Booking.com"
    card_selectors = ("[data-testid='flight-card']", "[data-testid='searchresults_card']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        return ("https://www.booking.com/flights/index.en-gb.html?type=ONEWAY&cabinClass=ECONOMY&"
                f"adults=1&children=&from={origin}.AIRPORT&to={destination}.AIRPORT&"
                f"depart={departure.isoformat()}&currency=INR")


class Yatra(Provider):
    name = "Yatra"
    card_selectors = ("[class*='flight-card']", "[class*='flightItem']", "[class*='result-set']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        stamp = departure.strftime("%d/%m/%Y")
        return ("https://flight.yatra.com/air-search-ui/dom2/trigger?type=O&viewName=normal&"
                f"origin={origin}&destination={destination}&flight_depart_date={stamp}&"
                "adt=1&chd=0&inf=0&class=Economy&source=fresco-home")


class AmazonFlights(Provider):
    name = "Amazon Flights"
    card_selectors = ("[class*='flight-card']", "[class*='FlightCard']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        return ("https://www.amazon.in/flights?tripType=oneway&adults=1&children=0&"
                f"origin={origin}&destination={destination}&departureDate={departure.isoformat()}")


class FlipkartFlights(Provider):
    name = "Flipkart Flights"
    card_selectors = ("[class*='flight-card']", "[class*='FlightCard']", "[data-testid='flight-card']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        return ("https://www.flipkart.com/travel/flights?tripType=oneway&adults=1&children=0&"
                f"from={origin}&to={destination}&departureDate={departure.isoformat()}")


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


def extract_verified_inr(text: str, require_checked_bag: bool = True) -> int | None:
    normalized = " ".join(text.lower().replace("-", " ").split())
    nonstop = any(term in normalized for term in ("non stop", "nonstop", "direct"))
    no_checked_bag = any(
        term in normalized
        for term in (
            "no check in baggage",
            "no checked baggage",
            "checked baggage not included",
            "checked bag not included",
        )
    )
    checked_bag = any(
        term in normalized
        for term in (
            "checked bag included",
            "checked baggage included",
            "1 checked bag",
            "1 check in bag",
            "check in baggage included",
        )
    )
    if not nonstop or no_checked_bag or (require_checked_bag and not checked_bag):
        return None
    return extract_lowest_inr(text)


PROVIDERS = [
    Paytm(), MakeMyTrip(), Skyscanner(), Goibibo(), Agoda(), BookingCom(),
    Yatra(), AmazonFlights(), FlipkartFlights(),
]
