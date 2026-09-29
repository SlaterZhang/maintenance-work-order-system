# 成员 A：设备资产与运行监测服务

本模块实现 `contracts/openapi.yaml` 2.0.0 中由 `MEMBER_A` 负责的全部 7 个操作：设备分页查询、新建、详情、乐观锁更新、遥测数据查询与批量接入，以及接收成员 C 的设备状态事件。遥测样本入库后，服务还会按 `C-INT-02` 调用成员 B 的健康评估接口。

## 技术选择

- Python 3.12、FastAPI、Pydantic v2；
- Python 标准库 `sqlite3`，每次操作使用独立连接，开启 WAL 和外键；
- 应用层、HTTP 入口与 SQLite 存储分层放置。

SQLite 保留设备档案、遥测样本、已处理批次、写请求幂等记录与设备状态审计记录。`EquipmentId` 由事务内的单调序列生成，不会因停用或重启而复用。A 调用 B 时采用事务发件箱：遥测数据和待评估任务同一事务落库，B 暂时不可用时保留 `PENDING` 记录，后续遥测写入或服务重启时使用原 `evaluationId` 重试。

## 启动

在仓库根目录执行：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r apps/equipment-monitoring/requirements.txt
cd apps/equipment-monitoring
uvicorn main:app --host 0.0.0.0 --port 8101 --reload
```

首次启动会创建 `data/equipment.db`，并自动写入 3 台虚构演示设备：`EQ-000001` 至 `EQ-000003`，其中 `EQ-000003` 为 `STOPPED`。也可手动执行：

```bash
cd apps/equipment-monitoring
python -m src.infrastructure.seed
```

Swagger UI 位于 `http://localhost:8101/docs`。服务直连时由 `INTERNAL_API_TOKEN` 保护内部接口；面向前端的 JWT 校验与权限映射由成员 D 的 8080 网关负责。未配置 `INTERNAL_API_TOKEN` 时为本地信任模式，仅用于独立开发。

> 早期 Wave 1 任务书曾写作 `/api/v1/equipment-status-events`，当前 2.0.0 权威契约已冻结为 `/api/v1/integration/equipment-status-events`，本实现以后者为准。

## 配置

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_PORT` | `8101` | 服务端口 |
| `EQUIPMENT_DB_PATH` | `data/equipment.db` | SQLite 文件，相对于模块目录 |
| `SEED_ON_START` | `true` | 空库启动时写入演示数据 |
| `INTERNAL_API_TOKEN` | 空 | 内部服务调用 Token |
| `WARNING_SERVICE_URL` | 空 | 成员 B 服务地址；联调时设为 `http://localhost:8102` |
| `OUTBOUND_TIMEOUT_SECONDS` | `3` | 调用 B 的单次超时秒数 |

时间输入必须携带 UTC 时区，例如 `2026-09-17T08:30:00Z`。写接口要求 UUID 格式的 `Idempotency-Key`；相同键与相同报文返回首次结果，相同键却更换报文返回 `409 IDEMPOTENCY_CONFLICT`。

## 测试

```bash
python -m pytest apps/equipment-monitoring
```

模块测试包含全部 API 的正常与主要异常流程，并直接重放 `contracts/examples/equipment-status-changed.json` 验证事件契约与幂等性。
