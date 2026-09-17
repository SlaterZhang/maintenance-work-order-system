from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ContractExamplesTest(unittest.TestCase):
    def test_repository_contracts_are_consistent(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_repo.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )


if __name__ == "__main__":
    unittest.main()
