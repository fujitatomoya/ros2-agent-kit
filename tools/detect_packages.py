#!/usr/bin/env python3
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

"""Detect the ROS packages affected by pull requests or by local changes.

Remote mode (GitHub API, read-only):
    python3 tools/detect_packages.py ros2/demos#806 [ros2/rclcpp#3235 ...] [--json]

Local mode (no network, the current repository):
    python3 tools/detect_packages.py --local [--base upstream/rolling] [--json]

For each PR the script fetches the changed files, lists the PR head tree,
locates every package.xml, maps each changed file to its nearest (deepest)
enclosing package directory, and reads the real <name> from that package.xml.
Directory names are not trusted because they can differ from the package name.
Files removed by the PR are resolved against the base tree instead.

Local mode does the same with ``git diff --name-only <merge-base>`` plus
untracked files, and reads package.xml from the working tree.

Output (default): one package name per line, the union across PRs, so that
    ros-ci-for-pr --packages $(python3 tools/detect_packages.py org/repo#N)
works. With --json: {"per_pr": {...}, "union": [...], "unmapped": [...], "warnings": [...]}

Auth: $GITHUB_ACCESS_TOKEN or $GITHUB_TOKEN if set, else ``gh auth token``.
Unauthenticated requests work but are heavily rate-limited.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

API = 'https://api.github.com'
PR_SPEC_RE = re.compile(r'^(?:https?://github\.com/)?([\w.-]+)/([\w.-]+)(?:#|/pull/)(\d+)/?$')
NAME_RE = re.compile(r'<name>\s*([^<\s]+)\s*</name>')


def parse_pr_spec(spec: str) -> Tuple[str, str, int]:
    m = PR_SPEC_RE.match(spec.strip())
    if not m:
        raise ValueError(f"cannot parse PR spec '{spec}' (expected org/repo#number or a PR URL)")
    return m.group(1), m.group(2), int(m.group(3))


def get_token() -> Optional[str]:
    for var in ('GITHUB_ACCESS_TOKEN', 'GITHUB_TOKEN'):
        if os.environ.get(var):
            return os.environ[var]
    try:
        out = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def api_get(path: str, token: Optional[str]):
    req = urllib.request.Request(API + path)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'ros2-agent-kit-detect-packages')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


# --- pure mapping helpers ----------------------------------------------------

def nearest_package_dir(path: str, pkg_dirs: Iterable[str]) -> Optional[str]:
    """Deepest package dir that is an ancestor of (or equal to) the file's directory."""
    best = None
    for d in pkg_dirs:
        if d == '' or path == d or path.startswith(d + '/'):
            if best is None or len(d) > len(best):
                best = d
    return best


def package_name_from_xml(xml: str, fallback: str) -> str:
    m = NAME_RE.search(xml)
    return m.group(1) if m else fallback


def package_dirs_from_paths(paths: Iterable[str]) -> List[str]:
    return sorted({os.path.dirname(p) for p in paths if os.path.basename(p) == 'package.xml'})


class Result:

    def __init__(self) -> None:
        self.per_pr: Dict[str, List[str]] = {}
        self.unmapped: List[str] = []
        self.warnings: List[str] = []

    @property
    def union(self) -> List[str]:
        return sorted(set().union(*self.per_pr.values())) if self.per_pr else []

    def to_dict(self) -> dict:
        return {'per_pr': self.per_pr, 'union': self.union, 'unmapped': self.unmapped,
                'warnings': self.warnings}


# --- remote mode -------------------------------------------------------------

class GitHubTree:
    """Package directories and package.xml contents of one repo@ref, fetched lazily."""

    def __init__(self, owner: str, repo: str, ref: str, fetch: Callable, token: Optional[str],
                 result: Result):
        self.owner, self.repo, self.ref = owner, repo, ref
        self.fetch, self.token, self.result = fetch, token, result
        self._dirs: Optional[List[str]] = None
        self._names: Dict[str, str] = {}

    @property
    def package_dirs(self) -> List[str]:
        if self._dirs is None:
            tree = self.fetch(f'/repos/{self.owner}/{self.repo}/git/trees/{self.ref}?recursive=1',
                              self.token)
            if tree.get('truncated'):
                self.result.warnings.append(
                    f'tree listing truncated for {self.owner}/{self.repo}@{self.ref}; '
                    'package detection may be incomplete')
            self._dirs = package_dirs_from_paths(
                item['path'] for item in tree.get('tree', []) if item.get('type') == 'blob')
        return self._dirs

    def package_name(self, pkg_dir: str) -> str:
        if pkg_dir not in self._names:
            xml_path = f'{pkg_dir}/package.xml' if pkg_dir else 'package.xml'
            data = self.fetch(f'/repos/{self.owner}/{self.repo}/contents/{xml_path}?ref={self.ref}',
                              self.token)
            xml = base64.b64decode(data['content']).decode('utf-8', errors='replace')
            self._names[pkg_dir] = package_name_from_xml(xml, os.path.basename(pkg_dir) or self.repo)
        return self._names[pkg_dir]


def changed_files(owner: str, repo: str, number: int, fetch: Callable,
                  token: Optional[str]) -> List[dict]:
    files, page = [], 1
    while True:
        batch = fetch(f'/repos/{owner}/{repo}/pulls/{number}/files?per_page=100&page={page}', token)
        files.extend(batch)
        if len(batch) < 100:
            return files
        page += 1


