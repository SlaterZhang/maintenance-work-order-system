# Wave 4h 合库与 PR 操作指引（负责人手动执行）

> 目标：把 D 的全部成果（含 Wave4f 身份权限、Wave4g 文档）安全合入 `main`，走分支 + PR，不直推 main。
> 依据：`docs/02_Git分支与提交规范.md`（main 必须始终可构建可测试；禁止强推 main）。
> 本文件为**操作指引**（非 GPT 任务书），由负责人手动执行，助手逐步核对。

---

## 零、现状实测（2026-10-04，助手独立复验）

| 分支 | HEAD | 相对 origin/main | 说明 |
| --- | --- | --- | --- |
| `origin/main` | `1e821f1` | — | 已含 PR#3：成员 B 正式预警模块（**179 用例**） |
| `feat/d-advance-baseline` | `755b12b` | behind 6 / ahead 31 | D 全套 + A 预生成 |
| `feat/d-wave4f-identity-roles` | `bcfcf11` | behind 6 / ahead 32 | 7 角色身份权限补全（已推远端） |
| `feat/d-wave4g-entry-doc` | `755b12b` | behind 6 / ahead 31 | 六章文档 + README（**未提交**） |

**关键结论（已实测，非推断）：**

1. `origin/main` 比 d-baseline **多 6 个提交**（就是 PR#3 那批 B 模块）。
2. 干跑合并 `origin/main` → `feat/d-advance-baseline`：**仅 14 个冲突文件，全部在 `apps/fault-warning/`**；其余 **103 个文件干净自动合并**。
3. 冲突根因：`apps/fault-warning/` 在两边的**历史无关**（main 是成员 B 的 PR#3，d-baseline 是 AI 预生成），形成 add/add 冲突。
4. **判定：B 模块整体取 `origin/main` 版**。证据 —— 两版实现同一套契约端点（GET `/api/v1/warnings`、GET `/warnings/{id}`、POST `/warnings/{id}/acknowledgements`、POST `/health-evaluations`、POST `/integration/warning-events`）；main 版经 PR 评审合入且独立 worktree 实测 **179 passed**；d-baseline 版为 AI 应急预生成，测试仅 28 项。
5. **A 模块**：d-baseline 已含 A 预生成（28 文件 +1070 行），合并时自动带入、无冲突。`origin/memberA`（`379455a`）为另一份 A 实现，**本指引不改动、不合并**（见第六节待决项）。

---

## 一、步骤 0：收尾当前 `feat/d-wave4g-entry-doc`（含两处小修）

在 `feat/d-wave4g-entry-doc` 分支上执行。

### 0.1 新增 `.gitignore` 忽略项（防误提交浏览器调试产物）

在 `.gitignore` 的 “# IDE and operating system” 段追加一行：

```gitignore
# 本地工具产物
.playwright-mcp/
```

并删除已存在的目录（未跟踪，直接删）：

```powershell
Remove-Item -Recurse -Force .playwright-mcp
```

### 0.2 修正波次范围措辞（问题 1）

两处文档把 `（Wave0 ~ Wave4e）` 改成 `（Wave0 起，编号见该目录）`：

- `docs/参赛材料/作品说明文档.md` 第 29 / 43 / 114 行附近（共 3 处）
- `README.md` 第 73 / 145 行附近（共 2 处）

> 原因：目录现含 21（wave4f 分支）/22（wave4g）号，写死 Wave4e 已过时。

### 0.3 提交并推送

```powershell
cd "E:\zh3g\Desktop\Soochow_University\graduate_third_one\云计算技术\移动云杯\project\maintenance-work-order-system"

git add "docs/参赛材料/作品说明文档.md" README.md .gitignore
git add "AI初步生成的结果/IDE提示词/22_Wave4g_参赛作品说明文档_任务书.md"
git add "AI初步生成的结果/IDE提示词/23_Wave4h_合库与PR_操作指引.md"

git commit -m "docs(d): 新增六章参赛作品说明文档与作品级README"

git push -u origin feat/d-wave4g-entry-doc
```

---

## 二、步骤 1：把 `origin/main` 同步进 `feat/d-advance-baseline`（解决 B 冲突）

```powershell
git switch feat/d-advance-baseline
git pull --ff-only origin feat/d-advance-baseline

git merge origin/main
```

此时会停在冲突状态，`git status` 应显示 **14 个 `apps/fault-warning/` 文件冲突**（`both added`）。

**解决方式：B 模块整体取 main 版**（`--theirs` = 正在并入的 `origin/main`）：

```powershell
git checkout --theirs -- apps/fault-warning
git add apps/fault-warning
git status --short          # 确认无 UU/AA 残留
```

**验证后再提交：**

```powershell
python -m pytest apps\fault-warning -q
```

期望：**179 passed**（若通过，说明成员 B 的正式实现完整、先前预生成版中的校验未丢失）。

```powershell
git commit -m "chore(d): 同步main基线，B模块采用成员B正式实现(PR#3，179用例)"
```

---

