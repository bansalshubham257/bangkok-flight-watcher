from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class RoundTrip:
    """One open-jaw round trip: BLR -> out_city, then in_city -> BLR."""

    out_date: date
    back_date: date
    out_city: str  # HKT or BKK (leg 1: BLR -> out_city)
    in_city: str  # BKK or HKT (leg 2: in_city -> BLR)
    label: str  # base | fri-out | thu-out | mon-back | tue-back

    @property
    def key(self) -> str:
        return (
            f"{self.out_date.isoformat()}/{self.back_date.isoformat()}"
            f"/BLR-{self.out_city}/{self.in_city}-BLR/{self.label}"
        )


def october_weekends(year: int = 2026) -> list[tuple[date, date]]:
    """Saturday-out / Sunday-back pairs covering every October weekend.

    The final Saturday (31 Oct) pairs with Sunday 1 Nov as its return.
    """
    pairs = [
        (date(year, 10, 3), date(year, 10, 4)),
        (date(year, 10, 10), date(year, 10, 11)),
        (date(year, 10, 17), date(year, 10, 18)),
        (date(year, 10, 24), date(year, 10, 25)),
        (date(year, 10, 31), date(year, 11, 1)),
    ]
    assert all(saturday.weekday() == 5 and sunday.weekday() == 6 for saturday, sunday in pairs)
    return pairs


def roundtrip_matrix(year: int = 2026) -> list[RoundTrip]:
    """All 50 combos: 5 weekends x 2 directions x (base + 4 one-side buffers).

    Direction A: out via Phuket (BLR->HKT), back via Bangkok (BKK->BLR).
    Direction B: out via Bangkok (BLR->BKK), back via Phuket (HKT->BLR).
    Buffers move ONE side only: outbound Fri/Thu, or return Mon/Tue.
    """
    combos: list[RoundTrip] = []
    for saturday, sunday in october_weekends(year):
        for out_city, in_city in (("HKT", "BKK"), ("BKK", "HKT")):
            combos.append(RoundTrip(saturday, sunday, out_city, in_city, "base"))
            combos.append(RoundTrip(saturday - timedelta(days=1), sunday, out_city, in_city, "fri-out"))
            combos.append(RoundTrip(saturday - timedelta(days=2), sunday, out_city, in_city, "thu-out"))
            combos.append(RoundTrip(saturday, sunday + timedelta(days=1), out_city, in_city, "mon-back"))
            combos.append(RoundTrip(saturday, sunday + timedelta(days=2), out_city, in_city, "tue-back"))
    return combos
