import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    base_url: str = "https://restful-booker.herokuapp.com"
    username: str = field(default="admin", repr=False)
    password: str = field(default="password123", repr=False)
    timeout_seconds: float = 15.0
    read_attempts: int = 3
    retry_backoff_seconds: float = 0.25

    def __post_init__(self):
        if self.timeout_seconds <= 0 or self.read_attempts < 1 or self.retry_backoff_seconds < 0:
            raise ValueError("Timeout and attempts must be positive; backoff must be nonnegative")

    @classmethod
    def from_env(cls):
        return cls(
            base_url=os.getenv("BOOKER_BASE_URL", cls.base_url).rstrip("/"),
            username=os.getenv("BOOKER_USERNAME", "admin"),
            password=os.getenv("BOOKER_PASSWORD", "password123"),
            timeout_seconds=float(os.getenv("BOOKER_TIMEOUT_SECONDS", "15")),
            read_attempts=int(os.getenv("BOOKER_READ_ATTEMPTS", "3")),
            retry_backoff_seconds=float(os.getenv("BOOKER_RETRY_BACKOFF_SECONDS", "0.25")),
        )
