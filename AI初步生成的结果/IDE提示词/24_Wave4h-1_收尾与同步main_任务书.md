# Wave 4h-1 任务书：收尾 Wave4g 分支并同步 main 基线

> 上游：`23_Wave4h_合库与PR_操作指引.md`（总方案）
> 本任务书只覆盖该指引的 **步骤 0 + 步骤 1**，即「把当前 wave4g 分支收尾并推送」+「把 origin/main 同步进 feat/d-advance-baseline，B 模块精确取 main 版」。
> 执行者：湛卢 IDE；验收者：负责人（助手复验）。

---

## 一、目标

1. 在 `feat/d-wave4g-entry-doc` 上完成 3 处收尾小修（`.gitignore` + 5 处措辞），提交并推送。
2. 在 `feat/d-advance-baseline` 上把 `origin/main` 合并进来，**`apps/fault-warning/` 整目录精确采用 main 版**，使分支对齐 main 基线。

## 二、前置状态（助手实测）

- 当前分支 `feat/d-wave4g-entry-doc`（HEAD `755b12b`），工作区有未提交的 `README.md`、未跟踪的 `docs/参赛材料/作品说明文档.md` 与 `23_...任务书.md`。
- `origin/main` = `1e821f1`，含 PR#3：**成员 B 正式预警模块（179 用例，实测全绿）**。
- `feat/d-advance-baseline`（`755b12b`）：behind origin/main **6** / ahead **31**。
- **干跑合并实测**：`origin/main` → `feat/d-advance-baseline` 仅 **14 个冲突文件，全部位于 `apps/fault-warning/`**；其余 103 个文件干净自动合并。

## 三、硬约束

1. **只按本任务书的命令执行，不要自行改变冲突解决策略**（尤其不要 `git merge --abort` 后换方案）。
2. `apps/fault-warning/` **整目录取 main 版**——不能只用 `git checkout --theirs`，因为 d-baseline 独有文件会残留（实测残留 10 个），必须删目录后重新取出。
3. 不改动 `contracts/`、`shared/`、其他三个模块（A/C/D 均无冲突，自动合并即可）。
4. 不引入新依赖，不 `push --force`，不直推 `main`。
5. 每步验证失败就**停下回报**，不要跳过。

---

## 四、操作步骤

### 步骤 A：收尾 `feat/d-wave4g-entry-doc`

**A1. `.gitignore` 末尾追加**（当前末尾是 `.zhanlu/`）：

```gitignore

# 本地工具产物
.playwright-mcp/
```

**A2. 删除已存在的调试产物目录**：

```bash
rm -rf .playwright-mcp
```

（PowerShell：`Remove-Item -Recurse -Force .playwright-mcp`）

**A3. 措辞修正（把写死的波次范围改掉）**

`docs/参赛材料/作品说明文档.md`：

- `21 份可追溯的任务书与提示词证据` → `20 余份可追溯的任务书与提示词证据`
- `目录下 21 份任务书与提示词（Wave0 ~ Wave4e，含方案、任务书、IDE 提示词与契约审计报告）` → `目录下 20 余份任务书与提示词（Wave0 起，含方案、任务书、IDE 提示词与契约审计报告）`
- `（21 份任务书与提示词，AI 辅助开发全过程证据）` → `（20 余份任务书与提示词，AI 辅助开发全过程证据）`

`README.md`：

- `# 21 份任务书/提示词（AI 辅助开发全过程证据）` → `# 20 余份任务书/提示词（AI 辅助开发全过程证据）`
- `全过程证据（Wave0 ~ Wave4e 的 21 份任务书与提示词）` → `全过程证据（Wave0 起共 20 余份任务书与提示词）`

**A4. 提交并推送**

```bash
git add "docs/参赛材料/作品说明文档.md" README.md .gitignore
git add "AI初步生成的结果/IDE提示词/22_Wave4g_参赛作品说明文档_任务书.md"
git add "AI初步生成的结果/IDE提示词/23_Wave4h_合库与PR_操作指引.md"
git add "AI初步生成的结果/IDE提示词/24_Wave4h-1_收尾与同步main_任务书.md"
git commit -m "docs(d): 新增六章参赛作品说明文档与作品级README，忽略本地调试产物"
git push -u origin feat/d-wave4g-entry-doc
```

### 步骤 B：同步 `origin/main` 进 `feat/d-advance-baseline`

```bash
git switch feat/d-advance-baseline
git pull --ff-only origin feat/d-advance-baseline
git fetch origin
git merge origin/main
```

此时应停在冲突状态（`git status` 显示 **14 个 `apps/fault-warning/` 文件 both added**）。**接着执行**：

```bash
rm -rf apps/fault-warning
git checkout origin/main -- apps/fault-warning
git add -A apps/fault-warning
```

**验证 1（必须为空输出才算通过）**：

```bash
git diff --stat origin/main -- apps/fault-warning
```

**验证 2（期望 179 passed）**：

```bash
python -m pytest apps/fault-warning -q
```

两项都通过后提交：

```bash
git commit -m "chore(d): 同步main基线，B模块采用成员B正式实现(PR#3，179用例)"
git push -u origin feat/d-advance-baseline
```

---

## 五、验收标准（助手将独立复验）

