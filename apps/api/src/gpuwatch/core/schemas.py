"""Shared API schema building blocks."""

from __future__ import annotations

import base64
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
)

from gpuwatch.core.money import nusd_to_usd

# Money is integer nano-dollars internally and USD floats on the wire.
Usd = Annotated[int, PlainSerializer(nusd_to_usd, return_type=float)]


# Self-hosted deployments often use internal domains (corp.local, example.test), which strict
# deliverability validators reject, so emails are checked for shape only.
Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    AfterValidator(str.lower),
]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class Page[T](ApiModel):
    items: list[T]
    next_cursor: str | None = Field(None, description="Pass as ?cursor= to fetch the next page")


def encode_cursor(value: int | str) -> str:
    return base64.urlsafe_b64encode(str(value).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> str | None:
    if not cursor:
        return None
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode()).decode()
    except (ValueError, UnicodeDecodeError):
        return None


class Ack(ApiModel):
    ok: bool = True
    message: str = ""
