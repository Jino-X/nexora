"""Standalone automation worker: `python -m app.automations.worker`.

In production run this as its own process (and set RUN_SCHEDULER_IN_API=false on the API). Several
workers can run at once because claims are leased in the database."""

from __future__ import annotations

import asyncio
import contextlib
import signal

from app.automations.scheduler import AutomationScheduler
from app.config import get_settings
from app.core.logging import configure_logging
from app.services import build_services, close_services


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    services = await build_services(settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)
    try:
        await AutomationScheduler(services).run_forever(stop)
    finally:
        await close_services(services)


if __name__ == "__main__":
    asyncio.run(main())
