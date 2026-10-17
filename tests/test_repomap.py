#!/usr/bin/env python3
# Copyright 2025-2026 Bootstrap Academy
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for the RepoMap scanner (``repomap.py``).

The cases can be driven three ways: directly (``python3 tests/test_repomap.py``),
through unittest (``python3 -m unittest tests.test_repomap``) or through the
bash entry point the shared runners collect (``bash tests/test_repomap.sh``).
Running the file as a script prints one ``PASS:``/``FAIL:`` line per case plus
the ``Results:`` summary the .sh suites in this repository emit.
"""

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    # Keep the suite runnable from any working directory: repomap.py lives in
    # the repository root and is not installed as a package.
    sys.path.insert(0, str(REPO_ROOT))

from repomap import (  # noqa: E402
    NO_EXTENSION,
    TRUNCATION_MARKER,
    main as repomap_main,
    print_report,
    scan_project,
)


class RepoMapTestCase(unittest.TestCase):
    """Base case providing a throwaway project directory."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def build_nested(self):
        """Create ``a/b/c/file.txt`` and return the ``c`` directory."""
        nested = self.root / "a" / "b" / "c"
        nested.mkdir(parents=True)
        (nested / "file.txt").write_text("data", encoding="utf-8")
        return nested


class TestScanProject(RepoMapTestCase):
    def test_tree_and_file_statistics(self):
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text(
            "print('hello')", encoding="utf-8"
        )
        (self.root / "README.md").write_text("# Demo", encoding="utf-8")

        result = scan_project(self.root)

        self.assertEqual(result["file_count"], 2)
        self.assertEqual(result["dir_count"], 1)
        self.assertEqual(result["extensions"][".py"], 1)
        self.assertEqual(result["extensions"][".md"], 1)
        self.assertTrue(any("main.py" in line for line in result["tree"]))

    def test_files_without_extension_are_counted(self):
        (self.root / "Makefile").write_text("all:", encoding="utf-8")

        result = scan_project(self.root)

        self.assertEqual(result["extensions"][NO_EXTENSION], 1)
        self.assertEqual(result["file_count"], 1)

    def test_ignored_directories(self):
        ignored = self.root / ".git"
        ignored.mkdir()
        (ignored / "hidden.txt").write_text("ignored", encoding="utf-8")
        (self.root / "visible.txt").write_text("visible", encoding="utf-8")

        result = scan_project(self.root)

        self.assertEqual(result["file_count"], 1)
        self.assertFalse(any(".git" in line for line in result["tree"]))

    def test_detect_project_config(self):
        (self.root / "pyproject.toml").write_text("[project]", encoding="utf-8")

        result = scan_project(self.root)

        self.assertEqual(len(result["configs"]), 1)
        self.assertEqual(result["configs"][0][0], "pyproject.toml")

    def test_detect_project_config_in_subdirectory(self):
        package = self.root / "packages" / "api"
        package.mkdir(parents=True)
        (package / "pyproject.toml").write_text("[project]", encoding="utf-8")

        result = scan_project(self.root)

        self.assertEqual(
            [path for path, _ in result["configs"]],
            ["packages/api/pyproject.toml"],
        )

    def test_missing_path(self):
        missing = self.root / "does-not-exist"

        with self.assertRaises(FileNotFoundError):
            scan_project(missing)

    def test_path_is_file(self):
        file_path = self.root / "hello.txt"
        file_path.write_text("hello", encoding="utf-8")

        with self.assertRaises(NotADirectoryError):
            scan_project(file_path)