| 项 | 期望 |
| --- | --- |
| A1–A3 改动 | 仅 `.gitignore`、`README.md`、`作品说明文档.md`；无其他文件被改 |
| `feat/d-wave4g-entry-doc` | 已推送，`git status` 干净 |
| 同步后 `git diff --stat origin/main -- apps/fault-warning` | **空** |
| B 模块测试 | **179 passed** |
| 全量基线（同步后） | **A 21 / B 179 / C 75 / D 18 / 顶层 1 = 294** |
| `python scripts/check_repo.py` | **32 项 0 警告** |
| 未越界 | `contracts/`、`shared/`、A/C/D 模块无异常改动；无强推 |

---

## 六、给湛卢 IDE 的提示词正文（直接复制）

```text
你在仓库 maintenance-work-order-system 中工作，分支为 feat/d-wave4g-entry-doc。
本任务分两部分：先收尾当前分支，再把 origin/main 同步进 feat/d-advance-baseline。
严格按下列命令与修改执行，不要自行改动解决策略，不要 push --force，不要直推 main。
每步验证不通过就停下并报告，不要跳过。

【第一部分：收尾 feat/d-wave4g-entry-doc】
1) 在 .gitignore 末尾追加两行：
# 本地工具产物
.playwright-mcp/
2) 删除调试产物目录：rm -rf .playwright-mcp（PowerShell 用 Remove-Item -Recurse -Force .playwright-mcp）
3) 修改 docs/参赛材料/作品说明文档.md 中 3 处文字：
   - “21 份可追溯的任务书与提示词证据” → “20 余份可追溯的任务书与提示词证据”
   - “目录下 21 份任务书与提示词（Wave0 ~ Wave4e，含方案、任务书、IDE 提示词与契约审计报告）” → “目录下 20 余份任务书与提示词（Wave0 起，含方案、任务书、IDE 提示词与契约审计报告）”
   - “（21 份任务书与提示词，AI 辅助开发全过程证据）” → “（20 余份任务书与提示词，AI 辅助开发全过程证据）”
4) 修改 README.md 中 2 处文字：
   - “# 21 份任务书/提示词（AI 辅助开发全过程证据）” → “# 20 余份任务书/提示词（AI 辅助开发全过程证据）”
   - “全过程证据（Wave0 ~ Wave4e 的 21 份任务书与提示词）” → “全过程证据（Wave0 起共 20 余份任务书与提示词）”
5) 提交并推送：
   git add "docs/参赛材料/作品说明文档.md" README.md .gitignore
   git add "AI初步生成的结果/IDE提示词/22_Wave4g_参赛作品说明文档_任务书.md"
   git add "AI初步生成的结果/IDE提示词/23_Wave4h_合库与PR_操作指引.md"
   git add "AI初步生成的结果/IDE提示词/24_Wave4h-1_收尾与同步main_任务书.md"
   git commit -m "docs(d): 新增六章参赛作品说明文档与作品级README，忽略本地调试产物"
   git push -u origin feat/d-wave4g-entry-doc

【第二部分：同步 origin/main 进 feat/d-advance-baseline】
6) git switch feat/d-advance-baseline
   git pull --ff-only origin feat/d-advance-baseline
   git fetch origin
   git merge origin/main
   —— 此时会停在冲突状态：仅 apps/fault-warning/ 下 14 个文件 both added，属预期。
7) 解决冲突（整目录精确取 main 版，必须按此顺序）：
   rm -rf apps/fault-warning
   git checkout origin/main -- apps/fault-warning
   git add -A apps/fault-warning
8) 验证一：git diff --stat origin/main -- apps/fault-warning  —— 必须无输出。
9) 验证二：python -m pytest apps/fault-warning -q  —— 必须是 179 passed。
10) 提交并推送：
   git commit -m "chore(d): 同步main基线，B模块采用成员B正式实现(PR#3，179用例)"
   git push -u origin feat/d-advance-baseline

完成后回报：两个分支的 HEAD 短哈希、验证一输出（应为空）、验证二结果（179 passed）、以及 git status 是否干净。
不要继续做任何“下一步”（如合并 wave4f/wave4g、开 PR），等负责人指令。
```

---

## 七、使用记录（评分证据，务必登记）

| 日期 | IDE/模型 | 任务 | 产出 | 结果 |
| --- | --- | --- | --- | --- |
| 2026-10-04 | 湛卢 IDE（待填） | Wave4h-1 收尾 Wave4g 并同步 main 基线 | `.gitignore` 忽略项、5 处措辞修正、wave4g 推送、d-advance-baseline 对齐 main（B 取 179 用例版） | 待负责人验收 |
| 2026-10-04 | 湛卢 IDE / GLM-5.3 | Wave4h-1 全部步骤（A1–A4、步骤 B、验证 1/2、提交推送） | 收尾提交 `6a3fa65`（.gitignore 追加 `.playwright-mcp/`、删除调试产物目录、5 处"21 份→20 余份"措辞修正、22/23/24 任务书入库）已推送 wave4g；合并提交 `559eeae`（origin/main → d-advance-baseline，14 个 B 模块冲突按"删目录整取 main 版"解决，清除 d-baseline 独有残留文件）已推送 d-advance-baseline | 验证 1：`git diff --stat origin/main -- apps/fault-warning` 空输出（无差异）；验证 2：`python -m pytest apps/fault-warning -q` **179 passed**（13.82s）。`feat/d-wave4g-entry-doc` HEAD `6a3fa65`、`feat/d-advance-baseline` HEAD `559eeae`，两分支均已推送、工作区干净。待负责人验收 |
