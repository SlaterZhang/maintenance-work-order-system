import json
from functools import lru_cache
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parents[4] / "contracts"


@lru_cache(maxsize=1)
def load_shared_enums() -> dict:
    return json.loads(
        (CONTRACTS_DIR / "shared-enums.json").read_text(encoding="utf-8")
    )


def risk_level_codes() -> tuple[str, ...]:
    return tuple(item["code"] for item in load_shared_enums()["riskLevel"])


def order_priority_for(risk_level: str) -> str:
    for item in load_shared_enums()["riskLevel"]:
        if item["code"] == risk_level:
            return item["orderPriority"]
    raise ValueError(f"未知风险等级：{risk_level}")


def warning_status_values() -> tuple[str, ...]:
    return tuple(load_shared_enums()["warningStatus"])