def detect_remote(specs: List[str], fetch: Callable = api_get,
                  token: Optional[str] = None) -> Result:
    result = Result()
    for spec in specs:
        owner, repo, number = parse_pr_spec(spec)
        key = f'{owner}/{repo}#{number}'
        pr = fetch(f'/repos/{owner}/{repo}/pulls/{number}', token)
        base = GitHubTree(pr['base']['repo']['owner']['login'], pr['base']['repo']['name'],
                          pr['base']['sha'], fetch, token, result)
        if pr.get('head', {}).get('repo'):
            head = GitHubTree(pr['head']['repo']['owner']['login'], pr['head']['repo']['name'],
                              pr['head']['sha'], fetch, token, result)
        else:
            result.warnings.append(f'{key}: head repository is gone (deleted fork); '
                                   'using the base tree for every file')
            head = base
        names: Set[str] = set()
        for entry in changed_files(owner, repo, number, fetch, token):
            path = entry['filename']
            tree = base if entry.get('status') == 'removed' else head
            d = nearest_package_dir(path, tree.package_dirs)
            if d is None and tree is head and entry.get('status') != 'removed':
                d = nearest_package_dir(path, base.package_dirs)
                tree = base
            if d is None:
                result.unmapped.append(f'{key}:{path}')
            else:
                names.add(tree.package_name(d))
        result.per_pr[key] = sorted(names)
    return result


# --- local mode --------------------------------------------------------------

def _git(args: List[str], cwd: Optional[str]) -> str:
    return subprocess.run(['git'] + args, cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


def default_base(cwd: Optional[str]) -> Optional[str]:
    for ref in ('upstream/rolling', 'origin/rolling', 'upstream/HEAD', 'origin/HEAD',
                'origin/main', 'origin/master', 'main', 'master'):
        probe = subprocess.run(['git', 'rev-parse', '--verify', '--quiet', ref], cwd=cwd,
                               capture_output=True, text=True)
        if probe.returncode == 0:
            return ref
    return None


def detect_local(base: Optional[str] = None, cwd: Optional[str] = None) -> Result:
    result = Result()
    top = _git(['rev-parse', '--show-toplevel'], cwd).strip()
    base = base or default_base(top)
    if base is None:
        raise RuntimeError('cannot determine a base ref; pass --base <ref>')
    merge_base = _git(['merge-base', base, 'HEAD'], top).strip()
    changed = set(_git(['diff', '--name-only', merge_base], top).split())
    changed |= set(_git(['ls-files', '--others', '--exclude-standard'], top).split())
    tracked = _git(['ls-files', '--', '*package.xml', 'package.xml'], top).split()
    untracked = [p for p in _git(['ls-files', '--others', '--exclude-standard'], top).split()
                 if os.path.basename(p) == 'package.xml']
    # Packages that existed at the merge base but were removed since still count.
    at_base = [p for p in _git(['ls-tree', '-r', '--name-only', merge_base], top).split()
               if os.path.basename(p) == 'package.xml']
    pkg_dirs = package_dirs_from_paths(tracked + untracked + at_base)
    names: Set[str] = set()
    cache: Dict[str, str] = {}
    key = f'local:{merge_base[:10]}..HEAD'
    for path in sorted(changed):
        d = nearest_package_dir(path, pkg_dirs)
        if d is None:
            result.unmapped.append(f'{key}:{path}')
            continue
        if d not in cache:
            xml_file = Path(top) / d / 'package.xml'
            try:
                xml = xml_file.read_text(encoding='utf-8', errors='replace')
            except OSError:
                # Deleted in the working tree: read it from the merge base.
                rel = f'{d}/package.xml' if d else 'package.xml'
                xml = _git(['show', f'{merge_base}:{rel}'], top)
            cache[d] = package_name_from_xml(xml, os.path.basename(d) or os.path.basename(top))
        names.add(cache[d])
    result.per_pr[key] = sorted(names)
    return result


# --- cli ---------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pulls', nargs='*', help='PRs as org/repo#number or PR URLs')
    ap.add_argument('--local', action='store_true', help='use the local repository instead')
    ap.add_argument('--base', help='base ref for --local (default: upstream/rolling and fallbacks)')
    ap.add_argument('--cwd', help='repository directory for --local')
    ap.add_argument('--json', action='store_true', help='emit JSON with per-PR detail')
    args = ap.parse_args(argv)

    try:
        if args.local:
            result = detect_local(args.base, args.cwd)
        else:
            if not args.pulls:
                ap.error('give at least one PR spec, or use --local')
            token = get_token()
            if not token:
                print('warning: no GitHub token found; using unauthenticated API (low rate limit)',
                      file=sys.stderr)
            result = detect_remote(args.pulls, api_get, token)
    except (ValueError, RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    for key, names in result.per_pr.items():
        print(f"# {key}: {', '.join(names) if names else '(none)'}", file=sys.stderr)
    for f in result.unmapped:
        print(f'# unmapped (no package.xml ancestor): {f}', file=sys.stderr)
    for w in result.warnings:
        print(f'warning: {w}', file=sys.stderr)
    if result.union:
        print('\n'.join(result.union))
    return 0


if __name__ == '__main__':
    sys.exit(main())
