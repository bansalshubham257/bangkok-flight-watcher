from dataclasses import dataclass
from datetime import date
import os


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    database_url: str
    year: int = 2026
    month: int = 10
    origin: str = "BLR"
    destination: str = "BKK"
    drop_rupees: int = 500
    price_threshold: int = 15_000
    summary_drop_rupees: int = 1_500
    min_delay_seconds: int = 300
    max_delay_seconds: int = 360
    dates_per_run: int = 3
    headless: bool = True
    alert_on_first_seen: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        def flag(name: str, default: bool) -> bool:
            return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}

        settings = cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            database_url=os.getenv("DATABASE_URL", "sqlite:///prices.db"),
            year=int(os.getenv("SEARCH_YEAR", "2026")),
            month=int(os.getenv("SEARCH_MONTH", "10")),
            drop_rupees=int(os.getenv("DROP_RUPEES", "500")),
            price_threshold=int(os.getenv("PRICE_THRESHOLD", "15000")),
            summary_drop_rupees=int(os.getenv("SUMMARY_DROP_RUPEES", "1500")),
            min_delay_seconds=int(os.getenv("MIN_DELAY_SECONDS", "300")),
            max_delay_seconds=int(os.getenv("MAX_DELAY_SECONDS", "360")),
            dates_per_run=int(os.getenv("DATES_PER_RUN", "3")),
            headless=flag("HEADLESS", True),
            alert_on_first_seen=flag("ALERT_ON_FIRST_SEEN", True),
        )
        if settings.min_delay_seconds > settings.max_delay_seconds:
            raise ValueError("MIN_DELAY_SECONDS cannot exceed MAX_DELAY_SECONDS")
        if date.today() > date(settings.year, settings.month, 31 if settings.month == 10 else 28):
            raise ValueError("Configured search month is in the past")
        return settings
