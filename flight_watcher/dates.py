import calendar
from datetime import date


def target_dates(year: int, month: int) -> list[date]:
    """All Thursday (3), Friday (4), and Saturday (5) dates in a month."""
    last_day = calendar.monthrange(year, month)[1]
    return [
        date(year, month, day)
        for day in range(1, last_day + 1)
        if date(year, month, day).weekday() in (3, 4, 5)
    ]
