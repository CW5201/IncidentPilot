from __future__ import annotations

from typing import Any

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB


def json_type() -> Any:
    return JSON().with_variant(JSONB, "postgresql")
