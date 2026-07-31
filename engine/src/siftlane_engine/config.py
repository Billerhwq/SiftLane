from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SIFTLANE_ENGINE_",
        env_file=".env",
        extra="ignore",
    )

    bind_address: str = "127.0.0.1"
    port: int = Field(default=8090, ge=1, le=65535)
    data_dir: Path = Path("./data")
    api_token: str = ""
    allowed_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )
    worker_count: int = Field(default=2, ge=1, le=16)
    scheduler_poll_seconds: float = Field(default=1.0, ge=0.05, le=60)
    scheduler_lease_seconds: float = Field(default=30.0, ge=1, le=600)
    sse_heartbeat_seconds: float = Field(default=10.0, ge=1, le=60)
    request_timeout_seconds: float = Field(default=30.0, ge=1, le=120)
    request_min_delay_seconds: float = Field(default=1.0, ge=0, le=60)
    max_response_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    max_redirects: int = Field(default=5, ge=0, le=10)
    allow_private_networks: bool = False
    respect_robots_txt: bool = True
    user_agent: str = "SiftlaneEngine/0.1 (+controlled collection)"

    @property
    def database_path(self) -> Path:
        return self.data_dir.expanduser().resolve() / "crawler.db"
