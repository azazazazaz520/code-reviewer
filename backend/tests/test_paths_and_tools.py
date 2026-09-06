"""路径边界和快照文件 Tool 的回归测试。"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.engine.paths import (
    PathSecurityError,
    file_line_count,
    normalize_diff_path,
    normalize_relative_path,
    resolve_snapshot_path,
)
from app.engine.tools.context import ApprovedContextRef, TaskToolContext
from app.engine.tools.read_file import read_file, read_file_in_context, read_file_page_in_context


class PathNormalisationTests(unittest.TestCase):
    def test_preserves_hidden_files_and_removes_only_explicit_prefix(self):
        self.assertEqual(normalize_relative_path("./.env"), ".env")
        self.assertEqual(normalize_relative_path(".github\\workflows\\ci.yml"), ".github/workflows/ci.yml")
        self.assertEqual(normalize_diff_path("a/src/app.py"), "src/app.py")

    def test_rejects_escape_and_absolute_paths(self):
        for path in ("../secret", "src/../../secret", "/etc/passwd", "C:\\secret", "\\\\server\\share", "src\x00/app.py"):
            with self.subTest(path=path):
                with self.assertRaises(PathSecurityError):
                    normalize_relative_path(path)

    def test_symlink_is_checked_after_resolution(self):
        with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as outside_dir:
            root = Path(temp_dir)
            outside = Path(outside_dir) / "secret.txt"
            outside.write_text("secret", encoding="utf-8")
            link = root / "linked.txt"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("当前环境不支持创建符号链接")

            with self.assertRaises(PathSecurityError):
                resolve_snapshot_path(root, "linked.txt")


class ReadFileContextTests(unittest.TestCase):
    def test_line_count_uses_streaming_reader(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "large.py"
            target.write_text("first\nsecond\nthird", encoding="utf-8")

            with mock.patch.object(Path, "read_text", side_effect=AssertionError("不应读取完整文本")):
                self.assertEqual(file_line_count(target), 3)

    def test_direct_tool_call_is_rejected(self):
        self.assertIn("requires task snapshot context", read_file("anything.py"))

    def test_reads_only_approved_snapshot_ranges_and_pages(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "src" / "app.py"
            target.parent.mkdir()
            target.write_text("\n".join(f"line-{n}" for n in range(1, 405)), encoding="utf-8")
            context = TaskToolContext(
                repo_root=str(root),
                revision="rev-1",
                approved_context_refs=(
                    ApprovedContextRef("src/app.py", 1, 404),
                ),
            )

            first = read_file_page_in_context(context, "src/app.py", 1, 200)
            second = read_file_page_in_context(context, "src/app.py", 201, 200)
            third = read_file_page_in_context(context, "src/app.py", 401, 200)
            absolute = read_file_in_context(context, str(target), 1, 1)
            self.assertEqual((first.start_line, first.end_line, first.total_lines), (1, 200, 404))
            self.assertFalse(first.complete)
            self.assertFalse(second.complete)
            self.assertTrue(third.complete)
            self.assertIn("1|line-1", absolute)
            self.assertNotIn(str(root), absolute)
            self.assertIn("201|line-201", read_file_in_context(context, "src/app.py", 201, 1))

            denied = read_file_in_context(context, "src/app.py", 405, 1)
            self.assertTrue(denied.startswith("Error:"))

    def test_unapproved_file_and_range_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "allowed.py").write_text("allowed\nsecond\n", encoding="utf-8")
            (root / "secret.py").write_text("secret\n", encoding="utf-8")
            context = TaskToolContext(
                repo_root=str(root),
                revision="rev-1",
                approved_context_refs=(ApprovedContextRef("allowed.py", 1, 1),),
            )

            self.assertIn("not approved", read_file_in_context(context, "secret.py"))
            self.assertIn("not approved", read_file_in_context(context, "allowed.py", 2, 1))
            self.assertIn("不能包含 ..", read_file_in_context(context, "../secret.py"))


if __name__ == "__main__":
    unittest.main()
