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

"""Watch the upstream documents that the policy depends on (design section 11.2).

    python3 tools/watch_sources.py            # compare, print changes, exit 1 if any changed
    python3 tools/watch_sources.py --update   # store the current hashes and today's date

Each entry in policy/sources.json has a URL, and optionally a watch_url that is
fetched instead when the canonical page blocks automated clients (the OSRF
policy page does; its Discourse announcement thread is watched in its place).
For a Discourse topic URL the hash covers the title and the first post's
rendered body from the topic JSON, since the HTML page changes on every load.
For a GitHub repository URL the
hash is the SHA of the repository's default branch tree, read through the API.
For a web page the hash covers the visible text of the page with tags and
whitespace removed, which is stable across page loads but changes when the
wording changes. The scheduled workflow opens an issue when a hash differs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

SOURCES = Path(__file__).resolve().parent.parent / 'policy' / 'sources.json'
GITHUB_REPO_RE = re.compile(r'^https://github\.com/([\w.-]+)/([\w.-]+)/?$')
DISCOURSE_TOPIC_RE = re.compile(r'^(https://[\w.-]+)/t/[\w-]+/(\d+)/?$')


def get_token():
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


def fetch(url: str, token=None, accept='text/html') -> bytes:
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'ros2-agent-kit-watch-sources')
    req.add_header('Accept', accept)
    if token and 'api.github.com' in url:
        req.add_header('Authorization', f'Bearer {token}')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def page_text(raw: bytes) -> str:
    text = raw.decode('utf-8', errors='replace')
    text = re.sub(r'(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>', ' ', text)
    text = re.sub(r'(?s)<!--.*?-->', ' ', text)
    text = re.sub(r'(?s)<[^>]+>', ' ', text)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def current_hash(url: str, token=None) -> str:
    m = GITHUB_REPO_RE.match(url)
    if m:
        owner, repo = m.groups()
        info = json.loads(fetch(f'https://api.github.com/repos/{owner}/{repo}', token,
                                'application/vnd.github+json'))
        branch = info['default_branch']
        ref = json.loads(fetch(f'https://api.github.com/repos/{owner}/{repo}/commits/{branch}',
                               token, 'application/vnd.github+json'))
        return 'tree:' + ref['commit']['tree']['sha']
    m = DISCOURSE_TOPIC_RE.match(url)
    if m:
        # Discourse pages carry view counts and relative times that change on every load;
        # the topic JSON gives the first post's rendered body, which changes only when edited.
        base, topic_id = m.groups()
        topic = json.loads(fetch(f'{base}/t/{topic_id}.json', None, 'application/json'))
        first = topic['post_stream']['posts'][0]
        body = topic.get('title', '') + '\n' + page_text(first.get('cooked', '').encode())
        return 'post:' + hashlib.sha256(body.encode()).hexdigest()
    return 'text:' + hashlib.sha256(page_text(fetch(url, token)).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--update', action='store_true', help='store the current hashes')
    ap.add_argument('--json', action='store_true', help='machine-readable result')
    args = ap.parse_args()
    data = json.loads(SOURCES.read_text(encoding='utf-8'))
    token = get_token()
    today = dt.date.today().isoformat()
    changed, errors = [], []
    for sid, src in data['sources'].items():
        try:
            now = current_hash(src.get('watch_url') or src['url'], token)
        except (urllib.error.URLError, KeyError, ValueError, OSError) as exc:
            errors.append({'id': sid, 'url': src['url'], 'error': str(exc)})
            continue
        before = src.get('sha256')
        if args.update:
            src['sha256'] = now
            src['verified'] = today
        elif before and before != now:
            changed.append({'id': sid, 'url': src['url'], 'stored': before, 'current': now,
                            'verified': src.get('verified')})
        elif not before:
            changed.append({'id': sid, 'url': src['url'], 'stored': None, 'current': now,
                            'verified': src.get('verified')})
    if args.update:
        SOURCES.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
    result = {'changed': changed, 'errors': errors, 'updated': args.update}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for c in changed:
            print(f"changed: {c['id']} {c['url']} (last verified {c['verified']})")
        for e in errors:
            print(f"error: {e['id']} {e['url']}: {e['error']}", file=sys.stderr)
        if args.update:
            print(f'stored hashes for {len(data["sources"]) - len(errors)} source(s)')
        elif not changed:
            print('no source changed')
    return 1 if (changed and not args.update) or errors else 0


if __name__ == '__main__':
    sys.exit(main())
