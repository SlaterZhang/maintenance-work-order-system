# Wave 4h-2 任务书：并入 wave4f / wave4g 并统一测试数字

> 上游：`23_Wave4h_合库与PR_操作指引.md`（总方案）步骤 2 ~ 4。
> 执行者：湛卢 IDE；验收者：负责人（助手复验）。
> 本任务书只做「把两个已验证分支并入基线 + 同步文档数字」，**不开 PR**。

---

## 一、目标

1. 把 `feat/d-wave4f-identity-roles`（7 身份权限补全）并入 `feat/d-advance-baseline`。
2. 把 `feat/d-wave4g-entry-doc`（六章作品文档 + README + 忽略项）并入 `feat/d-advance-baseline`。
3. 把交付文档里的测试数字从旧的 **142（A21/B28/C75/D18）** 同步为真实基线 **308（A21/B179/C75/D32）**。

## 二、前置状态（助手干跑实测）

| 对象 | HEAD | 说明 |
| --- | --- | --- |
| `feat/d-advance-baseline` | `559eeae` | 已对齐 main（B 取 179 用例版） |
| `feat/d-wave4f-identity-roles` | `bcfcf11` | 7 身份 / 21 权限补全 |
| `feat/d-wave4g-entry-doc` | `ffeb0df` | 六章文档 + README + `.gitignore` |

- **两次合并已预演：均零冲突**（wave4f 基点即 755b12b，wave4g 只动文档，互不重叠）。
- **合并后全量实测：A 21 / B 179 / C 75 / D 32 / 顶层 1 = 308 全过；`check_repo` 32 项 0 警告。**
- 合并后 `apps/integration-quality` 由 18 → **32** 项（wave4f 新增 14 项身份/权限测试）。

## 三、硬约束

1. 两次合并都是**纯合并**，不得改动任何代码内容；若出现冲突就**停下回报**（理论上不会）。
2. **只改交付文档的 4 个数字位置**，`AI初步生成的结果/IDE提示词/` 下历史任务书里的旧数字是**历史记录，禁止回改**。
3. 不 `push --force`，不直推 `main`，**不开 PR**（下一阶段再做）。
4. 合并与数字修改**分成独立提交**，便于追溯。

---

## 四、操作步骤

### 步骤 A：合并两个分支

```bash
git switch feat/d-advance-baseline
git pull --ff-only origin feat/d-advance-baseline
git fetch origin
git merge --no-edit origin/feat/d-wave4f-identity-roles
git merge --no-edit origin/feat/d-wave4g-entry-doc
```

合并后应立即验证（期望 **D = 32**）：

```bash
python -m pytest apps/integration-quality -q
```

### 步骤 B：同步文档测试数字（4 处）

**B1. `docs/参赛材料/作品说明文档.md` 第 98 行**

```diff
-四模块 142 项测试全绿（A 21 / B 28 / C 75 / D 18），另有顶层契约示例测试 1 项
+四模块 307 项测试全绿（A 21 / B 179 / C 75 / D 32），另有顶层契约示例测试 1 项
```

**B2. `docs/参赛材料/作品说明文档.md` 第 118 行**

```diff
-测试与门禁：各模块 `python -m pytest -q` 共 142 项，仓库根 `python scripts/check_repo.py` 32 项 0 警告。
+测试与门禁：各模块 `python -m pytest -q` 共 307 项（另有顶层契约示例测试 1 项，合计 308），仓库根 `python scripts/check_repo.py` 32 项 0 警告。
```

**B3. `README.md` 第 9 行**

```diff
-- 质量门禁：四模块 142 项测试全绿（A 21 / B 28 / C 75 / D 18）+ 顶层契约示例测试 1 项，`scripts/check_repo.py` 契约门禁 32 项 0 警告；
+- 质量门禁：四模块 307 项测试全绿（A 21 / B 179 / C 75 / D 32）+ 顶层契约示例测试 1 项（合计 308），`scripts/check_repo.py` 契约门禁 32 项 0 警告；
```

**B4. `README.md` 第 103 行**

```diff
-# 四模块共 142 项测试（A 21 / B 28 / C 75 / D 18）
+# 四模块共 307 项测试（A 21 / B 179 / C 75 / D 32）
```

### 步骤 C：提交并推送

```bash
git add "docs/参赛材料/作品说明文档.md" README.md
git add "AI初步生成的结果/IDE提示词/25_Wave4h-2_并入分支与统一数字_任务书.md"
git commit -m "docs(d): 同步交付文档测试基线至307项(A21/B179/C75/D32)"
git push -u origin feat/d-advance-baseline
```

---

## 五、验收标准（助手将独立复验）

