from dataclasses import dataclass
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class PriceState:
    last_price: int
    alert_anchor: int


class Store:
    """Small SQLite store. Mount a Railway Volume at /data for persistence."""

    def __init__(self, database_url: str):
        if not database_url.startswith("sqlite:///"):
            raise ValueError("This build expects DATABASE_URL=sqlite:////data/prices.db")
        self.path = Path(database_url.removeprefix("sqlite:///"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS prices (
                departure TEXT PRIMARY KEY,
                last_price INTEGER NOT NULL,
                alert_anchor INTEGER NOT NULL,
                source TEXT NOT NULL,
                checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
        """)

    def get_price(self, departure: str) -> PriceState | None:
        row = self.connection.execute(
            "SELECT last_price, alert_anchor FROM prices WHERE departure=?", (departure,)
        ).fetchone()
        return PriceState(*row) if row else None

    def save_price(self, departure: str, price: int, anchor: int, source: str) -> None:
        self.connection.execute("""
            INSERT INTO prices(departure,last_price,alert_anchor,source)
            VALUES(?,?,?,?)
            ON CONFLICT(departure) DO UPDATE SET
              last_price=excluded.last_price, alert_anchor=excluded.alert_anchor,
              source=excluded.source, checked_at=CURRENT_TIMESTAMP
        """, (departure, price, anchor, source))
        self.connection.commit()

    def all_prices(self) -> list[tuple[str, int, str]]:
        return self.connection.execute(
            "SELECT departure, last_price, source FROM prices ORDER BY departure"
        ).fetchall()

    def next_index(self, key: str, size: int, advance: int = 1) -> int:
        row = self.connection.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        current = (row[0] if row else 0) % size
        nxt = (current + advance) % size
        self.connection.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, nxt),
        )
        self.connection.commit()
        return current

    def close(self) -> None:
        self.connection.close()
