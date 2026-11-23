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

"""Shared test helpers: temporary git repositories and loaded policy."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

GATE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(GATE_DIR))

from ros2_gate import profile as profile_mod  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / 'fixtures'
HUMAN = ('Jane Developer', 'jane@example.com')
AGENT = ('Claude', 'noreply@anthropic.com')


def load_profile(pid: str) -> profile_mod.Profile:
    profiles = profile_mod.load_profiles()
    return profile_mod.Profile(pid, profiles[pid], reason='test')


def identities():
    return profile_mod.load_identities()


def git(repo: str, *args, env=None, check=True) -> str:
    merged = dict(os.environ)
    merged.pop('GIT_DIR', None)
    merged.pop('GIT_WORK_TREE', None)
    if env:
        merged.update(env)
    proc = subprocess.run(['git', '-C', repo] + list(args), capture_output=True, text=True,
                          env=merged)
    if check and proc.returncode != 0:
        raise RuntimeError(f'git {args} failed: {proc.stderr}')
    return proc.stdout


def new_repo(name='Jane Developer', email='jane@example.com', remote=None) -> str:
    repo = tempfile.mkdtemp(prefix='ros2gate-')
    git(repo, 'init', '-q', '-b', 'rolling')
    git(repo, 'config', 'user.name', name)
    git(repo, 'config', 'user.email', email)
    git(repo, 'config', 'commit.gpgsign', 'false')
    if remote:
        git(repo, 'remote', 'add', 'origin', remote)
    return repo


def commit(repo: str, message: str, filename='file.txt', author=None, signoff=False) -> str:
    path = Path(repo) / filename
    path.write_text(path.read_text() + 'x\n' if path.exists() else 'x\n')
    git(repo, 'add', filename)
    args = ['commit', '-q', '-m', message]
    if signoff:
        args.append('-s')
    if author:
        args += ['--author', author]
    git(repo, *args)
    return git(repo, 'rev-parse', 'HEAD').strip()
