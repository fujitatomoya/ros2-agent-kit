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

"""Hook adapter for Claude Code and Codex.

Reads the hook payload as JSON on stdin and translates it into ros2-gate calls.
Block signal: exit code 2 with the reason on stderr, which both harnesses honor.
Confirmation signal: the ``ask`` permission decision as JSON on stdout, which makes Claude Code
show its permission prompt with the reason. Codex accepts ``ask`` in its schema but runs the
command anyway, so there, and wherever a prompt is not documented to appear, a command that
needs confirmation is blocked and the human runs it.
Context: plain text on stdout for SessionStart.

Events handled:
  SessionStart          -> G5, print the active profile in one line
  PreToolUse  (Bash)    -> G1, G2 and G3, guard the command
  PostToolUse (Write|Edit) -> G4, check PR_BODY.md / ISSUE_BODY.md after they are written;
                              G6, advisory style check on edited source files
  Stop                  -> G7, verification claims without evidence (advisory)
"""

from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'gate'))

from ros2_gate import body, claims, guard, lint, profile as profile_mod  # noqa: E402
from ros2_gate.cli import github_org, repo_root  # noqa: E402

PR_BODY_RE = re.compile(r'^(?:pr|pull[-_]?request)[-_]?body\.md$', re.I)
ISSUE_BODY_RE = re.compile(r'^(?:issue|bug|feature)[-_]?(?:request[-_]?)?body\.md$', re.I)
TEMPLATE_HINT_RE = re.compile(r'<!--\s*ros2-gate:\s*template\s*=\s*([\w.-]+)\s*-->')

ALLOW, BLOCK = 0, 2
# Permission modes in which Claude Code is not documented to prompt for a hook's ask decision.
NO_PROMPT_MODES = ('bypassPermissions', 'dontAsk')


def _read_payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def on_session_start(payload: dict, prof) -> int:
    line = f'ros2-agent-kit: {prof.summary()}'
    distro = os.environ.get('ROS_DISTRO')
    if distro:
        line += f'; ROS_DISTRO={distro}'
    line += ('. Contribution rules are enforced by ros2-gate hooks: commits need the human '
             "contributor's sign-off, and where the profile says so the agent submits a pull "
             'request or an issue only after the human confirms the exact command, and does '
             'not post comments or reviews.')
    print(line)
    return ALLOW


def can_ask(payload: dict) -> bool:
    """True when this is Claude Code in a mode where a hook's ask decision prompts the human.

    Codex sets ``PLUGIN_ROOT`` and sends ``turn_id``; it parses ``ask`` and then runs the
    command, so it must never receive one. Anything that is not positively Claude Code is
    treated the same way.
    """
    if os.environ.get('PLUGIN_ROOT') or 'turn_id' in payload:
        return False
    if not os.environ.get('CLAUDE_PROJECT_DIR'):
        return False
    return payload.get('permission_mode') not in NO_PROMPT_MODES


def on_pre_tool_use(payload: dict, prof, identities, cwd) -> int:
    if payload.get('tool_name') != 'Bash':
        return ALLOW
    command = (payload.get('tool_input') or {}).get('command') or ''
    decision = guard.guard(command, prof, identities, cwd)
    if decision.allowed:
        return ALLOW
    if decision.needs_confirmation:
        if can_ask(payload):
            print(json.dumps({'hookSpecificOutput': {
                'hookEventName': 'PreToolUse',
                'permissionDecision': 'ask',
                'permissionDecisionReason': f'ros2-gate {decision.gate}: {decision.reason}.'}}))
            return ALLOW
        print(f'ros2-gate {decision.gate} needs the human to confirm `{decision.command}`: '
              f'{decision.reason}. This harness or permission mode cannot show a confirmation '
              'prompt from a hook, so show the human the exact command and let them run it.',
              file=sys.stderr)
        return BLOCK
    print(f'ros2-gate {decision.gate} blocked `{decision.command}`: {decision.reason}',
          file=sys.stderr)
    return BLOCK