## 三、步骤 2 / 3：并入 Wave4f 与 Wave4g

```powershell
git merge feat/d-wave4f-identity-roles -m "feat(d): 并入Wave4f契约7角色身份权限与看板快捷登录"
git merge feat/d-wave4g-entry-doc    -m "docs(d): 并入Wave4g参赛作品说明文档与作品级README"
```

两步均应为**快进或干净合并**（wave4f/wave4g 都切自 d-baseline，无交叉冲突）。

---

## 四、步骤 4：同步文档中的测试数字（必做）

合入 B(179) + wave4f(D 32) 后，总数变化如下，需同步更新文档：

| 模块 | 原文档写的 | 合并后实际 |
| --- | --- | --- |
| A 设备监测 | 21 | 21 |
| B 故障预警 | **28** | **179** |
| C 维修工单 | 75 | 75 |
| D 集成质量 | **18** | **32** |
| 顶层契约 | 1 | 1 |
| **合计** | **142** | **308** |

需要改的位置：
- `README.md`：第 9 行、第 103 行注释、第 107 行附近（B 28 → 179、D 18 → 32、合计 142 → 308）
- `docs/参赛材料/作品说明文档.md`：第 98 行（“四模块 142 项测试全绿（A 21 / B 28 / C 75 / D 18）”）、第 118 行（“共 142 项”）

改完统一跑一次确认：

```powershell
python -m pytest apps\equipment-monitoring apps\fault-warning apps\maintenance apps\integration-quality tests -q
python scripts\check_repo.py
```

期望：**308 passed（含顶层 1）** + 门禁 **32 项 0 警告**。

```powershell
git add README.md "docs/参赛材料/作品说明文档.md"
git commit -m "docs(d): 同步合库后测试基线至308项"
git push -u origin feat/d-advance-baseline
```

---

## 五、步骤 5：开 PR → main，评审后合并

```powershell
gh pr create --base main --head feat/d-advance-baseline `
  --title "feat(d): 集成 D 身份权限/看板/部署与参赛文档，并入 A 预生成" `
  --body "见 docs/参赛材料/作品说明文档.md 与 AI初步生成的结果/IDE提示词/23_Wave4h_合库与PR_操作指引.md"
```

> 若未装 `gh`，用网页开 PR：`https://github.com/SlaterZhang/maintenance-work-order-system/compare/main...feat/d-advance-baseline`

**合并后立刻验证 main 可构建可测试**（本地）：

```powershell
git switch main
git pull --ff-only origin main
python -m pytest apps\equipment-monitoring apps\fault-warning apps\maintenance apps\integration-quality tests -q
python scripts\check_repo.py
```

期望仍是 **308 passed + 32 项 0 警告**。再起一次服务冒烟：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1
# 浏览器打开 web/dashboard.html，走一遍六条演示流程
powershell -ExecutionPolicy Bypass -File scripts\start_all.ps1 -Stop
```

---

## 六、待决项（负责人已拍板 2026-10-04）

1. **A 模块归属 —— 已决：不合并 `origin/memberA`**。d-baseline 自带 A 预生成（署名 zh3g），合并时自动带入、无冲突，即为交付版；`origin/memberA`（`379455a`，提交者 `LCX`）不并入 main。
2. **分支清理 —— 已决：只删负责人自己创建的分支**。各分支提交者实测如下，**队友的分支一律不删、由负责人联系对应队友处理**：

   | 分支 | 提交者 | 是否已并入 main | 处理方式 |
   | --- | --- | --- | --- |
   | `docs/api-contract-v2` | `gcw_xeImQCFy <zcrssg@qq.com>`（队友） | ✅ 已完全并入 | 联系队友确认后由**队友**删除 |
   | `feat/b-fault-warning` | `kuy-3117`（队友 B） | ✅ 已完全并入（PR#3） | 联系**队友 B** 删除 |
   | `origin/memberA` | `LCX`（队友 A） | ❌ 未并入 | 联系**队友 A** 处理 |
   | `feat/d-advance-baseline` | `zh3g`（负责人） | ❌ 本指引合并后进 main | 合并进 main 后**负责人自删** |
   | `feat/d-wave4f-identity-roles` | `zh3g`（负责人） | ❌ 本指引并入 | 并入基线后**负责人自删** |
   | `feat/d-wave4g-entry-doc` | `zh3g`（负责人） | ❌ 本指引并入 | 并入基线后**负责人自删** |

   删除前必须逐一确认 `git merge-base --is-ancestor <branch> main` 为真（即已并入）。
3. **`docs/所有链路与bug.md` 与 `docs/所有流程路线与bug.md`**：疑似同一文件的两个名字，建议统一为一个并确认已入库。

---

## 七、使用记录（评分证据）

| 日期 | 执行者 | 任务 | 产出 | 结果 |
| --- | --- | --- | --- | --- |
| 2026-10-04 | 助手（Hermes） | 编写合库与 PR 操作指引，含冲突面实测与 B 模块取舍判定 | `23_Wave4h_合库与PR_操作指引.md` | 待负责人执行 |
