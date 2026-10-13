"""test_ci_yaml.py — E4 GitHub Actions CI yaml 结构测试

覆盖:
  1. .github/workflows/ci.yml 文件存在
  2. YAML 可解析(无 syntax error)
  3. 含 3 OS(ubuntu/macos/windows)
  4. 含 pytest 步骤
  5. 含静默 except 验证步骤
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(__file__.replace("\\", "/").rsplit("/", 2)[0]))


class TestCiYamlStructure(unittest.TestCase):

    CI_PATH = Path(".github/workflows/ci.yml")

    def test_ci_yml_exists(self):
        """ci.yml 文件存在。"""
        self.assertTrue(self.CI_PATH.exists(), f"{self.CI_PATH} 不存在")

    def test_ci_yml_is_valid_yaml(self):
        """YAML 语法可解析。"""
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml 未装,跳过")
        data = yaml.safe_load(self.CI_PATH.read_text(encoding="utf-8"))
        self.assertIsNotNone(data)

    def test_ci_yml_has_3_os(self):
        """strategy.matrix.os 含 ubuntu/macos/windows。"""
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml 未装,跳过")
        data = yaml.safe_load(self.CI_PATH.read_text(encoding="utf-8"))
        os_list = data["jobs"]["test"]["strategy"]["matrix"]["os"]
        for expected in ["ubuntu-latest", "macos-latest", "windows-latest"]:
            self.assertIn(expected, os_list, f"缺 OS:{expected}")

    def test_ci_yml_runs_pytest(self):
        """含 pytest 运行步骤。"""
        text = self.CI_PATH.read_text(encoding="utf-8")
        self.assertIn("pytest", text)
        self.assertIn("tests/", text)

    def test_ci_yml_checks_silent_except(self):
        """含静默 except 验证步骤。"""
        text = self.CI_PATH.read_text(encoding="utf-8")
        self.assertIn("except.*pass", text)
        self.assertIn("except.*continue", text)

    def test_ci_yml_triggers_on_push_main(self):
        """push 触发器含 main 分支。"""
        try:
            import yaml
        except ImportError:
            self.skipTest("pyyaml 未装,跳过")
        data = yaml.safe_load(self.CI_PATH.read_text(encoding="utf-8"))
        on = data.get(True, data.get("on", {}))  # YAML 1.1 'on' 是 bool,需 True 访问
        if not on:
            on = data.get("on", {})
        push_branches = on.get("push", {}).get("branches", [])
        self.assertIn("main", push_branches, f"push 应触发 main 分支,实际 {push_branches}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