class TestMaxDepth(RepoMapTestCase):
    def test_truncation_marker_marks_directory_only_subtrees(self):
        """A cut-off directory holding only directories must still be marked."""
        self.build_nested()

        result = scan_project(self.root, max_depth=2)

        self.assertTrue(any(TRUNCATION_MARKER in line for line in result["tree"]))
        self.assertFalse(any("c/" in line for line in result["tree"]))

    def test_counts_stop_at_the_depth_limit(self):
        self.build_nested()

        result = scan_project(self.root, max_depth=2)

        # Only a and b are scanned; the marker is what tells the user that c
        # and its file were left out of the tree and the counters alike.
        self.assertEqual(result["dir_count"], 2)
        self.assertEqual(result["file_count"], 0)
        self.assertTrue(any(TRUNCATION_MARKER in line for line in result["tree"]))

    def test_ignored_directories_below_the_limit_are_not_counted(self):
        boundary = self.root / "a" / "b"
        boundary.mkdir(parents=True)
        ignored = boundary / "node_modules"
        ignored.mkdir()
        (ignored / "dep.js").write_text("//", encoding="utf-8")

        result = scan_project(self.root, max_depth=2)

        self.assertEqual(result["file_count"], 0)
        self.assertFalse(any(TRUNCATION_MARKER in line for line in result["tree"]))

    def test_empty_directory_is_not_marked_as_truncated(self):
        (self.root / "a").mkdir()

        result = scan_project(self.root, max_depth=1)

        self.assertFalse(any(TRUNCATION_MARKER in line for line in result["tree"]))


def _run_cli(argv):
    """Run ``repomap.main()`` with ``argv`` and return (code, stdout, stderr).

    The scanner entry point is imported as ``repomap_main`` because this module
    has an entry point of its own: calling a local ``main()`` here would recurse
    into the whole suite instead of exercising the CLI.
    """
    stdout, stderr = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "argv", ["repomap.py", *argv]):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = repomap_main()
    return code, stdout.getvalue(), stderr.getvalue()


class TestReport(RepoMapTestCase):
    """Cover print_report() and the repomap.main() error paths in-process."""

    def test_report_lists_tree_and_summary(self):
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text(
            "print('hello')", encoding="utf-8"
        )

        report = io.StringIO()
        with redirect_stdout(report):
            print_report(scan_project(self.root))

        self.assertIn("src/", report.getvalue())
        self.assertIn("main.py", report.getvalue())
        self.assertIn("文件数：1", report.getvalue())

    def test_report_points_out_truncated_trees(self):
        self.build_nested()

        report = io.StringIO()
        with redirect_stdout(report):
            print_report(scan_project(self.root, max_depth=2))

        self.assertIn(TRUNCATION_MARKER, report.getvalue())
        self.assertIn("截断", report.getvalue())

    def test_missing_path_is_reported_on_stderr(self):
        code, _, stderr = _run_cli([str(self.root / "does-not-exist")])

        self.assertEqual(code, 1)
        self.assertIn("路径不存在", stderr)

    def test_invalid_max_depth_is_rejected(self):
        (self.root / "a").mkdir()

        with self.assertRaises(SystemExit) as caught:
            _run_cli([str(self.root), "--max-depth", "0"])

        self.assertEqual(caught.exception.code, 2)


class TestCommandLine(RepoMapTestCase):
    """A single end-to-end run, so the ``repomap.py <dir>`` entry point and its
    exit code stay covered without paying for one interpreter per case."""

    def test_report_is_printed_with_exit_zero(self):
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text(
            "print('hello')", encoding="utf-8"
        )
        env = dict(os.environ, PYTHONIOENCODING="utf-8")

        completed = subprocess.run(
            [sys.executable, str(REPO_ROOT / "repomap.py"), str(self.root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("main.py", completed.stdout)
        self.assertIn("文件数：1", completed.stdout)


class _Reporter(unittest.TextTestResult):
    """Print one PASS/FAIL line per case, in the shape the .sh suites use."""

    def _case_name(self, test):
        return test.id().split(".")[-1]

    def addSuccess(self, test):
        super().addSuccess(test)
        print(f"PASS: {self._case_name(test)}")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        print(f"FAIL: {self._case_name(test)}: {err[0].__name__}: {err[1]}")

    def addError(self, test, err):
        super().addError(test, err)
        print(f"FAIL: {self._case_name(test)}: {err[0].__name__}: {err[1]}")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        print(f"SKIP: {self._case_name(test)}: {reason}")


def run_repomap_tests() -> int:
    """Run the suite and print the PASS/FAIL lines the .sh runners parse."""
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(
        resultclass=_Reporter, stream=io.StringIO(), verbosity=0
    ).run(suite)
    failed = len(result.failures) + len(result.errors)
    print("")
    print(
        f"Results: {result.testsRun - failed} passed, "
        f"{failed} failed, {result.testsRun} total"
    )
    if failed:
        print("")
        for _, trace in result.failures + result.errors:
            print(trace, end="")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(run_repomap_tests())
