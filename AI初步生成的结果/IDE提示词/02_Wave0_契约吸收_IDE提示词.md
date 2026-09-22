# 给湛卢 IDE 的提示词 · Wave 0 契约核对

> 用法：打开湛卢 IDE，开到本仓库，粘贴下面提示词。生成/修改完成后，把 diff 发回给负责人审查，审查通过才允许提交。
> 用完在本文件末尾追加一条使用记录（日期、用了什么能力、产出）。

---

## 提示词 A：契约差异审计

```
请对比 main 分支与 docs/api-contract-v2 分支中 contracts/ 目录的全部差异（git diff main origin/docs/api-contract-v2 -- contracts/），输出一份结构化审计报告：

1. 按文件分组列出每个变更：新增/修改/删除了什么（字段、枚举值、路径、响应码、schema 定义）；
2. 标注每个变更的兼容性：对 v1.1.0 的调用方（A/B/C/D 四服务）来说是「向后兼容（加可选字段/新路径）」还是「破坏性（改类型/删字段/改语义/升主版本）」；
3. 对每个破坏性变更，说明如果 A 和 B 仍按 v1.1.0 实现，会在运行时出现什么具体故障（哪个请求会 400/409/解析失败）；
4. 输出一张「建议吸收清单」表格：变更项 | 建议（立即吸收/拆独立PR/退回） | 理由；
5. 不要修改任何文件，只输出报告。报告写入 AI初步生成的结果/IDE提示词/wave0-契约审计报告.md。
```

## 提示词 B：枚举一致性检查

```
请检查仓库中以下文件之间的一致性，不要修改文件，只输出报告：
- contracts/shared-enums.json
- contracts/openapi.yaml 中引用的全部枚举
- contracts/schemas/*.payload.schema.json 中的 enum 定义
- contracts/examples/*.json 中的实际取值

报告内容：
1. 三个层级（enums / openapi / schema / examples）之间每个枚举的值集合是否完全一致；
2. 每个示例报文的字段是否都能通过对应的 payload schema 校验（用 jsonschema 手工核对，列出任何不匹配）；
3. shared-enums.json 的 contractVersion 与 openapi.yaml 的 info.version 是否一致；
4. 结论列表：每处不一致给出修复建议（改哪个文件哪一行）。
```

## 提示词 C：check_repo.py 改动审查

```
请阅读 git diff main origin/docs/api-contract-v2 -- scripts/check_repo.py 的改动，回答：
1. 新增的每条校验规则分别在检查什么？
2. 是否有校验被写死为「v2 专属」（例如强制要求 contractVersion=2.0.0、强制要求某个 v2 新枚举存在）？如果有，列出具体行号——这会导致 main 的 v1.1.0 基线无法通过检查，必须改回中性校验；
3. 改动后 python scripts/check_repo.py --strict 在 main 基线上是否能通过？请实际运行并贴出输出；
4. 输出需要修改的行号和建议改法，但不要直接修改，等负责人确认。
```

---

## 使用记录（每次用完追加）

| 日期 | IDE能力 | 任务 | 产出 | 结果 |
| --- | --- | --- | --- | --- |
| 2026-09-22 | git diff 契约比对、jsonschema/payload 校验、脚本实跑（提示词 A/B/C） | Wave0 契约核对：差异审计 + 枚举一致性 + check_repo 改动审查 | `wave0-契约审计报告.md`（v2 有 13 项破坏性变更；v2 版 check_repo 在 main 基线跑挂 7 项需中性化；发现 openapi.yaml:2166 非法示例值 WORK_LOG_WRITE） | 待负责人审查 |
