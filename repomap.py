"""RepoMap: scan a project directory and summarize its structure.

The scan stops at ``MAX_DEPTH`` (or the ``--max-depth`` option) and every
directory that was cut off carries an explicit ``... (达到最大深度)`` marker,
so a truncated report can never be mistaken for a complete one.
"""


from __future__ import annotations

import json
import argparse
import os
import sys
from collections import Counter
from pathlib import Path


IGNORED_DIRS = {
    ".git", ".hg", ".svn",
    "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".tox", ".nox",
    ".venv", "venv", "env",
    "node_modules", "vendor",
    "dist", "build", "target",
    ".idea", ".vscode",
    ".next", ".nuxt",
    "coverage", ".coverage",
}

CONFIG_FILES = {
    "pyproject.toml": "Python 项目配置",
    "setup.py": "Python 安装配置",
    "setup.cfg": "Python 工具配置",
    "requirements.txt": "Python 依赖清单",
    "Pipfile": "Pipenv 依赖配置",
    "poetry.lock": "Poetry 锁定文件",
    "package.json": "Node.js 项目配置",
    "package-lock.json": "npm 锁定文件",
    "pnpm-lock.yaml": "pnpm 锁定文件",
    "yarn.lock": "Yarn 锁定文件",
    "Cargo.toml": "Rust 项目配置",
    "Cargo.lock": "Rust 锁定文件",
    "go.mod": "Go 模块配置",
    "go.sum": "Go 依赖校验文件",
    "pom.xml": "Maven 项目配置",
    "build.gradle": "Gradle 构建配置",
    "build.gradle.kts": "Gradle Kotlin 构建配置",
    "Dockerfile": "Docker 镜像构建配置",
    "docker-compose.yml": "Docker Compose 配置",
    "docker-compose.yaml": "Docker Compose 配置",
    "Makefile": "构建任务配置",
    "CMakeLists.txt": "CMake 构建配置",
    "tsconfig.json": "TypeScript 配置",
    "vite.config.js": "Vite 配置",
    "vite.config.ts": "Vite 配置",
}

MAX_DEPTH = 12

NO_EXTENSION = "[无扩展名]"
TRUNCATION_MARKER = "达到最大深度"


def _is_reportable(entry: os.DirEntry[str]) -> bool:
    """Return True when ``entry`` belongs in the report.

    Symbolic links are skipped so a scan can neither loop nor escape the
    project, and directories named in ``IGNORED_DIRS`` are treated as absent.
    """
    if entry.is_symlink():
        return False
    if entry.is_dir(follow_symlinks=False):
        return entry.name not in IGNORED_DIRS
    return True


def scan_project(root: Path, max_depth: int = MAX_DEPTH) -> dict:
    """Scan a project directory and return its tree and summary.

    The tree, the counters and the config list all describe the scanned part of
    the project: everything down to ``max_depth``. Every directory that was cut
    off carries a ``... (达到最大深度)`` marker, so the truncation is never
    silent.
    """
    root = root.expanduser().resolve()

    if not root.exists():
        raise FileNotFoundError(f"路径不存在：{root}")
    if not root.is_dir():
        raise NotADirectoryError(f"路径不是目录：{root}")

    file_count = 0
    dir_count = 0
    extension_counts = Counter()
    configs = []
    errors = []
    tree_lines = [f"{root.name}/"]

    def record_file(path: Path) -> None:
        nonlocal file_count
        file_count += 1
        extension_counts[path.suffix.lower() or NO_EXTENSION] += 1
        if path.name in CONFIG_FILES:
            configs.append(
                (path.relative_to(root).as_posix(), CONFIG_FILES[path.name])
            )

    def has_entries(directory: Path) -> bool:
        """Return True when ``directory`` holds anything the report would list.

        Only the immediate children are inspected: this is the depth limit, so
        deciding whether the cut actually hid something stays cheap and finite.
        """
        try:
            with os.scandir(directory) as iterator:
                return any(_is_reportable(entry) for entry in iterator)
        except OSError as exc:
            errors.append(f"{directory}: {exc}")
            return False

    def walk(directory: Path, prefix: str, depth: int) -> None:
        nonlocal dir_count

        if depth >= max_depth:
            if has_entries(directory):
                tree_lines.append(f"{prefix}└── ... ({TRUNCATION_MARKER})")
            return

        try:
            with os.scandir(directory) as iterator:
                entries = sorted(
                    (entry for entry in iterator if _is_reportable(entry)),
                    key=lambda entry: (
                        not entry.is_dir(follow_symlinks=False),
                        entry.name.casefold(),
                    ),
                )
        except OSError as exc:
            errors.append(f"{directory}: {exc}")
            tree_lines.append(f"{prefix}└── [无法读取：{exc}]")
            return

        for index, entry in enumerate(entries):
            is_last = index == len(entries) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")
            path = Path(entry.path)

            if entry.is_dir(follow_symlinks=False):
                dir_count += 1
                tree_lines.append(f"{prefix}{connector}{entry.name}/")
                walk(path, child_prefix, depth + 1)
            else:
                record_file(path)
                tree_lines.append(f"{prefix}{connector}{entry.name}")

    walk(root, "", 0)

    return {
        "root": root,
        "tree": tree_lines,
        "file_count": file_count,
        "dir_count": dir_count,
        "extensions": extension_counts,
        "configs": sorted(configs),
        "errors": errors,
    }


def print_report(result: dict) -> None:
    """Print a readable project report."""
    print("=== 项目目录树 ===")
    print("\n".join(result["tree"]))
    if any(TRUNCATION_MARKER in line for line in result["tree"]):
        print("\n（目录树与统计信息均在最大深度处截断，可用 --max-depth 调整）")

    print("\n=== 统计信息 ===")
    print(f"目录数：{result['dir_count']}")
    print(f"文件数：{result['file_count']}")

    print("\n=== 文件类型统计 ===")
    for extension, count in result["extensions"].most_common():
        print(f"{extension}: {count}")

    print("\n=== 项目配置文件 ===")
    if result["configs"]:
        for path, description in result["configs"]:
            print(f"{path} — {description}")
    else:
        print("未识别到常见项目配置文件")

    if result["errors"]:
        print(f"\n=== 扫描警告（{len(result['errors'])} 项）===")
        for error in result["errors"]:
            print(f"- {error}")

def print_json_report(result: dict) -> None:
    """Print the scan result as valid JSON."""
    json_result = {
        **result,
        "root": str(result["root"]),
        "extensions": dict(result["extensions"]),
    }

    sys.stdout.buffer.write(
    (json.dumps(json_result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )

def main() -> int:
    parser = argparse.ArgumentParser(
        description="扫描项目目录，输出目录树、文件统计和常见配置文件。"
    )
    parser.add_argument("path", help="要扫描的项目目录")
    parser.add_argument(
        "--max-depth",
        type=int,
        default=MAX_DEPTH,
        help=(
            f"目录树与统计的最大深度，默认 {MAX_DEPTH}"
            "（更深的内容以截断标记省略）"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出扫描结果",
    )
    args = parser.parse_args()

    if args.max_depth < 1:
        parser.error("--max-depth 必须大于等于 1")

    try:
        result = scan_project(Path(args.path), args.max_depth)
    except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"扫描失败：{exc}", file=sys.stderr)
        return 1

    if args.json:
        print_json_report(result)
    else:
        print_report(result)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
