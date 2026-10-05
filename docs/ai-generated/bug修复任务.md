# Bug 修复任务清单

项目路径：`E:\zh3g\Desktop\Soochow_University\graduate_third_one\云计算技术\移动云杯\project\maintenance-work-order-system`

文件：`web/dashboard.html`

---

## Bug 1: 工单时间线不显示（严重）

**问题描述**：点击工单行展开后，时间线没有显示

**期望**：点击工单行后，应该显示 5 个状态节点的水平时间线（待确认 → 待派单 → 维修中 → 待验收 → 已完成），当前状态高亮

**实际**：点击工单行后只显示标题、描述、负责人信息，没有时间线

**排查结果**：
- `orderTimelineHtml()` 函数已存在
- `orderPanelRow()` 函数中有调用 `orderTimelineHtml(o)` 的代码
- CSS 样式 `.timeline` / `.timeline-node` 已添加

**可能原因**：
1. `orderTimelineHtml()` 函数定义位置有问题
2. `orderPanelRow()` 中调用位置不对
3. 函数返回的 HTML 没有正确插入到 DOM

**修复要求**：
1. 检查 `orderTimelineHtml()` 函数是否正确定义
2. 检查 `orderPanelRow()` 中调用 `orderTimelineHtml(o)` 的位置
3. 确保展开行时时间线正确渲染

---

## Bug 2: 健康度显示"--"（中等）

**问题描述**：设备详情页的健康度显示"--"，但有预警时应该是数值

**期望**：当设备有预警时，健康度应该显示预警中的 healthScore 数值（如 30.6）

**实际**：显示 "--"

**排查结果**：
- 设备 EQ-000001 有预警 WARN-20261004-0004，健康度 30.6
- 但 `refreshEquipmentDetail()` 中 `state.healthMap[state.openEq]` 返回空

**可能原因**：
- `state.healthMap` 没有正确填充
- `refreshDashboard()` 中没有调用 B 服务获取健康度数据

**修复要求**：
1. 检查 `refreshDashboard()` 是否获取并缓存了健康度数据
2. 检查 `state.healthMap` 的数据结构
3. 确保设备详情页能正确读取健康度

---

## 验证方法

1. 登录 USER-D-001
2. 进入设备详情页（点击 EQ-000001）
3. 健康度应显示数值（如 30.6），不是 "--"
4. 进入"维修工单"页面
5. 点击任意工单行展开
6. 应该看到状态流转时间线