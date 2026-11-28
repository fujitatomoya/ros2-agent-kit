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

"""Cache a GitHub organization's default PR and issue templates for ros2-gate.

Usage:
    python3 tools/fetch_templates.py ros2 [--force]

Reads ``.github/PULL_REQUEST_TEMPLATE.md`` and ``.github/ISSUE_TEMPLATE/*`` from
the ``<org>/.github`` repository and stores them under
``$XDG_CACHE_HOME/ros2-agent-kit/templates/<org>/.github/``, where
``ros2-gate check-pr-body`` and ``check-issue-body`` look when the working
repository has no template of its own. The gate engine itself never touches
the network; this helper is the only place that does, and it is read-only.

Auth: ``$GITHUB_ACCESS_TOKEN`` or ``$GITHUB_TOKEN`` if set, else ``gh auth token``.
Unauthenticated requests work but are rate-limited.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = 'https://api.github.com'


def cache_dir() -> Path:
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache')
    return Path(base) / 'ros2-agent-kit' / 'templates'


def get_token() -> str | None:
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


def api_get(path: str, token: str | None):
    req = urllib.request.Request(API + path)
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('User-Agent', 'ros2-agent-kit-fetch-templates')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_file(org: str, path: str, token: str | None) -> bytes | None:
    try:
        data = api_get(f'/repos/{org}/.github/contents/{path}', token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if isinstance(data, dict) and data.get('encoding') == 'base64':
        return base64.b64decode(data['content'])
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('org', help='GitHub organization or user, for example ros2')
    ap.add_argument('--force', action='store_true', help='overwrite cached files')
    args = ap.parse_args()
    token = get_token()
    if not token:
        print('warning: no GitHub token found; using unauthenticated API', file=sys.stderr)

    dest = cache_dir() / args.org / '.github'
    dest.mkdir(parents=True, exist_ok=True)
    written = 0

    for name in ('PULL_REQUEST_TEMPLATE.md', 'pull_request_template.md'):
        content = fetch_file(args.org, '.github/' + name, token)
        if content is not None:
            target = dest / name
            if args.force or not target.exists():
                target.write_bytes(content)
                written += 1
            print(f'cached {target}')
            break
    else:
        print(f'no PR template in {args.org}/.github', file=sys.stderr)

    try:
        listing = api_get(f'/repos/{args.org}/.github/contents/.github/ISSUE_TEMPLATE', token)
    except urllib.error.HTTPError as exc:
        listing = [] if exc.code == 404 else None
        if listing is None:
            raise
    issue_dir = dest / 'ISSUE_TEMPLATE'
    for item in listing or []:
        if item.get('type') != 'file':
            continue
        content = fetch_file(args.org, item['path'], token)
        if content is None:
            continue
        issue_dir.mkdir(exist_ok=True)
        target = issue_dir / item['name']
        if args.force or not target.exists():
            target.write_bytes(content)
            written += 1
        print(f'cached {target}')
    print(f'{written} file(s) written to {dest}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
