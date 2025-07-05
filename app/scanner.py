import logging
import asyncio
import time
from . import config
from .state import state
_logger = logging.getLogger(__name__)

def start():
    _logger.info("Starting scanner...")
    # threading.Thread(target=_start, daemon=True).start()
    asyncio.create_task(_start())
    _logger.info("Scanner started.")

async def _start():
    delay = config.update_delay.total_seconds()

    while True:
        now = time.time()
        next_run = state.next_run

        if next_run is None or next_run <= now:
            _logger.info("Scheduled time reached or not set. Running scan.")
            await _run_scan(delay)
            continue

        timeout = max(0, next_run - now)
        try:
            cmd = await asyncio.wait_for(state.scanner_message_queue.get(), timeout=timeout)
            if cmd == "scan_now":
                _logger.info("Immediate scan requested.")
                await _run_scan(delay)
        except asyncio.TimeoutError:
            _logger.info("Scheduled scan triggered by timeout.")
            await _run_scan(delay)


async def _run_scan(delay):
    try:
        _logger.info("Running scan...")
        _logger.info("Scan complete.")
    except Exception as e:
        _logger.exception(f"Scan failed. {type(e).__name__}: {e}")
    finally:
        state.next_run = time.time() + delay
