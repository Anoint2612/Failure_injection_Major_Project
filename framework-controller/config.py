import os


class Settings:
    """Centralized configuration loaded from environment variables with sensible defaults."""

    PROMETHEUS_URL: str = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    HEALTH_PATH: str = os.getenv("HEALTH_PATH", "/health")
    HEALTH_TIMEOUT: float = float(os.getenv("HEALTH_TIMEOUT", "15.0"))
    EXPERIMENT_TIMEOUT: float = float(os.getenv("EXPERIMENT_TIMEOUT", "10.0"))


settings = Settings()
