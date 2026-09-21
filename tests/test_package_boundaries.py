from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from compensation_calculator import CompensationCalculator as LegacyCalculator
from personal_injury.domain.calculator import CompensationCalculator


class PackageBoundaryTests(unittest.TestCase):
    def test_legacy_entry_uses_the_single_packaged_calculator(self):
        self.assertIs(LegacyCalculator, CompensationCalculator)

        payload = {
            "disability_level": 8,
            "age": 35,
            "dependents": [{"age": 10, "supporters": 2}],
        }
        self.assertEqual(
            LegacyCalculator().calculate_total(payload),
            CompensationCalculator().calculate_total(payload),
        )

    def test_package_import_does_not_require_repository_root_modules(self):
        src_dir = Path(__file__).resolve().parents[1] / "src"
        script = (
            "import sys; "
            f"sys.path.insert(0, {str(src_dir)!r}); "
            "import personal_injury.web.app; "
            "from personal_injury.domain.calculator import CompensationCalculator; "
            "assert CompensationCalculator.__module__ == 'personal_injury.domain.calculator'"
        )
        completed = subprocess.run(
            [sys.executable, "-I", "-c", script],
            cwd=tempfile.gettempdir(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
