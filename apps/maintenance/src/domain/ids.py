import random
from datetime import datetime, timezone


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def new_order_id() -> str:
    """WO-YYYYMMDD-NNNN"""
    return f"WO-{_today()}-{random.randint(1, 9999):04d}"


def new_spare_request_id() -> str:
    """SPR-YYYYMMDD-NNNN"""
    return f"SPR-{_today()}-{random.randint(1, 9999):04d}"


def new_equipment_id() -> str:
    return f"EQ-{random.randint(1, 999999):06d}"


def new_spare_part_id() -> str:
    return f"SP-{random.randint(1, 999999):06d}"