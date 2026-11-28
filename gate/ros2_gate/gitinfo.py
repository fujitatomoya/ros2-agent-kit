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

"""Thin, read-only helpers around the git command line."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple


class GitError(RuntimeError):
    pass


def run_git(args: List[str], cwd: Optional[str] = None, check: bool = True) -> str:
    try:
        proc = subprocess.run(
            ['git'] + args, cwd=cwd, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise GitError('git is not installed or not on PATH') from exc
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def is_repository(cwd: Optional[str] = None) -> bool:
    try:
        return run_git(['rev-parse', '--is-inside-work-tree'], cwd).strip() == 'true'
    except GitError:
        return False


def toplevel(cwd: Optional[str] = None) -> str:
    return run_git(['rev-parse', '--show-toplevel'], cwd).strip()


def remotes(cwd: Optional[str] = None) -> List[Tuple[str, str]]:
    """Return ``(name, url)`` for every remote, ``upstream`` first, then ``origin``."""
    names = [n for n in run_git(['remote'], cwd).split() if n]
    order = sorted(names, key=lambda n: {'upstream': 0, 'origin': 1}.get(n, 2))
    result = []
    for name in order:
        url = run_git(['remote', 'get-url', name], cwd, check=False).strip()
        if url:
            result.append((name, url))
    return result


_REMOTE_PATTERNS = [
    re.compile(r'^[\w.-]+@(?P<host>[\w.-]+):(?P<path>.+)$'),              # git@host:org/repo
    re.compile(r'^\w+://(?:[^@/]+@)?(?P<host>[\w.-]+)(?::\d+)?/(?P<path>.+)$'),  # scheme://host/org/repo
]


def normalize_remote(url: str) -> str:
    """Reduce a remote URL to ``host/org/repo`` without scheme, user, or ``.git``."""
    url = url.strip()
    for pat in _REMOTE_PATTERNS:
        m = pat.match(url)
        if m:
            path = m.group('path').strip('/')
            if path.endswith('.git'):
                path = path[:-4]
            return f"{m.group('host').lower()}/{path}"
    return url


_IDENT_RE = re.compile(r'^(?P<name>.*?)\s*<(?P<email>[^<>]*)>(?:\s+\d+\s+[+-]\d{4})?\s*$')


def parse_ident(ident: str) -> Tuple[str, str]:
    """Parse ``Name <email>`` or ``Name <email> 1700000000 +0900``."""
    m = _IDENT_RE.match(ident.strip())
    if not m:
        raise GitError(f'cannot parse identity: {ident!r}')
    return m.group('name').strip(), m.group('email').strip()


def author_ident(cwd: Optional[str] = None) -> Tuple[str, str]:
    """The identity git would use as author for a new commit in ``cwd``."""
    return parse_ident(run_git(['var', 'GIT_AUTHOR_IDENT'], cwd))


@dataclass
class Commit:
    sha: str
    author_name: str
    author_email: str
    committer_name: str
    committer_email: str
    message: str

    @property
    def subject(self) -> str:
        return self.message.strip().split('\n', 1)[0]


def commit_info(ref: str = 'HEAD', cwd: Optional[str] = None) -> Commit:
    out = run_git(['log', '-1', '--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B', ref], cwd)
    parts = out.split('\x00', 5)
    if len(parts) != 6:
        raise GitError(f'unexpected git log output for {ref}')
    return Commit(*parts)


def rev_list(base: str, head: str = 'HEAD', cwd: Optional[str] = None) -> List[str]:
    out = run_git(['rev-list', '--reverse', f'{base}..{head}'], cwd)
    return [s for s in out.split() if s]


def ref_exists(ref: str, cwd: Optional[str] = None) -> bool:
    proc = subprocess.run(['git', 'rev-parse', '--verify', '--quiet', ref],
                          cwd=cwd, capture_output=True, text=True)
    return proc.returncode == 0


def merge_base(a: str, b: str = 'HEAD', cwd: Optional[str] = None) -> Optional[str]:
    try:
        return run_git(['merge-base', a, b], cwd).strip() or None
    except GitError:
        return None
