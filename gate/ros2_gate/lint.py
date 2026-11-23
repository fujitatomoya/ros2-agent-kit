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

"""G6: a fast, advisory style check on one edited file.

The ament linters are the oracle when they are installed. Without them a few
built-in checks catch the rules agents get wrong most: 100 columns, tabs, and
one sentence per line in documentation.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import List, Optional, Tuple

from .findings import Report

GATE = 'G6'
MAX_COLUMNS = 100
TIMEOUT = 30

_TOOLS = {
    'cpp': ['ament_uncrustify', 'ament_cpplint'],
    'python': ['ament_flake8', 'ament_pep257'],
    'cmake': ['ament_lint_cmake'],
    'xml': ['ament_xmllint'],
}
_EXT = {
    '.cpp': 'cpp', '.hpp': 'cpp', '.cc': 'cpp', '.h': 'cpp', '.c': 'cpp', '.hh': 'cpp',
    '.py': 'python',
    '.cmake': 'cmake',
    '.xml': 'xml',
    '.md': 'docs', '.rst': 'docs',
}
_SENTENCE_BREAK = re.compile(r'[.!?]["\')\]]?\s+[A-Z]')


def kind_of(path: str) -> Optional[str]:
    name = os.path.basename(path)
    if name == 'CMakeLists.txt':
        return 'cmake'
    return _EXT.get(os.path.splitext(name)[1].lower())


def _run_tool(tool: str, path: str, cwd: Optional[str]) -> Tuple[Optional[int], str]:
    try:
        proc = subprocess.run([tool, path], cwd=cwd, capture_output=True, text=True,
                              timeout=TIMEOUT, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    return proc.returncode, (proc.stdout + proc.stderr)


def _builtin_checks(path: str, kind: str, report: Report) -> None:
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            lines = fh.read().split('\n')
    except OSError:
        return
    long_lines: List[int] = []
    tab_lines: List[int] = []
    multi: List[int] = []
    in_fence = False
    in_front_matter = kind == 'docs' and lines and lines[0].strip() == '---'
    for i, line in enumerate(lines, 1):
        if kind == 'docs':
            if in_front_matter:
                if i > 1 and line.strip() == '---':
                    in_front_matter = False
                continue
            if line.strip().startswith('```'):
                in_fence = not in_fence
                continue
            if in_fence or line.startswith('    '):
                continue
            if _SENTENCE_BREAK.search(line.strip()):
                multi.append(i)
            continue
        if len(line) > MAX_COLUMNS:
            long_lines.append(i)
        if '\t' in line and kind != 'cmake':
            tab_lines.append(i)
    if long_lines:
        report.warning(GATE, f'{len(long_lines)} line(s) over {MAX_COLUMNS} columns, first at '
                             f'{", ".join(map(str, long_lines[:5]))}', subject=path)
    if tab_lines:
        report.warning(GATE, f'tabs on line(s) {", ".join(map(str, tab_lines[:5]))}; ROS 2 uses spaces',
                       subject=path)
    if multi:
        report.warning(GATE, f'more than one sentence on line(s) {", ".join(map(str, multi[:5]))}; '
                             'ROS documentation uses one sentence per line', subject=path)


def lint_file(path: str, cwd: Optional[str] = None) -> Report:
    report = Report()
    kind = kind_of(path)
    if kind is None or not os.path.isfile(path):
        return report
    ran_tool = False
    for tool in _TOOLS.get(kind, []):
        if shutil.which(tool) is None:
            continue
        ran_tool = True
        code, output = _run_tool(tool, path, cwd)
        if code is None:
            report.info(GATE, f'{tool} could not run: {output}', subject=path)
        elif code != 0:
            head = '\n'.join(output.strip().split('\n')[:15])
            report.warning(GATE, f'{tool} reports problems:\n{head}',
                           fix=f'{tool} --reformat {path}' if tool == 'ament_uncrustify' else None,
                           subject=path)
    if not ran_tool and kind != 'docs':
        report.info(GATE, f'no ament linter installed for {kind} files; built-in checks only',
                    subject=path)
    _builtin_checks(path, kind, report)
    return report
