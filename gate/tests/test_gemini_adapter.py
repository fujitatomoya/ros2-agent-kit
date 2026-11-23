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

"""Recorded hook payloads for the Gemini CLI adapter."""

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests import helpers

ADAPTER = helpers.GATE_DIR.parent / 'adapters' / 'gemini_hook.py'


def run_hook(payload: dict):
    env = dict(os.environ)
    env.pop('ROS2_GATE_PROFILE', None)
    proc = subprocess.run([sys.executable, str(ADAPTER)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)
    out = json.loads(proc.stdout) if proc.stdout.strip() else None
    return proc.returncode, out, proc.stderr


def payload(event, repo, **extra):
    base = {'session_id': 's', 'transcript_path': '/tmp/t.json', 'cwd': repo,
            'hook_event_name': event, 'timestamp': '2026-11-23T00:00:00Z'}
    base.update(extra)
    return base


class GeminiAdapter(unittest.TestCase):

    def setUp(self):
        self.repo = helpers.new_repo(remote='git@github.com:ros2/rclcpp.git')
        Path(self.repo, '.github').mkdir()
        shutil.copy(helpers.FIXTURES / 'ros2_PULL_REQUEST_TEMPLATE.md',
                    Path(self.repo, '.github', 'PULL_REQUEST_TEMPLATE.md'))

    def test_session_start_context(self):
        code, out, err = run_hook(payload('SessionStart', self.repo, source='startup'))
        self.assertEqual(code, 0, err)
        self.assertEqual(out['hookSpecificOutput']['hookEventName'], 'SessionStart')
        self.assertIn('profile osra-ros2', out['hookSpecificOutput']['additionalContext'])

    def test_before_tool_denies_posting(self):
        p = payload('BeforeTool', self.repo, tool_name='run_shell_command',
                    tool_input={'command': 'gh pr comment 1 -b done'})
        code, out, err = run_hook(p)
        self.assertEqual(code, 0, err)
        self.assertEqual(out['decision'], 'deny')
        self.assertIn('G3', out['reason'])

    def test_before_tool_allows_silently(self):
        p = payload('BeforeTool', self.repo, tool_name='run_shell_command',
                    tool_input={'command': 'git commit -s -m x'})
        code, out, err = run_hook(p)
        self.assertEqual(code, 0, err)
        self.assertIsNone(out)

    def test_before_tool_ignores_other_tools(self):
        p = payload('BeforeTool', self.repo, tool_name='read_file', tool_input={'file_path': 'x'})
        self.assertIsNone(run_hook(p)[1])

    def test_after_tool_reports_draft_problems(self):
        pr_body = Path(self.repo, 'PR_BODY.md')
        pr_body.write_text((helpers.FIXTURES / 'ros2_PULL_REQUEST_TEMPLATE.md').read_text())
        p = payload('AfterTool', self.repo, tool_name='write_file',
                    tool_input={'file_path': str(pr_body), 'content': ''}, tool_response={})
        code, out, err = run_hook(p)
        self.assertEqual(code, 0, err)
        ctx = out['hookSpecificOutput']['additionalContext']
        self.assertIn('G4', ctx)
        self.assertIn('Generative AI', ctx)


if __name__ == '__main__':
    unittest.main()