| 项 | 期望 |
| --- | --- |
| 两次合并 | 均为 merge 提交（双父），零冲突 |
| 合并未改代码 | `git diff` 除文档数字外无源码改动 |
| D 模块测试 | **32 passed** |
| 全量基线 | **A 21 / B 179 / C 75 / D 32 / 顶层 1 = 308** |
| 文档数字 | 4 处全部为 `307（A 21 / B 179 / C 75 / D 32）`，无 `142` / `B 28` / `D 18` 残留 |
| 历史任务书 | `AI初步生成的结果/IDE提示词/17|22|23` 未被改动 |
| `check_repo.py` | **32 项 0 警告** |
| 分支状态 | 已推送、工作区干净、未开 PR |

---

## 六、给湛卢 IDE 的提示词正文（直接复制）

```text
你在仓库 maintenance-work-order-system 中工作。本任务把两个已验证分支并入 feat/d-advance-baseline，
并把交付文档里的测试数字同步为真实基线。严格按命令执行；出现冲突就停下报告；不要开 PR；不要 push --force。

【步骤 A：合并两个分支】
git switch feat/d-advance-baseline
git pull --ff-only origin feat/d-advance-baseline
git fetch origin
git merge --no-edit origin/feat/d-wave4f-identity-roles
git merge --no-edit origin/feat/d-wave4g-entry-doc
合并后验证：python -m pytest apps/integration-quality -q  —— 必须是 32 passed。

【步骤 B：同步文档数字，只改下面 4 处，别的一律不动】

1) docs/参赛材料/作品说明文档.md 第 98 行：
   把 “四模块 142 项测试全绿（A 21 / B 28 / C 75 / D 18），另有顶层契约示例测试 1 项”
   改为 “四模块 307 项测试全绿（A 21 / B 179 / C 75 / D 32），另有顶层契约示例测试 1 项”

2) docs/参赛材料/作品说明文档.md 第 118 行：
   把 “测试与门禁：各模块 `python -m pytest -q` 共 142 项，仓库根 `python scripts/check_repo.py` 32 项 0 警告。”
   改为 “测试与门禁：各模块 `python -m pytest -q` 共 307 项（另有顶层契约示例测试 1 项，合计 308），仓库根 `python scripts/check_repo.py` 32 项 0 警告。”

3) README.md 第 9 行：
   把 “四模块 142 项测试全绿（A 21 / B 28 / C 75 / D 18）+ 顶层契约示例测试 1 项”
   改为 “四模块 307 项测试全绿（A 21 / B 179 / C 75 / D 32）+ 顶层契约示例测试 1 项（合计 308）”

4) README.md 第 103 行：
   把 “# 四模块共 142 项测试（A 21 / B 28 / C 75 / D 18）”
   改为 “# 四模块共 307 项测试（A 21 / B 179 / C 75 / D 32）”

注意：AI初步生成的结果/IDE提示词/ 下历史任务书里的旧数字是历史记录，禁止回改。

【步骤 C：提交并推送】
git add "docs/参赛材料/作品说明文档.md" README.md
git add "AI初步生成的结果/IDE提示词/25_Wave4h-2_并入分支与统一数字_任务书.md"
git commit -m "docs(d): 同步交付文档测试基线至307项(A21/B179/C75/D32)"
git push -u origin feat/d-advance-baseline

【完成后回报】
- 两个 merge 提交的短哈希；
- python -m pytest apps/integration-quality -q 结果（应 32 passed）；
- 四模块全量结果（应 A21/B179/C75/D32/顶层1 = 308）；
- python scripts/check_repo.py 结果（应 32 项 0 警告）；
- git status 是否干净。
不要做任何“下一步”（如开 PR），等负责人指令。
```

---

## 七、使用记录（评分证据，务必登记）

| 日期 | IDE/模型 | 任务 | 产出 | 结果 |
| --- | --- | --- | --- | --- |
| 2026-10-04 | 湛卢 IDE（待填） | Wave4h-2 并入 wave4f/wave4g 并统一测试数字 | 两个合并提交 + 文档数字同步至 307/308 | 待负责人验收 |
| 2026-10-04 | 湛卢 IDE / GLM-5.3 | Wave4h-2 全部步骤（A 合并 + B 数字同步 + C 提交推送） | merge1（wave4f，零冲突，并入 7 身份/21 权限 + 14 项 D 测试）、merge2（wave4g，零冲突，并入六章文档/README/.gitignore）；数字同步提交 `474bf14`（README 2 处、作品说明文档 2 处，142/B28/D18→307/B179/D32，历史任务书未回改） | D 模块 **32 passed**；全量 **A 21 / B 179 / C 75 / D 32 / 顶层 1 = 308 全过**；`check_repo` **32 项 0 警告**；`feat/d-advance-baseline` HEAD `474bf14` 已推送，工作区干净。未开 PR、未强推、未改源码。待负责人验收 |
