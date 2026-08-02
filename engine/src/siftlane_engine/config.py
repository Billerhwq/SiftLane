from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
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
    auth_mode: Literal["local", "team"] = "local"
    api_token: str = ""
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: SecretStr = SecretStr("")
    secret_key: SecretStr = SecretStr("")
    session_ttl_minutes: int = Field(default=480, ge=5, le=43_200)
    login_window_seconds: int = Field(default=300, ge=30, le=3600)
    login_max_attempts: int = Field(default=5, ge=1, le=100)
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
    connector_timeout_seconds: float = Field(default=30.0, ge=1, le=300)
    delivery_timeout_seconds: float = Field(default=15.0, ge=1, le=120)
    delivery_poll_seconds: float = Field(default=1.0, ge=0.05, le=60)
    max_delivery_bytes: int = Field(default=8 * 1024 * 1024, ge=1024)
    readiness_max_queue_size: int = Field(default=10_000, ge=1, le=1_000_000)
    allow_private_networks: bool = False
    respect_robots_txt: bool = True
    user_agent: str = "SiftlaneEngine/0.1 (+controlled collection)"

    @model_validator(mode="after")
    def validate_auth_boundary(self) -> "Settings":
        local_addresses = {"127.0.0.1", "localhost", "::1"}
        if (
            self.bind_address not in local_addresses
            and self.auth_mode == "local"
            and not self.api_token
        ):
            raise ValueError(
                "a non-loopback bind requires team auth or a non-empty API token"
            )
        bootstrap_password = self.bootstrap_admin_password.get_secret_value()
        if bootstrap_password and len(bootstrap_password) < 12:
            raise ValueError("bootstrap admin password must contain at least 12 characters")
        secret_key = self.secret_key.get_secret_value()
        if self.auth_mode == "team" and len(secret_key) < 32:
            raise ValueError("team auth requires an engine secret key of at least 32 characters")
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir.expanduser().resolve() / "crawler.db"

    @property
    def connector_inbox_path(self) -> Path:
        return self.data_dir.expanduser().resolve() / "connector-inbox"

    @property
    def connector_packages_path(self) -> Path:
        return self.data_dir.expanduser().resolve() / "connectors"

    @property
    def export_path(self) -> Path:
        return self.data_dir.expanduser().resolve() / "exports"
