from datetime import date

from flight_watcher.dates import target_dates
from flight_watcher.providers import (
    extract_lowest_inr,
    extract_paytm_verified_inr,
    extract_verified_inr,
)
from flight_watcher.store import Store


def test_october_2026_dates():
    assert target_dates(2026, 10) == [
        date(2026, 10, d) for d in (1, 2, 3, 8, 9, 10, 15, 16, 17, 22, 23, 24, 29, 30, 31)
    ]


def test_price_parser():
    assert extract_lowest_inr("from ₹12,499 other INR 10,250 and ₹999") == 10_250


def test_verified_price_requires_nonstop_and_checked_bag_on_same_card():
    assert extract_verified_inr("IndiGo Non-stop · 1 checked bag · ₹14,999") == 14_999
    assert extract_verified_inr("IndiGo Non-stop · cabin bag only · ₹12,847") is None
    assert extract_verified_inr("One stop · 1 checked bag · ₹11,500") is None
    assert extract_verified_inr(
        "IndiGo Non-stop · ₹28,070", require_checked_bag=False
    ) == 28_070
    assert extract_verified_inr(
        "Thai AirAsia Non Stop · No Check-in Baggage · ₹15,932",
        require_checked_bag=False,
    ) is None


def test_paytm_rendered_text_rejects_no_baggage_card():
    text = """Thu, 15 Oct
₹16,490
Thai AirAsia
11:20 PM
3h 50m
Non Stop
No Check-in Baggage
₹15,932
Thai Airways
12:55 AM
3h 55m
Non Stop
₹28,166
"""
    assert extract_paytm_verified_inr(text) == 28_166


def test_summary_only_changes_for_date_or_price(tmp_path):
    store = Store(f"sqlite:///{tmp_path / 'prices.db'}")
    assert store.summary_changed("top_three", [("2026-10-01", 14_000)])
    assert not store.summary_changed("top_three", [("2026-10-01", 14_000)])
    assert store.summary_changed("top_three", [("2026-10-01", 13_999)])
    assert store.summary_changed("top_three", [("2026-10-02", 13_999)])
    store.close()
