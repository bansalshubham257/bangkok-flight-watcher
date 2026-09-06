from datetime import date

from flight_watcher.dates import target_dates
from flight_watcher.providers import (
    extract_lowest_inr,
    extract_openjaw_inr,
    extract_paytm_verified_inr,
    extract_verified_inr,
)
from flight_watcher.runner import build_roundtrip_message
from flight_watcher.weekends import RoundTrip, october_weekends, roundtrip_matrix
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


def test_october_weekends_are_sat_sun_pairs():
    pairs = october_weekends()
    assert [(s.day, r.day) for s, r in pairs] == [(3, 4), (10, 11), (17, 18), (24, 25), (31, 1)]
    assert pairs[-1][1].month == 11


def test_roundtrip_matrix_covers_both_directions_and_buffers():
    combos = roundtrip_matrix()
    assert len(combos) == 50
    first = combos[:5]
    assert [(c.out_city, c.in_city, c.label) for c in first] == [
        ("HKT", "BKK", "base"), ("HKT", "BKK", "fri-out"), ("HKT", "BKK", "thu-out"),
        ("HKT", "BKK", "mon-back"), ("HKT", "BKK", "tue-back"),
    ]
    assert combos[5].out_city == "BKK" and combos[5].in_city == "HKT"
    assert len({c.key for c in combos}) == 50


def test_openjaw_parser_accepts_direct_pair_in_any_order():
    card = ("12:45 – 14:40\nHKTPhuket\n-\nBLRBengaluru Intl\ndirect\n3h 25m\n"
            "06:30 – 11:45\nBLRBengaluru Intl\n-\nHKTPhuket\ndirect\n3h 45m\n"
            "IndiGo\n₹\xa031,742\nSale\nSelect")
    assert extract_openjaw_inr(card, "HKT", "BKK") is None  # same-city RT, wrong pair
    assert extract_openjaw_inr(card, "HKT", "HKT") == 31_742


def test_openjaw_parser_rejects_stops_and_wrong_cities():
    card = ("08:05 – 10:15\nBKKSuvarnabhumi\n-\nBLRBengaluru Intl\ndirect\n3h 40m\n"
            "09:55 – 15:35\nBLRBengaluru Intl\n-\nHKTPhuket\ndirect\n4h 10m\n"
            "IndiGo, Air India\n₹\xa033,297\nSale\nSelect")
    assert extract_openjaw_inr(card, "HKT", "BKK") == 33_297
    stopped = card.replace("HKTPhuket\ndirect\n4h 10m",
                           "HKTPhuket\n1 stop\nBOM\n4h 10m")
    assert extract_openjaw_inr(stopped, "HKT", "BKK") is None


def test_roundtrip_message_shows_buffers_and_cheaper_direction():
    known = {
        RoundTrip(date(2026, 10, 3), date(2026, 10, 4), "HKT", "BKK", "base").key: 33_297,
        RoundTrip(date(2026, 10, 3), date(2026, 10, 4), "BKK", "HKT", "base").key: 31_742,
        RoundTrip(date(2026, 10, 3), date(2026, 10, 4), "HKT", "BKK", "fri-out").key: 30_000,
    }
    message = build_roundtrip_message(known)
    assert "Out HKT / Back BKK: ₹33,297" in message
    assert "Fri out ₹30,000 (−₹3,297)" in message
    assert "Cheaper: B by ₹1,555" in message
