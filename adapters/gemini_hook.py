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

"""Hook adapter for Gemini CLI extensions.

Gemini reads the hook payload as JSON on stdin and expects a single JSON object
on stdout; plain text must go to stderr. Events handled:

  SessionStart -> G5, additionalContext with the active profile
  BeforeTool   -> G1 and G3 on run_shell_command, decision deny with the reason
  AfterTool    -> G4 on write_file/replace/edit of PR_BODY.md or ISSUE_BODY.md
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'gate'))

from ros2_gate import guard, profile as profile_mod  # noqa: E402

sys.path.insert(0, HERE)
from claude_codex_hook import check_body_file  # noqa: E402


def emit(obj: dict) -> int:
    print(json.dumps(obj))
    return 0


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    event = payload.get('hook_event_name', '')
    cwd = payload.get('cwd') or os.getcwd()
    try:
        prof = profile_mod.detect(cwd)
        identities = profile_mod.load_identities()
    except Exception as exc:
        print(f'ros2-gate: cannot load policy: {exc}', file=sys.stderr)
        return 0
    try:
        if event == 'SessionStart':
            line = f'ros2-agent-kit: {prof.summary()}'
            if os.environ.get('ROS_DISTRO'):
                line += f"; ROS_DISTRO={os.environ['ROS_DISTRO']}"
            return emit({'hookSpecificOutput': {'hookEventName': 'SessionStart',
                                                'additionalContext': line}})
        if event == 'BeforeTool':
            if payload.get('tool_name') != 'run_shell_command':
                return 0
            command = (payload.get('tool_input') or {}).get('command') or ''
            d = guard.guard(command, prof, identities, cwd)
            if d.allowed:
                return 0
            return emit({'decision': 'deny',
                         'reason': f'ros2-gate {d.gate} blocked `{d.command}`: {d.reason}'})
        if event == 'AfterTool':
            path = (payload.get('tool_input') or {}).get('file_path') or ''
            text = check_body_file(path, prof, cwd)
            if text:
                return emit({'hookSpecificOutput': {'hookEventName': 'AfterTool',
                                                    'additionalContext': text}})
            return 0
    except Exception as exc:
        print(f'ros2-gate: internal error, allowing: {exc}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
