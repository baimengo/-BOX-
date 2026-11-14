import importlib.util
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import 红烧box as app


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class InstallerRuntimeTests(unittest.TestCase):
    def test_source_mode_uses_project_folder(self):
        self.assertEqual(app.BASE_DIR, PROJECT_ROOT)

    def test_frozen_subprocess_invokes_exe_without_python_flags(self):
        with patch.object(app, "FROZEN", True):
            self.assertEqual(app.build_self_command(["--check-install"]), [sys.executable, "--check-install"])

    def test_frozen_mode_keeps_runtime_data_outside_bundle(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "_MEIPASS", str(Path(directory) / "bundle"), create=True), \
             patch.dict(os.environ, {"LOCALAPPDATA": directory}):
            spec = importlib.util.spec_from_file_location(
                "runtime_paths_frozen_test", PROJECT_ROOT / "runtime_paths.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(module.DATA_DIR, Path(directory) / "红烧box")
            self.assertEqual(os.environ["PLAYWRIGHT_BROWSERS_PATH"], str(Path(directory) / "bundle" / "ms-playwright"))

    def test_first_installed_run_copies_bundled_mapping(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            package = root / "package"
            package.mkdir()
            template = "1001103: 1:31a-1-1\n1001104: 1:31a-1-2\n"
            (package / "当前映射表.txt").write_text(template, encoding="utf-8")
            data = root / "data"
            for name, value in (
                ("FROZEN", True), ("PACKAGE_DIR", package), ("BASE_DIR", data),
                ("MAPPING_FILE", data / "当前映射表.txt"),
                ("USER_DATA_DIR", data / "bilibili_user_data"),
                ("DEBUG_DIR", data / "debug"),
                ("MAPPING_HISTORY_DIR", data / "映射表历史"),
            ):
                stack.enter_context(patch.object(app, name, value))
            stack.enter_context(patch.object(app, "log"))
            self.assertEqual(app.load_mapping_table(), {
                "1001103": "1:31a-1-1", "1001104": "1:31a-1-2"
            })
            self.assertEqual((data / "当前映射表.txt").read_text(encoding="utf-8"), template)


if __name__ == "__main__":
    unittest.main()
