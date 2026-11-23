# Copyright 2026 Tomoya Fujita
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

"""The evidence ledger (design section 6.4).

``ros2-gate run -- <cmd>`` records the command, its exit code, the time, HEAD,
and a hash of the working tree in ``.ros2-agent-kit/evidence.jsonl`` at the
repository root. ``ros2-gate evidence`` prints only the entries whose tree hash
matches the current tree, so a claim can be checked against what was run.

The tree hash covers HEAD, the diff of tracked files against HEAD, and the
contents of untracked files, except the usual colcon output directories and the
ledger directory itself, so a build does not invalidate its own evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

from . import gitinfo

LEDGER_DIR = '.ros2-agent-kit'
LEDGER_FILE = 'evidence.jsonl'
EXCLUDED_UNTRACKED = ('build/', 'install/', 'log/', LEDGER_DIR + '/')

KINDS: Dict[str, re.Pattern] = {
    'build': re.compile(r'\bcolcon\s+build\b|\bcmake\s+--build\b|\bmake\b|\bninja\b|\bcatkin\b'),
    'test': re.compile(r'\bcolcon\s+test\b|\bctest\b|\bpytest\b|\blaunch_test\b|\bgtest\b'),
    'lint': re.compile(r'\bament_(?:uncrustify|cpplint|flake8|pep257|lint_cmake|copyright|xmllint|'
                       r'lint_auto|mypy|clang_format|clang_tidy|cppcheck)\b|\bpre-commit\b'),
}


def classify(command: str) -> List[str]:
    """Which kinds of evidence a command provides. ``colcon test`` also covers lint."""
    kinds = [k for k, pat in KINDS.items() if pat.search(command)]
    if 'test' in kinds and re.search(r'\bcolcon\s+test\b', command):
        kinds.append('lint')
    return kinds


def ensure_excluded(top: Path) -> None:
    """Add the ledger directory to ``.git/info/exclude`` once."""
    try:
        exclude = Path(gitinfo.run_git(['rev-parse', '--git-path', 'info/exclude'], str(top)).strip())
        if not exclude.is_absolute():
            exclude = top / exclude
        exclude.parent.mkdir(parents=True, exist_ok=True)
        line = LEDGER_DIR + '/'
        existing = exclude.read_text(encoding='utf-8') if exclude.exists() else ''
        if line not in existing.split('\n'):
            with exclude.open('a', encoding='utf-8') as fh:
                if existing and not existing.endswith('\n'):
                    fh.write('\n')
                fh.write(line + '\n')
    except (gitinfo.GitError, OSError):
        pass


def ledger_path(cwd: Optional[str] = None) -> Path:
    top = Path(gitinfo.toplevel(cwd))
    ensure_excluded(top)
    return top / LEDGER_DIR / LEDGER_FILE


def tree_hash(cwd: Optional[str] = None) -> str:
    top = Path(gitinfo.toplevel(cwd))
    h = hashlib.sha256()
    head = gitinfo.run_git(['rev-parse', '--verify', '--quiet', 'HEAD'], str(top), check=False).strip()
    h.update((head or 'no-head').encode())
    if head:
        diff = subprocess.run(['git', 'diff', 'HEAD', '--binary', '--no-color'], cwd=str(top),
                              capture_output=True, check=False).stdout
        h.update(diff)
    untracked = gitinfo.run_git(['ls-files', '--others', '--exclude-standard', '-z'], str(top))
    for rel in sorted(p for p in untracked.split('\0') if p):
        if rel.startswith(EXCLUDED_UNTRACKED):
            continue
        h.update(rel.encode())
        try:
            h.update(hashlib.sha256((top / rel).read_bytes()).digest())
        except OSError:
            h.update(b'unreadable')
    return h.hexdigest()


def read_entries(cwd: Optional[str] = None) -> List[dict]:
    path = ledger_path(cwd)
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding='utf-8').split('\n'):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def matching_entries(cwd: Optional[str] = None, tree: Optional[str] = None) -> List[dict]:
    tree = tree or tree_hash(cwd)
    return [e for e in read_entries(cwd) if e.get('tree') == tree]


def successful_kinds(cwd: Optional[str] = None, tree: Optional[str] = None) -> Dict[str, dict]:
    """Kind -> the latest successful entry for the current tree."""
    found: Dict[str, dict] = {}
    for e in matching_entries(cwd, tree):
        if e.get('exit_code') == 0:
            for kind in e.get('kinds', []):
                found[kind] = e
    return found


def run_and_record(argv: List[str], cwd: Optional[str] = None) -> int:
    """Run ``argv`` with inherited stdio, record the outcome, return its exit code."""
    top = gitinfo.toplevel(cwd)
    command = ' '.join(argv)
    tree_before = tree_hash(cwd)
    started = time.time()
    try:
        proc = subprocess.run(argv, cwd=cwd or top, check=False)
        code = proc.returncode
    except FileNotFoundError:
        code = 127
    duration = round(time.time() - started, 1)
    entry = {
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'command': command,
        'argv': argv,
        'exit_code': code,
        'duration_s': duration,
        'head': gitinfo.run_git(['rev-parse', '--verify', '--quiet', 'HEAD'], top, check=False).strip() or None,
        'tree_before': tree_before,
        'tree': tree_hash(cwd),
        'cwd': os.path.relpath(os.path.abspath(cwd or top), top),
        'kinds': classify(command),
    }
    path = ledger_path(cwd)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(entry) + '\n')
    return code


def format_entry(e: dict, current: bool = True) -> str:
    head = (e.get('head') or '')[:10]
    mark = '' if current else ' (stale tree)'
    return (f"{e.get('timestamp', '?')}  exit {e.get('exit_code')}  HEAD {head}  "
            f"{e.get('command', '')}{mark}")
