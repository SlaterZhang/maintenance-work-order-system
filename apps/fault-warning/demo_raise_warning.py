import json
import sys
from pathlib import Path

import httpx

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"
EXAMPLE_PATH = CONTRACTS_DIR / "examples" / "warning-raised.json"
TARGET = "http://localhost:8103/api/v1/integration/warning-events"


def main() -> int:
    event = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    headers = {
        "X-Trace-Id": "trace-20260917-001",
        "Idempotency-Key": event["eventId"],
        "X-Internal-Token": "dev-internal-token-change-me",
    }
    print(f"目标地址: {TARGET}")
    print(f"请求报文: {json.dumps(event, ensure_ascii=False, indent=2)}")
    try:
        response = httpx.post(TARGET, json=event, headers=headers, timeout=5.0)
    except httpx.HTTPError as exc:
        print(f"C 服务未就绪，未发送成功：{exc}")
        return 1
    print(f"HTTP {response.status_code}")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
