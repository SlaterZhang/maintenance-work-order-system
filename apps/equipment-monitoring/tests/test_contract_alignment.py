from __future__ import annotations

import json

from conftest import REPOSITORY_ROOT
from src.domain.models import EquipmentStatus, RiskLevel


def test_equipment_status_values_match_shared_contract() -> None:
    shared_enums = json.loads(
        (REPOSITORY_ROOT / "contracts" / "shared-enums.json").read_text(encoding="utf-8")
    )

    assert [status.value for status in EquipmentStatus] == shared_enums["equipmentStatus"]
    assert [level.value for level in RiskLevel] == [
        item["code"] for item in shared_enums["riskLevel"]
    ]
