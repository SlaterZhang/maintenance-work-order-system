"""调用成员 B 的健康评估（C-INT-02 同款内部端点）。

演示注入流程（docs/06 §14 步骤 1-2）：A 落库遥测样本后，由 A 服务端
（而非浏览器持内部令牌）调用 B 完成评估，消除"内部令牌下发到前端"
的权限旁路。失败**不静默**：返回错误说明，由看板展示。
"""

import httpx

from src.config import settings


class MemberBClient:
    """内部端点：``POST /api/v1/health-evaluations``（X-Internal-Token）。"""

    @staticmethod
    def evaluate_health(
        body: dict, trace_id: str, idem_key: str,
    ) -> tuple[dict | None, str | None]:
        """执行一次健康评估。

        返回 ``(evaluation, error)``：
        * 成功：``({"healthScore": ...}, None)``
        * 失败：``(None, "成员B评估失败(HTTP 500): ...")``——不 mock 结果，
          看板据此展示真实错误（阶段1 排查报告 P0-1 的教训：静默失败
          会把根因藏进日志）。
        """
        try:
            r = httpx.post(
                f"{settings.member_b_base}/api/v1/health-evaluations",
                json=body,
                headers={
                    "X-Internal-Token": settings.internal_api_token,
                    "X-Trace-Id": trace_id,
                    "Idempotency-Key": idem_key,
                },
                timeout=5.0,
            )
        except httpx.HTTPError as exc:
            return None, f"成员B不可达：{exc.__class__.__name__}"
        if r.status_code == 200:
            return r.json(), None
        detail = ""
        try:
            detail = r.json().get("message", "")
        except ValueError:
            detail = r.text[:120]
        return None, f"成员B评估失败(HTTP {r.status_code})：{detail}"
