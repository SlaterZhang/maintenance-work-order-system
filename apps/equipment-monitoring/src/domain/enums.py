import json
from functools import lru_cache
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "contracts"


@lru_cache(maxsize=1)
def load_shared_enums() -> dict:
    return json.loads(
        (CONTRACTS_DIR / "shared-enums.json").read_text(encoding="utf-8")
    )


def equipment_status_values() -> tuple[str, ...]:
    return tuple(load_shared_enums()["equipmentStatus"])


def event_type_values() -> tuple[str, ...]:
    return tuple(load_shared_enums()["eventType"])
