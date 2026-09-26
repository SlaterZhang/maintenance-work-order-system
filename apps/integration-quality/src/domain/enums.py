import json
from functools import lru_cache
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "contracts"


@lru_cache(maxsize=1)
def load_shared_enums() -> dict:
    return json.loads(
        (CONTRACTS_DIR / "shared-enums.json").read_text(encoding="utf-8")
    )


def role_code_values() -> tuple[str, ...]:
    return tuple(load_shared_enums()["roleCode"])


def permission_code_values() -> tuple[str, ...]:
    return tuple(load_shared_enums()["permissionCode"])


def notification_channel_values() -> tuple[str, ...]:
    return tuple(load_shared_enums()["notificationChannel"])


TEMPLATE_CODES = (
    "WARNING_CREATED",
    "WORK_ORDER_CREATED",
    "WORK_ORDER_ASSIGNED",
    "WORK_ORDER_STATUS_CHANGED",
    "SPARE_REQUEST_PENDING",
)
