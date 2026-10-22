import asyncio

from app.core.logging_config import setup_logging
from app.workers.scheduler import scheduler_loop


def main() -> None:
    setup_logging()
    asyncio.run(scheduler_loop())


if __name__ == "__main__":
    main()
