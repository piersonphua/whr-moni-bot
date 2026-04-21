from __future__ import annotations

import asyncio
import logging

from expense_bot.config import Settings
from expense_bot.runtime import run_polling_forever


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    logging.getLogger(__name__).info("Booting Traxpense bot")
    asyncio.run(run_polling_forever(settings))


if __name__ == "__main__":
    main()
