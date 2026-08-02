import uvicorn

from .api import create_app
from .config import Settings
from .logging_config import LOGGING_CONFIG


def main() -> None:
    settings = Settings()
    uvicorn.run(
        create_app(settings),
        host=settings.bind_address,
        port=settings.port,
        log_level="info",
        log_config=LOGGING_CONFIG,
    )


if __name__ == "__main__":
    main()
