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

"""Command-line entry point. Exit codes: 0 pass or allow, 1 fail or block, 2 usage or runtime error."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, body, commit, doctor as doctor_mod, gitinfo, guard, profile as profile_mod
from .findings import Report

PASS, FAIL, USAGE = 0, 1, 2

_BODY_TEMPLATE_HINT_RE = re.compile(r'<!--\s*ros2-gate:\s*template\s*=\s*([\w.-]+)\s*-->')


def repo_root(cwd: Optional[str]) -> Optional[Path]:
    return Path(gitinfo.toplevel(cwd)) if gitinfo.is_repository(cwd) else None


def github_org(prof: profile_mod.Profile, cwd: Optional[str]) -> Optional[str]:
    """``ros2`` from ``github.com/ros2/rclcpp``, preferring the matched remote."""
    urls = [prof.matched_remote] if prof.matched_remote else []
    if not urls and gitinfo.is_repository(cwd):
        urls = [gitinfo.normalize_remote(u) for _, u in gitinfo.remotes(cwd)]
    for url in urls:
        parts = url.split('/')
        if len(parts) >= 3 and parts[0].endswith('github.com'):
            return parts[1]
    return None


def _emit(report: Report, as_json: bool) -> int:
    if as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.format_text())
    return PASS if report.ok else FAIL


def cmd_profile(args, prof, cwd) -> int:
    if args.short:
        line = f'ros2-gate: {prof.summary()}'
        distro = os.environ.get('ROS_DISTRO')
        if distro:
            line += f'; ROS_DISTRO={distro}'
        print(line)
        return PASS
    if args.json:
        print(json.dumps({'id': prof.id, 'reason': prof.reason,
                          'matched_remote': prof.matched_remote, 'description': prof.description,
                          'sources': prof.sources, 'rules': prof.data.get('rules', {})}, indent=2))
        return PASS
    print(f'profile: {prof.id}')
    print(f'reason: {prof.reason}')
    if prof.description:
        print(f'description: {prof.description}')
    sources = profile_mod.load_sources()
    for sid in prof.sources:
        src = sources.get(sid, {})
        print(f"source: {sid} {src.get('url', '')} (verified {src.get('verified', '?')})")
    print('rules:')
    print(json.dumps(prof.data.get('rules', {}), indent=2))
    return PASS


def cmd_check_commit(args, prof, cwd, identities) -> int:
    if args.message_file:
        report = commit.check_message_file(args.message_file, prof, identities, cwd)
    else:
        report = commit.check_commit(args.ref, prof, identities, cwd)
    return _emit(report, args.json)


def cmd_check_range(args, prof, cwd, identities) -> int:
    report = commit.check_range(prof, identities, base=args.base, head=args.head, cwd=cwd)
    return _emit(report, args.json)


def _read(path: str) -> str:
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def cmd_check_pr_body(args, prof, cwd) -> int:
    text = _read(args.file)
    template_text = None
    if args.template:
        template_text = _read(args.template)
    else:
        found = body.find_pr_template(repo_root(cwd), github_org(prof, cwd))
        if found:
            template_text = found.read_text(encoding='utf-8', errors='replace')
    report = body.check_pr_body(text, template_text, prof, issue=args.issue, final=not args.draft)
    return _emit(report, args.json)


def cmd_check_issue_body(args, prof, cwd) -> int:
    text = _read(args.file)
    name = args.template
    if not name:
        m = _BODY_TEMPLATE_HINT_RE.search(text)
        name = m.group(1) if m else 'bug_report'
    path = Path(name) if os.sep in name or name.endswith(('.yml', '.yaml', '.md')) and Path(name).is_file() else None
    if path is None:
        path = body.find_issue_template(repo_root(cwd), name, github_org(prof, cwd))
    report = Report()
    if path is None or not path.is_file():
        report.error(body.GATE, f'issue template "{name}" not found locally or in the cache',
                     fix='pass --template <path> or run tools/fetch_templates.py <org>')
        return _emit(report, args.json)
    template_text = path.read_text(encoding='utf-8', errors='replace')
    if path.suffix == '.md':
        report = body.check_issue_body_markdown(text, template_text, prof)
    else:
        report = body.check_issue_body(text, body.parse_issue_form(template_text), prof,
                                       final=not args.draft)
    return _emit(report, args.json)


def cmd_doctor(args, prof, cwd, identities) -> int:
    return _emit(doctor_mod.doctor(prof, identities, github_org(prof, cwd), cwd), args.json)


def cmd_install_hooks(args, cwd) -> int:
    return _emit(doctor_mod.install_hooks(cwd, force=args.force), args.json)


def cmd_guard(args, prof, cwd, identities) -> int:
    words = list(args.command)
    if words and words[0] == '--':
        words = words[1:]
    command = ' '.join(words).strip()
    if not command:
        print('guard: no command given', file=sys.stderr)
        return USAGE
    decision = guard.guard(command, prof, identities, cwd)
    if args.json:
        print(json.dumps(decision.to_dict()))
    elif decision.allowed:
        print('allow')
    else:
        print(f'block ({decision.gate}): {decision.reason}')
    return PASS if decision.allowed else FAIL


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog='ros2-gate', description=__doc__)
    p.add_argument('--version', action='version', version=f'ros2-gate {__version__}')
    p.add_argument('--cwd', help='repository directory (default: current directory)')
    p.add_argument('--profile', help='force a profile id instead of detecting it')
    p.add_argument('--json', action='store_true', help='machine-readable output')
    sub = p.add_subparsers(dest='cmd', required=True)

    sp = sub.add_parser('profile', help='detect the policy profile and print the active rules')
    sp.add_argument('--short', action='store_true', help='one line, for session-start context')

    sp = sub.add_parser('check-commit', help='validate one commit (G1)')
    sp.add_argument('ref', nargs='?', default='HEAD')
    sp.add_argument('--message-file', help='check a commit-msg hook file instead of a commit')

    sp = sub.add_parser('check-range', help='validate every commit since the merge base (G1)')
    sp.add_argument('--base', help='base ref (default: merge base with the target branch)')
    sp.add_argument('--head', default='HEAD')

    sp = sub.add_parser('check-pr-body', help='validate a PR body file against the template (G4)')
    sp.add_argument('file')
    sp.add_argument('--template', help='template file (default: discovered)')
    sp.add_argument('--issue', type=int, help='issue number the PR must reference')
    sp.add_argument('--draft', action='store_true',
                    help='sections the human writes may still be empty (warnings, not errors)')

    sp = sub.add_parser('check-issue-body', help='validate an issue body file against a form (G4)')
    sp.add_argument('file')
    sp.add_argument('--template', help='issue template name (bug_report) or path')
    sp.add_argument('--draft', action='store_true',
                    help='sections the human writes may still be empty (warnings, not errors)')

    sub.add_parser('doctor', help='report the prerequisites of the kit in this environment')

    sp = sub.add_parser('install-hooks', help='install tier C git hooks (commit-msg, pre-push)')
    sp.add_argument('--force', action='store_true', help='replace existing foreign hooks')

    sp = sub.add_parser('guard', help='decide whether a shell command is allowed (G1, G3)')
    sp.add_argument('command', nargs=argparse.REMAINDER, help='the command, after --')
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    cwd = args.cwd
    try:
        prof = profile_mod.detect(cwd, override=args.profile)
        identities = profile_mod.load_identities()
        if args.cmd == 'profile':
            return cmd_profile(args, prof, cwd)
        if args.cmd == 'check-commit':
            return cmd_check_commit(args, prof, cwd, identities)
        if args.cmd == 'check-range':
            return cmd_check_range(args, prof, cwd, identities)
        if args.cmd == 'check-pr-body':
            return cmd_check_pr_body(args, prof, cwd)
        if args.cmd == 'check-issue-body':
            return cmd_check_issue_body(args, prof, cwd)
        if args.cmd == 'guard':
            return cmd_guard(args, prof, cwd, identities)
        if args.cmd == 'doctor':
            return cmd_doctor(args, prof, cwd, identities)
        if args.cmd == 'install-hooks':
            return cmd_install_hooks(args, cwd)
    except (gitinfo.GitError, OSError, KeyError, ValueError) as exc:
        print(f'ros2-gate: {exc}', file=sys.stderr)
        return USAGE
    return USAGE
