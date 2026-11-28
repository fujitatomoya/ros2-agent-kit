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

"""``doctor``: report the prerequisites of the kit, and ``install-hooks``: tier C git hooks."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Optional

from . import gitinfo
from .body import cache_dir, find_pr_template
from .findings import Report
from .identities import AgentIdentities
from .profile import KIT_ROOT, Profile

GATE = 'doctor'


def doctor(profile: Profile, identities: AgentIdentities, org: Optional[str],
           cwd: Optional[str] = None) -> Report:
    report = Report()
    report.info(GATE, f'python {sys.version.split()[0]} at {sys.executable}')
    if shutil.which('git') is None:
        report.error(GATE, 'git is not on PATH')
        return report
    if not gitinfo.is_repository(cwd):
        report.warning(GATE, 'not inside a git repository; profile detection falls back to app')
    else:
        try:
            name, email = gitinfo.author_ident(cwd)
            if identities.matches(name, email):
                report.error(GATE, f'git identity "{name} <{email}>" is an agent identity',
                             fix='set user.name and user.email to the human contributor')
            else:
                report.info(GATE, f'git identity: {name} <{email}>')
        except gitinfo.GitError as exc:
            report.error(GATE, f'git identity is not configured ({exc})',
                         fix='git config user.name "Your Name"; git config user.email you@example.com')
    report.info(GATE, f'profile: {profile.summary()} ({profile.reason})')
    distro = os.environ.get('ROS_DISTRO')
    if distro:
        report.info(GATE, f'ROS_DISTRO={distro}')
    else:
        report.warning(GATE, 'ROS_DISTRO is not set; source your ROS 2 installation for build and test skills')
    local_template = find_pr_template(Path(gitinfo.toplevel(cwd)) if gitinfo.is_repository(cwd) else None)
    if local_template:
        report.info(GATE, f'PR template found in the repository: {local_template}')
    elif org:
        cached = cache_dir() / org / '.github'
        if (cached / 'PULL_REQUEST_TEMPLATE.md').exists():
            report.info(GATE, f'organization templates cached for {org} at {cached}')
        else:
            report.warning(GATE, f'no PR template in the repository and none cached for {org}',
                           fix=f'python3 {KIT_ROOT}/tools/fetch_templates.py {org}')
    for tool, why in (('gh', 'read-only GitHub queries in skills'),
                      ('ros-ci-for-pr', 'the ci-trigger skill'),
                      ('colcon', 'build and test evidence'),
                      ('ament_uncrustify', 'the fast style check on edited C++ files'),
                      ('ament_flake8', 'the fast style check on edited Python files')):
        if shutil.which(tool):
            report.info(GATE, f'{tool} found')
        else:
            report.warning(GATE, f'{tool} not found; needed for {why}')
    if os.environ.get('GITHUB_ACCESS_TOKEN'):
        report.info(GATE, 'GITHUB_ACCESS_TOKEN is set (value not shown)')
    else:
        report.warning(GATE, 'GITHUB_ACCESS_TOKEN is not set; ci-trigger cannot create Jenkins jobs')
    if gitinfo.is_repository(cwd):
        hooks = Path(gitinfo.run_git(['rev-parse', '--git-path', 'hooks'], cwd).strip())
        if not hooks.is_absolute():
            hooks = Path(gitinfo.toplevel(cwd)) / hooks
        installed = [n for n in ('commit-msg', 'pre-push') if _is_ours(hooks / n)]
        if installed:
            report.info(GATE, f"tier C git hooks installed: {', '.join(installed)}")
        else:
            report.info(GATE, 'tier C git hooks not installed in this repository',
                        fix='python3 gate/ros2-gate install-hooks')
    return report


_MARK = '# ros2-agent-kit hook'


def _is_ours(path: Path) -> bool:
    try:
        return _MARK in path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return False


def _hook_script(subcommand: str, gate_path: Path) -> str:
    launcher = str(gate_path)
    if subcommand == 'commit-msg':
        body = f'exec python3 "{launcher}" check-commit --message-file "$1"\n'
    else:
        body = f'exec python3 "{launcher}" check-range\n'
    return f'#!/bin/sh\n{_MARK}: {subcommand} -> ros2-gate\n{body}'


def install_hooks(cwd: Optional[str] = None, force: bool = False) -> Report:
    report = Report()
    if not gitinfo.is_repository(cwd):
        report.error(GATE, 'not inside a git repository')
        return report
    hooks = Path(gitinfo.run_git(['rev-parse', '--git-path', 'hooks'], cwd).strip())
    if not hooks.is_absolute():
        hooks = Path(gitinfo.toplevel(cwd)) / hooks
    hooks.mkdir(parents=True, exist_ok=True)
    gate_path = KIT_ROOT / 'gate' / 'ros2-gate'
    for name in ('commit-msg', 'pre-push'):
        target = hooks / name
        if target.exists() and not _is_ours(target) and not force:
            report.error(GATE, f'{target} exists and is not ours; pass --force to replace it, '
                                'or add the ros2-gate call to it by hand')
            continue
        target.write_text(_hook_script(name, gate_path), encoding='utf-8')
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        report.info(GATE, f'installed {target}')
    return report
