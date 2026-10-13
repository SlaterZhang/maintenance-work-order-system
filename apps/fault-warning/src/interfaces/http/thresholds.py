"""B 阈值配置接口（v2.1.0 新增：阈值可在线调整并持久化）。

* ``GET /api/v1/scoring-thresholds``（登录身份即可）：返回当前生效阈值
  与默认值对照，供预警规则阈值页展示。
* ``PUT /api/v1/scoring-thresholds``（``ADMIN_ALL``）：校验后持久化到
  ``src/data/thresholds.json`` 并即时生效（apply_thresholds），无需重启。
"""

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from src.domain import scoring
from src.interfaces.http.deps import (
    current_user_context,
    require_permission,
    trace_id,
)

router = APIRouter(prefix="/api/v1", tags=["B-阈值配置"])

_THRESHOLD_FILE = (
    Path(__file__).resolve().parents[2] / "data" / "thresholds.json"
)

_LABELS = {
    "vibration_normal": "振动报警阈值 (mm/s)",
    "vibration_full": "振动满扣阈值 (mm/s)",
    "temperature_normal": "温度报警阈值 (℃)",
    "temperature_full": "温度满扣阈值 (℃)",
    "current_normal": "电流报警阈值 (A)",
    "current_full": "电流满扣阈值 (A)",
    "nominal_speed": "额定转速 (r/min)",
    "speed_dev_normal": "转速偏离报警阈值",
    "speed_dev_full": "转速偏离满扣阈值",
    "weight_vibration": "振动权重",
    "weight_temperature": "温度权重",
    "weight_current": "电流权重",
    "weight_speed": "转速权重",
}


def _persist(vals: dict) -> None:
    _THRESHOLD_FILE.parent.mkdir(parents=True, exist_ok=True)
    _THRESHOLD_FILE.write_text(
        json.dumps(vals, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _validate(vals: dict) -> str | None:
    """返回错误信息；None 表示通过。校验基于合并后的完整阈值（部分更新安全）。"""
    merged = dict(scoring.THRESH)
    for k, v in vals.items():
        merged[k] = float(v)
    vals = merged
    pairs = [
        ("vibration_normal", "vibration_full"),
        ("temperature_normal", "temperature_full"),
        ("current_normal", "current_full"),
        ("speed_dev_normal", "speed_dev_full"),
    ]
    for normal, full in pairs:
        n, f = float(vals.get(normal, 0)), float(vals.get(full, 0))
        if f <= n:
            return f"满扣阈值必须大于报警阈值：{_LABELS[normal]} {_LABELS[normal] and ''}{n} → {f}"
    weight_sum = sum(
        float(vals.get(k, 0))
        for k in ("weight_vibration", "weight_temperature", "weight_current", "weight_speed")
    )
    if abs(weight_sum - 100.0) > 0.01:
        return f"四项权重之和必须等于 100（当前 {weight_sum:g}）"
    for k, v in vals.items():
        if float(v) < 0:
            return f"阈值不能为负：{_LABELS.get(k, k)}"
    return None


@router.get("/scoring-thresholds")
def get_thresholds(
    request: Request = None,
    x_trace_id: str = Depends(trace_id),
) -> dict:
    current_user_context(request, x_trace_id)
    return {
        "values": dict(scoring.THRESH),
        "labels": _LABELS,
        "defaults": {
            "vibration_normal": scoring.VIBRATION_NORMAL_MM_S,
            "vibration_full": scoring.VIBRATION_FULL_MM_S,
            "temperature_normal": scoring.TEMPERATURE_NORMAL_C,
            "temperature_full": scoring.TEMPERATURE_FULL_C,
            "current_normal": scoring.CURRENT_NORMAL_A,
            "current_full": scoring.CURRENT_FULL_A,
            "nominal_speed": scoring.NOMINAL_SPEED_RPM,
            "speed_dev_normal": scoring.SPEED_DEVIATION_NORMAL,
            "speed_dev_full": scoring.SPEED_DEVIATION_FULL,
            "weight_vibration": 40.0,
            "weight_temperature": 25.0,
            "weight_current": 20.0,
            "weight_speed": 15.0,
        },
        "modelVersion": scoring.MODEL_VERSION,
    }


@router.put("/scoring-thresholds")
def update_thresholds(
    body: dict,
    request: Request = None,
    x_trace_id: str = Depends(trace_id),
) -> dict:
    ctx = current_user_context(request, x_trace_id)
    require_permission(ctx, "ADMIN_ALL")
    vals = body.get("values") or {}
    unknown = [k for k in vals if k not in scoring.THRESH]
    if unknown:
        return JSONResponse({"error": f"未知阈值键：{unknown}"}, status_code=400)
    err = _validate(vals)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    scoring.apply_thresholds(vals)
    _persist({k: scoring.THRESH[k] for k in scoring.THRESH})
    return {
        "ok": True,
        "values": dict(scoring.THRESH),
        "updatedBy": ctx.get("userId"),
        "modelVersion": scoring.MODEL_VERSION,
    }
