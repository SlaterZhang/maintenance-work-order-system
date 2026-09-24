# 给湛卢 IDE 的提示词 · Wave 1 成员 A 设备监测模块

> 用法：粘贴给湛卢 IDE，生成结果交负责人审查后再提交。用完在文末表格追加使用记录。

---

## 提示词 A：模块骨架生成

```
请为本仓库 apps/equipment-monitoring/ 实现成员 A 的设备资产与运行监测服务。
技术栈：Python 3.12 + FastAPI + pydantic v2 + SQLite（标准库 sqlite3 即可）。

背景：这是一个四服务微服务项目，A 服务负责设备主数据与运行状态。跨模块契约在 contracts/ 目录：
- contracts/openapi.yaml 中 C-INT-01（GET /api/v1/equipment/{equipmentId}，我方为提供方）和 C-INT-03（POST /api/v1/equipment-status-events，我方为接收方）；
- contracts/shared-enums.json 的 equipmentStatus 枚举；状态只用这些值；
- contracts/examples/ 里的示例报文是权威样例，响应结构要与其一致；
- contracts/schemas/event-envelope.schema.json 是事件包络，接收事件必须校验它。

要求：
1. 目录结构：src/domain（设备实体、状态机）、src/application（查询与状态更新用例）、src/interfaces（FastAPI 路由）、src/infrastructure（SQLite 存储）、tests/、requirements.txt、.env.example（端口 8101）；
2. GET /api/v1/equipment/{equipmentId}：200 返回 EquipmentSnapshot（字段以 openapi.yaml 的定义为准，逐字段对照，不得增删语义）；404 时返回 ErrorResponse 结构 {code:"EQUIPMENT_NOT_FOUND", message, traceId, details}；500 同构；
3. POST /api/v1/equipment-status-events：请求体先校验 event-envelope schema（EventId 唯一性幂等去重，重复返回原 202 结果），然后按 payload 的 equipmentId、status 更新设备状态；设备不存在返回 404 ErrorResponse；非法枚举 400；
4. 设备主数据：内存+SQLite 双实现可不做，直接 SQLite 即可；提供 seed 脚本插入至少 3 台设备（含 1 台 STOPPED）；
5. 时间一律 datetime 传 RFC 3339 UTC 格式字符串；
6. 用 pytest 写测试：查询 200/404、事件接收 202、重复 EventId 幂等、非法状态 400、设备不存在 404，每个用例给出断言；
7. 生成一个 main.py（或 app.py）支持 uvicorn 启动，并在 apps/equipment-monitoring/README.md 写明启动命令；
8. 不要修改 apps/ 之外、requirements.txt（根目录）之外的任何文件；契约文件只读。
生成时注意说明哪些文件是新文件、哪些是修改，便于我审查。
```

## 提示词 B：契约符合性自检

```
请自检 apps/equipment-monitoring/ 的实现是否符合 contracts/：
1. 打开 contracts/openapi.yaml，找到 C-INT-01 和 C-INT-03 的完整定义（路径、参数、请求/响应 schema、每个 response code）；
2. 逐字段核对代码中的 pydantic 模型与 openapi.yanml 中的 EquipmentSnapshot、EquipmentStatusChangedEvent、ErrorResponse：列出所有不一致（字段名、类型、必填性、枚举值域）；
3. 用 contracts/examples/equipment-status-changed.json 作为 fixture 写一个契约测试：POST 该报文必须返回 202，再 POST 一次（相同 EventId）也返回 202 且不产生重复副作用；
4. 检查 sqlite 连接是否在每个请求内关闭/复用得当，有没有阻塞调用；
5. 输出「差异修复清单」，等确认后修复，不要擅自改 contract 文件。
```

---

## 使用记录

| 日期 | IDE能力 | 任务 | 产出 | 结果 |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |
