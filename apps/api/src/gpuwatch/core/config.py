"""Runtime configuration, validated once at boot.

Every setting comes from the environment. Security-relevant settings are checked by
``Settings.guard`` so a misconfigured production deployment refuses to start instead of
running with demo secrets.

Redis is optional: leave ``REDIS_URL`` empty and the live view, rate limits and config
invalidation run in process (correct for one single-process replica; use Redis for
several replicas or WEB_CONCURRENCY above 1).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

INSECURE_SECRETS = {"", "change-me", "replace-with-output-of-make-env", "dev", "secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    environment: Literal["development", "test", "production"] = "development"
    cloud: Literal["local", "floci", "aws"] = Field("local", alias="GPUWATCH_CLOUD")
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://gpuwatch:gpuwatch@localhost:4442/gpuwatch"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    # Empty: no Redis. The live view, rate limits and config invalidation run in process.
    redis_url: str = ""

    session_secret: str = "dev-session-secret-not-for-production"  # noqa: S105 dev default, refused in production by guard()
    api_key_pepper: str = "dev-api-key-pepper-not-for-production"
    session_ttl_hours: int = 12
    cookie_secure: bool = False
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:4410"]
    )

    # Webhook signing secrets are sealed before they reach the database.
    key_mode: Literal["local", "kms"] = "local"
    local_master_key: str = "dev-local-master-key-not-for-production"
    kms_key_id: str = "alias/gpuwatch-local"

    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    s3_force_path_style: bool = False
    # Cost and usage report exports. Rows keep only the object key.
    reports_bucket: str = "gpuwatch-local-reports"
    storage: Literal["local", "s3"] = "local"
    local_storage_dir: str = "./.data/reports"

    # Mail for alert notifications. log: written to the log only (nothing delivered).
    mail_mode: Literal["log", "smtp", "ses"] = "log"
    mail_from: str = "GPUWatch <alerts@gpuwatch.local>"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = False
    # Public URL of the dashboard, used for links in notifications.
    dashboard_url: str = "http://localhost:4410"

    max_body_bytes: int = 8_000_000
    default_rpm_limit: int = 600

    # Ingest. A batch carries one collection interval; agents send every few seconds.
    ingest_rpm_per_host: int = Field(240, ge=10)
    ingest_max_samples: int = Field(20_000, ge=100)
    # Samples further in the future than this are refused (clock skew), older ones than the
    # raw retention are refused (nothing could roll them up). Simulated hosts may backfill.
    ingest_max_future_s: int = 120
    simulated_backfill_days: int = Field(45, ge=1, le=400)

    # Health. A host that has not reported for this long is disconnected (and alerts).
    host_offline_after_s: int = Field(60, ge=15)
    live_ttl_s: int = 300

    # Retention, by resolution.
    raw_retention_days: int = Field(7, ge=1, le=60)
    rollup_1m_retention_days: int = Field(30, ge=1, le=400)
    rollup_1h_retention_days: int = Field(400, ge=30, le=3650)
    report_retention_days: int = 30

    # Worker cadence.
    worker_tick_s: float = Field(5.0, gt=0)
    alert_eval_interval_s: int = Field(15, ge=5)
    insight_eval_interval_s: int = Field(60, ge=15)
    # Late data: the rollup job waits this long after a minute ends before closing it.
    rollup_lag_s: int = Field(90, ge=10)
    # When set, /metrics needs "Authorization: Bearer <token>" (it lists hosts and GPUs).
    metrics_token: str | None = None
    # The worker serves its own /metrics here; 0 turns it off.
    worker_metrics_port: int = Field(9464, ge=0, le=65535)

    # Webhooks to loopback or private networks (an internal chat relay). Metadata and
    # link-local addresses are refused regardless (alerts/urls.py).
    webhook_allow_private: bool = True
    webhook_timeout_s: float = 10.0

    otel_enabled: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def cache_backend(self) -> Literal["redis", "memory"]:
        return "redis" if self.redis_url else "memory"

    def guard(self) -> None:
        """Refuse to boot in production with demo secrets or unsafe options."""
        if self.environment != "production":
            return
        problems: list[str] = []
        for name in ("session_secret", "api_key_pepper"):
            value = getattr(self, name)
            if value in INSECURE_SECRETS or "not-for-production" in value or len(value) < 32:
                problems.append(f"{name.upper()} must be a random value of at least 32 chars")
        if self.key_mode == "local" and (
            "not-for-production" in self.local_master_key or len(self.local_master_key) < 32
        ):
            problems.append("LOCAL_MASTER_KEY must be set (or use KEY_MODE=kms)")
        if self.session_secret == self.api_key_pepper:
            problems.append("SESSION_SECRET and API_KEY_PEPPER must differ")
        if self.cloud == "aws" and self.aws_endpoint_url:
            problems.append("AWS_ENDPOINT_URL must be unset when GPUWATCH_CLOUD=aws")
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true in production")
        if problems:
            raise RuntimeError("unsafe production configuration: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.guard()
    return settings
