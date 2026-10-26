"""boto3 client construction driven only by configuration (no emulator branches)."""

from __future__ import annotations

from typing import Any, cast

import boto3
from botocore.config import Config

from gpuwatch.core.config import Settings


def aws_client(settings: Settings, service: str) -> Any:
    endpoint = settings.aws_endpoint_url
    config = Config(
        retries={"max_attempts": 3, "mode": "standard"},
        s3={"addressing_style": "path" if settings.s3_force_path_style else "auto"},
        signature_version="s3v4" if service == "s3" else None,
        connect_timeout=3,
        read_timeout=10,
    )
    # boto3's stubs overload client() per literal service name; ours is chosen at runtime.
    return cast(Any, boto3).client(
        service, region_name=settings.aws_region, endpoint_url=endpoint, config=config
    )
