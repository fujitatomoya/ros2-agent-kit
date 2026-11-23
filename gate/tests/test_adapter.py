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

"""Recorded hook payloads for the Claude Code / Codex adapter."""

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests import helpers

ADAPTER = helpers.GATE_DIR.parent / 'adapters' / 'claude_codex_hook.py'


def run_hook(payload: dict, env=None):
    merged = dict(os.environ)
    merged.pop('ROS2_GATE_PROFILE', None)
    if env:
        merged.update(env)
    proc = subprocess.run([sys.executable, str(ADAPTER)], input=json.dumps(payload),
                          capture_output=True, text=True, env=merged)
    return proc.returncode, proc.stdout, proc.stderr


def payload(event, repo, **extra):
    base = {'session_id': 'abc', 'transcript_path': '/tmp/t.jsonl', 'cwd': repo,
            'hook_event_name': event, 'permission_mode': 'default'}
    base.update(extra)
    return base


class Adapter(unittest.TestCase):

    def setUp(self):
        self.repo = helpers.new_repo(remote='git@github.com:ros2/rclcpp.git')
        Path(self.repo, '.github').mkdir()
        shutil.copy(helpers.FIXTURES / 'ros2_PULL_REQUEST_TEMPLATE.md',
                    Path(self.repo, '.github', 'PULL_REQUEST_TEMPLATE.md'))

    def test_session_start_prints_profile(self):
        code, out, err = run_hook(payload('SessionStart', self.repo, source='startup'))
        self.assertEqual(code, 0, err)
        self.assertIn('profile osra-ros2', out)

    def test_pre_tool_use_blocks_gh_pr_create(self):
        p = payload('PreToolUse', self.repo, tool_name='Bash',
                    tool_input={'command': 'gh pr create --fill'}, tool_use_id='t1')
        code, out, err = run_hook(p)
        self.assertEqual(code, 2)
        self.assertIn('G3', err)

    def test_pre_tool_use_blocks_unsigned_commit(self):
        p = payload('PreToolUse', self.repo, tool_name='Bash',
                    tool_input={'command': 'git commit -m "x"'}, tool_use_id='t1')
        code, out, err = run_hook(p)
        self.assertEqual(code, 2)
        self.assertIn('G1', err)

    def test_pre_tool_use_allows_signed_commit(self):
        p = payload('PreToolUse', self.repo, tool_name='Bash',
                    tool_input={'command': 'git commit -s -m "x"'}, tool_use_id='t1')
        code, out, err = run_hook(p)
        self.assertEqual(code, 0, err)

    def test_pre_tool_use_ignores_other_tools(self):
        p = payload('PreToolUse', self.repo, tool_name='Read',
                    tool_input={'file_path': '/etc/hosts'}, tool_use_id='t1')
        self.assertEqual(run_hook(p)[0], 0)

    def test_post_tool_use_checks_pr_body(self):
        pr_body = Path(self.repo, 'PR_BODY.md')
        pr_body.write_text((helpers.FIXTURES / 'ros2_PULL_REQUEST_TEMPLATE.md').read_text())
        p = payload('PostToolUse', self.repo, tool_name='Write',
                    tool_input={'file_path': str(pr_body), 'content': ''}, tool_response={},
                    tool_use_id='t1')
        code, out, err = run_hook(p)
        self.assertEqual(code, 2)
        self.assertIn('G4', err)
        self.assertIn('Description', err)

    def test_post_tool_use_ignores_other_files(self):
        other = Path(self.repo, 'notes.md')
        other.write_text('hi')
        p = payload('PostToolUse', self.repo, tool_name='Write',
                    tool_input={'file_path': str(other)}, tool_response={}, tool_use_id='t1')
        self.assertEqual(run_hook(p)[0], 0)

    def test_garbage_payload_allows(self):
        proc = subprocess.run([sys.executable, str(ADAPTER)], input='not json',
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)


if __name__ == '__main__':
    unittest.main()
