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
    require_checked_bag = False

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
            await self.dismiss_overlays(page)
            amount = await self.extract_verified_card_price(page)
            if amount is None:
                raise RuntimeError(f"No qualifying non-stop flight card found on {self.name}")
            return Fare(amount=amount, source=self.name, url=page.url)
        finally:
            await page.close()

    async def dismiss_overlays(self, page: Page) -> None:
        """Hook for provider-specific popups. Never raises."""
        return None

    async def extract_verified_card_price(self, page: Page) -> int | None:
        prices: list[int] = []
        for selector in self.card_selectors:
            cards = page.locator(selector)
            for index in range(await cards.count()):
                text = await cards.nth(index).inner_text(timeout=5_000)
                amount = extract_verified_inr(text, require_checked_bag=self.require_checked_bag)
                if amount is not None:
                    prices.append(amount)
        if prices:
            return min(prices)
        # CSS class names on travel sites are frequently generated. Fall back
        # to rendered text segmented by fare lines, never to a page-wide min.
        body = await page.locator("body").inner_text(timeout=15_000)
        return extract_paytm_verified_inr(body)


class Paytm(Provider):
    name = "Paytm"
    card_selectors = ("[class*='FlightCard']", "[class*='flightCard']", "[class*='flight_list']")
    require_checked_bag = False
    debugged_page = False

    def url(self, origin: str, destination: str, departure: date) -> str:
        return ("https://tickets.paytm.com/flights/flightSearch/"
                f"{origin}-Bengaluru/{destination}-Bangkok/4/1/0/E/"
                f"{departure.isoformat()}?referer=search")

    async def dismiss_overlays(self, page: Page) -> None:
        # Paytm intermittently shows a "Time display options" modal
        # (12-hour vs 24-hour + "Save Preference") that covers results.
        # Prefer the affirmative action, fall back to close/Escape.
        candidates = (
            # Exact affirmative button from the modal.
            "button:has-text('Save Preference')",
            # Generic dialog close controls (cross button).
            "[aria-label='Close']",
            "button:has-text('×')",
            "button:has-text('✕')",
            "[class*='close' i][role='button']",
        )
        try:
            body = await page.locator("body").inner_text(timeout=5_000)
            if "time display options" not in body.lower() and "save preference" not in body.lower():
                return None
            LOG.info("Paytm time-format popup detected; dismissing")
        except Exception:
            pass
        for selector in candidates:
            try:
                locator = page.locator(selector).first
                await locator.wait_for(state="visible", timeout=3_000)
                await locator.click(timeout=3_000)
                LOG.info("Paytm popup dismissed via %s", selector)
                await page.wait_for_timeout(2_000)
                return None
            except Exception:
                continue
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(1_500)
        except Exception:
            pass
        return None

    async def extract_verified_card_price(self, page: Page) -> int | None:
        # Paytm frequently changes/minifies card class names. Its rendered text
        # remains structured: each card's price follows its stops and baggage
        # lines. Associate each price only with a tight preceding line window.
        text = await page.locator("body").inner_text(timeout=15_000)
        amount = extract_paytm_verified_inr(text)
        if amount is None and not self.debugged_page:
            self.debugged_page = True
            LOG.info(
                "Paytm diagnostic url=%s title=%s body=%r",
                page.url,
                await page.title(),
                text[:2_000],
            )
        return amount