def check_body_file(path: str, prof, cwd) -> str:
    """Run G4 on a PR_BODY.md or ISSUE_BODY.md draft. Returns the problem text, or '' when fine."""
    name = os.path.basename(path)
    if not (PR_BODY_RE.match(name) or ISSUE_BODY_RE.match(name)):
        return ''
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            text = fh.read()
    except OSError:
        return ''
    root = repo_root(cwd)
    org = github_org(prof, cwd)
    if PR_BODY_RE.match(name):
        found = body.find_pr_template(root, org)
        template = found.read_text(encoding='utf-8', errors='replace') if found else None
        report = body.check_pr_body(text, template, prof, final=False)
    else:
        m = TEMPLATE_HINT_RE.search(text)
        tname = m.group(1) if m else 'bug_report'
        found = body.find_issue_template(root, tname, org)
        if found is None:
            return (f'ros2-gate G4: issue template "{tname}" not found; run '
                    f'tools/fetch_templates.py {org or "<org>"} to cache the organization default')
        ttext = found.read_text(encoding='utf-8', errors='replace')
        if found.suffix == '.md':
            report = body.check_issue_body_markdown(text, ttext, prof)
        else:
            report = body.check_issue_body(text, body.parse_issue_form(ttext), prof, final=False)
    if report.ok:
        return ''
    return f'ros2-gate G4 found problems in {path}:\n{report.format_text()}'


def on_post_tool_use(payload: dict, prof, cwd) -> int:
    if payload.get('tool_name') not in ('Write', 'Edit', 'MultiEdit'):
        return ALLOW
    path = (payload.get('tool_input') or {}).get('file_path') or ''
    text = check_body_file(path, prof, cwd)
    if text:
        print(text, file=sys.stderr)
        return BLOCK
    if lint.kind_of(path):
        report = lint.lint_file(path, cwd)
        warnings = [f for f in report.findings if f.level == 'warning']
        if warnings:
            print(json.dumps({'hookSpecificOutput': {
                'hookEventName': 'PostToolUse',
                'additionalContext': 'ros2-gate G6 (advisory) on ' + path + ':\n'
                                     + '\n'.join(f.message + (f' (fix: {f.fix})' if f.fix else '')
                                                  for f in warnings)}}))
    return ALLOW


def on_stop(payload: dict, cwd) -> int:
    if payload.get('stop_hook_active'):
        return ALLOW
    message = payload.get('last_assistant_message') or ''
    report = claims.check_claims(message, cwd)
    warnings = [f for f in report.findings if f.level == 'warning']
    if warnings:
        print(json.dumps({'hookSpecificOutput': {
            'hookEventName': 'Stop',
            'additionalContext': 'ros2-gate G7: ' + ' '.join(f.message + '.' for f in warnings)
                                 + ' Only report results you ran on the current tree.'}}))
    return ALLOW


def main() -> int:
    payload = _read_payload()
    event = payload.get('hook_event_name', '')
    cwd = payload.get('cwd') or os.environ.get('CLAUDE_PROJECT_DIR') or os.getcwd()
    try:
        prof = profile_mod.detect(cwd)
        identities = profile_mod.load_identities()
    except Exception as exc:  # never break the harness because of the gate itself
        print(f'ros2-gate: cannot load policy: {exc}', file=sys.stderr)
        return ALLOW
    try:
        if event == 'SessionStart':
            return on_session_start(payload, prof)
        if event == 'PreToolUse':
            return on_pre_tool_use(payload, prof, identities, cwd)
        if event == 'PostToolUse':
            return on_post_tool_use(payload, prof, cwd)
        if event == 'Stop':
            return on_stop(payload, cwd)
    except Exception as exc:
        print(f'ros2-gate: internal error, allowing: {exc}', file=sys.stderr)
    return ALLOW


if __name__ == '__main__':
    sys.exit(main())
