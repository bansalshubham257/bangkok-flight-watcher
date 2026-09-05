from datetime import date

from flight_watcher.dates import target_dates
from flight_watcher.providers import extract_lowest_inr


def test_october_2026_dates():
    assert target_dates(2026, 10) == [
        date(2026, 10, d) for d in (1, 2, 3, 8, 9, 10, 15, 16, 17, 22, 23, 24, 29, 30, 31)
    ]


def test_price_parser():
    assert extract_lowest_inr("from ₹12,499 other INR 10,250 and ₹999") == 10_250
