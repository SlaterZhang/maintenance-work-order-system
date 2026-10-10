"""前端枚举台账与公共契约的一致性校验。

``web/js/enums.js`` 是界面侧唯一的枚举中文名/色调来源，但它是一份**副本**。
一旦契约里新增或改名枚举值，而前端台账没跟着改，界面上就会出现空白标签
或标错颜色（本项目已发生过：原型里凭印象写出 ``WAIT_FOR_PARTS`` 设备状态、
``OUT_OF_STOCK`` 备件状态、``EVALUATION_SUBMIT`` 权限等虚构值）。

本测试把"副本必须与契约逐字一致"变成机器可查的约束：新增枚举值时，
``contracts/shared-enums.json`` 与 ``web/js/enums.js`` 必须同步改，否则 CI 红。
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENUMS_JS = REPO_ROOT / "web" / "js" / "enums.js"
SHARED_ENUMS = REPO_ROOT / "contracts" / "shared-enums.json"

# enums.js 中需要逐字对齐契约的枚举块
CHECKED_BLOCKS = [
    "equipmentStatus",
    "riskLevel",
    "warningStatus",
    "workOrderStatus",
    "spareRequestStatus",
    "workOrderPriority",
    "workOrderSource",
    "notificationChannel",
    "roleCode",
    "permissionCode",
]


def _contract_codes(value) -> set[str]:
    """契约里的枚举可能是字符串数组，也可能是 ``{code: ...}`` 对象数组。"""
    if isinstance(value, list):
        return {
            item if isinstance(item, str) else item["code"]
            for item in value
        }
    raise AssertionError(f"未预期的枚举形态：{type(value)}")


def _js_blocks() -> dict[str, str]:
    source = ENUMS_JS.read_text(encoding="utf-8")
    return dict(re.findall(r'"(\w+)": \{(.*?)\n  \}', source, re.S))


class FrontendEnumLedgerTest(unittest.TestCase):
    """界面枚举台账必须与公共契约逐字一致。"""

    def test_frontend_enum_ledger_exists(self):
        self.assertTrue(
            ENUMS_JS.is_file(),
            "web/js/enums.js 缺失：界面枚举中文名无处收敛",
        )
        self.assertTrue(SHARED_ENUMS.is_file())

    def test_frontend_ledger_matches_contract(self):
        """每个受检枚举块的键集合必须与契约完全一致（不多不少）。"""
        contract = json.loads(SHARED_ENUMS.read_text(encoding="utf-8"))
        blocks = _js_blocks()
        problems: list[str] = []

        for name in CHECKED_BLOCKS:
            self.assertIn(name, contract, f"契约缺少枚举 {name}")
            block = blocks.get(name)
            if block is None:
                problems.append(f"{name}: enums.js 缺少该枚举块")
                continue

            actual = set(re.findall(r'"([A-Z_0-9]+)":', block))
            expected = _contract_codes(contract[name])

            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            if missing or extra:
                problems.append(f"{name}: 缺少 {missing} / 多出 {extra}")

        self.assertEqual(
            problems, [],
            "web/js/enums.js 与 contracts/shared-enums.json 不一致；"
            "枚举值是跨模块契约，必须同步修改：\n  " + "\n  ".join(problems),
        )

    def test_every_enum_entry_has_chinese_label(self):
        """受检块里每条枚举都要有中文名（避免界面上出现裸英文码）。"""
        blocks = _js_blocks()
        problems: list[str] = []

        for name in CHECKED_BLOCKS:
            block = blocks.get(name, "")
            # permissionCode 的值是纯字符串（"EQUIPMENT_READ": "设备查看"）
            for code, body in re.findall(
                r'"([A-Z_0-9]+)":\s*(\{[^}]*\}|"[^"]*")', block
            ):
                if body.startswith('"'):
                    if len(body) <= 2:
                        problems.append(f"{name}.{code}: 中文名为空")
                    continue
                zh = re.search(r'"zh":\s*"([^"]*)"', body)
                if not zh or not zh.group(1).strip():
                    problems.append(f"{name}.{code}: 缺少 zh 中文名")

        self.assertEqual(
            problems, [], "枚举缺少中文名：\n  " + "\n  ".join(problems),
        )

    def test_tone_vocabulary_is_closed(self):
        """色调只能是 tone 调色板里的键，避免写出界面上不存在的颜色名。"""
        source = ENUMS_JS.read_text(encoding="utf-8")
        palette_block = re.search(r'"tone": \{(.*?)\n  \}', source, re.S)
        self.assertIsNotNone(palette_block, "enums.js 缺少 tone 调色板")
        palette = set(re.findall(r'"(\w+)":', palette_block.group(1)))
        self.assertTrue({"ok", "warn", "bad", "info", "dim"} <= palette)

        used = set(re.findall(r'"tone":\s*"(\w+)"', source))
        unknown = sorted(used - palette)
        self.assertEqual(unknown, [], f"用到了调色板外的色调：{unknown}")

    def test_event_types_match_contract(self):
        """事件类型键必须与契约 eventType 一致（集成监控页直接展示）。"""
        contract = json.loads(SHARED_ENUMS.read_text(encoding="utf-8"))
        source = ENUMS_JS.read_text(encoding="utf-8")
        block = re.search(r'"eventType": \{(.*?)\n  \}', source, re.S)
        self.assertIsNotNone(block, "enums.js 缺少 eventType 块")
        # 只取事件名（顶层 PascalCase 键），排除块内的 zh/flow 字段
        actual = set(re.findall(r'"([A-Z][A-Za-z]*)": \{', block.group(1)))
        expected = _contract_codes(contract["eventType"])
        self.assertEqual(
            actual, expected,
            f"eventType 不一致：缺少 {sorted(expected - actual)} / "
            f"多出 {sorted(actual - expected)}",
        )


if __name__ == "__main__":
    unittest.main()
