/* ==========================================================================
   scoring.js —— 评分引擎（scoring.py 的忠实 JS 移植）
   --------------------------------------------------------------------------
   创新点 G（规则沙盒）与 C（反事实推演）共用。逐条对应
   apps/fault-warning/src/domain/scoring.py：

     ratio  = (value - normal) / (full - normal)      # 未截断偏离比例
     penalty = weight * min(1, max(0, ratio))          # 截断后扣分
     score  = 100 - Σ penalty
     任一 ratio ≥ 1.0 → 分数压到 ≤ 59.9（至少 HIGH）
     任一 ratio ≥ 1.5 → 分数压到 ≤ 39.9（至少 CRITICAL）
     风险分级：≥80 LOW / [60,80) MEDIUM / [40,60) HIGH / <40 CRITICAL

   移植原则：纯函数、无随机、无时间依赖——同一输入必得同一输出，
   与 B 服务 evaluate_sample() 的结果可逐条核对。
   注意：这是**前端试算**，仅用于沙盒/推演展示，不参与线上评估与判定。
   ========================================================================== */
"use strict";

/* 四项指标权重，合计 100（scoring.py WEIGHTS） */
const SCORING_WEIGHTS = { vibration: 40, temperature: 25, current: 20, speed: 15 };

/* 阈值默认值（scoring.py 常量）。沙盒里的滑块改的是这份配置的副本 */
const SCORING_DEFAULTS = {
  vibNormal: 3.0, vibFull: 6.0,          /* 振动速度 mm/s */
  tempNormal: 70, tempFull: 90,          /* 温度 ℃ */
  currNormal: 15, currFull: 30,          /* 电流 A */
  speedDevNormal: 0.05, speedDevFull: 0.15, /* 转速偏离比例 */
  nominalRpm: 1500,                       /* 额定转速 r/min */
};

/** 四指标未截断偏离比例（scoring.py metric_ratios） */
function jsRatios(s, cfg){
  cfg = cfg || SCORING_DEFAULTS;
  const num = v => Number(v) || 0;
  const raw = (v, n, f) => (num(v) - n) / (f - n);
  const speedDev = Math.abs(num(s.rotationalSpeedRpm) - cfg.nominalRpm) / cfg.nominalRpm;
  return {
    vibration:   raw(num(s.vibrationMmS), cfg.vibNormal, cfg.vibFull),
    temperature: raw(num(s.temperatureC), cfg.tempNormal, cfg.tempFull),
    current:     raw(num(s.currentA), cfg.currNormal, cfg.currFull),
    speed:       raw(speedDev, cfg.speedDevNormal, cfg.speedDevFull),
  };
}

/** 评分（scoring.py metric_penalties + _apply_severity_caps + evaluate_sample 的分数与风险部分） */
function jsScore(s, cfg){
  cfg = cfg || SCORING_DEFAULTS;
  const ratios = jsRatios(s, cfg);
  let score = 100;
  for (const k in ratios) score -= SCORING_WEIGHTS[k] * Math.min(1, Math.max(0, ratios[k]));
  const vals = Object.keys(ratios).map(k => ratios[k]);
  if (vals.some(r => r >= 1.5)) score = Math.min(score, 39.9);
  else if (vals.some(r => r >= 1.0)) score = Math.min(score, 59.9);
  score = Math.round(score * 10) / 10;
  const risk = score >= 80 ? "LOW" : score >= 60 ? "MEDIUM" : score >= 40 ? "HIGH" : "CRITICAL";
  return { score, risk, ratios };
}

/** 单指标扣分明细（沙盒展示用） */
function jsPenalties(s, cfg){
  cfg = cfg || SCORING_DEFAULTS;
  const ratios = jsRatios(s, cfg);
  const out = {};
  for (const k in ratios) out[k] = Math.round(SCORING_WEIGHTS[k] * Math.min(1, Math.max(0, ratios[k])) * 10) / 10;
  return out;
}

/** 疑似故障（scoring.py _FAULT_BY_METRIC）——返回扣分最大的指标对应故障 */
function jsTopFault(s, cfg){
  const p = jsPenalties(s, cfg);
  const top = Object.keys(p).sort((a, b) => p[b] - p[a])[0];
  if (!top || p[top] <= 0) return null;
  return {
    metric: top,
    penalty: p[top],
    fault: { vibration: "主轴轴承振动异常", temperature: "设备温升异常",
      current: "驱动电流异常", speed: "转速偏差异常" }[top],
  };
}
