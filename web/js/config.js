/* 全局配置与共享状态（阶段2前端拆分，2026-10-06） */
"use strict";
const REFRESH_MS = 5000;

const state = {
  token: localStorage.getItem("ims_token") || "",
  user: JSON.parse(localStorage.getItem("ims_user") || "null"),
  equipment: [], warnings: [], orders: [],
  healthMap: {},            // equipmentId -> {score, riskLevel, fault, action, warningId, status}
  latestEvaluation: {},     // equipmentId -> 最近一次注入评估结果（优先级高于 healthMap，避免被旧预警数据覆盖）
  openEq: null, expandedOrder: null,
  charts: {}, chartOk: false, chartData: [],
  telemetrySeen: new Set(),   // 已渲染样本 sampleId，用于图表增量追加
  _openForm: null,            // 填写中的工单操作表单 {orderId, action, values}
  assignees: null,            // 可派单工程师列表（D-API-03，懒加载）
  warnDenied: false,          // 当前角色无 WARNING_READ：预警区降级展示
  sessionExpiredNotified: false, // 401 只引导一次重新登录（P2-6）
  timer: null, polling: false, view: "dashboard", lastFetch: 0,
};

/* 工单状态中文映射 */
const STATUS_ZH = {
  PENDING_CONFIRMATION:"待确认", PENDING_ASSIGNMENT:"待分配", PENDING_ACCEPTANCE:"待接单",
  PENDING_MAINTENANCE:"待维修", MAINTAINING:"维修中", WAITING_PARTS:"等待备件",
  PENDING_INSPECTION:"待验收", COMPLETED:"已完成", CANCELLED:"已取消",
};
/* 预警状态中文映射（P2-9：预警列表/详情不再显示原始枚举） */
const WARN_STATUS_ZH = {
  OPEN:"预警中", ACKNOWLEDGED:"已确认", RESOLVED:"已解决",
  CLOSED:"已关闭", LINKED_TO_ORDER:"已转工单",
  CANCELLED:"已取消", FALSE_POSITIVE:"误报",
};
const EQ_STATUS_ZH = {
  RUNNING:"运行中", STOPPED:"已停止", TRIAL_RUNNING:"试运行",
  MAINTAINING:"维修中", UNKNOWN:"未知", OFFLINE:"离线",
};
const EQ_STATUS_COLOR = {
  RUNNING:"var(--green)", STOPPED:"#6b7a94", TRIAL_RUNNING:"var(--yellow)",
  MAINTAINING:"var(--red)",
};
/* 工单状态机可用动作（对照 C 服务状态机） */
const TRANSITIONS = {
  PENDING_CONFIRMATION:["CONFIRM","CANCEL"],
  PENDING_ASSIGNMENT:["ASSIGN","CANCEL"],
  PENDING_ACCEPTANCE:["ASSIGN","ACCEPT","CANCEL"],
  PENDING_MAINTENANCE:["START"],
  MAINTAINING:["WAIT_FOR_PARTS","SUBMIT_FOR_INSPECTION"],
  WAITING_PARTS:["RESUME"],
  PENDING_INSPECTION:["PASS_INSPECTION","REJECT_INSPECTION"],
  COMPLETED:[], CANCELLED:[],
};
const ACTION_META = {
  CONFIRM:             {label:"确认工单", perm:"WORK_ORDER_CONFIRM",  kind:"cyan"},
  ASSIGN:              {label:"派单",     perm:"WORK_ORDER_ASSIGN",   kind:"cyan", form:"assign"},
  ACCEPT:              {label:"接单",     perm:"WORK_ORDER_ACCEPT",   kind:"cyan"},
  START:               {label:"开始维修", perm:"WORK_ORDER_MAINTAIN", kind:"green"},
  WAIT_FOR_PARTS:      {label:"等待备件", perm:"WORK_ORDER_MAINTAIN", kind:"ghost"},
  RESUME:              {label:"恢复维修", perm:"WORK_ORDER_MAINTAIN", kind:"green"},
  SUBMIT_FOR_INSPECTION:{label:"提交验收", perm:"WORK_ORDER_MAINTAIN", kind:"green", form:"submit"},
  PASS_INSPECTION:     {label:"验收通过", perm:"WORK_ORDER_INSPECT",  kind:"green", form:"pass"},
  REJECT_INSPECTION:   {label:"验收驳回", perm:"WORK_ORDER_INSPECT",  kind:"danger", form:"reject"},
  CANCEL:              {label:"取消工单", perm:"WORK_ORDER_CANCEL",   kind:"ghost", form:"cancel"},
};
const LIGHT_COLOR = {green:"var(--green)", yellow:"var(--yellow)", red:"var(--red)", gray:"#6b7a94"};
