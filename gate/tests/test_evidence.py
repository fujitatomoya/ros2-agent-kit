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

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from tests import helpers
from ros2_gate import claims, evidence, guard, lint
from ros2_gate.findings import WARNING

OSRA = helpers.load_profile('osra-ros2')
IDS = helpers.identities()


class Ledger(unittest.TestCase):

    def setUp(self):
        self.repo = helpers.new_repo()
        helpers.commit(self.repo, 'base', signoff=True)

    def test_tree_hash_tracks_changes_but_not_build_dirs(self):
        h0 = evidence.tree_hash(self.repo)
        self.assertEqual(h0, evidence.tree_hash(self.repo))
        Path(self.repo, 'build').mkdir()
        Path(self.repo, 'build', 'x.o').write_text('obj')
        Path(self.repo, '.ros2-agent-kit').mkdir()
        Path(self.repo, '.ros2-agent-kit', 'evidence.jsonl').write_text('{}\n')
        self.assertEqual(h0, evidence.tree_hash(self.repo))
        Path(self.repo, 'new.cpp').write_text('int x;\n')
        h1 = evidence.tree_hash(self.repo)
        self.assertNotEqual(h0, h1)
        Path(self.repo, 'file.txt').write_text('edited\n')
        self.assertNotEqual(h1, evidence.tree_hash(self.repo))

    def test_run_records_and_evidence_filters_by_tree(self):
        code = evidence.run_and_record([sys.executable, '-c', 'print("colcon test fake")'], self.repo)
        self.assertEqual(code, 0)
        code = evidence.run_and_record(['no-such-program-xyz', 'build'], self.repo)
        self.assertEqual(code, 127)
        entries = evidence.read_entries(self.repo)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]['exit_code'], 0)
        self.assertEqual(sorted(entries[0]['kinds']), ['lint', 'test'])
        self.assertEqual(entries[1]['exit_code'], 127)
        self.assertEqual(len(evidence.matching_entries(self.repo)), 2)
        exclude = Path(self.repo, '.git', 'info', 'exclude').read_text()
        self.assertIn('.ros2-agent-kit/', exclude)
        Path(self.repo, 'file.txt').write_text('changed after the run\n')
        self.assertEqual(evidence.matching_entries(self.repo), [])

    def test_classify(self):
        self.assertEqual(evidence.classify('colcon build --packages-select rclcpp'), ['build'])
        self.assertEqual(sorted(evidence.classify('colcon test --packages-select rclcpp')), ['lint', 'test'])
        self.assertEqual(evidence.classify('ament_flake8 src'), ['lint'])
        self.assertEqual(evidence.classify('ls'), [])


class PushGate(unittest.TestCase):

    def setUp(self):
        self.repo = helpers.new_repo()
        helpers.commit(self.repo, 'base', signoff=True)
        helpers.git(self.repo, 'branch', 'origin/rolling')
        helpers.git(self.repo, 'checkout', '-q', '-b', 'feature')
        helpers.commit(self.repo, 'work', signoff=True)

    def check(self, cmd):
        return guard.guard(cmd, OSRA, IDS, cwd=self.repo)

    def test_push_blocked_without_evidence(self):
        d = self.check('git push -u origin feature')
        self.assertFalse(d.allowed)
        self.assertEqual(d.gate, 'G2')
        self.assertIn('build and test', d.reason)

    def test_push_allowed_with_evidence(self):
        evidence.run_and_record(['true'], self.repo)  # not build or test
        self.assertFalse(self.check('git push').allowed)
        # Fake build and test commands that exist on every system.
        evidence.run_and_record(['sh', '-c', 'true # colcon build'], self.repo)
        self.assertIn('test', self.check('git push').reason)
        evidence.run_and_record(['sh', '-c', 'true # colcon test'], self.repo)
        self.assertTrue(self.check('git push origin feature').allowed)

    def test_push_blocked_by_unsigned_commit(self):
        helpers.commit(self.repo, 'oops no signoff')
        d = self.check('git push')
        self.assertFalse(d.allowed)
        self.assertIn('G1', d.reason)

    def test_dry_run_and_delete_allowed(self):
        self.assertTrue(self.check('git push --dry-run').allowed)
        self.assertTrue(self.check('git push origin --delete old').allowed)


class Claims(unittest.TestCase):

    def test_find_claims(self):
        kinds = {k for k, _ in claims.find_claims(
            'I ran the suite and all tests pass. The build succeeded and lint is clean.')}
        self.assertEqual(kinds, {'test', 'build', 'lint'})
        self.assertEqual(claims.find_claims('You should make sure the tests pass before pushing.'), [])
        self.assertEqual(claims.find_claims('Two tests fail on this branch.'), [])

    def test_check_claims_against_ledger(self):
        repo = helpers.new_repo()
        helpers.commit(repo, 'base', signoff=True)
        report = claims.check_claims('All tests pass now.', repo)
        self.assertTrue(any(f.level == WARNING and 'no successful test' in f.message
                            for f in report.findings))
        evidence.run_and_record(['sh', '-c', 'true # colcon test'], repo)
        self.assertEqual(claims.check_claims('All tests pass now. Lint is clean.', repo).findings, [])


class Lint(unittest.TestCase):

    def test_builtin_checks(self):
        repo = helpers.new_repo()
        cpp = Path(repo, 'a.cpp')
        cpp.write_text('int x;\n' + 'x' * 120 + '\n\tint y;\n')
        report = lint.lint_file(str(cpp), repo)
        msgs = [f.message for f in report.findings if f.level == WARNING]
        self.assertTrue(any('over 100 columns' in m for m in msgs))
        self.assertTrue(any('tabs' in m for m in msgs))
        doc = Path(repo, 'README.md')
        doc.write_text('# Title\n\nOne sentence. Two sentences here.\n\n```\ncode. Not checked.\n```\n')
        report = lint.lint_file(str(doc), repo)
        self.assertTrue(any('one sentence per line' in f.message for f in report.findings))
        self.assertIsNone(lint.kind_of('x.unknown'))
        self.assertEqual(lint.kind_of('CMakeLists.txt'), 'cmake')


class StopHook(unittest.TestCase):

    def test_stop_hook_advises(self):
        repo = helpers.new_repo()
        helpers.commit(repo, 'base', signoff=True)
        adapter = helpers.GATE_DIR.parent / 'adapters' / 'claude_codex_hook.py'
        payload = {'hook_event_name': 'Stop', 'cwd': repo, 'stop_hook_active': False,
                   'last_assistant_message': 'Done. The build succeeds and all tests pass.'}
        env = dict(os.environ)
        env.pop('ROS2_GATE_PROFILE', None)
        proc = subprocess.run([sys.executable, str(adapter)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out['hookSpecificOutput']['hookEventName'], 'Stop')
        self.assertIn('G7', out['hookSpecificOutput']['additionalContext'])
        payload['stop_hook_active'] = True
        proc = subprocess.run([sys.executable, str(adapter)], input=json.dumps(payload),
                              capture_output=True, text=True, env=env)
        self.assertEqual(proc.stdout.strip(), '')


if __name__ == '__main__':
    unittest.main()
