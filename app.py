import asyncio
import logging
import os
import random
import signal
import time

from flight_watcher.config import Settings
from flight_watcher.runner import FlightWatcher


async def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    watcher = FlightWatcher(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await watcher.start()
    try:
        if settings.diagnostic_all_providers:
            await watcher.diagnose_all_providers()
            return
        while not stop.is_set():
            cycle_started = time.monotonic()
            try:
                await watcher.run_once()
            except Exception:
                logging.getLogger(__name__).exception("Scan failed; next run will retry")
            interval = random.randint(settings.min_delay_seconds, settings.max_delay_seconds)
            delay = max(1, int(interval - (time.monotonic() - cycle_started)))
            logging.info("Next scan in %s seconds", delay)
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
    finally:
        await watcher.close()


if __name__ == "__main__":
    asyncio.run(main())
