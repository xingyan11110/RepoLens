#!/usr/bin/env bash
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

# RepoMap scanner suite.
#
# The shared runners (Makefile `check` and tests/run-all.sh) only collect
# tests/test_*.sh, so the Python cases in tests/test_repomap.py need a bash
# entry point. This mirrors tests/test_process_scope_rpc.sh, which drives
# tests/process_scope_rpc_cases.py: the payload prints its own PASS/FAIL lines
# and trailing `Results:` summary, and this file only has to locate an
# interpreter and forward the exit code.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${REPOLENS_PYTHON:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "  FAIL: a python3 interpreter is available"
  echo "    install python3, or point REPOLENS_PYTHON at an interpreter"
  echo ""
  echo "Results: 0 passed, 1 failed, 1 total"
  exit 1
fi

echo "=== RepoMap scanner (repomap.py) ==="
exec "$PYTHON_BIN" "$SCRIPT_DIR/tests/test_repomap.py"