class MakeMyTrip(Provider):
    name = "MakeMyTrip"
    card_selectors = (".listingCard", ".clusterContent", "[class*='listingCard']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        stamp = departure.strftime("%d%%2F%m%%2F%Y")
        return ("https://www.makemytrip.com/flight/search?"
                f"itinerary={origin}-{destination}-{stamp}&tripType=O&cabinClass=E&"
                "paxType=A-4_C-1_I-0&intl=true&msv=2&"
                "msExperiments=showFare%3Atrue&lang=eng&ssr=false")


class Goibibo(Provider):
    name = "Goibibo"
    card_selectors = ("[data-testid='flight-card']", "[class*='FlightCard']", "[class*='CardWrap']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        stamp = departure.strftime("%d%%2F%m%%2F%Y")
        return ("https://www.goibibo.com/flight/search?"
                f"itinerary={origin}-{destination}-{stamp}&tripType=O&cabinClass=E&"
                "paxType=A-4_C-1_I-0&intl=true&msv=2&"
                "msExperiments=showFare%3Atrue&lang=eng&ssr=false")


class Skyscanner(Provider):
    name = "Skyscanner"
    card_selectors = ("[data-testid='itinerary-card']", "[class*='FlightsTicket']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        stamp = departure.strftime("%y%m%d")
        return (f"https://www.skyscanner.co.in/transport/flights/{origin.lower()}/"
                f"bkkt/{stamp}/?adultsv2=4&cabinclass=economy&childrenv2=3&"
                "ref=home&rtn=0&preferdirects=true&outboundaltsenabled=false&"
                "inboundaltsenabled=false&currency=INR")


class Agoda(Provider):
    name = "Agoda"
    card_selectors = ("[data-component='flight-card']", "[data-testid='flight-card']", "[class*='FlightCard']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        return ("https://www.agoda.com/flights/results?"
                f"departureFrom={origin}&departureFromType=1&arrivalTo={destination}&"
                f"arrivalToType=0&departDate={departure.isoformat()}&searchType=1&"
                "cabinType=Economy&adults=4&children=1&sort=8")


class BookingCom(Provider):
    name = "Booking.com"
    card_selectors = ("[data-testid='flight-card']", "[data-testid='searchresults_card']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        return ("https://www.booking.com/flights/index.en-gb.html?type=ONEWAY&cabinClass=ECONOMY&"
                f"adults=4&children=3&from={origin}.AIRPORT&to={destination}.AIRPORT&"
                f"depart={departure.isoformat()}&currency=INR")


class Yatra(Provider):
    name = "Yatra"
    card_selectors = ("[class*='flight-card']", "[class*='flightItem']", "[class*='result-set']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        stamp = departure.strftime("%d/%m/%Y")
        return ("https://flight.yatra.com/air-search-ui/pwaint_flight/trigger?flex=0&"
                "viewName=normal&source=fresco-flights&type=O&class=Economy&"
                "ADT=4&CHD=1&INF=0&noOfSegments=1&"
                f"origin={origin}&originCountry=IN&destination={destination}&"
                f"destinationCountry=TH&flight_depart_date={stamp}&arrivalDate=")


class Ixigo(Provider):
    name = "Ixigo"
    card_selectors = ("[data-testid='flight-card']", "[class*='flight-card']", "[class*='FlightCard']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        stamp = departure.strftime("%d%m%Y")
        return ("https://www.ixigo.com/search/result/flight?"
                f"from={origin}&to={destination}&date={stamp}&adults=4&children=1&"
                "infants=0&class=e&source=Search+Form&stops=0")


class Cheapflights(Provider):
    name = "Cheapflights"
    card_selectors = ("div.nrc6", "div.nrc6-inner", "[class*='FlightCard']")

    def url(self, origin: str, destination: str, departure: date) -> str:
        return (f"https://www.in.cheapflights.com/flight-search/{origin}-{destination}/"
                f"{departure.isoformat()}/4adults/children-3?sort=bestflight_a&fs=stops%3D0")


class EaseMyTrip(Provider):
    name = "EaseMyTrip"
    card_selectors = (
        "[class*='flight-list']", "[class*='flightCard']", "[class*='fltResult']",
    )

    def url(self, origin: str, destination: str, departure: date) -> str:
        stamp = departure.strftime("%d%%2F%m%%2F%Y")
        # EaseMyTrip's supplied Bangkok search uses Don Mueang (DMK).
        return ("https://www.easemytrip.com/flight-search/listing?"
                f"org={origin}-Bangaluru,%20India&dept=DMK-Bangkok,%20Thailand&"
                "adt=1&chd=0&inf=0&cabin=0&airline=Any&"
                f"deptDT={stamp}&arrDT=undefined&isOneway=true&isDomestic=false&"
                "CCODE=IN&curr=INR&apptype=B2C")

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
            "cabin bag only",
            "hand baggage only",
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


def extract_paytm_verified_inr(text: str) -> int | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    prices: list[int] = []
    previous_price_index = -1
    for index, line in enumerate(lines):
        amount = extract_lowest_inr(line)
        if amount is None:
            continue
        # Paytm renders each fare at the end of its card. Starting after the
        # previous rupee line keeps baggage text from one card out of the next.
        context = " ".join(lines[previous_price_index + 1: index + 1])
        verified = extract_verified_inr(context, require_checked_bag=False)
        if verified is not None:
            prices.append(amount)
        previous_price_index = index
    return min(prices) if prices else None


ALL_PROVIDERS = [
    Paytm(), MakeMyTrip(), Skyscanner(), Goibibo(), Agoda(), BookingCom(),
    Yatra(), Ixigo(), Cheapflights(), EaseMyTrip(),
]

# Only sources that have produced comparable per-passenger prices on Railway
# belong in the alert rotation. Other providers remain available to diagnostics.
PROVIDERS = [Cheapflights(), Paytm()]
