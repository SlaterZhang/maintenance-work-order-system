/* ==========================================================================
   enums.js —— 界面枚举台账（中文名 / 语义色调的唯一来源）
   --------------------------------------------------------------------------
   这里是一份 contracts/shared-enums.json 的**前端副本**，用途有两个：
     · 页面上永远不出现裸英文枚举码（用户看不懂 PENDING_ACCEPTANCE）；
     · 状态色由语义色调（ok/warn/bad/info/purple/dim）统一决定，
       而不是每个页面各写一套颜色。

   副本会漂移，所以 tests/test_frontend_enums.py 会逐字比对键集合：
   往契约里加枚举值而忘了改这里，CI 会直接失败并指出缺了哪个。
   改契约时请同步改本文件——两处必须一致。
   ========================================================================== */
"use strict";

const ENUMS = {
  "contractVersion": "2.1.0",
  "equipmentStatus": {
    "RUNNING": { "zh": "运行中", "tone": "ok" },
    "WARNING": { "zh": "预警中", "tone": "warn" },
    "STOPPED": { "zh": "已停止", "tone": "dim" },
    "MAINTAINING": { "zh": "维修中", "tone": "bad" },
    "TRIAL_RUNNING": { "zh": "试运行", "tone": "info" }
  },
  "riskLevel": {
    "LOW": { "zh": "低", "tone": "ok", "priority": "P4" },
    "MEDIUM": { "zh": "中", "tone": "info", "priority": "P3" },
    "HIGH": { "zh": "高", "tone": "warn", "priority": "P2" },
    "CRITICAL": { "zh": "严重", "tone": "bad", "priority": "P1" }
  },
  "warningStatus": {
    "OPEN": { "zh": "待处理", "tone": "bad" },
    "ACKNOWLEDGED": { "zh": "已确认", "tone": "warn" },
    "LINKED_TO_ORDER": { "zh": "已转工单", "tone": "info" },
    "RESOLVED": { "zh": "已闭环", "tone": "ok" },
    "FALSE_POSITIVE": { "zh": "误报", "tone": "dim" },
    "CANCELLED": { "zh": "已取消", "tone": "dim" }
  },
  "workOrderStatus": {
    "PENDING_CONFIRMATION": { "zh": "待确认", "tone": "bad" },
    "PENDING_ASSIGNMENT": { "zh": "待派单", "tone": "warn" },
    "PENDING_ACCEPTANCE": { "zh": "待接单", "tone": "info" },
    "PENDING_MAINTENANCE": { "zh": "待维修", "tone": "info" },
    "MAINTAINING": { "zh": "维修中", "tone": "bad" },
    "WAITING_PARTS": { "zh": "待备件", "tone": "warn" },
    "PENDING_INSPECTION": { "zh": "待检验", "tone": "warn" },
    "COMPLETED": { "zh": "已完成", "tone": "ok" },
    "CANCELLED": { "zh": "已取消", "tone": "dim" }
  },
  "spareRequestStatus": {
    "PENDING_APPROVAL": { "zh": "待审批", "tone": "warn" },
    "APPROVED": { "zh": "已批准", "tone": "info" },
    "RESERVED": { "zh": "已预留", "tone": "info" },
    "ISSUED": { "zh": "已发料", "tone": "ok" },
    "PARTIALLY_RETURNED": { "zh": "部分退料", "tone": "dim" },
    "CLOSED": { "zh": "已关单", "tone": "ok" },
    "REJECTED": { "zh": "已驳回", "tone": "bad" },
    "CANCELLED": { "zh": "已取消", "tone": "dim" }
  },
  "workOrderPriority": {
    "P1": { "zh": "P1 紧急", "tone": "bad", "slaHours": 12 },
    "P2": { "zh": "P2 高", "tone": "warn", "slaHours": 24 },
    "P3": { "zh": "P3 中", "tone": "info", "slaHours": 72 },
    "P4": { "zh": "P4 低", "tone": "dim", "slaHours": 168 }
  },
  "workOrderSource": {
    "WARNING": { "zh": "预警自动建单" },
    "MANUAL": { "zh": "人工报修" },
    "INSPECTION": { "zh": "巡检发现" }
  },
  "notificationChannel": {
    "IN_APP": { "zh": "站内" },
    "EMAIL": { "zh": "邮件" }
  },
  "roleCode": {
    "SYSTEM_ADMIN": { "zh": "系统管理员" },
    "EQUIPMENT_OPERATOR": { "zh": "设备操作员" },
    "WARNING_ANALYST": { "zh": "预警分析师" },
    "MAINTENANCE_SUPERVISOR": { "zh": "维修主管" },
    "MAINTENANCE_ENGINEER": { "zh": "维修工程师" },
    "WAREHOUSE_MANAGER": { "zh": "仓库管理员" },
    "INSPECTOR": { "zh": "验收员" }
  },
  "permissionCode": {
    "EQUIPMENT_READ": "设备查看",
    "EQUIPMENT_MANAGE": "设备管理",
    "TELEMETRY_READ": "遥测查看",
    "TELEMETRY_WRITE": "遥测写入",
    "WARNING_READ": "预警查看",
    "WARNING_ACKNOWLEDGE": "预警确认",
    "WORK_ORDER_READ": "工单查看",
    "WORK_ORDER_CREATE": "工单创建",
    "WORK_ORDER_CONFIRM": "工单确认",
    "WORK_ORDER_ASSIGN": "工单派单",
    "WORK_ORDER_ACCEPT": "工单接单",
    "WORK_ORDER_MAINTAIN": "维修执行",
    "WORK_ORDER_INSPECT": "工单验收",
    "WORK_ORDER_CANCEL": "工单取消",
    "SPARE_READ": "备件查看",
    "SPARE_REQUEST": "备件申请",
    "SPARE_APPROVE": "备件审批",
    "SPARE_ISSUE": "备件发料",
    "USER_ACCESS_READ": "用户权限查看",
    "NOTIFICATION_SEND": "通知发送",
    "ADMIN_ALL": "系统管理"
  },
  "eventType": {
    "WarningRaised": { "zh": "预警建单", "flow": "B → C" },
    "EquipmentStatusChanged": { "zh": "状态联动", "flow": "C → A" },
    "MaintenanceConclusionReported": { "zh": "维修结论闭环", "flow": "C → B" },
    "OrderCancelledReported": { "zh": "工单取消回流", "flow": "C → B" },
    "WarningResolvedReported": { "zh": "预警自动闭环", "flow": "B → C" }
  },
  "tone": {
    "ok": "#2fd88a",
    "warn": "#ffc53d",
    "bad": "#ff5c5c",
    "info": "#39d2ff",
    "purple": "#a78bfa",
    "dim": "#8ba0c0"
  }
};

/* 便捷访问器（platform.js 里的 tag()/enumZh() 都走这里） */
function enumGroup(name){ return ENUMS[name] || {}; }
