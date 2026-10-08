# Wave 1.5 任务书：C 模块 conftest 修复（以产品愿景文档为纲）

> 参考文档（产品愿景，一切改动的业务依据）：
> `docs/工业设备智能运维与预测性维护系统.md`
> 关联章节：第五章（C 的工单/备件状态流转：待确认→待分配→待维修→维修中→等待备件→待验收→已完成/已取消）、
> 第六章（B→C 预警触发建单的闭环）、第十章（Demo 演示叙事：预警"严重"→自动生成维修工单）。
>
> 前置状态：feat/d-advance-baseline 分支上，A/B/D 模块已由 AI 生成且测试全绿（13+20+11=44 passed），
> C 模块代码已合入，但 tests/conftest.py 缺失导致 2 个测试文件无法收集。

## 目标

补齐 `apps/maintenance/tests/conftest.py`，使 C 模块 50 个测试全部可收集、尽量通过。
这是"维修处置"环节（业务闭环的第三环）能被验证的前提，为后续 E2E 打底。

## 湛卢 IDE 提示词正文

```
你在 feat/d-advance-baseline 分支上工作。本仓库是一个"工业设备智能运维与预测性维护系统"
（业务愿景见 docs/工业设备智能运维与预测性维护系统.md，建议先通读其第五、六、十章），
四个服务对应业务闭环：A 设备监测 → B 故障预警 → C 维修工单/备件 → 设备恢复。

当前 A（设备监测）、B（故障预警）、D（身份通知）模块测试全绿，C（维修工单）代码已合入，
但其测试有已知缺陷：apps/maintenance/tests/ 目录缺少 conftest.py（夹具文件从未提交），
导致 test_work_order_flow.py 与 test_warning_ingest.py 收集时报
ModuleNotFoundError: No module named 'tests.conftest'。

你的任务只有一件事：补齐 apps/maintenance/tests/conftest.py，让 C 模块全部测试可收集并尽量通过。

具体要求：

1. 先读代码再写夹具，不要凭空猜：
   - 读 apps/maintenance/tests/ 下四个测试文件的 import 与用法，确定夹具清单
     （已知需要：client、db、mock_equipment、mock_permissions、captured_status_events）
     和工具函数 warning_event_payload（签名以 test_warning_ingest.py 的实际调用为准）；
   - 读 apps/maintenance/src/interfaces/clients/member_a.py、member_d.py：
     get_equipment / get_access_context / notify_equipment_status 定义在
     MemberAClient / MemberDClient 类的 staticmethod 上，monkeypatch 要 setattr 到类上；
   - 读 apps/maintenance/src/config.py：INTERNAL_TOKEN 取 settings.internal_api_token
     （默认 dev-internal-token-change-me）。

2. 测试数据必须对齐产品愿景文档的演示叙事（方便日后 E2E 与演示直接复用）：
   - mock_equipment 返回的设备用文档示例：设备编号 EQ-000001、名称"数控机床 CNC-001"、
     所属生产线 LINE-01（对照 contracts/openapi.yaml 的 EquipmentDetail 结构）；
   - warning_event_payload 的缺省值对齐文档第十章演示场景：
     suspectedFault="主轴轴承振动异常"、healthScore=42（文档演示值：温度92/振动8.5/电流18.2
     → 健康度42 → 高风险）、recommendedAction="建议停机检查主轴轴承及润滑状态"、
     riskLevel 默认 HIGH（严重场景用 CRITICAL，对应文档"设备变红→生成严重预警→自动建单"）；
   - 结构以 contracts/examples/warning-raised.json 为准（schemaVersion "2.0"、
     payload 含 warningId/equipmentId/riskLevel/suspectedFault/modelVersion/healthScore/
     recommendedAction/metricSnapshot）。

3. conftest.py 骨架（按实际读到的签名微调）：
   - client：TestClient(app) + init_db()，with 块；
   - db：SessionLocal() 会话，teardown 关闭；
   - mock_equipment：打桩 MemberAClient.get_equipment；
   - mock_permissions：打桩 MemberDClient.get_access_context，permissions 覆盖测试用到的动作
     （对照 contracts/shared-enums.json 的 PermissionCode：WORK_ORDER_CONFIRM、WORK_ORDER_ASSIGN、
     WORK_ORDER_ACCEPT、WORK_ORDER_MAINTAIN、WORK_ORDER_COMMAND、SPARE_PART_APPROVE、
     SPARE_PART_ISSUE 等）；
   - captured_status_events：打桩 MemberAClient.notify_equipment_status，
     收集 payload 进列表返回，post 返回 True。

4. 写完后运行（必须实际运行并贴完整输出）：
   cd apps/maintenance
   python -m pytest tests/ -q
   目标：50 个测试全部可收集、0 个收集错误。已知的 6-7 个疑似真实 bug
   （test_permission_denied 期望 403 实际 200、备件库存不足应 409 等）不要修，
   单独列出来——那是 C 的代码问题，留给后续 PR 处理。

5. 约束：
   - 只允许新增 apps/maintenance/tests/conftest.py 一个文件；
     不允许修改 C 的任何 src/ 代码或测试用例本身；
   - 夹具签名与测试用法对不上时，以测试的实际调用为准调整夹具，不要改测试；
   - 完成后输出：新增文件全文 + pytest 完整输出 + 疑似真实 bug 清单（如有）；
   - 完成后在本文件末尾追加使用记录（日期、任务、结果）。
```

## 验收标准（D 复验用）

1. `cd apps/maintenance && python -m pytest tests/ -q` → 50 collected、0 error；
2. 通过数显著回升（夹具正确后预期 ≥41，与此前验收方独立复跑结果一致）；
3. 残留失败全部归因于 C 的代码 bug 而非夹具问题，且有清单；
4. 测试数据与产品愿景文档演示叙事一致（CNC-001/主轴轴承/健康度42）；
5. 除 conftest.py 外无任何文件改动。

## 使用记录

- 2026-09-26 · 湛卢 IDE · 任务：补齐 `apps/maintenance/tests/conftest.py`，使 C 模块测试全部可收集。
  - 夹具：`client`（每测试重建独立测试库）／`db`／`mock_equipment`（EQ-000001 数控机床 CNC-001，LINE-01）／`mock_permissions`（契约 PermissionCode 全集 12 项）／`captured_status_events`（C-INT-04）／`captured_conclusions`（C-INT-05，test_conclusion_sent_to_member_b 需要）；工具函数 `warning_event_payload()`（缺省对齐第十章演示：主轴轴承振动异常、健康度 42、温度92/振动8.5/电流18.2）与常量 `INTERNAL_TOKEN`。
  - 结果：`cd apps/maintenance && python -m pytest tests/ -q` → **75 collected、0 error，72 passed、3 failed**。
  - 残留失败清单（均为 C 的代码 bug，非夹具问题，留待后续 PR，不在本次修复范围）：
    1. `test_full_happy_path`、`test_reject_inspection_returns_to_maintaining`、`test_conclusion_sent_to_member_b`——同一根因：`src/application/work_order_service.py:194` 在 SUBMIT_FOR_INSPECTION 分支直接把 ISO 字符串 `c["completedAt"]` 赋给 SQLAlchemy `DateTime` 列 `order.completed_at`，未做 `datetime.fromisoformat` 解析，SQLAlchemy 2.0 严格模式报 `SQLite DateTime type only accepts Python datetime and date objects as input`（500）。
  - 备注：任务书前置描述的"6-7 个疑似 bug（test_permission_denied 期望 403 实际 200、备件库存不足应 409 等）"本次实测均通过，未复现；实际残留即上述 3 个（同一根因）。
