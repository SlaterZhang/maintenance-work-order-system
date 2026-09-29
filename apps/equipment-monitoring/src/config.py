from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_path: Path
    seed_on_start: bool = True
    internal_api_token: str | None = None
    warning_service_url: str | None = None
    outbound_timeout_seconds: float = 3.0

    @classmethod
    def from_environment(cls) -> "Settings":
        configured_path = Path(os.getenv("EQUIPMENT_DB_PATH", "data/equipment.db"))
        if not configured_path.is_absolute():
            configured_path = MODULE_ROOT / configured_path
        return cls(
            database_path=configured_path,
            seed_on_start=_as_bool(os.getenv("SEED_ON_START"), True),
            internal_api_token=os.getenv("INTERNAL_API_TOKEN") or None,
            warning_service_url=os.getenv("WARNING_SERVICE_URL") or None,
            outbound_timeout_seconds=float(os.getenv("OUTBOUND_TIMEOUT_SECONDS", "3")),
        )
