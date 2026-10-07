"""A 注入控制台（演示专用端点）。

阶段1鉴权闭合（2026-10-06）：看板的"注入演示数据"不再由浏览器直连
A 的内部遥测接口和 B 的内部评估接口（前端持 ``X-Internal-Token``
= 内部服务凭据下发，权限旁路）。改为一个授权端点：

* 登录身份即可（Bearer JWT 经 D-API-02 校验）——注入控制台是演示
  道具，不在这里演权限（演示脚本口径）；
* A 落库遥测样本后，由服务端调用 B 完成健康评估（docs/06 §14
  步骤 1-2），评估失败**如实上抛**，不静默、不 mock。
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.application import telemetry_service
from src.domain.errors import BadRequestError
from src.domain.models import Equipment
from src.infrastructure.db import get_db
from src.interfaces.clients.member_b import MemberBClient
from src.interfaces.http.deps import (
    idempotency_key, operator_context, trace_id,
)

router = APIRouter(prefix="/api/v1/equipment", tags=["A-注入控制台"])

# 演示注入预设（对照 docs/06 第十章演示数据）：
# ABNORMAL → 规则引擎压到健康度约 42，触发高风险预警；
# NORMAL   → 健康度约 92，用于维修后恢复注入。
SIMULATION_PRESETS = {
    "ABNORMAL": {
        "temperatureC": 96.7,
        "vibrationMmS": 9.8,
        "currentA": 18.3,
        "rotationalSpeedRpm": 1450.0,
    },
    "NORMAL": {
        "temperatureC": 65.2,
        "vibrationMmS": 3.4,
        "currentA": 11.7,
        "rotationalSpeedRpm": 1450.0,
    },
}


@router.post("/{equipmentId}/simulate")
def simulate_telemetry(
    equipmentId: str,
    body: dict,
    request: Request,
    x_trace_id: str = Depends(trace_id),
    idem: str = Depends(idempotency_key),
    db: Session = Depends(get_db),
) -> dict:
    """注入一条演示遥测并联动 B 健康评估。

    请求体：``{"mode": "ABNORMAL" | "NORMAL"}``（缺省 ``ABNORMAL``）。
    每次注入生成全新的 sampleId/batchId/evaluationId，天然可重复点击。
    NORMAL 模式额外把设备主数据状态复位为 RUNNING（任何非运行状态），
    响应中 ``equipmentStatusRestored/From`` 反映复位前的状态。
    """
    operator_context(request, x_trace_id)   # 登录身份即可（演示道具）

    mode = str(body.get("mode") or "ABNORMAL").upper()
    if mode not in SIMULATION_PRESETS:
        raise BadRequestError(f"mode 必须为 {list(SIMULATION_PRESETS)} 之一")

    measured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    sample = {
        "sampleId": str(uuid.uuid4()),
        "measuredAt": measured_at,
        **SIMULATION_PRESETS[mode],
    }
    batch = {
        "batchId": str(uuid.uuid4()),
        "source": "SIMULATOR",
        "samples": [sample],
    }
    ingest = telemetry_service.ingest_telemetry(db, equipmentId, batch)

    # “恢复正常数据” = 演示现场完全复位（2026-10-07）：设备主数据状态一并
    # 恢复为 RUNNING。此前只回滚遥测——设备一旦经“等待备件”进入 STOPPED，
    # 恢复注入后看板仍显示“已停止”（状态正常只能由 C 的状态事件改回）。
    # 状态复位是 A 的主数据职责，不依赖 B 评估结果（评估失败照常如实上抛）。
    status_restored_from = None
    if mode == "NORMAL":
        equipment = (
            db.query(Equipment)
            .filter(Equipment.equipment_id == equipmentId)
            .first()
        )
        if equipment is not None and equipment.current_status != "RUNNING":
            status_restored_from = equipment.current_status
            equipment.current_status = "RUNNING"
            equipment.version += 1
            db.commit()

    evaluation, error = MemberBClient.evaluate_health(
        {
            "evaluationId": str(uuid.uuid4()),
            "equipmentId": equipmentId,
            "requestedAt": measured_at,
            "sample": sample,
        },
        trace_id=x_trace_id,
        # B 的幂等键要求 UUID：每次注入生成全新评估标识（客户端键仅约束本端点）
        idem_key=str(uuid.uuid4()),
    )
    return {
        "simulationId": batch["batchId"],
        "equipmentId": equipmentId,
        "mode": mode,
        "sample": sample,
        "ingest": ingest,
        "equipmentStatusRestored": status_restored_from is not None,
        "equipmentStatusRestoredFrom": status_restored_from,
        "evaluation": evaluation,
        "evaluationError": error,
    }
